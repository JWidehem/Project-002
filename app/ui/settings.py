from __future__ import annotations
import math

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QCheckBox, QLineEdit, QTextEdit, QPushButton, QScrollArea,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QPoint, QRectF, QPointF
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap,
)
import sounddevice as sd
from app.ui import theme

LANGUAGES     = [("fr", "Français"), ("en", "English"), ("es", "Español")]
MODELS        = ["tiny", "base", "small", "medium", "large-v3"]
CLEANUP_LEVELS = [("none", "Aucun"), ("light", "Léger"), ("medium", "Moyen")]

# Shared blurred background reference (set externally by MainWindow)
_settings_bg_cache: QPixmap | None = None


def _fmt_hotkey(h: str) -> str:
    _MAP = {
        "<ctrl>": "Ctrl", "<shift>": "Shift", "<alt>": "Alt", "<cmd>": "⊞",
        "<space>": "Space", "<enter>": "Enter", "<backspace>": "⌫",
        "<delete>": "Del", "<esc>": "Échap", "<tab>": "Tab",
        **{f"<f{i}>": f"F{i}" for i in range(1, 13)},
    }
    if not h:
        return "(non configuré)"
    return " + ".join(
        _MAP.get(p.strip().lower(), p.strip().upper()) for p in h.split("+")
    )


# ── Glassmorphism section card (mirrors GlassCard in main_window.py) ──────────

class _GlassCard(QWidget):
    """Glassmorphism card: blurred bg slice + warm tint + gold rim."""

    def __init__(self, parent=None, radius: int = 12) -> None:
        super().__init__(parent)
        self._radius = radius

    def paintEvent(self, _event) -> None:
        global _settings_bg_cache
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r   = self.rect()
        rad = float(self._radius)

        clip = QPainterPath()
        clip.addRoundedRect(float(r.x()), float(r.y()),
                            float(r.width()), float(r.height()), rad, rad)
        p.setClipPath(clip)

        if _settings_bg_cache is not None and not _settings_bg_cache.isNull():
            from PyQt6.QtCore import QRect
            top_left = self.mapTo(self.window(), QPoint(0, 0))
            src_rect = QRect(top_left.x(), top_left.y(), r.width(), r.height())
            blurred  = theme.blur_pixmap_region(_settings_bg_cache, src_rect)
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


# ── Section header label ───────────────────────────────────────────────────────

def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "color: rgba(201,168,76,0.70); font-size:9px; font-weight:700;"
        " letter-spacing:1.8px; background:transparent;"
    )
    return lbl


def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "color: rgba(255,255,255,0.40); font-size:11px; background:transparent;"
    )
    return lbl


# ── Row builders ───────────────────────────────────────────────────────────────

def _row(label_text: str, widget: QWidget,
         hint: str = "") -> QHBoxLayout:
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(12)
    lbl = _field_label(label_text)
    lbl.setFixedWidth(160)
    row.addWidget(lbl)
    row.addWidget(widget, 1)
    if hint:
        h = QLabel(hint)
        h.setStyleSheet(
            "color:rgba(255,255,255,0.22); font-size:10px; background:transparent;"
        )
        h.setWordWrap(True)
        row.addWidget(h)
    return row


# ── Toggle switch ──────────────────────────────────────────────────────────────

class _ToggleSwitch(QWidget):
    """Minimal pill toggle switch (replaces plain QCheckBox)."""

    def __init__(self, checked: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._checked = checked
        self.setFixedSize(44, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @property
    def isChecked(self) -> bool:  # type: ignore[override]
        return self._checked

    def setChecked(self, v: bool) -> None:
        self._checked = v
        self.update()

    def mousePressEvent(self, _ev) -> None:
        self._checked = not self._checked
        self.update()

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        r = h / 2.0
        # Track
        if self._checked:
            p.setBrush(QColor(201, 168, 76, 180))
            p.setPen(QPen(QColor(201, 168, 76, 230), 1.2))
        else:
            p.setBrush(QColor(40, 32, 20, 220))
            p.setPen(QPen(QColor(255, 255, 255, 40), 1.2))
        p.drawRoundedRect(QRectF(0, 0, w, h), r, r)
        # Knob
        knob_r = h * 0.38
        knob_x = (w - h + knob_r + h * 0.12) if self._checked else (knob_r + h * 0.12)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 245, 210, 240) if self._checked else QColor(160, 140, 100, 200))
        p.drawEllipse(QPointF(knob_x, h / 2.0), knob_r, knob_r)
        p.end()


# ── Icon classes for section headers (28×28, same style as main_window) ────────

class _IconBase(QWidget):
    _SIZE = 28

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(self._SIZE, self._SIZE)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def _p(self) -> QPainter:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        return p

    @staticmethod
    def _gold(a: int = 220) -> QColor:
        return QColor(201, 168, 76, a)

    @staticmethod
    def _white(a: int = 160) -> QColor:
        return QColor(255, 255, 255, a)


class _MicIcon(_IconBase):
    def paintEvent(self, _) -> None:
        p = self._p()
        sz = self._SIZE
        cx, cy = sz / 2, sz / 2
        # Capsule body
        bw, bh = sz * 0.20, sz * 0.31
        body = QRectF(cx - bw, cy - bh, bw * 2, bh * 2)
        p.setPen(QPen(self._gold(220), sz * 0.07))
        p.setBrush(QColor(201, 168, 76, 40))
        p.drawRoundedRect(body, bw, bw)
        # Sound arc
        pen_arc = QPen(self._gold(180), sz * 0.065)
        pen_arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen_arc)
        p.setBrush(Qt.BrushStyle.NoBrush)
        arc_r = sz * 0.38
        p.drawArc(
            QRectF(cx - arc_r, cy - arc_r + sz * 0.04, arc_r * 2, arc_r * 2),
            15 * 16, 150 * 16,
        )
        # Stand line
        p.setPen(QPen(self._gold(200), sz * 0.065))
        p.drawLine(QPointF(cx, cy + sz * 0.35), QPointF(cx, cy + sz * 0.45))
        p.drawLine(QPointF(cx - sz * 0.16, cy + sz * 0.45), QPointF(cx + sz * 0.16, cy + sz * 0.45))
        p.end()


class _KeyIcon(_IconBase):
    def paintEvent(self, _) -> None:
        p = self._p()
        sz = self._SIZE
        cx, cy = sz / 2, sz / 2
        # Key ring
        r = sz * 0.18
        p.setPen(QPen(self._gold(220), sz * 0.08))
        p.setBrush(QColor(201, 168, 76, 35))
        p.drawEllipse(QPointF(cx - sz * 0.18, cy - sz * 0.04), r, r)
        # Key shaft
        p.setPen(QPen(self._gold(200), sz * 0.075))
        p.drawLine(QPointF(cx - sz * 0.02, cy - sz * 0.04),
                   QPointF(cx + sz * 0.38, cy - sz * 0.04))
        # Teeth
        for dx in (sz * 0.20, sz * 0.32):
            p.drawLine(QPointF(cx + dx, cy - sz * 0.04),
                       QPointF(cx + dx, cy + sz * 0.10))
        p.end()


class _BrainIcon(_IconBase):
    def paintEvent(self, _) -> None:
        p = self._p()
        sz = self._SIZE
        cx, cy = sz / 2, sz / 2
        # Stylized brain: two lobes
        pen = QPen(self._gold(210), sz * 0.07)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(QColor(201, 168, 76, 30))
        # Left lobe
        ll = QRectF(cx - sz * 0.42, cy - sz * 0.28, sz * 0.40, sz * 0.50)
        p.drawEllipse(ll)
        # Right lobe
        rl = QRectF(cx + sz * 0.02, cy - sz * 0.28, sz * 0.40, sz * 0.50)
        p.drawEllipse(rl)
        # Center divider
        p.setPen(QPen(self._gold(120), sz * 0.06))
        p.drawLine(QPointF(cx, cy - sz * 0.22), QPointF(cx, cy + sz * 0.20))
        # Horizontal groove lines (left + right)
        p.setPen(QPen(self._white(80), sz * 0.045))
        for dy in (-0.06, 0.06):
            p.drawLine(QPointF(cx - sz * 0.36, cy + sz * dy),
                       QPointF(cx - sz * 0.10, cy + sz * dy))
            p.drawLine(QPointF(cx + sz * 0.10, cy + sz * dy),
                       QPointF(cx + sz * 0.36, cy + sz * dy))
        p.end()


class _BrushIcon(_IconBase):
    def paintEvent(self, _) -> None:
        p = self._p()
        sz = self._SIZE
        cx, cy = sz / 2, sz / 2
        # Brush handle (angled line)
        pen = QPen(self._gold(210), sz * 0.09)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(cx + sz * 0.22, cy - sz * 0.28),
                   QPointF(cx - sz * 0.08, cy + sz * 0.10))
        # Bristles (fat rounded end)
        p.setPen(QPen(self._gold(180), sz * 0.075))
        p.setBrush(QColor(201, 168, 76, 60))
        p.drawEllipse(QPointF(cx - sz * 0.16, cy + sz * 0.22), sz * 0.18, sz * 0.14)
        # Sparkle dots (text-cleaned shine)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._white(130))
        for dx, dy, dr in [(0.20, -0.20, 0.045), (0.32, -0.06, 0.032)]:
            p.drawEllipse(QPointF(cx + sz * dx, cy + sz * dy), sz * dr, sz * dr)
        p.end()


class _GlobeIcon(_IconBase):
    def paintEvent(self, _) -> None:
        p = self._p()
        sz = self._SIZE
        cx, cy = sz / 2, sz / 2
        r = sz * 0.36
        # Globe circle
        p.setPen(QPen(self._gold(210), sz * 0.07))
        p.setBrush(QColor(201, 168, 76, 25))
        p.drawEllipse(QPointF(cx, cy), r, r)
        # Latitude lines
        p.setPen(QPen(self._white(90), sz * 0.05))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for yoff in (-sz * 0.12, sz * 0.12):
            half_w = math.sqrt(max(0.0, r * r - yoff * yoff))
            p.drawLine(QPointF(cx - half_w, cy + yoff), QPointF(cx + half_w, cy + yoff))
        # Longitude (vertical ellipse)
        p.setPen(QPen(self._gold(100), sz * 0.05))
        p.drawEllipse(QPointF(cx, cy), sz * 0.14, r)
        # Central meridian
        p.setPen(QPen(self._white(70), sz * 0.045))
        p.drawLine(QPointF(cx, cy - r), QPointF(cx, cy + r))
        p.end()


class _CogIcon(_IconBase):
    def paintEvent(self, _) -> None:
        p = self._p()
        sz = self._SIZE
        cx = cy = sz / 2.0
        n = 8
        r_out = sz * 0.39
        r_in  = sz * 0.27
        r_hole = sz * 0.10
        tooth_half = math.pi / n * 0.55
        points = []
        for i in range(n):
            a0 = 2 * math.pi * i / n
            for ar, radius in (
                (a0 - tooth_half,        r_in),
                (a0 - tooth_half * 0.70, r_out),
                (a0 + tooth_half * 0.70, r_out),
                (a0 + tooth_half,        r_in),
            ):
                points.append(QPointF(cx + radius * math.cos(ar),
                                      cy - radius * math.sin(ar)))
        gear = QPainterPath()
        gear.moveTo(points[0])
        for pt in points[1:]:
            gear.lineTo(pt)
        gear.closeSubpath()
        hole = QPainterPath()
        hole.addEllipse(QPointF(cx, cy), r_hole, r_hole)
        final = gear.subtracted(hole)
        p.setPen(QPen(self._gold(210), sz * 0.05))
        p.setBrush(QColor(255, 255, 255, 45))
        p.drawPath(final)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._gold(220))
        p.drawEllipse(QPointF(cx, cy), r_hole * 0.55, r_hole * 0.55)
        p.end()


# ── Section header with icon + title ──────────────────────────────────────────

def _section_header(icon: QWidget, title: str) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)
    row.addWidget(icon)
    lbl = QLabel(title)
    lbl.setStyleSheet(
        "color: rgba(255,255,255,0.55); font-size:9px; font-weight:700;"
        " letter-spacing:1.8px; background:transparent;"
    )
    row.addWidget(lbl)
    row.addStretch()
    return row


# ── HotkeyCapture button ───────────────────────────────────────────────────────

class HotkeyCapture(QPushButton):
    def __init__(self, hotkey: str = "", parent=None) -> None:
        super().__init__(parent)
        self._hotkey = hotkey
        self._capturing = False
        self._update_display()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.clicked.connect(self._start_capture)

    @property
    def hotkey(self) -> str:
        return self._hotkey

    def set_hotkey(self, h: str) -> None:
        self._hotkey = h
        if not self._capturing:
            self._update_display()

    def _update_display(self) -> None:
        if self._capturing:
            self.setText("Appuyez sur votre combinaison…")
            self.setStyleSheet(
                "QPushButton { background: rgba(201,168,76,0.12);"
                " border: 1px solid #C9A84C; color: #E8C96A;"
                " border-radius: 7px; padding: 7px 14px;"
                " font-size: 12px; text-align: left; }"
            )
        else:
            self.setText(_fmt_hotkey(self._hotkey))
            self.setStyleSheet(
                "QPushButton { background: rgba(14,12,8,0.82);"
                " border: 1px solid rgba(255,255,255,0.07);"
                " border-bottom: 1px solid rgba(201,168,76,0.32);"
                " color: #F0EDE0; border-radius: 7px;"
                " padding: 7px 14px; font-size: 12px; text-align: left; }"
                " QPushButton:hover { border-color: rgba(201,168,76,0.5); color: #C9A84C; }"
            )

    def _start_capture(self) -> None:
        self._capturing = True
        self._update_display()
        self.setFocus()

    def _stop_capture(self, new_hotkey: str | None) -> None:
        self._capturing = False
        if new_hotkey is not None:
            self._hotkey = new_hotkey
        self._update_display()
        self.clearFocus()

    def keyPressEvent(self, event) -> None:
        if not self._capturing:
            super().keyPressEvent(event)
            return
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._stop_capture(None)
            event.accept()
            return
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt,
                   Qt.Key.Key_Meta, Qt.Key.Key_AltGr):
            event.accept()
            return
        parts: list[str] = []
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("<ctrl>")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("<shift>")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("<alt>")
        _SPECIAL: dict = {
            Qt.Key.Key_Space: "<space>", Qt.Key.Key_Return: "<enter>",
            Qt.Key.Key_Enter: "<enter>", Qt.Key.Key_Backspace: "<backspace>",
            Qt.Key.Key_Delete: "<delete>", Qt.Key.Key_Tab: "<tab>",
            **{getattr(Qt.Key, f"Key_F{i}"): f"<f{i}>" for i in range(1, 13)},
        }
        if key in _SPECIAL:
            parts.append(_SPECIAL[key])
        else:
            ch = event.text().lower()
            if ch and ch.isprintable() and not ch.isspace():
                parts.append(ch)
            else:
                event.accept()
                return
        if parts:
            self._stop_capture("+".join(parts))
        event.accept()

    def focusOutEvent(self, event) -> None:
        if self._capturing:
            self._stop_capture(None)
        super().focusOutEvent(event)


# ── Main SettingsWidget ───────────────────────────────────────────────────────

class SettingsWidget(QWidget):
    def __init__(self, settings: dict, on_save) -> None:
        super().__init__()
        self._on_save = on_save
        self._defaults = dict(settings)   # kept for reset
        self._build_ui(settings)

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self, s: dict) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Scrollable content area ─────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        content.setAutoFillBackground(False)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(12)

        # ── 1. DICTÉE ─────────────────────────────────────────────────────
        dictee_card = _GlassCard(radius=12)
        d_lay = QVBoxLayout(dictee_card)
        d_lay.setContentsMargins(18, 14, 18, 16)
        d_lay.setSpacing(12)
        d_lay.addLayout(_section_header(_MicIcon(), "DICTÉE"))
        d_lay.addWidget(_hline())

        self.device_combo = QComboBox()
        self.device_combo.addItem("Défaut système", None)
        current_device = s.get("audio_device")
        selected_idx = 0
        try:
            for i, dev in enumerate(sd.query_devices()):
                if dev["max_input_channels"] > 0:
                    label = f"{dev['name']} ({dev['hostapi']})"
                    self.device_combo.addItem(label, i)
                    if i == current_device:
                        selected_idx = self.device_combo.count() - 1
        except Exception:
            pass
        self.device_combo.setCurrentIndex(selected_idx)
        d_lay.addLayout(_row("Microphone", self.device_combo))

        self.language_combo = QComboBox()
        for code, label in LANGUAGES:
            self.language_combo.addItem(label, code)
        lang_idx = next((i for i, (c, _) in enumerate(LANGUAGES)
                         if c == s.get("language", "fr")), 0)
        self.language_combo.setCurrentIndex(lang_idx)
        d_lay.addLayout(_row("Langue de transcription", self.language_combo))
        lay.addWidget(dictee_card)

        # ── 2. RACCOURCIS ─────────────────────────────────────────────────
        hk_card = _GlassCard(radius=12)
        hk_lay = QVBoxLayout(hk_card)
        hk_lay.setContentsMargins(18, 14, 18, 16)
        hk_lay.setSpacing(12)
        hk_lay.addLayout(_section_header(_KeyIcon(), "RACCOURCIS CLAVIER"))
        hk_lay.addWidget(_hline())

        self.hold_capture   = HotkeyCapture(s.get("hotkey_hold", ""))
        self.toggle_capture = HotkeyCapture(s.get("hotkey_toggle", ""))

        hold_row = _row("Mode Maintien", self.hold_capture,
                        hint="Maintenez la touche pour dicter")
        toggle_row = _row("Mode Toggle", self.toggle_capture,
                          hint="Appuyez une fois pour démarrer, encore pour arrêter")
        hk_lay.addLayout(hold_row)
        hk_lay.addLayout(toggle_row)

        self.conflict_label = QLabel("")
        self.conflict_label.setStyleSheet(
            "color:#E06030; font-size:11px; background:transparent;"
        )
        hk_lay.addWidget(self.conflict_label)

        hint_row = QHBoxLayout()
        hint_row.addStretch()
        hint_lbl = QLabel("Cliquez sur un raccourci, puis appuyez sur la combinaison souhaitée")
        hint_lbl.setStyleSheet(
            "color:rgba(255,255,255,0.20); font-size:10px; background:transparent;"
        )
        hint_row.addWidget(hint_lbl)
        hk_lay.addLayout(hint_row)
        lay.addWidget(hk_card)

        # ── 3. MODÈLE ASR ─────────────────────────────────────────────────
        mdl_card = _GlassCard(radius=12)
        mdl_lay = QVBoxLayout(mdl_card)
        mdl_lay.setContentsMargins(18, 14, 18, 16)
        mdl_lay.setSpacing(12)
        mdl_lay.addLayout(_section_header(_BrainIcon(), "MODÈLE ASR"))
        mdl_lay.addWidget(_hline())

        self.model_combo = QComboBox()
        _MODEL_LABELS = {
            "tiny":     "tiny — ultra-rapide · basse qualité",
            "base":     "base — rapide · qualité correcte",
            "small":    "small — équilibré · recommandé",
            "medium":   "medium — précis · plus lent",
            "large-v3": "large-v3 — meilleure qualité · lent",
        }
        for m in MODELS:
            self.model_combo.addItem(_MODEL_LABELS.get(m, m), m)
        midx = MODELS.index(s.get("model", "small")) if s.get("model", "small") in MODELS else 2
        self.model_combo.setCurrentIndex(midx)
        mdl_lay.addLayout(_row("Modèle Whisper", self.model_combo))

        _COMPUTE_OPTIONS = [
            ("cpu",  "CPU — stable, aucun prérequis"),
            ("cuda", "GPU CUDA — rapide, nécessite NVIDIA"),
            ("auto", "Auto — GPU si disponible, sinon CPU"),
        ]
        self.compute_combo = QComboBox()
        for code, label in _COMPUTE_OPTIONS:
            self.compute_combo.addItem(label, code)
        cur_dev = s.get("compute_device", "cpu")
        cidx = next((i for i, (c, _) in enumerate(_COMPUTE_OPTIONS) if c == cur_dev), 0)
        self.compute_combo.setCurrentIndex(cidx)
        mdl_lay.addLayout(_row("Accélération", self.compute_combo,
                               hint="Redémarrez l'app après changement"))

        # Preload toggle
        preload_row = QHBoxLayout()
        preload_row.setContentsMargins(0, 0, 0, 0)
        preload_row.setSpacing(12)
        preload_lbl = _field_label("Charger au démarrage")
        preload_lbl.setFixedWidth(160)
        self.preload_toggle = _ToggleSwitch(checked=s.get("preload_model", False))
        preload_sub = QLabel("Le modèle reste en mémoire, prêt à l'instant")
        preload_sub.setStyleSheet(
            "color:rgba(255,255,255,0.28); font-size:10px; background:transparent;"
        )
        preload_row.addWidget(preload_lbl)
        preload_row.addWidget(self.preload_toggle)
        preload_row.addWidget(preload_sub, 1)
        mdl_lay.addLayout(preload_row)
        lay.addWidget(mdl_card)

        # ── 4. NETTOYAGE TEXTE ────────────────────────────────────────────
        cl_card = _GlassCard(radius=12)
        cl_lay = QVBoxLayout(cl_card)
        cl_lay.setContentsMargins(18, 14, 18, 16)
        cl_lay.setSpacing(12)
        cl_lay.addLayout(_section_header(_BrushIcon(), "NETTOYAGE TEXTE"))
        cl_lay.addWidget(_hline())

        self.cleanup_combo = QComboBox()
        _CL_LABELS = {
            "none":   "Aucun — texte brut Whisper",
            "light":  "Léger — mots parasites supprimés",
            "medium": "Moyen — léger + doublons + ponctuation",
        }
        for code, label in CLEANUP_LEVELS:
            self.cleanup_combo.addItem(_CL_LABELS.get(code, label), code)
        cl_idx = next((i for i, (c, _) in enumerate(CLEANUP_LEVELS)
                       if c == s.get("cleanup_level", "light")), 1)
        self.cleanup_combo.setCurrentIndex(cl_idx)
        cl_lay.addLayout(_row("Niveau", self.cleanup_combo))

        self.fillers_edit = QLineEdit(", ".join(s.get("filler_words", [])))
        self.fillers_edit.setPlaceholderText("euh, hum, ben, voilà…")
        cl_lay.addLayout(_row("Mots parasites", self.fillers_edit,
                              hint="séparés par des virgules"))

        # Glossary
        gl_lbl = _field_label("Glossaire Whisper")
        cl_lay.addWidget(gl_lbl)
        self.glossary_edit = QTextEdit()
        self.glossary_edit.setPlainText("\n".join(s.get("glossary", [])))
        self.glossary_edit.setFixedHeight(72)
        self.glossary_edit.setPlaceholderText(
            "Un mot par ligne — termes spécifiques, noms propres, sigles…"
        )
        cl_lay.addWidget(self.glossary_edit)
        lay.addWidget(cl_card)

        # ── 5. GÉNÉRAL ────────────────────────────────────────────────────
        gen_card = _GlassCard(radius=12)
        gen_lay = QVBoxLayout(gen_card)
        gen_lay.setContentsMargins(18, 14, 18, 16)
        gen_lay.setSpacing(12)
        gen_lay.addLayout(_section_header(_CogIcon(), "GÉNÉRAL"))
        gen_lay.addWidget(_hline())

        as_row = QHBoxLayout()
        as_row.setContentsMargins(0, 0, 0, 0)
        as_row.setSpacing(12)
        as_lbl = _field_label("Lancer au démarrage Windows")
        as_lbl.setFixedWidth(200)
        self.autostart_toggle = _ToggleSwitch(checked=s.get("autostart", False))
        as_sub = QLabel("WhisperFlow démarre avec la session Windows")
        as_sub.setStyleSheet(
            "color:rgba(255,255,255,0.28); font-size:10px; background:transparent;"
        )
        as_row.addWidget(as_lbl)
        as_row.addWidget(self.autostart_toggle)
        as_row.addWidget(as_sub, 1)
        gen_lay.addLayout(as_row)
        lay.addWidget(gen_card)

        lay.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        # ── Footer ────────────────────────────────────────────────────────
        footer = QWidget()
        footer.setAutoFillBackground(False)
        footer.setStyleSheet(
            "background: rgba(10,8,6,0.80);"
            " border-top: 1px solid rgba(201,168,76,0.18);"
        )
        f_lay = QHBoxLayout(footer)
        f_lay.setContentsMargins(18, 10, 18, 10)
        f_lay.setSpacing(10)

        self.reset_btn = QPushButton("Réinitialiser")
        self.reset_btn.setFixedHeight(34)
        self.reset_btn.setStyleSheet(
            "QPushButton { background: transparent; border:1px solid rgba(255,255,255,0.10);"
            " color: rgba(255,255,255,0.35); border-radius:7px; font-size:12px; padding:0 16px; }"
            "QPushButton:hover { border-color: rgba(255,255,255,0.28); color: rgba(255,255,255,0.65); }"
        )
        self.reset_btn.clicked.connect(self._reset)
        f_lay.addWidget(self.reset_btn)
        f_lay.addStretch()

        self.save_btn = QPushButton("  Enregistrer  ")
        self.save_btn.setFixedHeight(34)
        self.save_btn.setStyleSheet(
            "QPushButton { background: rgba(201,168,76,0.18);"
            " border:1px solid rgba(201,168,76,0.55); color:#E8C96A;"
            " border-radius:7px; font-size:13px; font-weight:600; padding:0 22px; }"
            "QPushButton:hover { background:rgba(201,168,76,0.30);"
            " border-color:#C9A84C; color:#FFF5D0; }"
            "QPushButton:pressed { background:rgba(201,168,76,0.45); }"
        )
        self.save_btn.clicked.connect(self._save)
        f_lay.addWidget(self.save_btn)

        root.addWidget(footer)

    # ── Actions ────────────────────────────────────────────────────────────

    def _save(self) -> None:
        data = {
            "autostart":      self.autostart_toggle.isChecked,
            "language":       self.language_combo.currentData(),
            "hotkey_hold":    self.hold_capture.hotkey,
            "hotkey_toggle":  self.toggle_capture.hotkey,
            "model":          self.model_combo.currentData(),
            "preload_model":  self.preload_toggle.isChecked,
            "cleanup_level":  self.cleanup_combo.currentData(),
            "filler_words":   [w.strip() for w in self.fillers_edit.text().split(",")
                               if w.strip()],
            "glossary":       [w.strip() for w in self.glossary_edit.toPlainText().splitlines()
                               if w.strip()],
            "audio_device":   self.device_combo.currentData(),
            "compute_device": self.compute_combo.currentData(),
        }
        self._on_save(data)

    def _reset(self) -> None:
        self.sync_from(self._defaults)

    def show_conflict(self, message: str) -> None:
        self.conflict_label.setText(message)

    def sync_from(self, s: dict) -> None:
        self.autostart_toggle.setChecked(s.get("autostart", False))
        lang_idx = next((i for i, (c, _) in enumerate(LANGUAGES)
                         if c == s.get("language", "fr")), 0)
        self.language_combo.setCurrentIndex(lang_idx)
        self.hold_capture.set_hotkey(s.get("hotkey_hold", ""))
        self.toggle_capture.set_hotkey(s.get("hotkey_toggle", ""))
        model = s.get("model", "small")
        self.model_combo.setCurrentIndex(MODELS.index(model) if model in MODELS else 2)
        self.preload_toggle.setChecked(s.get("preload_model", False))
        cl_idx = next((i for i, (c, _) in enumerate(CLEANUP_LEVELS)
                       if c == s.get("cleanup_level", "light")), 1)
        self.cleanup_combo.setCurrentIndex(cl_idx)
        self.fillers_edit.setText(", ".join(s.get("filler_words", [])))
        self.glossary_edit.setPlainText("\n".join(s.get("glossary", [])))
        cur_dev = s.get("audio_device")
        for i in range(self.device_combo.count()):
            if self.device_combo.itemData(i) == cur_dev:
                self.device_combo.setCurrentIndex(i)
                break
        _CC = ["cpu", "cuda", "auto"]
        cd = s.get("compute_device", "cpu")
        self.compute_combo.setCurrentIndex(_CC.index(cd) if cd in _CC else 0)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _hline() -> QWidget:
    line = QWidget()
    line.setFixedHeight(1)
    line.setAutoFillBackground(False)
    line.setStyleSheet("background: rgba(201,168,76,0.14); border:none;")
    return line


class SettingsWindow(QDialog):
    """Thin dialog wrapper around SettingsWidget."""

    def __init__(self, settings: dict, on_save) -> None:
        super().__init__()
        self.setWindowTitle("Réglages — WhisperFlow")
        self.setMinimumWidth(440)
        self.setStyleSheet(theme.STYLESHEET)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        def _save_and_close(data: dict) -> None:
            on_save(data)
            self.accept()

        self._widget = SettingsWidget(settings, _save_and_close)
        layout.addWidget(self._widget)

    def show_conflict(self, message: str) -> None:
        self._widget.show_conflict(message)

    def __getattr__(self, name: str):
        # Delegate attribute access to inner SettingsWidget (e.g. for tests)
        widget = object.__getattribute__(self, "_widget")
        return getattr(widget, name)
