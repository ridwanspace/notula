"""Core meeting models. The transcript is the system of record: summaries are
derived from it and can be regenerated without touching the audio again."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SummaryLanguage(StrEnum):
    ENGLISH = "en"
    INDONESIAN = "id"


@dataclass(frozen=True, slots=True)
class Utterance:
    start_seconds: float
    speaker: str
    text: str


@dataclass(frozen=True, slots=True)
class Transcript:
    utterances: tuple[Utterance, ...]
    duration_seconds: float

    def speakers(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for u in self.utterances:
            seen.setdefault(u.speaker, None)
        return tuple(seen)

    def as_text(self) -> str:
        """Render for the pass-2 summarizer prompt: ``[MM:SS] Speaker: text``."""
        lines: list[str] = []
        for u in self.utterances:
            minutes, seconds = divmod(int(u.start_seconds), 60)
            lines.append(f"[{minutes:02d}:{seconds:02d}] {u.speaker}: {u.text}")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class ActionItem:
    task: str
    owner: str | None = None
    due: str | None = None


@dataclass(frozen=True, slots=True)
class MeetingSummary:
    title: str
    tldr: str
    key_points: tuple[str, ...]
    decisions: tuple[str, ...]
    action_items: tuple[ActionItem, ...]
    open_questions: tuple[str, ...]
    language: SummaryLanguage


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
        )


@dataclass(frozen=True, slots=True)
class StageReport:
    """What one pipeline stage actually did — measured, not asserted."""

    stage: str
    seconds: float
    usage: TokenUsage = field(default_factory=TokenUsage)
    model: str = ""
    cost_usd: float | None = None
    detail: str = ""
