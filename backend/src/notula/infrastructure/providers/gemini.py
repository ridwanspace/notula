"""Gemini multimodal transcription adapter (pass 1).

Audio ≤ 15 MB goes inline; anything larger goes through the Files API with an
ACTIVE-state poll. Output is schema-constrained JSON, still validated by the
domain parser — the schema constrains shape, not sanity.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from google import genai
from google.genai import types
from pydantic import BaseModel

from notula.application.ports import TranscriptionResult
from notula.domain.models import TokenUsage
from notula.domain.parsing import transcript_from_json

_INLINE_LIMIT_BYTES = 15 * 1024 * 1024


def _read_bytes(path: Path) -> bytes:
    # Sync read of a local file; keeps the adapter free of async-fs deps (ASYNC240).
    return path.read_bytes()


_UPLOAD_POLL_SECONDS = 2.0
_UPLOAD_POLL_ATTEMPTS = 60

TRANSCRIBE_PROMPT = """You are a precise transcriptionist.

Transcribe this meeting audio verbatim with speaker diarization and an MM:SS
start timestamp for every utterance.

Rules:
- Label speakers "Speaker 1", "Speaker 2", ... unless real names are evident
  from the conversation (introductions, people addressing each other by name).
- The audio may mix languages (e.g. Bahasa Indonesia and English);
  transcribe in the language actually spoken.
- If a passage is unintelligible, write [inaudible]; never guess.
"""

ROSTER_RULE = """- Known participants: {roster}.
  Map diarized speakers to these people using conversational cues. Spell names
  EXACTLY as given above. If a speaker cannot be confidently mapped, keep
  "Speaker N".
"""


class _SchemaUtterance(BaseModel):
    start: str
    speaker: str
    text: str


class _SchemaTranscript(BaseModel):
    utterances: list[_SchemaUtterance]


class GeminiTranscriber:
    def __init__(self, api_key: str, model: str, timeout_ms: int = 300_000) -> None:
        # Explicit timeout: without one, a stalled connection (e.g. a blackholed
        # IPv6 path — TCP connects, data never flows) hangs the worker forever.
        self._client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=timeout_ms)
        )
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    async def transcribe(
        self, path: Path, *, roster: str, duration_seconds: float
    ) -> TranscriptionResult:
        prompt = TRANSCRIBE_PROMPT
        if roster.strip():
            prompt += ROSTER_RULE.format(roster=roster.strip()[:500])

        data = _read_bytes(path)
        uploaded: types.File | None = None
        if len(data) <= _INLINE_LIMIT_BYTES:
            mime = "audio/wav" if path.suffix.lower() == ".wav" else "audio/flac"
            audio: types.Part | types.File = types.Part.from_bytes(data=data, mime_type=mime)
        else:
            uploaded = await self._upload(path)
            audio = uploaded

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=[audio, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_SchemaTranscript,
                    temperature=0.0,
                ),
            )
        finally:
            if uploaded is not None and uploaded.name:
                try:
                    await self._client.aio.files.delete(name=uploaded.name)
                except Exception:  # noqa: S110 - best-effort cleanup only
                    pass

        meta = response.usage_metadata
        usage = TokenUsage(
            input_tokens=(meta.prompt_token_count or 0) if meta else 0,
            output_tokens=(meta.candidates_token_count or 0) if meta else 0,
        )
        transcript = transcript_from_json(response.text or "", duration_seconds=duration_seconds)
        return TranscriptionResult(transcript=transcript, usage=usage, model=self._model)

    async def _upload(self, path: Path) -> types.File:
        uploaded = await self._client.aio.files.upload(file=path)
        for _ in range(_UPLOAD_POLL_ATTEMPTS):
            state = uploaded.state.name if uploaded.state else ""
            if state == "ACTIVE":
                return uploaded
            if state == "FAILED":
                raise RuntimeError("Gemini Files API failed to process the upload")
            await asyncio.sleep(_UPLOAD_POLL_SECONDS)
            uploaded = await self._client.aio.files.get(name=uploaded.name or "")
        raise TimeoutError("Gemini Files API upload did not become ACTIVE in time")
