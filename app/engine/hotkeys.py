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

# Interval at which we check whether the pynput Listener thread is still alive.
# Windows can silently kill the low-level keyboard hook (UAC, security timeout);
# the thread stays alive but stops delivering events.  We detect this by tracking
# the timestamp of the last received key event and restarting if too much time
# elapses without any event while the listener thread is still "alive".
_WATCHDOG_INTERVAL_S = 10.0


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
    def __init__(self, on_start, on_stop, on_cancel, on_latch=None) -> None:
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_cancel = on_cancel
        self._on_latch = on_latch  # optional: called when hold is latched to hands-free
        self._state: AppState | None = None
        self._listener: kb.Listener | None = None
        self._hold_keys: frozenset = frozenset()
        self._latch_keys: frozenset = frozenset()   # extra key(s) that latch hold → hands-free
        self._pressed: set = set()
        self._hold_active = False      # recording via hold (push-to-talk)
        self._latch_active = False     # recording latched — hands-free (latch key pressed during hold)
        self._lock = threading.Lock()
        self.conflict_detected = False
        self._watchdog_timer: threading.Timer | None = None
        self._last_event_time: float = 0.0
        self._suspended = False

    def set_state(self, state: AppState) -> None:
        self._state = state

    def configure(self, hold_key: str, toggle_key: str) -> None:
        """Configure hotkeys.

        hold_key  : combo to start hold recording (e.g. '<ctrl>+<alt>')
        toggle_key: superset combo whose extra keys act as the latch/stop key
                    (e.g. '<ctrl>+<alt>+<space>' → latch key is <space>)
        """
        self._hold_keys = _parse_hotkey(hold_key)
        toggle_keys = _parse_hotkey(toggle_key)
        # Latch key(s) = keys in toggle that are NOT in hold.
        # Example: hold=Ctrl+Alt, toggle=Ctrl+Alt+Space → _latch_keys={space}
        self._latch_keys = toggle_keys - self._hold_keys

    def start(self) -> None:
        self.stop()  # also cancels watchdog
        self.conflict_detected = False
        import time
        self._last_event_time = time.monotonic()
        try:
            self._listener = kb.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
            )
            self._listener.start()
        except (OSError, RuntimeError):
            self.conflict_detected = True
        self._schedule_watchdog()

    def stop(self) -> None:
        self._cancel_watchdog()
        if self._listener:
            self._listener.stop()
            self._listener = None
        with self._lock:
            self._pressed.clear()
            self._hold_active = False
            self._latch_active = False

    def suspend(self) -> None:
        """Temporarily ignore all key events (call before injecting text)."""
        with self._lock:
            self._suspended = True

    def resume(self) -> None:
        """Resume key event processing and clear any stale pressed state."""
        with self._lock:
            self._suspended = False
            self._pressed.clear()

    def reset(self) -> None:
        """Clear active/pressed state after an external cancel (error, timeout)."""
        with self._lock:
            self._pressed.clear()
            self._hold_active = False
            self._latch_active = False

    def _schedule_watchdog(self) -> None:
        t = threading.Timer(_WATCHDOG_INTERVAL_S, self._watchdog_check)
        t.daemon = True
        self._watchdog_timer = t
        t.start()

    def _cancel_watchdog(self) -> None:
        t = self._watchdog_timer
        self._watchdog_timer = None
        if t is not None:
            t.cancel()

    def _watchdog_check(self) -> None:
        """Periodic check: restart listener if its thread has died."""
        import logging, time
        restart = False
        with self._lock:
            listener = self._listener
        if listener is not None and not listener.is_alive():
            logging.warning("HotkeyManager: listener thread died — restarting")
            restart = True
        if restart:
            self.start()  # also schedules next watchdog
            return
        self._schedule_watchdog()  # reschedule

    # --- Internal helpers ---

    def _canonical(self, key):
        """Normalise left/right modifier variants to their canonical form."""
        return _CANONICAL_MAP.get(key, key)

    # --- Listener callbacks ---

    def _on_press(self, key) -> None:
        import time
        self._last_event_time = time.monotonic()
        with self._lock:
            if self._suspended:
                return
        # Escape cancels any active recording or transcription immediately.
        if key == kb.Key.esc:
            if self._state and self._state.current() in (AppState.RECORDING, AppState.TRANSCRIBING):
                with self._lock:
                    self._hold_active = False
                    self._latch_active = False
                    self._pressed.clear()
                self._on_cancel()
            return

        key = self._canonical(key)
        action = None

        with self._lock:
            # Self-heal: if hold is stuck True but app is already IDLE,
            # a key-up event was swallowed by the OS (e.g. Alt+Tab, Win+D).
            if self._hold_active and \
                    self._state is not None and self._state.current() == AppState.IDLE:
                self._hold_active = False
                self._latch_active = False
                self._pressed.clear()
            elif not self._hold_active and not self._latch_active:
                # Pure IDLE: remove stale non-combo keys (missed OS key-up events)
                combo_keys = self._hold_keys | self._latch_keys
                stale = frozenset(k for k in self._pressed if k not in combo_keys)
                if stale:
                    self._pressed -= stale
            self._pressed.add(key)
            current_set = frozenset(self._pressed)

            if self._hold_active:
                # Push-to-talk active: latch key pressed → switch to hands-free.
                if self._latch_keys and key in self._latch_keys:
                    self._hold_active = False
                    self._latch_active = True
                    action = "latch_start"

            elif self._latch_active:
                # Hands-free mode: latch key pressed again → stop and transcribe.
                if self._latch_keys and key in self._latch_keys:
                    self._latch_active = False
                    action = "latch_stop"

            else:
                # IDLE — detect hold combo start.
                if current_set == self._hold_keys:
                    self._hold_active = True
                    action = "hold_start"

        if action == "hold_start":
            self._on_hold_press()
        elif action == "latch_start":
            if self._on_latch is not None:
                self._on_latch(True)
        elif action == "latch_stop":
            self._on_latch_stop()

    def _on_release(self, key) -> None:
        with self._lock:
            if self._suspended:
                return
        key = self._canonical(key)
        release_hold = False

        with self._lock:
            if self._hold_active and key in self._hold_keys:
                # Hold key released before latching → stop and transcribe.
                release_hold = True
                self._hold_active = False
            # If _latch_active: releasing keys does NOT stop recording (that's the point).
            self._pressed.discard(key)

        if release_hold:
            self._on_hold_release()

    def _on_hold_press(self) -> None:
        # Guard against the race where _on_release fires between _hold_timer_fired
        # releasing the lock and this call: if _hold_active was already cleared,
        # don't start (avoids state stuck in RECORDING with _hold_active=False).
        with self._lock:
            if not self._hold_active:
                return
        self._on_start()

    def _on_hold_release(self) -> None:
        self._on_stop()

    def _on_latch_stop(self) -> None:
        """Space pressed in hands-free mode: stop recording and transcribe."""
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
