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

# When toggle_keys is a strict superset of hold_keys (e.g. Ctrl+Alt vs Ctrl+Alt+Space),
# hold activation is deferred by this many seconds to allow the extra key to arrive.
_HOLD_DEFER_S = 0.35


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
        self._hold_active = False           # recording via hold (push-to-talk)
        self._toggle_active = False         # recording via toggle (hands-free)
        self._hold_pending = False          # deferred hold: timer started, not yet committed
        self._hold_defer_timer: threading.Timer | None = None
        self._toggle_is_hold_superset = False  # True when toggle ⊃ hold keys
        self._lock = threading.Lock()
        self.conflict_detected = False

    def set_state(self, state: AppState) -> None:
        self._state = state

    def configure(self, hold_key: str, toggle_key: str) -> None:
        self._hold_keys = _parse_hotkey(hold_key)
        self._toggle_keys = _parse_hotkey(toggle_key)
        # Detect superset case: e.g. hold=Ctrl+Alt, toggle=Ctrl+Alt+Space
        self._toggle_is_hold_superset = bool(
            self._toggle_keys and self._hold_keys
            and self._toggle_keys > self._hold_keys
        )

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
        self._cancel_hold_timer()
        if self._listener:
            self._listener.stop()
            self._listener = None
        with self._lock:
            self._pressed.clear()
            self._hold_active = False
            self._toggle_active = False
            self._hold_pending = False

    # --- Internal helpers ---

    def _canonical(self, key):
        """Normalise left/right modifier variants to their canonical form."""
        return _CANONICAL_MAP.get(key, key)

    def _cancel_hold_timer(self) -> None:
        with self._lock:
            t = self._hold_defer_timer
            self._hold_defer_timer = None
            self._hold_pending = False
        if t is not None:
            t.cancel()

    def _hold_timer_fired(self) -> None:
        """Defer window expired with no superset key: commit to hold mode."""
        with self._lock:
            if not self._hold_pending:
                return  # was cancelled (Space pressed just in time)
            self._hold_pending = False
            self._hold_active = True
        self._on_hold_press()

    # --- Listener callbacks ---

    def _on_press(self, key) -> None:
        # Escape cancels any active recording or transcription immediately.
        if key == kb.Key.esc:
            if self._state and self._state.current() in (AppState.RECORDING, AppState.TRANSCRIBING):
                self._cancel_hold_timer()
                with self._lock:
                    self._hold_active = False
                    self._toggle_active = False
                    self._pressed.clear()
                self._on_cancel()
            return

        key = self._canonical(key)
        action = None       # "hold_start" | "toggle_start" | "toggle_stop"
        timer_to_cancel = None
        timer_to_start = None

        with self._lock:
            self._pressed.add(key)
            current_set = frozenset(self._pressed)

            if self._hold_active:
                # Push-to-talk is active: ignore all other combos (Space, etc.)
                pass

            elif self._hold_pending:
                # Defer timer is running — only care about the toggle superset key
                if current_set == self._toggle_keys:
                    timer_to_cancel = self._hold_defer_timer
                    self._hold_defer_timer = None
                    self._hold_pending = False
                    self._toggle_active = True
                    action = "toggle_start"

            elif self._toggle_active:
                # Hands-free mode is active: either hold_keys or toggle_keys stops it
                if current_set == self._hold_keys or current_set == self._toggle_keys:
                    timer_to_cancel = self._hold_defer_timer
                    self._hold_defer_timer = None
                    self._hold_pending = False
                    self._toggle_active = False
                    action = "toggle_stop"

            else:
                # IDLE — detect a new combo
                if current_set == self._toggle_keys:
                    self._toggle_active = True
                    action = "toggle_start"
                elif (current_set == self._hold_keys
                      and not self._hold_pending):
                    if self._toggle_is_hold_superset:
                        # Defer: wait for the extra key before committing
                        self._hold_pending = True
                        t = threading.Timer(_HOLD_DEFER_S, self._hold_timer_fired)
                        self._hold_defer_timer = t
                        timer_to_start = t
                    else:
                        self._hold_active = True
                        action = "hold_start"

        if timer_to_cancel is not None:
            timer_to_cancel.cancel()
        if timer_to_start is not None:
            timer_to_start.start()

        if action == "hold_start":
            self._on_hold_press()
        elif action == "toggle_start":
            self._on_toggle_start()
        elif action == "toggle_stop":
            self._on_toggle_stop()

    def _on_release(self, key) -> None:
        key = self._canonical(key)
        release_hold = False
        timer_to_cancel = None

        with self._lock:
            if self._hold_pending and key in self._hold_keys:
                # Hold key released before timer fired → cancel pending hold, do nothing
                timer_to_cancel = self._hold_defer_timer
                self._hold_defer_timer = None
                self._hold_pending = False
            elif self._hold_active and key in self._hold_keys:
                release_hold = True
                self._hold_active = False
            # If _toggle_active: releasing keys does NOT stop recording (that's the point)
            self._pressed.discard(key)

        if timer_to_cancel is not None:
            timer_to_cancel.cancel()
        if release_hold:
            self._on_hold_release()

    def _on_hold_press(self) -> None:
        self._on_start()

    def _on_hold_release(self) -> None:
        self._on_stop()

    def _on_toggle_start(self) -> None:
        self._on_start()

    def _on_toggle_stop(self) -> None:
        if self._state is None:
            return
        current = self._state.current()
        if current == AppState.RECORDING:
            self._on_stop()
        elif current == AppState.TRANSCRIBING:
            self._on_cancel()

    # Kept for backward compatibility with existing tests
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
