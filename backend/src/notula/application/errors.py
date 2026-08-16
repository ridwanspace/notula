"""Application-level errors raised by use cases."""

from __future__ import annotations


class MeetingNotFoundError(Exception):
    """No meeting exists with the requested id."""


class MeetingNotReadyError(Exception):
    """The meeting is not in a state that allows the requested operation."""


class SummarizationFailedError(Exception):
    """The summarizer kept producing schema-invalid output after every repair attempt."""
