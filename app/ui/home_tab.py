"""Home tab builder: clock/welcome bento layout, stats pills, mini-history."""
from __future__ import annotations

import math
from pathlib import Path

from PyQt6.QtCore import (
    Qt, QObject, QPoint, QPointF, QRectF, QSize, QTimer, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QIcon, QLinearGradient,
    QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from app.ui import theme
from app.ui.glass_card import GlassCard


# ── File transcription helpers ──────────────────────────────────────────────────

class _FileWorkerSignals(QObject):
    """Thread-safe signals for file transcription worker."""
    done     = pyqtSignal(str)   # emitted with full text on success
    error    = pyqtSignal(str)   # emitted with error message on failure
    progress = pyqtSignal(int)   # 0-99, percentage of audio processed


class _WaveformIcon(QWidget):
    """Painted audio-waveform icon — 5 bars of varying height in gold."""

    def __init__(self, size: int = 44, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _) -> None:  # noqa: N802
        sz   = self.width()
        pnt  = QPainter(self)
        pnt.setRenderHint(QPainter.RenderHint.Antialiasing)

        bar_w   = sz * 0.10
        gap     = sz * 0.07
        heights = [0.35, 0.65, 1.00, 0.65, 0.35]
        total_w = len(heights) * bar_w + (len(heights) - 1) * gap
        x0      = (sz - total_w) / 2.0
        cy      = sz / 2.0

        for i, h in enumerate(heights):
            bh = sz * 0.80 * h
            x  = x0 + i * (bar_w + gap)
            y  = cy - bh / 2.0
            alpha = int(180 + 75 * h)
            pnt.setPen(Qt.PenStyle.NoPen)
            pnt.setBrush(QColor(201, 168, 76, alpha))
            pnt.drawRoundedRect(
                QRectF(x, y, bar_w, bh),
                bar_w / 2, bar_w / 2,
            )
        pnt.end()


class _TranscriptResultDialog(QDialog):
    """Glassmorphism dialog to display a long transcription result."""

    def __init__(self, filename: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(540, 420)
        self.resize(640, 500)
        self.setStyleSheet(theme.STYLESHEET)

        self._filename = filename

        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 4)
        root.setSpacing(0)

        # ── Title bar ──────────────────────────────────────────────────────
        bar = QWidget()
        bar.setFixedHeight(46)
        bar.setStyleSheet("background: transparent;")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(14, 0, 12, 0)
        bar_lay.setSpacing(0)

        title = QLabel(f"Transcription — {filename}")
        title.setStyleSheet(
            "color: rgba(255,255,255,0.88); font-size:13px; font-weight:600;"
            " background:transparent; letter-spacing:0.3px;"
        )
        bar_lay.addWidget(title)
        bar_lay.addStretch()

        close_btn = QPushButton("×")
        close_btn.setObjectName("winClose")
        close_btn.setToolTip("Fermer")
        close_btn.clicked.connect(self.accept)
        bar_lay.addWidget(close_btn)
        root.addWidget(bar)

        # ── Text area ──────────────────────────────────────────────────────
        self._text_edit = QPlainTextEdit(text)
        self._text_edit.setReadOnly(True)
        self._text_edit.setStyleSheet(
            "QPlainTextEdit {"
            "  background: rgba(0,0,0,0);"
            "  color: rgba(255,255,255,0.88);"
            "  border: none;"
            "  font-size: 13px;"
            "  line-height: 1.5;"
            "  padding: 4px 8px;"
            "}"
            "QScrollBar:vertical { width: 6px; background: transparent; }"
            "QScrollBar::handle:vertical { background: rgba(201,168,76,0.45); border-radius:3px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }"
        )
        root.addWidget(self._text_edit, 1)

        # ── Buttons ────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(14, 8, 14, 10)
        btn_row.setSpacing(10)

        copy_btn = QPushButton("Copier")
        copy_btn.setFixedHeight(32)
        copy_btn.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "  stop:0 rgba(201,168,76,0.55), stop:1 rgba(160,130,55,0.55));"
            "  color: rgba(255,245,210,0.95); font-weight:600; font-size:12px;"
            "  border: 1px solid rgba(201,168,76,0.70); border-radius:6px; padding:0 16px; }"
            "QPushButton:hover { background: rgba(201,168,76,0.68); }"
            "QPushButton:pressed { background: rgba(160,130,55,0.75); }"
        )
        copy_btn.clicked.connect(self._copy_text)

        save_btn = QPushButton("Enregistrer…")
        save_btn.setFixedHeight(32)
        save_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.08);"
            "  color: rgba(255,255,255,0.70); font-size:12px;"
            "  border: 1px solid rgba(255,255,255,0.18); border-radius:6px; padding:0 16px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.14); color:rgba(255,255,255,0.90); }"
        )
        save_btn.clicked.connect(self._save_text)

        close_btn2 = QPushButton("Fermer")
        close_btn2.setFixedHeight(32)
        close_btn2.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.08);"
            "  color: rgba(255,255,255,0.55); font-size:12px;"
            "  border: 1px solid rgba(255,255,255,0.12); border-radius:6px; padding:0 16px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.14); color:rgba(255,255,255,0.80); }"
        )
        close_btn2.clicked.connect(self.accept)

        btn_row.addWidget(copy_btn)
        btn_row.addWidget(save_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn2)
        root.addLayout(btn_row)

        # ── Drag to move ────────────────────────────────────────────────────
        self._drag_pos: QPoint | None = None

    def _copy_text(self) -> None:
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._text_edit.toPlainText())

    def _save_text(self) -> None:
        from datetime import datetime
        default = f"transcription_{Path(self._filename).stem}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer la transcription", default,
            "Texte (*.txt);;Tous les fichiers (*)"
        )
        if path:
            Path(path).write_text(self._text_edit.toPlainText(), encoding="utf-8")

    def paintEvent(self, _event) -> None:
        import app.ui.glass_card as _gc
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r   = self.rect()
        rad = 14.0
        path = QPainterPath()
        path.addRoundedRect(float(r.x()), float(r.y()), float(r.width()), float(r.height()), rad, rad)
        p.setClipPath(path)

        cache = _gc._bg_pixmap_cache
        if cache is not None and not cache.isNull():
            bw, bh = cache.width(), cache.height()
            ox = (bw - r.width())  // 2
            oy = (bh - r.height()) // 2
            p.drawPixmap(0, 0, cache, ox, oy, r.width(), r.height())
        else:
            p.fillRect(r, QColor(10, 8, 6))

        p.fillRect(r, QColor(6, 5, 3, 165))
        p.setClipping(False)

        rim = QLinearGradient(r.width() * .1, 0, r.width() * .9, 0)
        rim.setColorAt(0.0,  QColor(201, 168, 76, 0))
        rim.setColorAt(0.35, QColor(201, 168, 76, 130))
        rim.setColorAt(0.65, QColor(201, 168, 76, 130))
        rim.setColorAt(1.0,  QColor(201, 168, 76, 0))
        p.setPen(QPen(QBrush(rim), 1.5))
        p.drawLine(int(r.width() * .1), 1, int(r.width() * .9), 1)

        p.setPen(QPen(QColor(201, 168, 76, 180), 1.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(1, 1, -1, -1), rad, rad)

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = ev.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev) -> None:
        if self._drag_pos is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(ev)


class _ImportAudioCard(GlassCard):
    """
    Bento card for importing and transcribing an audio file.
    Receives an *on_transcribe_file* callable:
        on_transcribe_file(path: str, signals: _FileWorkerSignals) -> callable
    The callable returns a cancel function.
    """

    def __init__(self, on_transcribe_file=None) -> None:
        super().__init__(radius=14, strong_tint=True)
        self._on_transcribe_file = on_transcribe_file
        self._file_path: str | None = None
        self._cancel_fn = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(6)

        # ── Title ──────────────────────────────────────────────────────────
        self._title_btn = QPushButton("Importer un audio")
        self._title_btn.setFlat(True)
        self._title_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title_btn.clicked.connect(self._browse_file)
        self._title_btn.setStyleSheet(
            "QPushButton { color: rgba(255,255,255,0.90); font-size:14px; font-weight:600;"
            " letter-spacing:0.3px; background:transparent; border:none;"
            " text-align:center; padding:0; }"
            "QPushButton:hover { color:#E8C96A; }"
        )
        lay.addWidget(self._title_btn)

        # ── Icon ───────────────────────────────────────────────────────────
        icon_w = _WaveformIcon(36)
        lay.addWidget(icon_w, 0, Qt.AlignmentFlag.AlignCenter)

        # ── File label ─────────────────────────────────────────────────────
        self._file_lbl = QLabel("Aucun fichier sélectionné")
        self._file_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._file_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.38); font-size:10px; background:transparent;"
        )
        lay.addWidget(self._file_lbl)

        # ── Action button ──────────────────────────────────────────────────
        self._action_btn = QPushButton("Choisir un fichier")
        self._action_btn.setFixedHeight(28)
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_btn.setStyleSheet(self._style_browse())
        self._action_btn.clicked.connect(self._on_action)
        lay.addWidget(self._action_btn, 0, Qt.AlignmentFlag.AlignCenter)

    # ── Styles ─────────────────────────────────────────────────────────────

    @staticmethod
    def _style_browse() -> str:
        return (
            "QPushButton { background: rgba(255,255,255,0.10);"
            "  color: rgba(255,255,255,0.65); font-size:11px;"
            "  border: 1px solid rgba(255,255,255,0.20); border-radius:5px; padding:0 12px; }"
            "QPushButton:hover { background:rgba(255,255,255,0.18); color:rgba(255,255,255,0.90); }"
        )

    @staticmethod
    def _style_transcribe() -> str:
        return (
            "QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "  stop:0 rgba(201,168,76,0.55), stop:1 rgba(160,130,55,0.55));"
            "  color: rgba(255,245,210,0.95); font-weight:600; font-size:11px;"
            "  border: 1px solid rgba(201,168,76,0.70); border-radius:5px; padding:0 12px; }"
            "QPushButton:hover { background: rgba(201,168,76,0.68); }"
            "QPushButton:pressed { background: rgba(160,130,55,0.75); }"
        )

    @staticmethod
    def _style_cancel() -> str:
        return (
            "QPushButton { background: rgba(200,80,60,0.30);"
            "  color: rgba(255,160,140,0.90); font-size:11px;"
            "  border: 1px solid rgba(200,80,60,0.45); border-radius:5px; padding:0 12px; }"
            "QPushButton:hover { background: rgba(200,80,60,0.50); }"
        )

    # ── Slots ──────────────────────────────────────────────────────────────

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir un fichier audio", "",
            "Fichiers audio (*.mp3 *.m4a *.aac *.wav *.ogg *.flac *.wma *.opus *.mp4 *.webm);;"
            "Tous les fichiers (*)"
        )
        if not path:
            return
        self._file_path = path
        name = Path(path).name
        self._file_lbl.setText(name if len(name) <= 34 else f"…{name[-32:]}")
        self._file_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.72); font-size:10px; background:transparent;"
        )
        self._action_btn.setText("Transcrire")
        self._action_btn.setStyleSheet(self._style_transcribe())

    def _on_action(self) -> None:
        if self._cancel_fn is not None:
            # Currently transcribing → cancel
            self._cancel_fn()
            self._cancel_fn = None
            self._reset_idle()
            return

        if self._file_path is None:
            self._browse_file()
            return

        if self._on_transcribe_file is None:
            return

        # Start transcription
        signals = _FileWorkerSignals()
        signals.done.connect(self._on_done)
        signals.error.connect(self._on_error)
        signals.progress.connect(self._on_progress)

        self._cancel_fn = self._on_transcribe_file(self._file_path, signals)

        # UI → "in progress" state
        self._action_btn.setText("Annuler")
        self._action_btn.setStyleSheet(self._style_cancel())
        self._title_btn.setEnabled(False)
        self._file_lbl.setText("Transcription en cours…")
        self._file_lbl.setStyleSheet(
            "color: rgba(201,168,76,0.75); font-size:10px; background:transparent;"
        )

    def _on_progress(self, pct: int) -> None:
        self._file_lbl.setText(f"Transcription en cours\u2026 {pct} %")

    def _on_done(self, text: str) -> None:
        self._cancel_fn = None
        fname = Path(self._file_path).name if self._file_path else "audio"
        self._file_path = None          # reset → bouton reviendra à « Choisir un fichier »
        self._reset_idle()
        dlg = _TranscriptResultDialog(fname, text, parent=self.window())
        dlg.exec()

    def _on_error(self, msg: str) -> None:
        self._cancel_fn = None
        self._reset_idle()
        self._file_lbl.setText(f"Erreur : {msg[:50]}")
        self._file_lbl.setStyleSheet(
            "color: rgba(220,100,80,0.90); font-size:10px; background:transparent;"
        )

    def _reset_idle(self) -> None:
        self._title_btn.setEnabled(True)
        if self._file_path:
            self._action_btn.setText("Transcrire")
            self._action_btn.setStyleSheet(self._style_transcribe())
        else:
            self._action_btn.setText("Choisir un fichier")
            self._action_btn.setStyleSheet(self._style_browse())
            self._file_lbl.setText("Aucun fichier sélectionné")
        self._file_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.38); font-size:10px; background:transparent;"
        )


# ── Nav-card icons ─────────────────────────────────────────────────────────────

class _GaugeIcon(QWidget):
    """Painted speedometer gauge – used as icon in the Performances nav card."""

    def __init__(self, size: int = 52, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _) -> None:  # noqa: N802
        sz = self.width()
        cx = cy = sz / 2.0
        r  = sz * 0.37
        lw = sz * 0.065

        pnt = QPainter(self)
        pnt.setRenderHint(QPainter.RenderHint.Antialiasing)

        arc_rect  = QRectF(cx - r, cy - r, r * 2, r * 2)
        start_qt  = 225 * 16
        span_full = -270 * 16

        pen_track = QPen(QColor(255, 255, 255, 55), lw)
        pen_track.setCapStyle(Qt.PenCapStyle.RoundCap)
        pnt.setPen(pen_track)
        pnt.drawArc(arc_rect, start_qt, span_full)

        pen_fill = QPen(QColor(201, 168, 76, 220), lw)
        pen_fill.setCapStyle(Qt.PenCapStyle.RoundCap)
        pnt.setPen(pen_fill)
        pnt.drawArc(arc_rect, start_qt, int(span_full * 0.65))

        needle_deg = 225.0 - 0.65 * 270.0
        needle_rad = math.radians(needle_deg)
        tip_x  = cx + r * 0.72 * math.cos(needle_rad)
        tip_y  = cy - r * 0.72 * math.sin(needle_rad)
        tail_x = cx + r * 0.20 * math.cos(needle_rad + math.pi)
        tail_y = cy - r * 0.20 * math.sin(needle_rad + math.pi)
        pen_needle = QPen(QColor(255, 245, 210, 245), lw * 0.55)
        pen_needle.setCapStyle(Qt.PenCapStyle.RoundCap)
        pnt.setPen(pen_needle)
        pnt.drawLine(QPointF(tail_x, tail_y), QPointF(tip_x, tip_y))

        pnt.setPen(Qt.PenStyle.NoPen)
        pnt.setBrush(QColor(201, 168, 76, 230))
        pnt.drawEllipse(QPointF(cx, cy), lw * 0.9, lw * 0.9)

        pen_tick = QPen(QColor(255, 255, 255, 110), lw * 0.45)
        pen_tick.setCapStyle(Qt.PenCapStyle.RoundCap)
        pnt.setPen(pen_tick)
        for tick_deg in (225, 90, -45):
            tr = math.radians(tick_deg)
            pnt.drawLine(
                QPointF(cx + r        * math.cos(tr), cy - r        * math.sin(tr)),
                QPointF(cx + r * 0.80 * math.cos(tr), cy - r * 0.80 * math.sin(tr)),
            )
        pnt.end()


class _GearIcon(QWidget):
    """Painted gear/cog icon – used as icon in the Réglages nav card."""

    def __init__(self, size: int = 52, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _) -> None:  # noqa: N802
        sz     = self.width()
        cx     = cy = sz / 2.0
        n      = 8
        r_out  = sz * 0.39
        r_in   = sz * 0.28
        r_hole = sz * 0.105
        tooth_half = math.pi / n * 0.55

        points = []
        for i in range(n):
            a0 = 2 * math.pi * i / n
            for ar, radius in (
                (a0 - tooth_half,         r_in),
                (a0 - tooth_half * 0.70,  r_out),
                (a0 + tooth_half * 0.70,  r_out),
                (a0 + tooth_half,         r_in),
            ):
                points.append(QPointF(cx + radius * math.cos(ar),
                                      cy - radius * math.sin(ar)))

        gear = QPainterPath()
        gear.moveTo(points[0])
        for p in points[1:]:
            gear.lineTo(p)
        gear.closeSubpath()

        hole = QPainterPath()
        hole.addEllipse(QPointF(cx, cy), r_hole, r_hole)
        final = gear.subtracted(hole)

        pnt = QPainter(self)
        pnt.setRenderHint(QPainter.RenderHint.Antialiasing)
        lw = sz * 0.05
        pnt.setPen(QPen(QColor(201, 168, 76, 210), lw))
        pnt.setBrush(QColor(255, 255, 255, 55))
        pnt.drawPath(final)

        pnt.setPen(Qt.PenStyle.NoPen)
        pnt.setBrush(QColor(201, 168, 76, 220))
        pnt.drawEllipse(QPointF(cx, cy), r_hole * 0.6, r_hole * 0.6)
        pnt.end()


class _BentoNavCard(GlassCard):
    """
    Full-height navigation card for left/right bento columns.
    Large icon centred vertically, title + subtitle below.
    Entire card is clickable.
    """

    nav_clicked = pyqtSignal()

    def __init__(self, icon, title: str, subtitle: str) -> None:
        super().__init__(radius=14, strong_tint=False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(0)
        lay.addStretch()

        if isinstance(icon, QWidget):
            lay.addWidget(icon, 0, Qt.AlignmentFlag.AlignCenter)
        else:
            ic = QLabel(icon)
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            f_ic = QFont("Segoe UI Symbol", 26)
            ic.setFont(f_ic)
            ic.setStyleSheet(
                "color: rgba(255,255,255,0.88); background:transparent;"
            )
            lay.addWidget(ic)
        lay.addSpacing(10)

        t = QLabel(title)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setStyleSheet(
            "color: rgba(255,255,255,0.90); font-size:14px; font-weight:600;"
            " background:transparent; letter-spacing:0.3px;"
        )
        t.setWordWrap(True)
        lay.addWidget(t)
        lay.addSpacing(4)

        s = QLabel(subtitle)
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s.setStyleSheet(
            "color: rgba(255,255,255,0.38); font-size:10px; background:transparent;"
        )
        s.setWordWrap(True)
        lay.addWidget(s)
        lay.addStretch()

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            self.nav_clicked.emit()
        super().mousePressEvent(ev)


# ── Tab builder ────────────────────────────────────────────────────────────────

def build_home_tab(window, on_transcribe_file=None) -> QWidget:
    """
    Build and return the Accueil tab widget.
    Stores widget references on *window* so that _refresh_home() and
    _tick_clock() can update them later.
    """
    from PyQt6.QtWidgets import QGridLayout  # local to avoid polluting module namespace

    container = QWidget()
    container.setAutoFillBackground(False)
    grid = QGridLayout(container)
    grid.setContentsMargins(18, 14, 18, 14)
    grid.setSpacing(12)
    for c in range(3):
        grid.setColumnStretch(c, 1)
    grid.setRowStretch(0, 3)
    grid.setRowStretch(1, 2)

    # ── Centre-top: Clock / Welcome card ──────────────────────────────────
    clock_card = GlassCard(radius=16, strong_tint=True)
    ck_lay = QVBoxLayout(clock_card)
    ck_lay.setContentsMargins(24, 20, 24, 20)
    ck_lay.setSpacing(4)
    ck_lay.addStretch()

    window._home_date_lbl = QLabel()
    window._home_date_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window._home_date_lbl.setStyleSheet(
        "color: rgba(255,255,255,0.55); font-size:11px; letter-spacing:2px;"
        " text-transform:uppercase; background:transparent;"
    )
    ck_lay.addWidget(window._home_date_lbl)

    window._home_clock_lbl = QLabel("00:00")
    window._home_clock_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    f_clock = QFont("Segoe UI", 48)
    f_clock.setWeight(QFont.Weight.Thin)
    window._home_clock_lbl.setFont(f_clock)
    window._home_clock_lbl.setStyleSheet(
        "color: rgba(255,255,255,0.92); background:transparent; letter-spacing:-1px;"
    )
    ck_lay.addWidget(window._home_clock_lbl)

    welcome_lbl = QLabel("Welcome back,")
    welcome_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    welcome_lbl.setStyleSheet(
        "color: rgba(255,255,255,0.50); font-size:14px; background:transparent;"
    )
    name_lbl = QLabel("Jimmy")
    name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    name_lbl.setStyleSheet(
        "color: rgba(255,255,255,0.90); font-size:22px; font-weight:600;"
        " background:transparent; letter-spacing:0.5px;"
    )
    ck_lay.addWidget(welcome_lbl)
    ck_lay.addWidget(name_lbl)
    ck_lay.addStretch()
    grid.addWidget(clock_card, 0, 1)

    # ── Stats pills ────────────────────────────────────────────────────────
    stats_bar = QWidget()
    stats_bar.setAutoFillBackground(False)
    sb_lay = QHBoxLayout(stats_bar)
    sb_lay.setContentsMargins(0, 0, 0, 0)
    sb_lay.setSpacing(0)

    def _stat_pill(label: str) -> tuple[QWidget, QLabel]:
        pill = GlassCard(radius=10)
        pl = QVBoxLayout(pill)
        pl.setContentsMargins(14, 10, 14, 10)
        pl.setSpacing(1)
        val_lbl = QLabel("—")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.88); font-size:18px; font-weight:700;"
            " background:transparent;"
        )
        lbl_w = QLabel(label)
        lbl_w.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_w.setStyleSheet(
            "color: rgba(255,255,255,0.40); font-size:9px; letter-spacing:1.2px;"
            " background:transparent;"
        )
        pl.addWidget(val_lbl)
        pl.addWidget(lbl_w)
        return pill, val_lbl

    words_pill, window._stat_words_lbl = _stat_pill("MOTS")
    wpm_pill,   window._stat_wpm_lbl   = _stat_pill("WPM")
    days_pill,  window._stat_days_lbl  = _stat_pill("JOURS")
    sb_lay.addWidget(words_pill, 1)
    sb_lay.addSpacing(8)
    sb_lay.addWidget(wpm_pill, 1)
    sb_lay.addSpacing(8)
    sb_lay.addWidget(days_pill, 1)

    # ── Centre column wrapper ──────────────────────────────────────────────
    centre_wrap = QWidget()
    centre_wrap.setAutoFillBackground(False)
    cw_lay = QVBoxLayout(centre_wrap)
    cw_lay.setContentsMargins(0, 0, 0, 0)
    cw_lay.setSpacing(10)
    cw_lay.addWidget(clock_card, 3)
    cw_lay.addWidget(stats_bar, 1)
    grid.addWidget(centre_wrap, 0, 1, 2, 1)

    # ── Left column: Réglages ──────────────────────────────────────────────
    sets_card = _BentoNavCard(_GearIcon(52), "Réglages", "Modèles, raccourcis, options")
    sets_card.nav_clicked.connect(lambda: window._tabs.setCurrentIndex(2))
    grid.addWidget(sets_card, 1, 0)

    # ── Right column: Performances ─────────────────────────────────────────
    perf_card = _BentoNavCard(_GaugeIcon(52), "Performances", "CPU · RAM · Threads")
    perf_card.nav_clicked.connect(lambda: window._tabs.setCurrentIndex(3))
    grid.addWidget(perf_card, 1, 2)

    # ── Mini historique ────────────────────────────────────────────────────
    hist_card = GlassCard(radius=14, strong_tint=True)
    h_lay = QVBoxLayout(hist_card)
    h_lay.setContentsMargins(16, 14, 16, 14)
    h_lay.setSpacing(6)
    hist_title = QPushButton("Historique")
    hist_title.setFlat(True)
    hist_title.setCursor(Qt.CursorShape.PointingHandCursor)
    hist_title.clicked.connect(lambda: window._tabs.setCurrentIndex(1))
    hist_title.setStyleSheet(
        "QPushButton { color: rgba(255,255,255,0.90); font-size:14px; font-weight:600;"
        " letter-spacing:0.3px; background:transparent; border:none;"
        " text-align:center; padding:0; }"
        "QPushButton:hover { color:#E8C96A; }"
    )
    h_lay.addWidget(hist_title)
    window._home_hist_list = QListWidget()
    window._home_hist_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    window._home_hist_list.setStyleSheet(
        "QListWidget { background:transparent; border:none; color:rgba(255,255,255,0.75);"
        " font-size:12px; }"
        "QListWidget::item { padding:5px 2px; border-bottom:1px solid rgba(255,255,255,0.06); }"
        "QListWidget::item:hover { background:rgba(201,168,76,0.10); }"
    )
    window._home_hist_list.itemDoubleClicked.connect(
        lambda: window._tabs.setCurrentIndex(1)
    )
    h_lay.addWidget(window._home_hist_list, 1)
    view_all_btn = QPushButton("Voir tout →")
    view_all_btn.setFixedHeight(28)
    view_all_btn.setStyleSheet(
        "QPushButton { background:transparent; border:none; color:rgba(201,168,76,0.65);"
        " font-size:11px; text-align:right; padding-right:2px; }"
        "QPushButton:hover { color:#E8C96A; }"
    )
    view_all_btn.clicked.connect(lambda: window._tabs.setCurrentIndex(1))
    h_lay.addWidget(view_all_btn, 0, Qt.AlignmentFlag.AlignRight)

    # Rearrange cw_lay: embed stats_bar inside clock_card, then clock + bottom section
    cw_lay.removeWidget(stats_bar)
    stats_bar.setParent(None)  # type: ignore[arg-type]
    cw_lay.removeWidget(clock_card)
    while cw_lay.count():
        item = cw_lay.takeAt(0)
        if item.widget():
            item.widget().setParent(None)  # type: ignore[arg-type]

    ck_lay.addWidget(stats_bar)
    cw_lay.addWidget(clock_card, 1)

    # ── Bottom section: mini-hist (top) + import audio (bottom) ───────────
    bottom_wrap = QWidget()
    bottom_wrap.setAutoFillBackground(False)
    bw_lay = QVBoxLayout(bottom_wrap)
    bw_lay.setContentsMargins(0, 0, 0, 0)
    bw_lay.setSpacing(10)
    bw_lay.addWidget(hist_card, 1)
    import_card = _ImportAudioCard(on_transcribe_file)
    bw_lay.addWidget(import_card, 1)

    cw_lay.addWidget(bottom_wrap, 1)

    # ── Clock timer ────────────────────────────────────────────────────────
    window._clock_timer = QTimer(window)
    window._clock_timer.timeout.connect(window._tick_clock)
    window._clock_timer.start(1000)
    window._tick_clock()

    window._refresh_home()
    return container
