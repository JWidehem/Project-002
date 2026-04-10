import queue
import math
from PyQt6.QtCore import Qt, QTimer, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QFont
from PyQt6.QtWidgets import QWidget, QApplication
from app.engine.state import AppState

BAR_COUNT = 10
UPDATE_MS = 33   # ~30fps
W, H = 120, 24  # very compact pill


class Overlay(QWidget):
    def __init__(self, rms_queue: queue.Queue) -> None:
        super().__init__()
        self._rms_queue = rms_queue
        self._rms_values: list[float] = [0.0] * BAR_COUNT
        self._state = AppState.IDLE
        self._latch_mode = False   # True when recording is latched (hands-free)
        self._spinner_angle = 0
        self._bar_tick = 0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedSize(W, H)
        self._position_on_active_screen()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(UPDATE_MS)

    def _position_on_active_screen(self) -> None:
        from PyQt6.QtGui import QCursor
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            # Centered horizontally, just above the taskbar
            x = geo.center().x() - self.width() // 2
            y = geo.bottom() - self.height() - 12
            self.move(x, y)

    def on_state_change(self, new_state: str) -> None:
        self._state = new_state
        if new_state != AppState.RECORDING:
            self._latch_mode = False  # reset on any exit from recording
        if new_state == AppState.IDLE:
            self.hide()
        else:
            self._position_on_active_screen()
            self.show()
        self.update()

    def set_latch(self, active: bool) -> None:
        """Called from hotkey thread — safe because bool assignment is atomic."""
        self._latch_mode = active
        self.update()

    def _tick(self) -> None:
        updated = False
        # Drain all pending RMS values but average them into a single bar shift
        # so the scroll speed is constant (1 bar per tick) regardless of callback rate
        pending = []
        while not self._rms_queue.empty():
            try:
                pending.append(self._rms_queue.get_nowait())
            except queue.Empty:
                break
        if pending:
            self._bar_tick += 1
            if self._bar_tick >= 2:  # shift bars every 2 ticks ≈ 15fps
                self._bar_tick = 0
                val = sum(pending) / len(pending)
                self._rms_values = self._rms_values[1:] + [val]
                updated = True
        if self._state == AppState.TRANSCRIBING:
            self._spinner_angle = (self._spinner_angle + 8) % 360
            updated = True
        if updated:
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background pill
        painter.setBrush(QColor(28, 28, 30, 230))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), H // 2, H // 2)

        if self._state == AppState.RECORDING:
            self._draw_recording(painter)
        elif self._state == AppState.TRANSCRIBING:
            self._draw_transcribing(painter)

    def _draw_recording(self, painter: QPainter) -> None:
        # Amber in latch (hands-free) mode, gold in normal hold mode
        if self._latch_mode:
            dot_color = QColor(218, 148, 60)   # warm copper-amber
            bar_color = QColor(210, 140, 60)
        else:
            dot_color = QColor(232, 201, 106)  # gold
            bar_color = QColor(201, 168, 76)

        # Dot on the left
        dot_r = 4
        dot_x = 10
        dot_y = H // 2
        painter.setBrush(dot_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPoint(dot_x, dot_y), dot_r, dot_r)

        # Bars to the right of the dot
        # Amplify RMS for display: speech RMS ~0.02-0.05 → scale to fill bar height
        bar_w = 2
        bar_area_x = dot_x + dot_r + 6
        bar_area_w = W - bar_area_x - 6
        spacing = max(1, (bar_area_w - BAR_COUNT * bar_w) // (BAR_COUNT + 1))
        painter.setBrush(bar_color)
        painter.setPen(Qt.PenStyle.NoPen)
        max_bar_h = H - 8
        for i, rms in enumerate(self._rms_values):
            # Scale: rms 0.05 → full height; amplify 12x so speech is visible
            bar_h = max(2, min(max_bar_h, int(rms * 12 * max_bar_h)))
            x = bar_area_x + spacing + i * (bar_w + spacing)
            y = (H - bar_h) // 2
            painter.drawRoundedRect(x, y, bar_w, bar_h, 1, 1)

    def _draw_transcribing(self, painter: QPainter) -> None:
        # Small spinning arc on the left
        arc_x, arc_y, arc_d = 8, (H - 16) // 2, 16
        pen = QPen(QColor(201, 168, 76), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(arc_x, arc_y, arc_d, arc_d,
                        self._spinner_angle * 16, 270 * 16)

        # "Transcription…" text
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(QPen(QColor(232, 201, 106)))
        text_rect = QRect(arc_x + arc_d + 8, 0, W - arc_x - arc_d - 16, H)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, "Transcription…")
