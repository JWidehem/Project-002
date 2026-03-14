from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QColor, QPixmap, QPainter
from PyQt6.QtCore import QSize, Qt
from pathlib import Path
from app.engine.state import AppState

_ASSETS = Path(__file__).parent.parent.parent / "assets"
_LOGO = _ASSETS / "logo00.png"

_STATUS_COLORS = {
    AppState.RECORDING: QColor(220, 60, 60),
    AppState.TRANSCRIBING: QColor(220, 140, 40),
}


def _make_icon(state: str) -> QIcon:
    """Logo as base icon; coloured dot overlay for non-idle states."""
    base = QPixmap(str(_LOGO)).scaled(
        QSize(32, 32),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    ) if _LOGO.exists() else QPixmap(QSize(32, 32))

    if not _LOGO.exists():
        base.fill(QColor(150, 150, 150))

    dot_color = _STATUS_COLORS.get(state)
    if dot_color:
        p = QPainter(base)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(dot_color)
        p.setPen(Qt.PenStyle.NoPen)
        r = base.width() // 5
        p.drawEllipse(base.width() - r * 2, base.height() - r * 2, r * 2, r * 2)
        p.end()

    return QIcon(base)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, on_open, on_history, on_settings, on_quit) -> None:
        super().__init__(_make_icon(AppState.IDLE))
        self.setToolTip("WhisperFlow — Idle")
        self.show()

        menu = QMenu()
        menu.addAction("🖥  Ouvrir WhisperFlow", on_open)
        menu.addSeparator()
        menu.addAction("📋 Historique", on_history)
        menu.addAction("⚙️ Réglages", on_settings)
        menu.addSeparator()
        menu.addAction("🚪 Quitter", on_quit)
        self.setContextMenu(menu)

        self._on_open = on_open
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._on_open()

    def on_state_change(self, new_state: str) -> None:
        self.setIcon(_make_icon(new_state))
        labels = {
            AppState.IDLE: "Idle",
            AppState.RECORDING: "Recording…",
            AppState.TRANSCRIBING: "Transcribing…",
        }
        self.setToolTip(f"WhisperFlow — {labels.get(new_state, new_state)}")

    def notify(self, title: str, message: str) -> None:
        self.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)
