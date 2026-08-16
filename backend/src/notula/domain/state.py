"""Meeting lifecycle state machine.

COMPLETED -> SUMMARIZING is deliberate: pass 2 is re-runnable against the stored
transcript (different language, updated prompt) without re-transcribing. A failed
re-summarize reverts to COMPLETED and keeps the last good summary.
"""

from __future__ import annotations

from enum import StrEnum

from notula.domain.errors import IllegalTransitionError


class MeetingState(StrEnum):
    UPLOADED = "uploaded"
    NORMALIZING = "normalizing"
    TRANSCRIBING = "transcribing"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"


ACTIVE_STATES: frozenset[MeetingState] = frozenset(
    {
        MeetingState.UPLOADED,
        MeetingState.NORMALIZING,
        MeetingState.TRANSCRIBING,
        MeetingState.SUMMARIZING,
    }
)

_ALLOWED: dict[MeetingState, frozenset[MeetingState]] = {
    MeetingState.UPLOADED: frozenset({MeetingState.NORMALIZING, MeetingState.FAILED}),
    MeetingState.NORMALIZING: frozenset({MeetingState.TRANSCRIBING, MeetingState.FAILED}),
    MeetingState.TRANSCRIBING: frozenset({MeetingState.SUMMARIZING, MeetingState.FAILED}),
    MeetingState.SUMMARIZING: frozenset({MeetingState.COMPLETED, MeetingState.FAILED}),
    # Re-runnable pass 2; a failed re-run transitions back to COMPLETED.
    MeetingState.COMPLETED: frozenset({MeetingState.SUMMARIZING}),
    # Full retry after a failure restarts the pipeline from the stored audio.
    MeetingState.FAILED: frozenset({MeetingState.NORMALIZING}),
}


def transition(current: MeetingState, target: MeetingState) -> MeetingState:
    """Validate and perform a state transition, raising IllegalTransitionError otherwise."""
    if target not in _ALLOWED[current]:
        raise IllegalTransitionError(f"cannot move meeting from {current!r} to {target!r}")
    return target
