import json
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from notula.application.errors import (
    MeetingNotFoundError,
    MeetingNotReadyError,
    SummarizationFailedError,
)
from notula.application.events import PipelineEvent
from notula.application.pipeline import create_meeting, process_meeting, resummarize
from notula.application.ports import (
    AudioInfo,
    Completion,
    MeetingRecord,
    PipelineConfig,
    PipelineDeps,
    StoredSummary,
    TranscriptionResult,
)
from notula.domain.models import (
    MeetingSummary,
    StageReport,
    SummaryLanguage,
    TokenUsage,
    Transcript,
    Utterance,
)
from notula.domain.state import MeetingState

FIXED_NOW = datetime(2026, 8, 16, 9, 0, 0, tzinfo=UTC)

VALID_JSON = json.dumps(
    {
        "title": "Standup",
        "tldr": "Quick recap.",
        "key_points": ["progress shared"],
        "decisions": [],
        "action_items": [],
        "open_questions": [],
    }
)


class FakeClock:
    def now(self) -> datetime:
        return FIXED_NOW


class FakeBus:
    def __init__(self) -> None:
        self.events: dict[str, list[PipelineEvent]] = {}

    async def publish(self, meeting_id: str, event: PipelineEvent) -> None:
        self.events.setdefault(meeting_id, []).append(event)

    def subscribe(self, meeting_id: str) -> AsyncIterator[PipelineEvent]:
        async def _replay() -> AsyncIterator[PipelineEvent]:
            for event in self.events.get(meeting_id, []):
                yield event

        return _replay()

    def kinds(self, meeting_id: str) -> list[str]:
        return [e.kind for e in self.events.get(meeting_id, [])]

    def states(self, meeting_id: str) -> list[object]:
        return [e.data["state"] for e in self.events.get(meeting_id, []) if e.kind == "state"]


class FakeRepo:
    def __init__(self) -> None:
        self.records: dict[str, MeetingRecord] = {}
        self.transcripts: dict[str, Transcript] = {}
        self.summaries: dict[str, list[StoredSummary]] = {}
        self.stage_reports: dict[str, list[StageReport]] = {}

    async def add(self, meeting: MeetingRecord) -> None:
        self.records[meeting.id] = meeting

    async def get(self, meeting_id: str) -> MeetingRecord | None:
        return self.records.get(meeting_id)

    async def list_recent(self, limit: int = 50) -> Sequence[MeetingRecord]:
        return list(self.records.values())[:limit]

    async def list_in_states(self, states: frozenset[MeetingState]) -> Sequence[MeetingRecord]:
        return [r for r in self.records.values() if r.state in states]

    async def set_state(
        self,
        meeting_id: str,
        state: MeetingState,
        *,
        error: str | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        record = self.records[meeting_id]
        record.state = state
        if error is not None:
            record.error = error
        if duration_seconds is not None:
            record.duration_seconds = duration_seconds

    async def save_transcript(
        self, meeting_id: str, transcript: Transcript, usage: TokenUsage, model: str
    ) -> None:
        self.transcripts[meeting_id] = transcript

    async def get_transcript(self, meeting_id: str) -> Transcript | None:
        return self.transcripts.get(meeting_id)

    async def save_summary(
        self,
        meeting_id: str,
        summary: MeetingSummary,
        usage: TokenUsage,
        model: str,
        repair_attempts: int,
    ) -> StoredSummary:
        stored = StoredSummary(
            summary=summary,
            model=model,
            usage=usage,
            repair_attempts=repair_attempts,
            version=len(self.summaries.get(meeting_id, [])) + 1,
            created_at=FIXED_NOW,
        )
        self.summaries.setdefault(meeting_id, []).append(stored)
        return stored

    async def get_latest_summary(self, meeting_id: str) -> StoredSummary | None:
        items = self.summaries.get(meeting_id)
        return items[-1] if items else None

    async def list_summaries(self, meeting_id: str) -> Sequence[StoredSummary]:
        return list(self.summaries.get(meeting_id, []))

    async def add_stage_report(self, meeting_id: str, report: StageReport) -> None:
        self.stage_reports.setdefault(meeting_id, []).append(report)

    async def get_stage_reports(self, meeting_id: str) -> Sequence[StageReport]:
        return list(self.stage_reports.get(meeting_id, []))


class FakeAudio:
    def __init__(self, duration: float, silences: tuple[float, ...] = ()) -> None:
        self.duration = duration
        self.silences = silences
        self.slice_calls: list[tuple[float, float]] = []

    async def probe(self, path: Path) -> AudioInfo:
        return AudioInfo(self.duration, 1000)

    async def normalize(self, src: Path, dst: Path) -> AudioInfo:
        dst.write_bytes(b"normalized")  # noqa: ASYNC240 — fake adapter, tiny file
        return AudioInfo(self.duration, 1000)

    async def detect_silences(self, path: Path) -> tuple[float, ...]:
        return self.silences

    async def slice(self, src: Path, dst: Path, start_seconds: float, end_seconds: float) -> None:
        self.slice_calls.append((start_seconds, end_seconds))
        dst.write_bytes(b"chunk")  # noqa: ASYNC240 — fake adapter, tiny file


class FakeTranscriber:
    def __init__(self, transcripts: list[Transcript]) -> None:
        self._transcripts = transcripts
        self.calls: list[tuple[Path, float]] = []

    @property
    def model(self) -> str:
        return "mock"

    async def transcribe(
        self, path: Path, *, roster: str, duration_seconds: float
    ) -> TranscriptionResult:
        self.calls.append((path, duration_seconds))
        transcript = self._transcripts[len(self.calls) - 1]
        return TranscriptionResult(transcript, TokenUsage(100, 40), "mock")


class FakeCompleter:
    def __init__(self, output: str = VALID_JSON) -> None:
        self.output = output

    @property
    def model(self) -> str:
        return "mock"

    async def complete_json(self, system: str, user: str) -> Completion:
        return Completion(self.output, TokenUsage(50, 20), "mock")


class FailingTranscriber:
    @property
    def model(self) -> str:
        return "mock"

    async def transcribe(
        self, path: Path, *, roster: str, duration_seconds: float
    ) -> TranscriptionResult:
        raise RuntimeError("boom")


def make_deps(
    tmp_path: Path,
    *,
    duration: float = 60.0,
    silences: tuple[float, ...] = (),
    transcripts: list[Transcript] | None = None,
    max_chunk_seconds: float = 1200.0,
    overlap_seconds: float = 10.0,
) -> tuple[PipelineDeps, FakeRepo, FakeBus]:
    repo = FakeRepo()
    bus = FakeBus()
    default_transcript = Transcript(
        utterances=(Utterance(0.0, "Rina", "halo"), Utterance(5.0, "Dimas", "hi")),
        duration_seconds=duration,
    )
    deps = PipelineDeps(
        repo=repo,
        bus=bus,
        audio=FakeAudio(duration, silences),
        transcriber=FakeTranscriber(transcripts or [default_transcript]),
        completer=FakeCompleter(),
        clock=FakeClock(),
        config=PipelineConfig(
            workdir=tmp_path,
            max_chunk_seconds=max_chunk_seconds,
            overlap_seconds=overlap_seconds,
        ),
    )
    return deps, repo, bus


async def submit(deps: PipelineDeps, tmp_path: Path, meeting_id: str = "m1") -> MeetingRecord:
    audio = tmp_path / "in.wav"
    audio.write_bytes(b"fake-audio")
    return await create_meeting(
        deps,
        meeting_id=meeting_id,
        filename="in.wav",
        audio_path=str(audio),
        roster="Rina, Dimas",
        language=SummaryLanguage.ENGLISH,
    )


class TestProcessMeeting:
    async def test_happy_path_completes_with_artifacts(self, tmp_path: Path) -> None:
        deps, repo, bus = make_deps(tmp_path)
        await submit(deps, tmp_path)
        await process_meeting(deps, "m1")

        record = repo.records["m1"]
        assert record.state is MeetingState.COMPLETED
        assert record.duration_seconds == 60.0
        assert record.error is None
        assert repo.transcripts["m1"].utterances
        assert repo.summaries["m1"][0].version == 1
        assert [r.stage for r in repo.stage_reports["m1"]] == [
            "normalize",
            "transcribe",
            "summarize",
        ]
        assert bus.states("m1") == [
            "uploaded",
            "normalizing",
            "transcribing",
            "summarizing",
            "completed",
        ]
        assert bus.kinds("m1")[-1] == "completed"

    async def test_stage_costs_use_reported_usage(self, tmp_path: Path) -> None:
        deps, repo, _ = make_deps(tmp_path)
        await submit(deps, tmp_path)
        await process_meeting(deps, "m1")
        by_stage = {r.stage: r for r in repo.stage_reports["m1"]}
        assert by_stage["normalize"].cost_usd is None
        assert by_stage["transcribe"].usage == TokenUsage(100, 40)
        assert by_stage["transcribe"].cost_usd == 0.0  # mock pricing
        assert by_stage["summarize"].usage == TokenUsage(50, 20)

    async def test_failure_records_error_and_never_raises(self, tmp_path: Path) -> None:
        deps, repo, bus = make_deps(tmp_path)
        deps = PipelineDeps(
            repo=deps.repo,
            bus=deps.bus,
            audio=deps.audio,
            transcriber=FailingTranscriber(),
            completer=deps.completer,
            clock=deps.clock,
            config=deps.config,
        )
        await submit(deps, tmp_path)
        await process_meeting(deps, "m1")

        record = repo.records["m1"]
        assert record.state is MeetingState.FAILED
        assert record.error == "boom"
        assert bus.kinds("m1")[-1] == "error"

    async def test_unknown_meeting_publishes_error(self, tmp_path: Path) -> None:
        deps, _, bus = make_deps(tmp_path)
        await process_meeting(deps, "ghost")
        assert bus.kinds("ghost") == ["error"]

    async def test_long_audio_is_chunked_and_merged(self, tmp_path: Path) -> None:
        # duration 100 with max 70 and overlap 5 -> chunks (0..70) and (65..100).
        chunk0 = Transcript(
            utterances=(Utterance(10.0, "Alice", "one"), Utterance(66.0, "Bob", "shared")),
            duration_seconds=70.0,
        )
        chunk1 = Transcript(  # chunk-relative to 65s
            utterances=(Utterance(1.0, "Bob", "shared"), Utterance(20.0, "Alice", "two")),
            duration_seconds=35.0,
        )
        deps, repo, bus = make_deps(
            tmp_path,
            duration=100.0,
            transcripts=[chunk0, chunk1],
            max_chunk_seconds=70.0,
            overlap_seconds=5.0,
        )
        await submit(deps, tmp_path)
        await process_meeting(deps, "m1")

        assert repo.records["m1"].state is MeetingState.COMPLETED
        merged = repo.transcripts["m1"]
        assert [u.text for u in merged.utterances] == ["one", "shared", "two"]
        assert [u.start_seconds for u in merged.utterances] == [10.0, 66.0, 85.0]
        progress = [e for e in bus.events["m1"] if e.kind == "progress"]
        assert len(progress) == 2
        assert progress[0].data["chunks"] == 2
        # Temp chunk files are cleaned up afterwards.
        assert not list(tmp_path.glob("*.chunk*.flac"))  # noqa: ASYNC240 — test assertion
        # Transcribe usage is summed across chunks.
        by_stage = {r.stage: r for r in repo.stage_reports["m1"]}
        assert by_stage["transcribe"].usage == TokenUsage(200, 80)


class TestResummarize:
    async def test_rerun_creates_new_version_and_reverts_state(self, tmp_path: Path) -> None:
        deps, repo, bus = make_deps(tmp_path)
        await submit(deps, tmp_path)
        await process_meeting(deps, "m1")

        stored = await resummarize(deps, "m1", language=SummaryLanguage.INDONESIAN)
        assert stored.version == 2
        assert repo.records["m1"].state is MeetingState.COMPLETED
        assert len(repo.stage_reports["m1"]) == 4
        assert bus.states("m1")[-2:] == ["summarizing", "completed"]

    async def test_unknown_meeting(self, tmp_path: Path) -> None:
        deps, _, _ = make_deps(tmp_path)
        with pytest.raises(MeetingNotFoundError):
            await resummarize(deps, "ghost", language=SummaryLanguage.ENGLISH)

    async def test_wrong_state_rejected(self, tmp_path: Path) -> None:
        deps, _, _ = make_deps(tmp_path)
        await submit(deps, tmp_path)  # still UPLOADED
        with pytest.raises(MeetingNotReadyError, match="uploaded"):
            await resummarize(deps, "m1", language=SummaryLanguage.ENGLISH)

    async def test_failed_rerun_keeps_last_good_summary(self, tmp_path: Path) -> None:
        deps, repo, _ = make_deps(tmp_path)
        await submit(deps, tmp_path)
        await process_meeting(deps, "m1")

        broken = PipelineDeps(
            repo=deps.repo,
            bus=deps.bus,
            audio=deps.audio,
            transcriber=deps.transcriber,
            completer=FakeCompleter(output="not json at all"),
            clock=deps.clock,
            config=deps.config,
        )
        with pytest.raises(SummarizationFailedError):
            await resummarize(broken, "m1", language=SummaryLanguage.ENGLISH)

        assert repo.records["m1"].state is MeetingState.COMPLETED
        latest = await repo.get_latest_summary("m1")
        assert latest is not None
        assert latest.version == 1

    async def test_missing_transcript_rejected(self, tmp_path: Path) -> None:
        deps, repo, _ = make_deps(tmp_path)
        await submit(deps, tmp_path)
        await process_meeting(deps, "m1")

        del repo.transcripts["m1"]
        with pytest.raises(MeetingNotReadyError, match="no stored transcript"):
            await resummarize(deps, "m1", language=SummaryLanguage.ENGLISH)
