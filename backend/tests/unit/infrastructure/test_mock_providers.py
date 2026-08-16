import hashlib
import importlib.util
import json
from importlib import resources
from pathlib import Path

from notula.domain.models import SummaryLanguage
from notula.domain.parsing import summary_from_json
from notula.infrastructure.providers.mock import MockCompleter, MockTranscriber

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "make_demo_audio.py"


def _load_generator():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("make_demo_audio", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_same_bytes_same_transcript(tmp_path: Path) -> None:
    audio = tmp_path / "a.bin"
    audio.write_bytes(b"deterministic-audio-bytes")
    transcriber = MockTranscriber()
    first = await transcriber.transcribe(audio, roster="", duration_seconds=70.0)
    second = await transcriber.transcribe(audio, roster="", duration_seconds=70.0)
    assert first.transcript == second.transcript
    assert first.usage == second.usage
    assert first.model == "mock"
    assert first.usage.input_tokens == 70 * 32


async def test_different_bytes_different_transcript(tmp_path: Path) -> None:
    a, b = tmp_path / "a.bin", tmp_path / "b.bin"
    a.write_bytes(b"meeting-recording-one")
    b.write_bytes(b"meeting-recording-two")
    transcriber = MockTranscriber()
    result_a = await transcriber.transcribe(a, roster="", duration_seconds=70.0)
    result_b = await transcriber.transcribe(b, roster="", duration_seconds=70.0)
    assert result_a.transcript != result_b.transcript


async def test_demo_wav_hits_bundled_fixture(tmp_path: Path) -> None:
    generator = _load_generator()
    wav = generator.main(tmp_path / "standup.wav")
    digest = hashlib.sha256(wav.read_bytes()).hexdigest()
    fixture = resources.files("notula.infrastructure.providers").joinpath(f"fixtures/{digest}.json")
    assert fixture.is_file(), "demo wav hash has no bundled fixture — regenerate the fixture"

    result = await MockTranscriber().transcribe(wav, roster="", duration_seconds=60.0)
    expected = json.loads(fixture.read_text(encoding="utf-8"))
    assert len(result.transcript.utterances) == len(expected["utterances"])
    decisions = [
        u.text for u in result.transcript.utterances if "agreed" in u.text or "decided" in u.text
    ]
    assert len(decisions) == 2
    assert result.transcript.duration_seconds == 60.0


async def test_completer_output_is_valid_summary_json(tmp_path: Path) -> None:
    generator = _load_generator()
    wav = generator.main(tmp_path / "standup.wav")
    transcription = await MockTranscriber().transcribe(wav, roster="", duration_seconds=60.0)
    user_prompt = "Summarize this meeting.\n\n" + transcription.transcript.as_text()

    completion = await MockCompleter().complete_json("system", user_prompt)
    summary = summary_from_json(completion.text, language=SummaryLanguage.ENGLISH)
    assert summary.decisions, "fixture contains agreed/decided lines"
    assert len(summary.action_items) == 3
    assert all(item.owner for item in summary.action_items)
    assert len(summary.open_questions) == 1
    assert completion.model == "mock"
    assert completion.usage.input_tokens > 0


async def test_completer_is_deterministic() -> None:
    prompt = "[00:01] Rina: We agreed to ship on Friday.\n[00:05] Dimas: I will write the notes."
    first = await MockCompleter().complete_json("s", prompt)
    second = await MockCompleter().complete_json("s", prompt)
    assert first == second
