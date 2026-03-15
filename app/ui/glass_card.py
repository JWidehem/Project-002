"""Shared glassmorphism card widget and background-blur cache."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QPoint, QRect
from PyQt6.QtGui import (
    QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import QWidget

from app.ui import theme

# Shared blurred background pixmap — set by MainWindow._rebuild_bg_cache,
# read by every GlassCard instance.
_bg_pixmap_cache: QPixmap | None = None


class GlassCard(QWidget):
    """
    Glassmorphism card: blurred background slice + dark warm tint + gold rim-light.
    Reads the shared _bg_pixmap_cache set by MainWindow at resize/show time.
    """

    def __init__(self, parent=None, radius: int = 12, strong_tint: bool = False) -> None:
        super().__init__(parent)
        self._radius = radius
        self._strong_tint = strong_tint

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r   = self.rect()
        rad = float(self._radius)

        # ── Clipping path ────────────────────────────────────────────────
        clip = QPainterPath()
        clip.addRoundedRect(float(r.x()), float(r.y()),
                            float(r.width()), float(r.height()), rad, rad)
        p.setClipPath(clip)

        # ── 1. Blurred background slice ──────────────────────────────────
        if _bg_pixmap_cache is not None and not _bg_pixmap_cache.isNull():
            top_left = self.mapTo(self.window(), QPoint(0, 0))
            src_rect  = QRect(top_left.x(), top_left.y(), r.width(), r.height())
            blurred   = theme.blur_pixmap_region(_bg_pixmap_cache, src_rect)
            p.drawPixmap(r, blurred)
        else:
            p.fillRect(r, QColor(10, 8, 6))

        # ── 2. Dark warm tint overlay ────────────────────────────────────
        t = theme.GLASS_TINT_STRONG if self._strong_tint else theme.GLASS_TINT
        p.fillRect(r, QColor(t[0], t[1], t[2], t[3]))

        p.setClipping(False)

        # ── 3. Gold rim-light (top edge) ─────────────────────────────────
        rim = QLinearGradient(r.width() * .1, 0, r.width() * .9, 0)
        rim.setColorAt(0.0,  QColor(201, 168, 76, 0))
        rim.setColorAt(0.35, QColor(201, 168, 76, 130))
        rim.setColorAt(0.65, QColor(201, 168, 76, 130))
        rim.setColorAt(1.0,  QColor(201, 168, 76, 0))
        p.setPen(QPen(QBrush(rim), 1.2))
        p.drawLine(int(r.width() * .10), 1, int(r.width() * .90), 1)

        # ── 4. Gold border ────────────────────────────────────────────────
        p.setPen(QPen(QColor(201, 168, 76, 200), 1.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(1, 1, -1, -1), rad, rad)
