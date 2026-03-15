from __future__ import annotations

import math

import pyperclip
from PyQt6.QtCore import Qt, QPoint, QPointF, QRect, QSize
from PyQt6.QtGui import (
    QBrush, QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from app.ui import theme

# ── Module-level bg cache (populated by main_window._rebuild_bg_cache) ─────────
_history_bg_cache: QPixmap | None = None


# ── Export icon (QPainter, gold on transparent) ───────────────────────────────

def _make_export_pixmap(size: int = 16) -> QPixmap:
    """Arrow-up-from-tray icon, gold, transparent background."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    gold = QColor(201, 168, 76, 210)
    pen = QPen(gold, max(1.0, size * 0.11))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    cx = size / 2.0
    # Shaft
    p.drawLine(QPointF(cx, size * 0.60), QPointF(cx, size * 0.14))
    # Arrowhead
    p.drawLine(QPointF(cx, size * 0.14), QPointF(cx - size * 0.22, size * 0.36))
    p.drawLine(QPointF(cx, size * 0.14), QPointF(cx + size * 0.22, size * 0.36))
    # Tray — left side
    p.drawLine(QPointF(size * 0.17, size * 0.60), QPointF(size * 0.17, size * 0.86))
    # Tray — bottom
    p.drawLine(QPointF(size * 0.17, size * 0.86), QPointF(size * 0.83, size * 0.86))
    # Tray — right side
    p.drawLine(QPointF(size * 0.83, size * 0.86), QPointF(size * 0.83, size * 0.60))
    p.end()
    return px


# ── Glassmorphism card (mirrors GlassCard in main_window.py / settings.py) ────

class _GlassCard(QWidget):
    """Blurred-background card with warm tint and gold rim."""

    def __init__(self, parent=None, radius: int = 14) -> None:
        super().__init__(parent)
        self._radius = radius

    def paintEvent(self, _event) -> None:
        global _history_bg_cache
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r   = self.rect()
        rad = float(self._radius)

        clip = QPainterPath()
        clip.addRoundedRect(
            float(r.x()), float(r.y()), float(r.width()), float(r.height()), rad, rad
        )
        p.setClipPath(clip)

        if _history_bg_cache is not None and not _history_bg_cache.isNull():
            top_left = self.mapTo(self.window(), QPoint(0, 0))
            src_rect = QRect(top_left.x(), top_left.y(), r.width(), r.height())
            blurred  = theme.blur_pixmap_region(_history_bg_cache, src_rect)
            p.drawPixmap(r, blurred)
        else:
            p.fillRect(r, QColor(10, 8, 6))

        t = theme.GLASS_TINT_STRONG
        p.fillRect(r, QColor(t[0], t[1], t[2], t[3]))

        p.setClipping(False)

        rim = QLinearGradient(r.width() * .1, 0, r.width() * .9, 0)
        rim.setColorAt(0.0,  QColor(201, 168, 76, 0))
        rim.setColorAt(0.35, QColor(201, 168, 76, 120))
        rim.setColorAt(0.65, QColor(201, 168, 76, 120))
        rim.setColorAt(1.0,  QColor(201, 168, 76, 0))
        p.setPen(QPen(QBrush(rim), 1.2))
        p.drawLine(int(r.width() * .10), 1, int(r.width() * .90), 1)

        p.setPen(QPen(QColor(201, 168, 76, 200), 1.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(1, 1, -1, -1), rad, rad)


# ── Thin gold divider ──────────────────────────────────────────────────────────

def _hline() -> QWidget:
    line = QWidget()
    line.setFixedHeight(1)
    line.setStyleSheet("background: rgba(201,168,76,0.15);")
    return line


# ── Clock / history icon (28 × 28, QPainter) ──────────────────────────────────

class _HistIcon(QWidget):
    _SIZE = 28

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(self._SIZE, self._SIZE)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    @staticmethod
    def _gold(a: int = 220) -> QColor:
        return QColor(201, 168, 76, a)

    @staticmethod
    def _white(a: int = 160) -> QColor:
        return QColor(255, 255, 255, a)

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        sz = self._SIZE
        cx, cy = sz / 2.0, sz / 2.0
        r = sz * 0.38

        # Clock face
        p.setPen(QPen(self._gold(220), sz * 0.07))
        p.setBrush(QColor(201, 168, 76, 30))
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Hour hand (~10 o'clock position)
        pen_h = QPen(self._gold(220), sz * 0.08)
        pen_h.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen_h)
        p.drawLine(
            QPointF(cx, cy),
            QPointF(cx + r * 0.50 * math.cos(math.radians(120)),
                    cy - r * 0.50 * math.sin(math.radians(120))),
        )

        # Minute hand (~2 o'clock position)
        pen_m = QPen(self._white(170), sz * 0.065)
        pen_m.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen_m)
        p.drawLine(
            QPointF(cx, cy),
            QPointF(cx + r * 0.72 * math.cos(math.radians(60)),
                    cy - r * 0.72 * math.sin(math.radians(60))),
        )

        # Centre dot
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._gold(220))
        p.drawEllipse(QPointF(cx, cy), sz * 0.06, sz * 0.06)
        p.end()


# ── Main HistoryWidget ─────────────────────────────────────────────────────────

class HistoryWidget(QWidget):
    def __init__(self, entries: list[dict], on_delete, on_export=None) -> None:
        super().__init__()
        self._on_delete = on_delete
        self._on_export = on_export
        self._all_entries: list[dict] = []
        self._filtered_entries: list[dict] = []
        self._build_ui()
        self.refresh(entries)

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(0)

        card = _GlassCard(radius=14)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer.addWidget(card, 1)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(18, 16, 18, 16)
        inner.setSpacing(12)

        # ── Header row ──────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(10)
        hdr.addWidget(_HistIcon())

        title_lbl = QLabel("HISTORIQUE DES DICTÉES")
        title_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.55); font-size:9px; font-weight:700;"
            " letter-spacing:1.8px; background:transparent;"
        )
        hdr.addWidget(title_lbl)
        hdr.addStretch()

        self._count_label = QLabel("0 entrée")
        self._count_label.setStyleSheet(
            "color:rgba(201,168,76,0.60); font-size:9px; background:transparent;"
        )
        hdr.addWidget(self._count_label)
        inner.addLayout(hdr)

        inner.addWidget(_hline())

        # ── Search bar ──────────────────────────────────────────────────
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Rechercher dans l'historique…")
        self._search_edit.setFixedHeight(32)
        self._search_edit.setStyleSheet(
            "QLineEdit { background:rgba(14,12,8,0.70);"
            " border:1px solid rgba(255,255,255,0.07);"
            " border-bottom:1px solid rgba(201,168,76,0.30);"
            " border-radius:8px; color:#F0EDE0; padding:0 12px; font-size:12px; }"
            "QLineEdit:focus { border-bottom:1px solid rgba(201,168,76,0.65);"
            " background:rgba(20,17,11,0.80); }"
        )
        self._search_edit.textChanged.connect(self._apply_filter)
        inner.addWidget(self._search_edit)

        inner.addWidget(_hline())

        # ── List widget ─────────────────────────────────────────────────
        self.list_widget = QListWidget()
        self.list_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.list_widget.setStyleSheet(
            "QListWidget { background:transparent; border:none;"
            " color:rgba(255,255,255,0.80); font-size:12px; outline:none; }"
            "QListWidget::item { padding:10px 6px;"
            " border-bottom:1px solid rgba(255,255,255,0.06); }"
            "QListWidget::item:selected { background:rgba(201,168,76,0.14);"
            " color:#F0EDE0; border-bottom:1px solid rgba(201,168,76,0.28); }"
            "QListWidget::item:hover:!selected { background:rgba(201,168,76,0.07); }"
            "QScrollBar:vertical { background:transparent; width:6px; margin:4px 0; }"
            "QScrollBar::handle:vertical { background:rgba(201,168,76,0.35);"
            " border-radius:3px; min-height:20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }"
        )
        self.list_widget.currentRowChanged.connect(self._on_row_changed)
        self.list_widget.itemDoubleClicked.connect(self._copy_selected)
        inner.addWidget(self.list_widget, 1)

        inner.addWidget(_hline())

        # ── Action row ──────────────────────────────────────────────────
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        _btn_style_export = (
            "QPushButton { background:rgba(14,12,8,0.70);"
            " border:1px solid rgba(255,255,255,0.07);"
            " border-bottom:1px solid rgba(201,168,76,0.35);"
            " color:rgba(201,168,76,0.75); border-radius:8px;"
            " padding:7px 18px; font-size:12px; }"
            "QPushButton:hover { background:rgba(201,168,76,0.12);"
            " color:rgba(201,168,76,1.0);"
            " border-bottom-color:rgba(201,168,76,0.65); }"
            "QPushButton:pressed { background:rgba(201,168,76,0.22); }"
        )
        self.export_btn = QPushButton("  Exporter")
        self.export_btn.setIcon(QIcon(_make_export_pixmap(15)))
        self.export_btn.setIconSize(QSize(15, 15))
        self.export_btn.setFixedHeight(34)
        self.export_btn.setStyleSheet(_btn_style_export)
        self.export_btn.setVisible(self._on_export is not None)
        self.export_btn.clicked.connect(self._export_all)

        self.copy_btn = QPushButton("Copier")
        self.copy_btn.setFixedHeight(34)
        self.copy_btn.setEnabled(False)
        self.copy_btn.setStyleSheet(
            "QPushButton { background:rgba(14,12,8,0.70);"
            " border:1px solid rgba(255,255,255,0.07);"
            " border-bottom:1px solid rgba(201,168,76,0.35);"
            " color:rgba(201,168,76,0.75); border-radius:8px;"
            " padding:7px 22px; font-size:12px; }"
            "QPushButton:hover { background:rgba(201,168,76,0.12);"
            " color:rgba(201,168,76,1.0);"
            " border-bottom-color:rgba(201,168,76,0.65); }"
            "QPushButton:pressed { background:rgba(201,168,76,0.22); }"
            "QPushButton:disabled { color:rgba(255,255,255,0.15);"
            " border-color:rgba(255,255,255,0.05); }"
        )
        self.copy_btn.clicked.connect(self._copy_selected)

        self.delete_btn = QPushButton("Supprimer")
        self.delete_btn.setFixedHeight(34)
        self.delete_btn.setEnabled(False)
        self.delete_btn.setStyleSheet(
            "QPushButton { background:rgba(14,12,8,0.70);"
            " border:1px solid rgba(255,255,255,0.07);"
            " border-bottom:1px solid rgba(220,80,80,0.35);"
            " color:rgba(220,80,80,0.75); border-radius:8px;"
            " padding:7px 22px; font-size:12px; }"
            "QPushButton:hover { background:rgba(220,80,80,0.12);"
            " color:rgba(220,80,80,1.0);"
            " border-bottom-color:rgba(220,80,80,0.65); }"
            "QPushButton:pressed { background:rgba(220,80,80,0.22); }"
            "QPushButton:disabled { color:rgba(255,255,255,0.15);"
            " border-color:rgba(255,255,255,0.05); }"
        )
        self.delete_btn.clicked.connect(self._delete_selected)

        action_row.addWidget(self.export_btn)
        action_row.addStretch()
        action_row.addWidget(self.copy_btn)
        action_row.addWidget(self.delete_btn)
        inner.addLayout(action_row)

    # ── Data ───────────────────────────────────────────────────────────────

    def refresh(self, entries: list[dict]) -> None:
        self._all_entries = list(entries)
        self._apply_filter(self._search_edit.text())

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        if needle:
            self._filtered_entries = [
                e for e in self._all_entries
                if needle in e.get("clean_text", "").lower()
                or needle in e.get("created_at", "").lower()
            ]
        else:
            self._filtered_entries = list(self._all_entries)
        self._populate_list()

    def _populate_list(self) -> None:
        self.list_widget.clear()
        for e in self._filtered_entries:
            dt      = e.get("created_at", "")[:16].replace("T", " ")
            text    = e.get("clean_text", "")
            dur     = e.get("duration_s")
            dur_str = f"  {dur:.0f}s" if dur is not None else ""
            preview = text[:80] + ("…" if len(text) > 80 else "")
            self.list_widget.addItem(f"  {dt}{dur_str}\n  {preview}")

        n = len(self._all_entries)
        self._count_label.setText(f"{n} entrée{'s' if n != 1 else ''}")
        self._on_row_changed(self.list_widget.currentRow())

    # ── Selection ──────────────────────────────────────────────────────────

    def _on_row_changed(self, row: int) -> None:
        enabled = 0 <= row < len(self._filtered_entries)
        self.copy_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)

    # ── Actions ────────────────────────────────────────────────────────────

    def _copy_selected(self) -> None:
        row = self.list_widget.currentRow()
        if 0 <= row < len(self._filtered_entries):
            pyperclip.copy(self._filtered_entries[row].get("clean_text", ""))

    def _delete_selected(self) -> None:
        row = self.list_widget.currentRow()
        if 0 <= row < len(self._filtered_entries):
            entry_id = self._filtered_entries[row].get("id")
            if entry_id is None:
                return
            self._on_delete(entry_id)
            self._all_entries = [
                e for e in self._all_entries if e.get("id") != entry_id
            ]
            self._apply_filter(self._search_edit.text())

    def _export_all(self) -> None:
        if self._on_export:
            self._on_export()


# ── Dialog wrapper ─────────────────────────────────────────────────────────────

class HistoryWindow(QDialog):
    """Thin dialog wrapper around HistoryWidget."""

    def __init__(self, entries: list[dict], on_delete, on_export=None) -> None:
        super().__init__()
        self.setWindowTitle("Historique — WhisperFlow")
        self.setMinimumSize(500, 400)
        self.setStyleSheet(theme.STYLESHEET)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._widget = HistoryWidget(entries, on_delete, on_export=on_export)
        layout.addWidget(self._widget)

    def refresh(self, entries: list[dict]) -> None:
        self._widget.refresh(entries)

    def __getattr__(self, name: str):
        # Delegate attribute access to inner HistoryWidget (e.g. for tests)
        widget = object.__getattribute__(self, "_widget")
        return getattr(widget, name)
