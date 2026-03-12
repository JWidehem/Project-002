from PyQt6.QtCore import QObject, pyqtSignal


class AppState(QObject):
    state_changed = pyqtSignal(str)

    IDLE = "IDLE"
    RECORDING = "RECORDING"
    TRANSCRIBING = "TRANSCRIBING"

    _VALID_TRANSITIONS: dict[str, set[str]] = {
        IDLE:         {RECORDING},
        RECORDING:    {TRANSCRIBING, IDLE},
        TRANSCRIBING: {IDLE},
    }

    def __init__(self) -> None:
        super().__init__()
        self._current: str = self.IDLE

    def transition(self, new_state: str) -> None:
        allowed = self._VALID_TRANSITIONS.get(self._current, set())
        if new_state not in allowed:
            raise ValueError(
                f"Invalid transition: {self._current} -> {new_state}"
            )
        self._current = new_state
        self.state_changed.emit(new_state)

    def current(self) -> str:
        return self._current
