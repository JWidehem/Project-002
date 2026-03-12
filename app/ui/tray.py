from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QColor, QPixmap
from PyQt6.QtCore import QSize
from app.engine.state import AppState

_STATE_COLORS = {
    AppState.IDLE: QColor(150, 150, 150),
    AppState.RECORDING: QColor(220, 60, 60),
    AppState.TRANSCRIBING: QColor(220, 140, 40),
}


def _make_icon(color: QColor) -> QIcon:
    px = QPixmap(QSize(16, 16))
    px.fill(color)
    return QIcon(px)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, on_history, on_settings, on_quit) -> None:
        super().__init__(_make_icon(_STATE_COLORS[AppState.IDLE]))
        self.setToolTip("WhisperFlow — Idle")
        self.show()

        menu = QMenu()
        menu.addAction("📋 Historique", on_history)
        menu.addAction("⚙️ Réglages", on_settings)
        menu.addSeparator()
        menu.addAction("🚪 Quitter", on_quit)
        self.setContextMenu(menu)

    def on_state_change(self, new_state: str) -> None:
        self.setIcon(_make_icon(_STATE_COLORS.get(new_state, _STATE_COLORS[AppState.IDLE])))
        labels = {
            AppState.IDLE: "Idle",
            AppState.RECORDING: "Recording…",
            AppState.TRANSCRIBING: "Transcribing…",
        }
        self.setToolTip(f"WhisperFlow — {labels.get(new_state, new_state)}")
