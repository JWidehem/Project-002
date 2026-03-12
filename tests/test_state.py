# tests/test_state.py
import pytest
from app.engine.state import AppState


@pytest.fixture
def state(qapp):
    return AppState()


def test_initial_state_is_idle(state):
    assert state.current() == AppState.IDLE


def test_idle_to_recording(state):
    state.transition(AppState.RECORDING)
    assert state.current() == AppState.RECORDING


def test_recording_to_transcribing(state):
    state.transition(AppState.RECORDING)
    state.transition(AppState.TRANSCRIBING)
    assert state.current() == AppState.TRANSCRIBING


def test_recording_to_idle_allowed(state):
    state.transition(AppState.RECORDING)
    state.transition(AppState.IDLE)
    assert state.current() == AppState.IDLE


def test_transcribing_to_idle(state):
    state.transition(AppState.RECORDING)
    state.transition(AppState.TRANSCRIBING)
    state.transition(AppState.IDLE)
    assert state.current() == AppState.IDLE


def test_invalid_transition_raises(state):
    with pytest.raises(ValueError, match="Invalid transition"):
        state.transition(AppState.TRANSCRIBING)  # IDLE → TRANSCRIBING invalid


def test_state_changed_signal_emitted(state, qtbot):
    with qtbot.waitSignal(state.state_changed, timeout=1000) as blocker:
        state.transition(AppState.RECORDING)
    assert blocker.args == [AppState.RECORDING]


def test_signal_emits_new_state_name(state, qtbot):
    signals = []
    state.state_changed.connect(signals.append)
    state.transition(AppState.RECORDING)
    state.transition(AppState.TRANSCRIBING)
    state.transition(AppState.IDLE)
    assert signals == [AppState.RECORDING, AppState.TRANSCRIBING, AppState.IDLE]
