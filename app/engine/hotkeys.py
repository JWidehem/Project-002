import threading
from pynput import keyboard as kb
from app.engine.state import AppState


_CANONICAL_MAP: dict = {
    kb.Key.ctrl_l:  kb.Key.ctrl,
    kb.Key.ctrl_r:  kb.Key.ctrl,
    kb.Key.shift_l: kb.Key.shift,
    kb.Key.shift_r: kb.Key.shift,
    kb.Key.alt_l:   kb.Key.alt,
    kb.Key.alt_r:   kb.Key.alt,
    kb.Key.cmd_l:   kb.Key.cmd,
    kb.Key.cmd_r:   kb.Key.cmd,
}


def _parse_hotkey(hotkey_str: str) -> frozenset:
    """Convert '<ctrl>+<shift>+<space>' to a frozenset of canonical pynput keys."""
    parts = hotkey_str.split("+")
    keys = set()
    for part in parts:
        part = part.strip()
        if part.startswith("<") and part.endswith(">"):
            name = part[1:-1]
            if not hasattr(kb.Key, name):
                raise ValueError(f"Unknown key: {part!r}")
            keys.add(kb.Key[name])
        else:
            keys.add(kb.KeyCode.from_char(part))
    return frozenset(keys)


class HotkeyManager:
    def __init__(self, on_start, on_stop, on_cancel) -> None:
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_cancel = on_cancel
        self._state: AppState | None = None
        self._listener: kb.Listener | None = None
        self._hold_keys: frozenset = frozenset()
        self._toggle_keys: frozenset = frozenset()
        self._pressed: set = set()
        self._hold_active = False
        self._lock = threading.Lock()
        self.conflict_detected = False

    def set_state(self, state: AppState) -> None:
        self._state = state

    def configure(self, hold_key: str, toggle_key: str) -> None:
        self._hold_keys = _parse_hotkey(hold_key)
        self._toggle_keys = _parse_hotkey(toggle_key)

    def start(self) -> None:
        self.stop()
        self.conflict_detected = False
        try:
            self._listener = kb.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
            )
            self._listener.start()
        except (OSError, RuntimeError):
            self.conflict_detected = True

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None
        with self._lock:
            self._pressed.clear()
            self._hold_active = False

    # --- Internal handlers ---

    def _canonical(self, key):
        """Normalise left/right modifier variants to their canonical form."""
        return _CANONICAL_MAP.get(key, key)

    def _on_press(self, key) -> None:
        key = self._canonical(key)
        with self._lock:
            self._pressed.add(key)
            current_set = frozenset(self._pressed)
            hold_triggered = current_set == self._hold_keys and not self._hold_active
            toggle_triggered = not hold_triggered and current_set == self._toggle_keys
            if hold_triggered:
                self._hold_active = True

        if hold_triggered:
            self._on_hold_press()
        elif toggle_triggered:
            self._on_toggle_press()

    def _on_release(self, key) -> None:
        key = self._canonical(key)
        with self._lock:
            release_hold = self._hold_active and key in self._hold_keys
            if release_hold:
                self._hold_active = False
            self._pressed.discard(key)

        if release_hold:
            self._on_hold_release()

    def _on_hold_press(self) -> None:
        self._on_start()

    def _on_hold_release(self) -> None:
        self._on_stop()

    def _on_toggle_press(self) -> None:
        if self._state is None:
            self._on_start()
            return
        current = self._state.current()
        if current == AppState.IDLE:
            self._on_start()
        elif current == AppState.RECORDING:
            self._on_stop()
        elif current == AppState.TRANSCRIBING:
            self._on_cancel()
