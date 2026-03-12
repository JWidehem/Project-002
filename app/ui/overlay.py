import queue
import math
from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtGui import QPainter, QColor, QPen
from PyQt6.QtWidgets import QWidget, QApplication
from app.engine.state import AppState

BAR_COUNT = 12
UPDATE_MS = 33  # ~30fps


class Overlay(QWidget):
    def __init__(self, rms_queue: queue.Queue) -> None:
        super().__init__()
        self._rms_queue = rms_queue
        self._rms_values: list[float] = [0.0] * BAR_COUNT
        self._state = AppState.IDLE

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedSize(380, 48)
        self._position_on_active_screen()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_rms)
        self._timer.start(UPDATE_MS)

    def _position_on_active_screen(self) -> None:
        from PyQt6.QtGui import QCursor
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.right() - self.width() - 16, geo.bottom() - self.height() - 16)

    def on_state_change(self, new_state: str) -> None:
        self._state = new_state
        if new_state == AppState.IDLE:
            self.hide()
        else:
            self._position_on_active_screen()
            self.show()
        self.update()

    def _update_rms(self) -> None:
        updated = False
        while not self._rms_queue.empty():
            try:
                val = self._rms_queue.get_nowait()
                self._rms_values = self._rms_values[1:] + [val]
                updated = True
            except queue.Empty:
                break
        if updated:
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.setBrush(QColor(30, 30, 30, 210))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 10, 10)

        if self._state == AppState.RECORDING:
            self._draw_bars(painter)
        elif self._state == AppState.TRANSCRIBING:
            self._draw_spinner(painter)

    def _draw_bars(self, painter: QPainter) -> None:
        bar_color = QColor(220, 60, 60)
        w = self.width()
        h = self.height()
        bar_w = 4
        spacing = (w - BAR_COUNT * bar_w) // (BAR_COUNT + 1)
        for i, rms in enumerate(self._rms_values):
            bar_h = max(4, int(rms * (h - 12)))
            x = spacing + i * (bar_w + spacing)
            y = (h - bar_h) // 2
            painter.setBrush(bar_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(x, y, bar_w, bar_h, 2, 2)

    def _draw_spinner(self, painter: QPainter) -> None:
        painter.setPen(QPen(QColor(200, 200, 200), 2))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Transcription…")
