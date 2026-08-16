"""FastAPI routes.

Wiring note: presentation and infrastructure are independent layers, so this
module never imports an adapter — the composition root (notula.main) builds
PipelineDeps and hands them in.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import Lifespan

from notula.application.errors import (
    MeetingNotFoundError,
    MeetingNotReadyError,
    SummarizationFailedError,
)
from notula.application.events import PipelineEvent
from notula.application.pipeline import create_meeting, resummarize
from notula.application.ports import PipelineDeps
from notula.domain.models import SummaryLanguage
from notula.domain.state import MeetingState
from notula.presentation.schemas import (
    HealthOut,
    MeetingDetailOut,
    MeetingListOut,
    MeetingOut,
    ResummarizeIn,
    StageOut,
    SubmitOut,
    SummaryOut,
    TranscriptOut,
)

_ALLOWED_MIME: dict[str, str] = {
    "audio/flac": ".flac",
    "audio/x-flac": ".flac",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/aac": ".aac",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
}

_SAFE_SUFFIX = re.compile(r"^\.[a-z0-9]{1,5}$")
_UPLOAD_CHUNK_BYTES = 1024 * 1024
_TERMINAL = frozenset({MeetingState.COMPLETED, MeetingState.FAILED})


class JobQueue(Protocol):
    def enqueue(self, meeting_id: str) -> None: ...


@dataclass(frozen=True, slots=True)
class ApiConfig:
    uploads_dir: Path
    max_upload_bytes: int
    provider_name: str


def _sse(kind: str, data: dict[str, object]) -> str:
    return f"event: {kind}\ndata: {json.dumps(data)}\n\n"


def _event_sse(event: PipelineEvent) -> str:
    return _sse(event.kind, dict(event.data))


def _suffix_for(filename: str, content_type: str) -> str:
    suffix = Path(filename).suffix.lower()
    if _SAFE_SUFFIX.match(suffix):
        return suffix
    return _ALLOWED_MIME[content_type]


def create_app(
    *,
    deps: PipelineDeps,
    queue: JobQueue,
    config: ApiConfig,
    lifespan: Lifespan[FastAPI] | None = None,
) -> FastAPI:
    app = FastAPI(title="Notula", version="0.1.0", lifespan=lifespan)

    @app.post("/api/meetings", response_model=SubmitOut, status_code=202)
    async def submit(
        file: UploadFile = File(...),  # noqa: B008
        roster: str = Form(""),
        language: str = Form("en"),
    ) -> SubmitOut:
        content_type = (file.content_type or "").lower()
        if content_type not in _ALLOWED_MIME:
            raise HTTPException(415, f"Unsupported audio type: {file.content_type}")
        try:
            summary_language = SummaryLanguage(language)
        except ValueError as e:
            raise HTTPException(422, f"Unsupported language: {language!r}") from e

        meeting_id = uuid.uuid4().hex
        config.uploads_dir.mkdir(parents=True, exist_ok=True)
        dest = config.uploads_dir / f"{meeting_id}{_suffix_for(file.filename or '', content_type)}"
        written = 0
        with dest.open("wb") as out:
            while chunk := await file.read(_UPLOAD_CHUNK_BYTES):
                written += len(chunk)
                if written > config.max_upload_bytes:
                    out.close()
                    dest.unlink(missing_ok=True)
                    limit_mb = config.max_upload_bytes // (1024 * 1024)
                    raise HTTPException(413, f"File exceeds the {limit_mb} MB upload limit")
                out.write(chunk)
        if written == 0:
            dest.unlink(missing_ok=True)
            raise HTTPException(400, "Empty file")

        await create_meeting(
            deps,
            meeting_id=meeting_id,
            filename=file.filename or dest.name,
            audio_path=str(dest),
            roster=roster.strip()[:500],
            language=summary_language,
        )
        queue.enqueue(meeting_id)
        return SubmitOut(id=meeting_id)

    @app.get("/api/meetings", response_model=MeetingListOut)
    async def list_meetings() -> MeetingListOut:
        records = await deps.repo.list_recent()
        return MeetingListOut(meetings=[MeetingOut.from_record(r) for r in records])

    @app.get("/api/meetings/{meeting_id}", response_model=MeetingDetailOut)
    async def get_meeting(meeting_id: str) -> MeetingDetailOut:
        record = await deps.repo.get(meeting_id)
        if record is None:
            raise HTTPException(404, "Meeting not found")
        stages = await deps.repo.get_stage_reports(meeting_id)
        stored = await deps.repo.get_latest_summary(meeting_id)
        transcript = await deps.repo.get_transcript(meeting_id)
        return MeetingDetailOut(
            meeting=MeetingOut.from_record(record),
            stages=[StageOut.from_report(s) for s in stages],
            summary=SummaryOut.from_stored(stored) if stored else None,
            transcript=TranscriptOut.from_transcript(transcript) if transcript else None,
        )

    @app.get("/api/meetings/{meeting_id}/events")
    async def meeting_events(meeting_id: str) -> StreamingResponse:
        record = await deps.repo.get(meeting_id)
        if record is None:
            raise HTTPException(404, "Meeting not found")

        async def stream() -> AsyncIterator[str]:
            subscription = deps.bus.subscribe(meeting_id)
            # Start the subscription generator before reading the snapshot so no
            # event can fall into the gap between the two.
            pending = asyncio.ensure_future(anext(subscription))
            await asyncio.sleep(0)
            try:
                current = await deps.repo.get(meeting_id)
                state = current.state if current else MeetingState.FAILED
                yield _sse("state", {"state": state.value})
                if state in _TERMINAL:
                    if state is MeetingState.COMPLETED:
                        yield _sse("completed", {})
                    else:
                        yield _sse("error", {"message": (current and current.error) or "failed"})
                    return
                while True:
                    try:
                        event = await pending
                    except StopAsyncIteration:
                        return
                    yield _event_sse(event)
                    if event.kind in ("completed", "error"):
                        return
                    pending = asyncio.ensure_future(anext(subscription))
            finally:
                pending.cancel()
                closer = getattr(subscription, "aclose", None)
                if closer is not None:
                    await cast("asyncio.Future[None]", closer())

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/api/meetings/{meeting_id}/summaries", response_model=SummaryOut)
    async def rerun_summary(meeting_id: str, body: ResummarizeIn) -> SummaryOut:
        try:
            stored = await resummarize(deps, meeting_id, language=SummaryLanguage(body.language))
        except MeetingNotFoundError as e:
            raise HTTPException(404, str(e)) from e
        except MeetingNotReadyError as e:
            raise HTTPException(409, str(e)) from e
        except SummarizationFailedError as e:
            raise HTTPException(502, str(e)) from e
        return SummaryOut.from_stored(stored)

    @app.get("/api/meetings/{meeting_id}/audio")
    async def meeting_audio(meeting_id: str) -> FileResponse:
        record = await deps.repo.get(meeting_id)
        if record is None or not await asyncio.to_thread(Path(record.audio_path).is_file):
            raise HTTPException(404, "Audio not found")
        return FileResponse(record.audio_path, filename=record.filename)

    @app.get("/healthz", response_model=HealthOut)
    async def healthz() -> HealthOut:
        return HealthOut(status="ok", provider=config.provider_name)

    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(static_dir / "index.html")

        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app
