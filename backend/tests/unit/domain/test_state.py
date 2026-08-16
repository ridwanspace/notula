import pytest

from notula.domain.errors import IllegalTransitionError
from notula.domain.state import ACTIVE_STATES, MeetingState, transition


def test_happy_path_chain() -> None:
    state = MeetingState.UPLOADED
    for target in (
        MeetingState.NORMALIZING,
        MeetingState.TRANSCRIBING,
        MeetingState.SUMMARIZING,
        MeetingState.COMPLETED,
    ):
        state = transition(state, target)
    assert state is MeetingState.COMPLETED


def test_every_active_state_can_fail() -> None:
    for state in ACTIVE_STATES:
        assert transition(state, MeetingState.FAILED) is MeetingState.FAILED


def test_completed_allows_resummarize() -> None:
    assert transition(MeetingState.COMPLETED, MeetingState.SUMMARIZING) is MeetingState.SUMMARIZING
    # ...and the re-run comes back to COMPLETED.
    assert transition(MeetingState.SUMMARIZING, MeetingState.COMPLETED) is MeetingState.COMPLETED


def test_failed_allows_full_retry() -> None:
    assert transition(MeetingState.FAILED, MeetingState.NORMALIZING) is MeetingState.NORMALIZING


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (MeetingState.UPLOADED, MeetingState.SUMMARIZING),
        (MeetingState.UPLOADED, MeetingState.COMPLETED),
        (MeetingState.NORMALIZING, MeetingState.COMPLETED),
        (MeetingState.TRANSCRIBING, MeetingState.NORMALIZING),
        (MeetingState.COMPLETED, MeetingState.TRANSCRIBING),
        (MeetingState.COMPLETED, MeetingState.FAILED),
        (MeetingState.FAILED, MeetingState.COMPLETED),
        (MeetingState.FAILED, MeetingState.SUMMARIZING),
    ],
)
def test_illegal_transitions_raise(current: MeetingState, target: MeetingState) -> None:
    with pytest.raises(IllegalTransitionError):
        transition(current, target)


def test_terminal_states_are_not_active() -> None:
    assert MeetingState.COMPLETED not in ACTIVE_STATES
    assert MeetingState.FAILED not in ACTIVE_STATES
