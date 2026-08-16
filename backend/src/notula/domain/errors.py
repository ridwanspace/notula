"""Domain errors."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for domain-level failures."""


class IllegalTransitionError(DomainError):
    """A meeting-state transition that the state machine does not allow."""


class SummaryParseError(DomainError):
    """LLM output failed schema validation; the message is fed back to the
    model by the repair loop, so it must name the offending field precisely."""


class TranscriptParseError(DomainError):
    """Transcription output failed schema validation."""
