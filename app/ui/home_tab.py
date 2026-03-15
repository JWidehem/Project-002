"""Home tab builder: clock/welcome bento layout, stats pills, mini-history."""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QIcon, QLinearGradient,
    QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QPushButton,
    QVBoxLayout, QWidget,
)

from app.ui import theme
from app.ui.glass_card import GlassCard


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

def build_home_tab(window) -> QWidget:
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

    # Rearrange cw_lay: embed stats_bar inside clock_card, then clock + hist below
    cw_lay.removeWidget(stats_bar)
    stats_bar.setParent(None)  # type: ignore[arg-type]
    cw_lay.removeWidget(clock_card)
    while cw_lay.count():
        item = cw_lay.takeAt(0)
        if item.widget():
            item.widget().setParent(None)  # type: ignore[arg-type]

    ck_lay.addWidget(stats_bar)
    cw_lay.addWidget(clock_card, 1)
    cw_lay.addWidget(hist_card, 1)

    # ── Clock timer ────────────────────────────────────────────────────────
    window._clock_timer = QTimer(window)
    window._clock_timer.timeout.connect(window._tick_clock)
    window._clock_timer.start(1000)
    window._tick_clock()

    window._refresh_home()
    return container
