"""SQLite persistence via the SQLAlchemy 2 async ORM (aiosqlite driver)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Float, Integer, Text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MeetingRow(Base):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    filename: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text)
    roster: Mapped[str] = mapped_column(Text)
    audio_path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class TranscriptRow(Base):
    __tablename__ = "transcripts"

    meeting_id: Mapped[str] = mapped_column(Text, primary_key=True)
    payload: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(Text)


class SummaryRow(Base):
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_id: Mapped[str] = mapped_column(Text, index=True)
    version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    repair_attempts: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(Text)


class StageReportRow(Base):
    __tablename__ = "stage_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_id: Mapped[str] = mapped_column(Text, index=True)
    stage: Mapped[str] = mapped_column(Text)
    seconds: Mapped[float] = mapped_column(Float)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(Text)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text)


def make_engine(db_path: Path) -> AsyncEngine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_async_engine(f"sqlite+aiosqlite:///{db_path}")


async def init_db(engine: AsyncEngine) -> None:
    # create_all instead of alembic: single-file SQLite store and a young schema (ADR-0002).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
