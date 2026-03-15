# tests/test_hotkeys.py
import pytest
from unittest.mock import MagicMock, patch, call


@pytest.fixture
def callbacks():
    return {
        "on_start": MagicMock(),
        "on_stop": MagicMock(),
        "on_cancel": MagicMock(),
    }


@pytest.fixture
def mgr(callbacks, mocker):
    mocker.patch("app.engine.hotkeys.kb.Listener")
    from app.engine.hotkeys import HotkeyManager
    m = HotkeyManager(**callbacks)
    m.configure("<ctrl>+<shift>+<space>", "<ctrl>+<shift>+d")
    return m


def test_hold_press_calls_on_start(mgr, callbacks):
    mgr._hold_active = True  # guard requires _hold_active before starting
    mgr._on_hold_press()
    callbacks["on_start"].assert_called_once()


def test_hold_release_calls_on_stop(mgr, callbacks):
    mgr._on_hold_release()
    callbacks["on_stop"].assert_called_once()


def test_on_press_triggers_hold_when_all_keys_pressed(mgr, callbacks):
    """Simulate pressing all hold-mode keys (canonical form) in sequence."""
    from pynput.keyboard import Key
    # _parse_hotkey maps <ctrl> → Key.ctrl, <shift> → Key.shift, <space> → Key.space
    mgr._on_press(Key.ctrl)
    mgr._on_press(Key.shift)
    mgr._on_press(Key.space)
    callbacks["on_start"].assert_called_once()


def test_on_release_triggers_hold_stop(mgr, callbacks):
    """Simulate releasing a canonical hold-mode key after hold was active."""
    from pynput.keyboard import Key
    mgr._hold_active = True
    mgr._on_release(Key.ctrl)
    callbacks["on_stop"].assert_called_once()


def test_toggle_when_idle_calls_on_start(mgr, callbacks, mock_state):
    from app.engine.state import AppState
    mock_state.current.return_value = AppState.IDLE
    mgr.set_state(mock_state)
    mgr._on_toggle_press()
    callbacks["on_start"].assert_called_once()


def test_toggle_when_recording_calls_on_stop(mgr, callbacks, mock_state):
    from app.engine.state import AppState
    mock_state.current.return_value = AppState.RECORDING
    mgr.set_state(mock_state)
    mgr._on_toggle_press()
    callbacks["on_stop"].assert_called_once()


def test_toggle_when_transcribing_calls_on_cancel(mgr, callbacks, mock_state):
    from app.engine.state import AppState
    mock_state.current.return_value = AppState.TRANSCRIBING
    mgr.set_state(mock_state)
    mgr._on_toggle_press()
    callbacks["on_cancel"].assert_called_once()


def test_conflict_signal_set_on_listener_exception(callbacks, mocker):
    mocker.patch(
        "app.engine.hotkeys.kb.Listener",
        side_effect=OSError("device access denied"),
    )
    from app.engine.hotkeys import HotkeyManager
    mgr = HotkeyManager(**callbacks)
    mgr.configure("<ctrl>+<shift>+<space>", "<ctrl>+<shift>+d")
    mgr.start()
    assert mgr.conflict_detected is True


def test_self_heal_when_hold_active_stuck_and_state_idle(callbacks, mock_state, mocker):
    """hold_active stuck True (OS swallowed key-up) → next key self-heals and re-arms combo."""
    mocker.patch("app.engine.hotkeys.kb.Listener")
    from pynput.keyboard import Key
    from app.engine.state import AppState
    from app.engine.hotkeys import HotkeyManager

    mock_state.current.return_value = AppState.IDLE
    mgr = HotkeyManager(**callbacks)
    mgr.configure("<ctrl>+<shift>+<space>", "<ctrl>+<shift>+d")
    mgr.set_state(mock_state)

    # Simulate stuck state: hold was active, key-up swallowed by OS
    mgr._hold_active = True
    mgr._pressed = {Key.ctrl, Key.shift}

    # Next key press self-heals and allows combo re-detection
    mgr._on_press(Key.ctrl)   # triggers self-heal, clears _pressed, adds ctrl
    mgr._on_press(Key.shift)
    mgr._on_press(Key.space)  # full combo → on_start
    callbacks["on_start"].assert_called_once()


def test_reset_clears_hotkey_state(callbacks, mocker):
    """reset() clears _hold_active, _toggle_active, _pressed."""
    mocker.patch("app.engine.hotkeys.kb.Listener")
    from pynput.keyboard import Key
    from app.engine.hotkeys import HotkeyManager

    mgr = HotkeyManager(**callbacks)
    mgr.configure("<ctrl>+<shift>+<space>", "<ctrl>+<shift>+d")
    mgr._hold_active = True
    mgr._toggle_active = True
    mgr._pressed = {Key.ctrl}

    mgr.reset()

    assert mgr._hold_active is False
    assert mgr._toggle_active is False
    assert len(mgr._pressed) == 0
