"""Composition root: builds adapters, wires ports, owns the app lifecycle.

This is the only module allowed to import across the presentation/infrastructure
boundary — everything else obeys the layer contracts in pyproject.toml.
"""

from __future__ import annotations

import functools
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import structlog
from fastapi import FastAPI

from notula.application.pipeline import process_meeting
from notula.application.ports import PipelineConfig, PipelineDeps
from notula.infrastructure.audio import PassthroughAudioProcessor, pick_audio_processor
from notula.infrastructure.db import init_db, make_engine, make_session_factory
from notula.infrastructure.events import InMemoryEventBus
from notula.infrastructure.providers.deepseek import DeepSeekCompleter
from notula.infrastructure.providers.gemini import GeminiTranscriber
from notula.infrastructure.providers.mock import MockCompleter, MockTranscriber
from notula.infrastructure.repository import SqlAlchemyMeetingRepository
from notula.infrastructure.settings import Settings
from notula.infrastructure.worker import MeetingWorker
from notula.presentation.api import ApiConfig, create_app

log = structlog.get_logger()


class UtcClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def build_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.validate_live()

    engine = make_engine(settings.db_path)
    repo = SqlAlchemyMeetingRepository(make_session_factory(engine), clock=UtcClock())
    bus = InMemoryEventBus()

    if settings.provider == "live":
        transcriber: object = GeminiTranscriber(
            api_key=settings.gemini_api_key, model=settings.gemini_model
        )
        completer: object = DeepSeekCompleter(
            api_key=settings.deepseek_api_key,
            model=settings.summarizer_model,
            base_url=settings.deepseek_base_url,
        )
        audio = pick_audio_processor()
    else:
        transcriber = MockTranscriber()
        completer = MockCompleter()
        # Mock mode must be byte-deterministic: the mock transcriber keys its
        # fixtures on the audio hash, so "normalize" must be a plain copy —
        # an ffmpeg re-encode would change the bytes and miss the fixture.
        audio = PassthroughAudioProcessor()

    deps = PipelineDeps(
        repo=repo,
        bus=bus,
        audio=audio,
        transcriber=transcriber,  # type: ignore[arg-type]
        completer=completer,  # type: ignore[arg-type]
        clock=UtcClock(),
        config=PipelineConfig(
            workdir=settings.workdir,
            max_chunk_seconds=settings.max_chunk_seconds,
            overlap_seconds=settings.overlap_seconds,
            max_repair_attempts=settings.max_repair_attempts,
        ),
    )
    worker = MeetingWorker(functools.partial(process_meeting, deps), repo)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        settings.workdir.mkdir(parents=True, exist_ok=True)
        settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        await init_db(engine)
        recovered = await worker.recover()
        if recovered:
            log.info("recovered interrupted meetings", count=len(recovered))
        await worker.start()
        log.info("notula ready", provider=settings.provider)
        try:
            yield
        finally:
            await worker.stop()
            await engine.dispose()

    return create_app(
        deps=deps,
        queue=worker,
        config=ApiConfig(
            uploads_dir=settings.uploads_dir,
            max_upload_bytes=settings.max_upload_bytes,
            provider_name=settings.provider,
        ),
        lifespan=lifespan,
    )
