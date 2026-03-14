from __future__ import annotations
import logging
import math
import os
import platform
import sys
import psutil
from pathlib import Path
from PyQt6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QGuiApplication, QIcon, QLinearGradient,
    QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QPushButton, QScrollArea, QSizeGrip,
    QTabWidget, QVBoxLayout, QWidget,
)
from app.ui import theme
from app.ui.history import HistoryWidget
from app.ui.settings import SettingsWidget

_ASSETS      = Path(__file__).parent.parent.parent / "assets"
_LOGO        = _ASSETS / "logo00.png"
_USE_ACRYLIC = False
_C_BG        = QColor(10, 8, 6, 235)
_C_BORDER    = QColor(201, 168, 76, 200)

# Shared blurred background pixmap — set by MainWindow, read by GlassCard
_bg_pixmap_cache: QPixmap | None = None


def _hw_detect() -> dict:
    """Detect CPU friendly name, RAM, GPU name + CUDA. Returns a profile dict."""
    import subprocess

    # ── CPU friendly name (Windows registry › fallback platform) ───────────────
    cpu_name = ""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
        )
        cpu_name = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        winreg.CloseKey(key)
        for noise in ("(R)", "(TM)", "  "):
            cpu_name = cpu_name.replace(noise, " ").strip()
    except Exception:
        pass
    if not cpu_name:
        cpu_name = (platform.processor() or platform.machine() or "CPU").split("@")[0].strip()
    if len(cpu_name) > 34:
        cpu_name = cpu_name[:32] + "…"

    cpu_cores = psutil.cpu_count(logical=False) or psutil.cpu_count() or 0
    ram_gb    = psutil.virtual_memory().total / 1024 ** 3

    # ── GPU name (wmic, no DLL risk) ──────────────────────────────────────
    gpu_name = "—"
    try:
        r = subprocess.run(
            ["wmic", "path", "win32_videocontroller", "get", "name", "/format:value"],
            capture_output=True, text=True, timeout=5,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        names = [
            l.split("=", 1)[1].strip()
            for l in r.stdout.splitlines()
            if l.startswith("Name=") and l.split("=", 1)[1].strip()
        ]
        if names:
            n = names[0]
            gpu_name = n[:34] + "…" if len(n) > 36 else n
    except Exception:
        pass

    # ── CUDA count (isolated subprocess to avoid DLL crash) ─────────────────
    cuda_count = 0
    try:
        r = subprocess.run(
            [sys.executable, "-c",
             "import ctranslate2; print(ctranslate2.get_cuda_device_count())"],
            capture_output=True, text=True, timeout=6,
        )
        if r.returncode == 0:
            cuda_count = int(r.stdout.strip())
    except Exception:
        pass

    rec_model, rec_device, rec_reason = _hw_recommend(ram_gb, cuda_count)
    return {
        "cpu_name":   cpu_name,
        "cpu_cores":  cpu_cores,
        "ram_gb":     round(ram_gb, 1),
        "gpu_name":   gpu_name,
        "cuda_count": cuda_count,
        "rec_model":  rec_model,
        "rec_device": rec_device,
        "rec_reason": rec_reason,
    }


def _hw_recommend(ram_gb: float, cuda_count: int) -> tuple[str, str, str]:
    if cuda_count > 0:
        if ram_gb >= 16:
            return "large-v3", "GPU", "GPU disponible · haute performance"
        return "medium", "GPU", "GPU disponible · transcription accélérée"
    if ram_gb >= 16:
        return "medium", "CPU", "Bonne configuration · bon équilibre"
    if ram_gb >= 8:
        return "small", "CPU", "Configuration standard · recommandé"
    if ram_gb >= 4:
        return "base", "CPU", "RAM modérée · modèle léger conseillé"
    return "tiny", "CPU", "RAM limitée · modèle minimal"


# ── GPU live monitoring via pynvml (nvidia-ml-py) ────────────────────────────
_nvml_handle = None  # None = untried, False = unavailable, otherwise device handle


def _get_nvml_handle():
    """Lazy-init pynvml; returns GPU-0 device handle, or None if unavailable."""
    global _nvml_handle
    if _nvml_handle is False:
        return None
    if _nvml_handle is not None:
        return _nvml_handle
    try:
        import pynvml  # type: ignore[import]
        pynvml.nvmlInit()
        _nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    except Exception:
        _nvml_handle = False
    return _nvml_handle if _nvml_handle is not False else None


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
        global _bg_pixmap_cache
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
            # Map this widget's top-left to the top-level window coordinates
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


def _fmt_k(n: int) -> str:
    """Format integer with K/M suffix for large numbers."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _fmt_hotkey(h: str) -> str:
    """Convert pynput hotkey string to human-readable display."""
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


class _HoverTip(QWidget):
    """Singleton glassmorphism hint popup shown when hovering a stat tile."""

    _instance: "_HoverTip | None" = None

    @classmethod
    def instance(cls) -> "_HoverTip":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedWidth(220)
        self.setStyleSheet(
            "background: rgb(22, 17, 12);"
            " border: 1px solid rgba(201,168,76,0.55);"
            " border-radius: 10px;"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 11, 14, 11)
        self._lbl = QLabel()
        self._lbl.setWordWrap(True)
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._lbl.setStyleSheet(
            "color: rgb(235,228,210); font-size:11px;"
            " background: transparent; border: none;"
        )
        lay.addWidget(self._lbl)

    def paintEvent(self, event) -> None:
        pass  # background handled by stylesheet

    def show_for(self, widget: QWidget, text: str) -> None:
        self._lbl.setText(text)
        self.adjustSize()
        pos = widget.mapToGlobal(QPoint(0, 0))
        x = pos.x() + (widget.width() - self.width()) // 2
        y = pos.y() - self.height() - 8
        screen = QGuiApplication.primaryScreen().availableGeometry()
        x = max(screen.left() + 4, min(x, screen.right() - self.width() - 4))
        if y < screen.top() + 4:
            y = pos.y() + widget.height() + 8
        self.move(x, y)
        self.show()

    def show_for_point(self, global_pt: QPoint, text: str) -> None:
        self._lbl.setText(text)
        self.adjustSize()
        x = global_pt.x() - self.width() // 2
        y = global_pt.y() - self.height() - 8
        screen = QGuiApplication.primaryScreen().availableGeometry()
        x = max(screen.left() + 4, min(x, screen.right() - self.width() - 4))
        if y < screen.top() + 4:
            y = global_pt.y() + 20
        self.move(x, y)
        self.show()


class _HintIcon(QWidget):
    """Wraps a tile icon and shows a hint popup on hover."""

    def __init__(self, icon: QWidget, hint: str) -> None:
        super().__init__()
        self._hint = hint
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        icon.setParent(self)
        lay.addWidget(icon, 0, Qt.AlignmentFlag.AlignCenter)

    def enterEvent(self, event) -> None:
        _HoverTip.instance().show_for(self, self._hint)

    def leaveEvent(self, event) -> None:
        _HoverTip.instance().hide()


class _StatTile(GlassCard):
    """Compact stat tile: painted-icon or emoji / big value / small label + optional ? hint badge."""

    def __init__(self, icon, value: str = "—", label: str = "", hint: str = "") -> None:
        super().__init__(radius=10)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 14, 10, 14)
        lay.setSpacing(4)
        if isinstance(icon, QWidget):
            if hint:
                wrapper = _HintIcon(icon, hint)
                lay.addWidget(wrapper, 0, Qt.AlignmentFlag.AlignCenter)
            else:
                icon.setParent(self)
                lay.addWidget(icon, 0, Qt.AlignmentFlag.AlignCenter)
        else:
            ic = QLabel(icon)
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ic.setStyleSheet("font-size:18px; background: transparent;")
            lay.addWidget(ic)
        self._val = QLabel(value)
        self._val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._val.setStyleSheet(
            "color:#E8C96A; font-size:22px; font-weight:700; background: transparent;"
        )
        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            "color:rgba(255,255,255,0.45); font-size:9px; letter-spacing:1.3px; background: transparent;"
        )
        lay.addWidget(self._val)
        lay.addWidget(lbl)

    def set_value(self, v: str) -> None:
        self._val.setText(v)


class _NavTile(GlassCard):
    """Square clickable navigation tile for bottom row."""

    nav_clicked = pyqtSignal()

    def __init__(self, icon: str, title: str, subtitle: str) -> None:
        super().__init__(radius=14)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(130)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 16, 12, 16)
        lay.setSpacing(6)
        
        ic = QLabel(icon)
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic.setStyleSheet("font-size:32px; background: transparent;")
        
        t = QLabel(title)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setStyleSheet(
            "color:#E8C96A; font-size:14px; font-weight:600; background: transparent;"
        )
        t.setWordWrap(True)
        
        s = QLabel(subtitle)
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s.setStyleSheet("color:#8A6A28; font-size:11px; background: transparent;")
        s.setWordWrap(True)
        
        lay.addWidget(ic)
        lay.addSpacing(4)
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addStretch()

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            self.nav_clicked.emit()
        super().mousePressEvent(ev)


# ── Tile icons (28×28 QPainter widgets) ───────────────────────────────────

class _TileIcon(QWidget):
    """Base class for all QPainter tile icons (28x28)."""
    _SIZE = 28

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(self._SIZE, self._SIZE)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def _painter(self) -> QPainter:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        return p

    @staticmethod
    def _gold(alpha: int = 220) -> QColor:
        return QColor(201, 168, 76, alpha)

    @staticmethod
    def _white(alpha: int = 180) -> QColor:
        return QColor(255, 255, 255, alpha)


class _CpuAppIcon(_TileIcon):
    """Mini CPU chip with a small inward arrow (= app process)."""
    def paintEvent(self, _) -> None:
        p = self._painter()
        sz = self._SIZE
        cx, cy = sz / 2, sz / 2
        bw = sz * 0.44   # chip body half-width
        # Chip body
        body = QRectF(cx - bw, cy - bw, bw * 2, bw * 2)
        p.setPen(QPen(self._gold(210), sz * 0.07))
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawRoundedRect(body, sz * 0.08, sz * 0.08)
        # Inner core
        core = body.adjusted(sz * 0.12, sz * 0.12, -sz * 0.12, -sz * 0.12)
        p.setPen(QPen(self._gold(160), sz * 0.055))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(core)
        # 3 pins each side
        for i in range(3):
            t = (i + 1) / 4
            y = cy - bw + bw * 2 * t
            p.setPen(QPen(self._white(160), sz * 0.055))
            p.drawLine(QPointF(cx - bw - sz * 0.17, y), QPointF(cx - bw, y))
            p.drawLine(QPointF(cx + bw, y), QPointF(cx + bw + sz * 0.17, y))
        # Downward arrow (= WhisperFlow pulling CPU)
        p.setPen(QPen(self._gold(240), sz * 0.07))
        arr_x, arr_y1, arr_y2 = cx, cy - sz * 0.07, cy + sz * 0.07
        p.drawLine(QPointF(arr_x, arr_y1), QPointF(arr_x, arr_y2))
        p.drawLine(QPointF(arr_x - sz * 0.1, arr_y2 - sz * 0.08), QPointF(arr_x, arr_y2))
        p.drawLine(QPointF(arr_x + sz * 0.1, arr_y2 - sz * 0.08), QPointF(arr_x, arr_y2))
        p.end()


class _CpuSysIcon(_TileIcon):
    """CPU chip with activity wave = system-wide CPU."""
    def paintEvent(self, _) -> None:
        p = self._painter()
        sz = self._SIZE
        cx, cy = sz / 2, sz / 2
        bw = sz * 0.38
        body = QRectF(cx - bw, cy - bw * 1.1, bw * 2, bw * 2)
        p.setPen(QPen(self._gold(210), sz * 0.07))
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawRoundedRect(body, sz * 0.08, sz * 0.08)
        p.setPen(QPen(self._gold(150), sz * 0.055))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(body.adjusted(sz * 0.11, sz * 0.11, -sz * 0.11, -sz * 0.11))
        for i in range(3):
            t = (i + 1) / 4
            y = body.top() + body.height() * t
            p.setPen(QPen(self._white(155), sz * 0.055))
            p.drawLine(QPointF(cx - bw - sz * 0.16, y), QPointF(cx - bw, y))
            p.drawLine(QPointF(cx + bw, y), QPointF(cx + bw + sz * 0.16, y))
        # Activity wave along the bottom
        wave_y = cy + bw * 0.85
        pts = [
            QPointF(cx - sz * 0.30, wave_y),
            QPointF(cx - sz * 0.14, wave_y - sz * 0.14),
            QPointF(cx,             wave_y),
            QPointF(cx + sz * 0.14, wave_y + sz * 0.14),
            QPointF(cx + sz * 0.30, wave_y),
        ]
        pen_w = QPen(self._white(200), sz * 0.065)
        pen_w.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen_w.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen_w)
        for i in range(len(pts) - 1):
            p.drawLine(pts[i], pts[i + 1])
        p.end()


class _RamAppIcon(_TileIcon):
    """RAM stick with a small app-fill bar."""
    def paintEvent(self, _) -> None:
        p = self._painter()
        sz = self._SIZE
        cx, cy = sz / 2, sz / 2
        # Stick body
        sw, sh = sz * 0.62, sz * 0.28
        stick = QRectF(cx - sw / 2, cy - sh / 2 - sz * 0.04, sw, sh)
        p.setPen(QPen(self._gold(210), sz * 0.065))
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawRoundedRect(stick, sz * 0.055, sz * 0.055)
        # Chip bumps on stick
        p.setPen(QPen(self._gold(160), sz * 0.05))
        for xf in (-0.16, 0.0, 0.16):
            cr = QRectF(cx + sz * xf - sz * 0.055, stick.top() + sz * 0.04, sz * 0.11, sh - sz * 0.08)
            p.setBrush(QColor(201, 168, 76, 40))
            p.drawRect(cr)
        # Pins at bottom of stick
        p.setPen(QPen(self._white(150), sz * 0.05))
        for xf in (-0.20, -0.08, 0.08, 0.20):
            px = cx + sz * xf
            p.drawLine(QPointF(px, stick.bottom()), QPointF(px, stick.bottom() + sz * 0.14))
        # Small fill bar below = app usage
        bar_w, bar_h = sz * 0.44, sz * 0.10
        bar = QRectF(cx - bar_w / 2, stick.bottom() + sz * 0.20, bar_w, bar_h)
        p.setPen(QPen(self._white(80), sz * 0.04))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(bar, 2, 2)
        fill = QRectF(bar.left(), bar.top(), bar_w * 0.42, bar_h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._gold(200))
        p.drawRoundedRect(fill, 2, 2)
        p.end()


class _RamSysIcon(_TileIcon):
    """Two RAM sticks stacked = system RAM."""
    def paintEvent(self, _) -> None:
        p = self._painter()
        sz = self._SIZE
        cx = sz / 2
        sw, sh = sz * 0.58, sz * 0.22
        for row, yc in enumerate([sz * 0.30, sz * 0.62]):
            stick = QRectF(cx - sw / 2, yc - sh / 2, sw, sh)
            p.setPen(QPen(self._gold(200 - row * 45), sz * 0.065))
            p.setBrush(QColor(255, 255, 255, 20 - row * 6))
            p.drawRoundedRect(stick, sz * 0.05, sz * 0.05)
            for xf in (-0.12, 0.06):
                cr = QRectF(cx + sz * xf - sz * 0.05, stick.top() + sz * 0.035, sz * 0.10, sh - sz * 0.07)
                p.setBrush(QColor(201, 168, 76, 30 + row * 5))
                p.setPen(QPen(self._gold(130 - row * 30), sz * 0.04))
                p.drawRect(cr)
        p.end()


class _GpuAppIcon(_TileIcon):
    """GPU chip (wider) with downward arrow = app GPU use."""
    def paintEvent(self, _) -> None:
        p = self._painter()
        sz = self._SIZE
        cx, cy = sz / 2, sz / 2
        bw, bh = sz * 0.44, sz * 0.32
        body = QRectF(cx - bw, cy - bh - sz * 0.02, bw * 2, bh * 2)
        p.setPen(QPen(self._gold(210), sz * 0.07))
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawRoundedRect(body, sz * 0.09, sz * 0.09)
        # Fan blades (2 circles)
        for dx in (-sz * 0.13, sz * 0.13):
            p.setPen(QPen(self._white(140), sz * 0.055))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx + dx, body.center().y()), sz * 0.10, sz * 0.10)
        # Bottom pin row
        p.setPen(QPen(self._white(160), sz * 0.06))
        for xf in (-0.25, -0.10, 0.10, 0.25):
            px = cx + sz * xf
            p.drawLine(QPointF(px, body.bottom()), QPointF(px, body.bottom() + sz * 0.15))
        # Downward arrow
        p.setPen(QPen(self._gold(240), sz * 0.075))
        arr_y2 = cy - sz * 0.04
        arr_y1 = arr_y2 - sz * 0.12
        p.drawLine(QPointF(cx, arr_y1), QPointF(cx, arr_y2))
        p.drawLine(QPointF(cx - sz * 0.09, arr_y2 - sz * 0.07), QPointF(cx, arr_y2))
        p.drawLine(QPointF(cx + sz * 0.09, arr_y2 - sz * 0.07), QPointF(cx, arr_y2))
        p.end()


class _GpuSysIcon(_TileIcon):
    """GPU chip with activity bars = system-wide GPU."""
    def paintEvent(self, _) -> None:
        p = self._painter()
        sz = self._SIZE
        cx, cy = sz / 2, sz / 2
        bw, bh = sz * 0.44, sz * 0.29
        body = QRectF(cx - bw, cy - bh - sz * 0.04, bw * 2, bh * 2)
        p.setPen(QPen(self._gold(210), sz * 0.07))
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawRoundedRect(body, sz * 0.09, sz * 0.09)
        for dx in (-sz * 0.13, sz * 0.13):
            p.setPen(QPen(self._white(130), sz * 0.055))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx + dx, body.center().y()), sz * 0.10, sz * 0.10)
        p.setPen(QPen(self._white(150), sz * 0.06))
        for xf in (-0.25, -0.10, 0.10, 0.25):
            px = cx + sz * xf
            p.drawLine(QPointF(px, body.bottom()), QPointF(px, body.bottom() + sz * 0.13))
        # Bar chart below = utilisation
        heights = [0.22, 0.38, 0.28, 0.45]
        bar_w = sz * 0.085
        base_y = body.bottom() + sz * 0.32
        for i, h in enumerate(heights):
            bx = cx - sz * 0.19 + i * sz * 0.13
            bh2 = sz * h
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._gold(160 + i * 18))
            p.drawRect(QRectF(bx, base_y - bh2, bar_w, bh2))
        p.end()


class _VramAppIcon(_TileIcon):
    """Lightning bolt inside a small frame = app VRAM."""
    def paintEvent(self, _) -> None:
        p = self._painter()
        sz = self._SIZE
        cx, cy = sz / 2, sz / 2
        # Outer frame
        fw = sz * 0.38
        frame = QRectF(cx - fw, cy - fw, fw * 2, fw * 2)
        p.setPen(QPen(self._gold(180), sz * 0.065))
        p.setBrush(QColor(201, 168, 76, 18))
        p.drawRoundedRect(frame, sz * 0.08, sz * 0.08)
        # Lightning bolt
        bolt = QPainterPath()
        bolt.moveTo(cx + sz * 0.06, cy - sz * 0.26)
        bolt.lineTo(cx - sz * 0.10, cy + sz * 0.02)
        bolt.lineTo(cx + sz * 0.03, cy + sz * 0.02)
        bolt.lineTo(cx - sz * 0.06, cy + sz * 0.26)
        bolt.lineTo(cx + sz * 0.12, cy - sz * 0.04)
        bolt.lineTo(cx - sz * 0.01, cy - sz * 0.04)
        bolt.closeSubpath()
        p.setPen(QPen(self._gold(240), sz * 0.03))
        p.setBrush(self._gold(220))
        p.drawPath(bolt)
        p.end()


class _VramSysIcon(_TileIcon):
    """Full lightning bolt + radiating lines = system VRAM."""
    def paintEvent(self, _) -> None:
        p = self._painter()
        sz = self._SIZE
        cx, cy = sz / 2, sz / 2
        # Lightning bolt
        bolt = QPainterPath()
        bolt.moveTo(cx + sz * 0.08, cy - sz * 0.30)
        bolt.lineTo(cx - sz * 0.12, cy + sz * 0.02)
        bolt.lineTo(cx + sz * 0.04, cy + sz * 0.02)
        bolt.lineTo(cx - sz * 0.08, cy + sz * 0.30)
        bolt.lineTo(cx + sz * 0.14, cy - sz * 0.04)
        bolt.lineTo(cx + sz * 0.01, cy - sz * 0.04)
        bolt.closeSubpath()
        p.setPen(QPen(self._gold(230), sz * 0.04))
        p.setBrush(self._gold(210))
        p.drawPath(bolt)
        # Radiating lines
        pen_r = QPen(self._white(120), sz * 0.055)
        pen_r.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen_r)
        for angle_deg, r0, r1 in [
            (-60,  sz * 0.36, sz * 0.46),
            (60,   sz * 0.36, sz * 0.46),
            (180,  sz * 0.36, sz * 0.46),
        ]:
            a = math.radians(angle_deg)
            p.drawLine(
                QPointF(cx + r0 * math.cos(a), cy - r0 * math.sin(a)),
                QPointF(cx + r1 * math.cos(a), cy - r1 * math.sin(a)),
            )
        p.end()


class _GaugeIcon(QWidget):
    """Painted speedometer gauge – used as icon in the Performances nav card."""

    def __init__(self, size: int = 52, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _) -> None:  # noqa: N802
        sz = self.width()
        cx = cy = sz / 2.0
        r  = sz * 0.37        # arc radius
        lw = sz * 0.065       # arc/line weight

        pnt = QPainter(self)
        pnt.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Arc: start 225° Qt-CCW from East, sweep -270° (CW) → ∩ shape open at bottom
        arc_rect  = QRectF(cx - r, cy - r, r * 2, r * 2)
        start_qt  = 225 * 16
        span_full = -270 * 16

        # ── Track (translucent white) ───────────────────────────────────────
        pen_track = QPen(QColor(255, 255, 255, 55), lw)
        pen_track.setCapStyle(Qt.PenCapStyle.RoundCap)
        pnt.setPen(pen_track)
        pnt.drawArc(arc_rect, start_qt, span_full)

        # ── Active fill (gold, 65 %) ────────────────────────────────────────
        pen_fill = QPen(QColor(201, 168, 76, 220), lw)
        pen_fill.setCapStyle(Qt.PenCapStyle.RoundCap)
        pnt.setPen(pen_fill)
        pnt.drawArc(arc_rect, start_qt, int(span_full * 0.65))

        # ── Needle ─────────────────────────────────────────────────────────
        needle_deg = 225.0 - 0.65 * 270.0          # ≈ 49.5° (≈ 1-2 h)
        needle_rad = math.radians(needle_deg)
        tip_x  = cx + r * 0.72 * math.cos(needle_rad)
        tip_y  = cy - r * 0.72 * math.sin(needle_rad)
        tail_x = cx + r * 0.20 * math.cos(needle_rad + math.pi)
        tail_y = cy - r * 0.20 * math.sin(needle_rad + math.pi)

        pen_needle = QPen(QColor(255, 245, 210, 245), lw * 0.55)
        pen_needle.setCapStyle(Qt.PenCapStyle.RoundCap)
        pnt.setPen(pen_needle)
        pnt.drawLine(QPointF(tail_x, tail_y), QPointF(tip_x, tip_y))

        # ── Center hub (gold dot) ───────────────────────────────────────────
        pnt.setPen(Qt.PenStyle.NoPen)
        pnt.setBrush(QColor(201, 168, 76, 230))
        pnt.drawEllipse(QPointF(cx, cy), lw * 0.9, lw * 0.9)

        # ── Tick marks (start / mid / end of arc) ──────────────────────────
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
        r_out  = sz * 0.39    # tooth tip radius
        r_in   = sz * 0.28    # tooth base / gear body rim
        r_hole = sz * 0.105   # center hole
        tooth_half = math.pi / n * 0.55   # half-angle of one tooth

        # ── Build gear polygon ─────────────────────────────────────────────────────
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

        # Subtract center hole
        hole = QPainterPath()
        hole.addEllipse(QPointF(cx, cy), r_hole, r_hole)
        final = gear.subtracted(hole)

        pnt = QPainter(self)
        pnt.setRenderHint(QPainter.RenderHint.Antialiasing)

        lw = sz * 0.05
        pnt.setPen(QPen(QColor(201, 168, 76, 210), lw))
        pnt.setBrush(QColor(255, 255, 255, 55))
        pnt.drawPath(final)

        # ── Center hub (gold dot) ────────────────────────────────────────────
        pnt.setPen(Qt.PenStyle.NoPen)
        pnt.setBrush(QColor(201, 168, 76, 220))
        pnt.drawEllipse(QPointF(cx, cy), r_hole * 0.6, r_hole * 0.6)

        pnt.end()


class _BentoNavCard(GlassCard):
    """
    Full-height navigation card for left/right bento columns.
    Large Glimmer-style icon (text) centred vertically, title + subtitle below.
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


class _TitleBar(QWidget):
    """Draggable frameless title bar."""

    def __init__(self, parent: QMainWindow) -> None:
        super().__init__(parent)
        self.setFixedHeight(62)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(0)

        # ── Left compensator: equal to right buttons width (28+4+28=60px) ─
        lay.addSpacing(60)

        # ── Centre: logo QPushButton ─────────────────────────────────────
        lay.addStretch()
        logo_btn = QPushButton()
        logo_btn.setObjectName("titleLogo")
        logo_btn.setFixedSize(56, 56)
        logo_btn.setStyleSheet(
            "QPushButton#titleLogo { border:none; background:transparent; }"
        )
        logo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logo_btn.setToolTip("Accueil")
        logo_btn.clicked.connect(lambda: parent._tabs.setCurrentIndex(0))
        if _LOGO.exists():
            px = QPixmap(str(_LOGO)).scaled(
                52, 52,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo_btn.setIcon(QIcon(px))
            logo_btn.setIconSize(QSize(52, 52))
        lay.addWidget(logo_btn)
        lay.addStretch()

        # ── Right: minimise + close côte à côte ─────────────────────────
        min_btn = QPushButton("–")
        min_btn.setObjectName("winMinimize")
        min_btn.setToolTip("Réduire")
        min_btn.clicked.connect(parent.showMinimized)
        lay.addWidget(min_btn)

        lay.addSpacing(4)

        close_btn = QPushButton("×")
        close_btn.setObjectName("winClose")
        close_btn.setToolTip("Masquer")
        close_btn.clicked.connect(parent.hide)
        lay.addWidget(close_btn)

    def mousePressEvent(self, ev) -> None:
        super().mousePressEvent(ev)


class MainWindow(QMainWindow):
    def __init__(self, settings: dict, on_save_settings, history_store,
                 on_record_toggle=None) -> None:
        super().__init__()
        self._settings = settings
        self._on_save_settings = on_save_settings
        self._history_store = history_store
        self._on_record_toggle = on_record_toggle  # callable(current_state) -> None

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setMinimumSize(780, 620)
        self.resize(900, 720)
        # Load background image once
        self._raw_bg = QPixmap(str(theme.BG_IMAGE)) if theme.BG_IMAGE.exists() else QPixmap()
        if _LOGO.exists():
            self.setWindowIcon(QIcon(str(_LOGO)))
        self.setStyleSheet(theme.STYLESHEET)

        central = QWidget()
        central.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        central.setAutoFillBackground(False)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(1, 1, 1, 4)
        root.setSpacing(0)

        root.addWidget(_TitleBar(self))

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.tabBar().hide()
        root.addWidget(self._tabs, 1)

        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 6, 2)
        grip_row.addStretch()
        grip = QSizeGrip(self)
        grip.setStyleSheet("background: transparent;")
        grip_row.addWidget(grip)
        root.addLayout(grip_row)

        self._tabs.addTab(self._make_home_tab(),     "  Accueil  ")
        self._tabs.addTab(self._make_history_tab(),  "  Historique  ")
        self._tabs.addTab(self._make_settings_tab(), "  Réglages  ")
        self._tabs.addTab(self._make_perf_tab(),     "  Performances  ")
        self._tabs.currentChanged.connect(self._on_tab_changed)

    # ── Public ────────────────────────────────────────────────────────────────

    def show_and_raise(self) -> None:
        try:
            self._refresh_home()
        except Exception:
            logging.exception("show_and_raise: _refresh_home failed")
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self._ensure_on_screen()
        self.activateWindow()
        self.raise_()
        logging.info("MainWindow shown")

    def _ensure_on_screen(self) -> None:
        """Move window to primary screen centre if it's entirely off-screen."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        geo = self.frameGeometry()
        if not avail.intersects(geo):
            self.move(
                avail.center().x() - geo.width() // 2,
                avail.center().y() - geo.height() // 2,
            )

    def update_settings(self, settings: dict) -> None:
        self._settings = settings
        self._settings_widget.sync_from(settings)
        self._refresh_home()

    def update_state(self, state: str) -> None:
        """Called from AppState.state_changed signal (UI uses overlay + hotkeys)."""
        pass

    # ── Qt overrides ──────────────────────────────────────────────────────────

    def _rebuild_bg_cache(self) -> None:
        """Scale raw background to current window size and store in module-level cache."""
        global _bg_pixmap_cache
        if not self._raw_bg.isNull():
            _bg_pixmap_cache = self._raw_bg.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            _bg_pixmap_cache = None

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r, rad = self.rect(), 14.0
        path = QPainterPath()
        path.addRoundedRect(
            float(r.x()), float(r.y()), float(r.width()), float(r.height()), rad, rad
        )
        p.setClipPath(path)

        # 1. Background image (cover)
        if _bg_pixmap_cache is not None and not _bg_pixmap_cache.isNull():
            # Centre-crop if scaled bigger than window
            bw, bh = _bg_pixmap_cache.width(), _bg_pixmap_cache.height()
            ox = (bw - r.width())  // 2
            oy = (bh - r.height()) // 2
            p.drawPixmap(0, 0, _bg_pixmap_cache, ox, oy, r.width(), r.height())
        else:
            p.fillPath(path, _C_BG)

        # 2. Dark warm vignette overlay so UI text stays readable
        p.fillRect(r, QColor(6, 5, 3, 80))

        p.setClipping(False)

        # 3. Gold rim-light on top edge
        rg = QLinearGradient(r.width() * .15, 0, r.width() * .85, 0)
        rg.setColorAt(0.0,  QColor(201, 168, 76, 0))
        rg.setColorAt(0.35, QColor(201, 168, 76, 140))
        rg.setColorAt(0.65, QColor(201, 168, 76, 140))
        rg.setColorAt(1.0,  QColor(201, 168, 76, 0))
        p.setPen(QPen(QBrush(rg), 1.5))
        p.drawLine(int(r.width() * .15), 1, int(r.width() * .85), 1)

        # 4. Window border
        p.setPen(QPen(_C_BORDER, 1.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(1, 1, -1, -1), rad, rad)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rebuild_bg_cache()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._rebuild_bg_cache()
        if _USE_ACRYLIC:
            theme.enable_acrylic(int(self.winId()), 0x28080706)

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()

    def nativeEvent(self, event_type, message_ptr):
        """Return HTCAPTION for the title-bar strip → Windows handles drag natively at OS speed."""
        if sys.platform != "win32" or event_type != b"windows_generic_MSG":
            return False, 0
        if not self.isVisible():
            return False, 0
        try:
            import ctypes, ctypes.wintypes
            msg = ctypes.wintypes.MSG.from_address(int(message_ptr))
            if msg.message == 0x0084:  # WM_NCHITTEST
                sx = ctypes.c_short(msg.lParam & 0xFFFF).value
                sy = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                local_y = sy - self.y()
                if 0 < local_y <= 63:      # title bar height
                    # Don't intercept clicks on close / minimize buttons
                    from PyQt6.QtWidgets import QApplication, QPushButton
                    if not isinstance(QApplication.widgetAt(sx, sy), QPushButton):
                        return True, 2     # HTCAPTION — drag owned by Windows
        except Exception:
            pass
        return False, 0

    # ── Tab builders ──────────────────────────────────────────────────────────

    def _make_home_tab(self) -> QWidget:
        # Non-scrollable container — bento fills the tab area
        container = QWidget()
        container.setAutoFillBackground(False)
        grid = QGridLayout(container)
        grid.setContentsMargins(18, 14, 18, 14)
        grid.setSpacing(12)
        # 3 equal columns
        for c in range(3):
            grid.setColumnStretch(c, 1)
        # 2 rows: top taller, bottom shorter
        grid.setRowStretch(0, 3)
        grid.setRowStretch(1, 2)

        # ── Centre-top: Clock / Welcome card (col 1, row 0) ───────────────
        clock_card = GlassCard(radius=16, strong_tint=True)
        ck_lay = QVBoxLayout(clock_card)
        ck_lay.setContentsMargins(24, 20, 24, 20)
        ck_lay.setSpacing(4)
        ck_lay.addStretch()

        self._home_date_lbl = QLabel()
        self._home_date_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._home_date_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.55); font-size:11px; letter-spacing:2px;"
            " text-transform:uppercase; background:transparent;"
        )
        ck_lay.addWidget(self._home_date_lbl)

        self._home_clock_lbl = QLabel("00:00")
        self._home_clock_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f_clock = QFont("Segoe UI", 48)
        f_clock.setWeight(QFont.Weight.Thin)
        self._home_clock_lbl.setFont(f_clock)
        self._home_clock_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.92); background:transparent; letter-spacing:-1px;"
        )
        ck_lay.addWidget(self._home_clock_lbl)

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

        # ── Centre-bottom: Stats pill (col 1, between rows — injected below clock) ──
        # We split centre col into clock (row 0) + stats (compact, row 0 bottom via nested)
        # Actually: put stats bar as row 0 col 1 companion → use nested VBox inside clock
        stats_bar = QWidget()
        stats_bar.setAutoFillBackground(False)
        sb_lay = QHBoxLayout(stats_bar)
        sb_lay.setContentsMargins(0, 0, 0, 0)
        sb_lay.setSpacing(0)

        def _stat_pill(value_attr: str, label: str) -> tuple[QWidget, QLabel]:
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

        words_pill, self._stat_words_lbl = _stat_pill("words",  "MOTS")
        wpm_pill,   self._stat_wpm_lbl   = _stat_pill("wpm",    "WPM")
        days_pill,  self._stat_days_lbl  = _stat_pill("days",   "JOURS")
        sb_lay.addWidget(words_pill, 1)
        sb_lay.addSpacing(8)
        sb_lay.addWidget(wpm_pill, 1)
        sb_lay.addSpacing(8)
        sb_lay.addWidget(days_pill, 1)

        # Wrap clock + stats bar vertically in col 1
        centre_wrap = QWidget()
        centre_wrap.setAutoFillBackground(False)
        cw_lay = QVBoxLayout(centre_wrap)
        cw_lay.setContentsMargins(0, 0, 0, 0)
        cw_lay.setSpacing(10)
        cw_lay.addWidget(clock_card, 3)
        cw_lay.addWidget(stats_bar, 1)
        grid.addWidget(centre_wrap, 0, 1, 2, 1)   # spans both rows, centre col

        # ── Left column: Réglages (col 0, spans both rows) ────────────────
        sets_card = _BentoNavCard(_GearIcon(52), "Réglages", "Modèles, raccourcis, options")
        sets_card.nav_clicked.connect(lambda: self._tabs.setCurrentIndex(2))
        grid.addWidget(sets_card, 1, 0)

        # ── Right column: Performances (col 2, spans both rows) ───────────
        perf_card = _BentoNavCard(_GaugeIcon(52), "Performances", "CPU · RAM · Threads")
        perf_card.nav_clicked.connect(lambda: self._tabs.setCurrentIndex(3))
        grid.addWidget(perf_card, 1, 2)

        # ── Inject Historique mini-list into bottom-centre of centre_wrap ──
        hist_card = GlassCard(radius=14, strong_tint=True)
        h_lay = QVBoxLayout(hist_card)
        h_lay.setContentsMargins(16, 14, 16, 14)
        h_lay.setSpacing(6)
        hist_title = QLabel("Historique")
        hist_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hist_title.setStyleSheet(
            "color: rgba(255,255,255,0.90); font-size:14px; font-weight:600;"
            " letter-spacing:0.3px; background:transparent;"
        )
        h_lay.addWidget(hist_title)
        self._home_hist_list = QListWidget()
        self._home_hist_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._home_hist_list.setStyleSheet(
            "QListWidget { background:transparent; border:none; color:rgba(255,255,255,0.75);"
            " font-size:12px; }"
            "QListWidget::item { padding:5px 2px; border-bottom:1px solid rgba(255,255,255,0.06); }"
            "QListWidget::item:hover { background:rgba(201,168,76,0.10); }"
        )
        self._home_hist_list.itemDoubleClicked.connect(
            lambda: self._tabs.setCurrentIndex(1)
        )
        h_lay.addWidget(self._home_hist_list, 1)
        view_all_btn = QPushButton("Voir tout →")
        view_all_btn.setFixedHeight(28)
        view_all_btn.setStyleSheet(
            "QPushButton { background:transparent; border:none; color:rgba(201,168,76,0.65);"
            " font-size:11px; text-align:right; padding-right:2px; }"
            "QPushButton:hover { color:#E8C96A; }"
        )
        view_all_btn.clicked.connect(lambda: self._tabs.setCurrentIndex(1))
        h_lay.addWidget(view_all_btn, 0, Qt.AlignmentFlag.AlignRight)

        # Replace stats_bar in cw_lay with hist_card at bottom
        # cw_lay currently: clock(3) + stats_bar(1)
        # We want:          clock(3) + hist_card(2)
        cw_lay.removeWidget(stats_bar)
        stats_bar.setParent(None)  # type: ignore[arg-type]

        # Re-insert: clock top, stats_bar row inside clock_card bottom area,
        # hist_card below clock
        # Simplest: remove clock, rebuild cw_lay
        cw_lay.removeWidget(clock_card)
        # Clear remaining items
        while cw_lay.count():
            item = cw_lay.takeAt(0)
            if item.widget():
                item.widget().setParent(None)  # type: ignore[arg-type]

        # Inner clock card now embeds stats bar as its last child
        ck_lay.addWidget(stats_bar)

        cw_lay.addWidget(clock_card, 1)
        cw_lay.addWidget(hist_card, 1)

        # Clock update timer
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(1000)
        self._tick_clock()

        self._refresh_home()
        return container

    def _make_history_tab(self) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(20, 16, 20, 16)
        self._history_widget = HistoryWidget(
            entries=self._history_store.list(),
            on_delete=self._history_store.delete,
        )
        lay.addWidget(self._history_widget)
        return wrap

    def _make_settings_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._settings_widget = SettingsWidget(
            settings=self._settings,
            on_save=self._on_settings_save,
        )
        scroll.setWidget(self._settings_widget)
        return scroll
    def _make_perf_tab(self) -> QWidget:
        outer = QWidget()
        root = QVBoxLayout(outer)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # ── Hardware profile card ─────────────────────────────────────────
        hw_card = GlassCard(radius=12)
        hw_lay  = QVBoxLayout(hw_card)
        hw_lay.setContentsMargins(16, 14, 16, 16)
        hw_lay.setSpacing(10)

        title_row = QHBoxLayout()
        hw_title = QLabel("PROFIL MATÉRIEL")
        hw_title.setStyleSheet(
            "color:rgba(255,255,255,0.55); font-size:9px; letter-spacing:1.5px;"
            " font-weight:600; background:transparent;"
        )
        title_row.addWidget(hw_title)
        title_row.addStretch()
        reanalyze_btn = QPushButton("Ré-analyser")
        reanalyze_btn.setFixedHeight(22)
        reanalyze_btn.setStyleSheet(
            "QPushButton { border:1px solid rgba(201,168,76,0.45); border-radius:5px;"
            " color:rgba(201,168,76,0.80); background:transparent; font-size:10px;"
            " padding:0 10px; }"
            "QPushButton:hover { background:rgba(201,168,76,0.12); color:#E8C96A; }"
            "QPushButton:pressed { background:rgba(201,168,76,0.22); }"
        )
        reanalyze_btn.clicked.connect(self._hw_reanalyze)
        title_row.addWidget(reanalyze_btn)
        hw_lay.addLayout(title_row)

        # Pills: Processeur / Mémoire / Carte graphique
        def _pill(header: str) -> tuple[QWidget, QLabel]:
            w = QWidget()
            w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            w.setStyleSheet(
                "QWidget { background:rgba(255,255,255,0.05); border-radius:8px;"
                " border:1px solid rgba(255,255,255,0.09); }"
            )
            pl = QVBoxLayout(w)
            pl.setContentsMargins(12, 9, 12, 9)
            pl.setSpacing(3)
            hdr = QLabel(header)
            hdr.setStyleSheet(
                "color:rgba(255,255,255,0.38); font-size:9px; letter-spacing:1px;"
                " background:transparent; border:none;"
            )
            val = QLabel("—")
            val.setStyleSheet(
                "color:rgba(240,235,220,0.88); font-size:11px;"
                " background:transparent; border:none;"
            )
            val.setWordWrap(True)
            pl.addWidget(hdr)
            pl.addWidget(val)
            return w, val

        pills_row = QHBoxLayout()
        pills_row.setSpacing(8)
        cpu_pill, self._hw_cpu_lbl = _pill("PROCESSEUR")
        ram_pill, self._hw_ram_lbl = _pill("MÉMOIRE")
        gpu_pill, self._hw_gpu_lbl = _pill("CARTE GRAPHIQUE")
        pills_row.addWidget(cpu_pill, 3)
        pills_row.addWidget(ram_pill, 2)
        pills_row.addWidget(gpu_pill, 3)
        hw_lay.addLayout(pills_row)

        # Recommendation band
        rec_band = QWidget()
        rec_band.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        rec_band.setStyleSheet(
            "QWidget { background:rgba(201,168,76,0.08); border-radius:8px;"
            " border:1px solid rgba(201,168,76,0.22); }"
        )
        rec_lay = QVBoxLayout(rec_band)
        rec_lay.setContentsMargins(14, 10, 14, 10)
        rec_lay.setSpacing(6)

        def _rec_row(caption: str) -> QLabel:
            row = QHBoxLayout()
            row.setSpacing(8)
            cap = QLabel(caption)
            cap.setStyleSheet(
                "color:rgba(255,255,255,0.45); font-size:10px;"
                " background:transparent; border:none;"
            )
            cap.setFixedWidth(120)
            badge = QLabel("—")
            badge.setStyleSheet(
                "color:#C9A84C; font-size:12px; font-weight:700;"
                " background:rgba(201,168,76,0.18); border-radius:4px;"
                " border:1px solid rgba(201,168,76,0.40); padding:0 8px;"
            )
            row.addWidget(cap)
            row.addWidget(badge)
            row.addStretch()
            rec_lay.addLayout(row)
            return badge

        self._hw_rec_badge  = _rec_row("Modèle recommandé")
        self._hw_rec_device = _rec_row("Exécution conseillée")

        self._hw_rec_reason = QLabel("—")
        self._hw_rec_reason.setStyleSheet(
            "color:rgba(255,255,255,0.32); font-size:10px;"
            " background:transparent; border:none;"
        )
        rec_lay.addWidget(self._hw_rec_reason)

        apply_btn = QPushButton("▶  Appliquer cette recommandation")
        apply_btn.setFixedHeight(26)
        apply_btn.setStyleSheet(
            "QPushButton { border:1px solid rgba(201,168,76,0.55); border-radius:6px;"
            " color:rgba(201,168,76,0.90); background:rgba(201,168,76,0.10); font-size:11px;"
            " font-weight:600; padding:0 12px; }"
            "QPushButton:hover { background:rgba(201,168,76,0.20); color:#E8C96A; }"
            "QPushButton:pressed { background:rgba(201,168,76,0.32); }"
        )
        apply_btn.clicked.connect(self._apply_hw_recommendation)
        rec_lay.addWidget(apply_btn)
        hw_lay.addWidget(rec_band)
        root.addWidget(hw_card)

        # ── CPU & RAM card ────────────────────────────────────────────────
        cpu_ram_card = GlassCard(radius=12)
        cr_lay = QVBoxLayout(cpu_ram_card)
        cr_lay.setContentsMargins(16, 12, 16, 14)
        cr_lay.setSpacing(8)
        t_cr = QLabel("CPU & RAM")
        t_cr.setStyleSheet(
            "color:rgba(255,255,255,0.55); font-size:9px; letter-spacing:1.5px;"
            " font-weight:600; background:transparent;"
        )
        cr_lay.addWidget(t_cr)
        row_cr = QHBoxLayout()
        row_cr.setSpacing(8)
        self._perf_app_cpu = _StatTile(_CpuAppIcon(), "—", "CPU APP",
            hint="Pourcentage du CPU utilisé par WhisperFlow uniquement.\nMonte pendant la transcription, retombe ensuite.")
        self._perf_sys_cpu = _StatTile(_CpuSysIcon(), "—", "CPU SYS",
            hint="Charge globale du processeur, tous programmes confondus.\nSi > 80% en permanence, le PC est sous pression.")
        self._perf_app_ram = _StatTile(_RamAppIcon(), "—", "RAM APP",
            hint="Mémoire vive occupée par l'application.\nInclut le modèle Whisper chargé en cache.")
        self._perf_sys_ram = _StatTile(_RamSysIcon(), "—", "RAM SYS",
            hint="Mémoire vive totale utilisée par l'ensemble du système.\nLe reste est disponible pour d'autres applications.")
        row_cr.addWidget(self._perf_app_cpu)
        row_cr.addWidget(self._perf_sys_cpu)
        row_cr.addWidget(self._perf_app_ram)
        row_cr.addWidget(self._perf_sys_ram)
        cr_lay.addLayout(row_cr)
        root.addWidget(cpu_ram_card)

        # ── GPU & VRAM card (visible only when GPU detected) ──────────────
        self._perf_gpu_card = GlassCard(radius=12)
        self._perf_gpu_card.setVisible(False)
        gv_lay = QVBoxLayout(self._perf_gpu_card)
        gv_lay.setContentsMargins(16, 12, 16, 14)
        gv_lay.setSpacing(8)
        t_gv = QLabel("GPU & VRAM")
        t_gv.setStyleSheet(
            "color:rgba(255,255,255,0.55); font-size:9px; letter-spacing:1.5px;"
            " font-weight:600; background:transparent;"
        )
        gv_lay.addWidget(t_gv)
        row_gv = QHBoxLayout()
        row_gv.setSpacing(8)
        self._perf_gpu_app  = _StatTile(_GpuAppIcon(), "—", "GPU APP",
            hint="Utilisation du cœur GPU par WhisperFlow pendant la transcription.\nRevient à 0 % entre les dictées.")
        self._perf_sys_gpu  = _StatTile(_GpuSysIcon(), "—", "GPU SYS",
            hint="Utilisation du GPU en pourcentage, tous programmes confondus.\nWhisperFlow l'utilise activement pendant la transcription.")
        self._perf_vram_app = _StatTile(_VramAppIcon(), "—", "VRAM APP",
            hint="Mémoire vidéo allouée par WhisperFlow pour charger le modèle.\nReste stable tant que le modèle est en cache.")
        self._perf_sys_vram = _StatTile(_VramSysIcon(), "—", "VRAM SYS",
            hint="Mémoire vidéo totale occupée sur la carte graphique.\nInclut les jeux, navigateurs et autres apps GPU.")
        row_gv.addWidget(self._perf_gpu_app)
        row_gv.addWidget(self._perf_sys_gpu)
        row_gv.addWidget(self._perf_vram_app)
        row_gv.addWidget(self._perf_sys_vram)
        gv_lay.addLayout(row_gv)
        root.addWidget(self._perf_gpu_card)

        # ── Info row ──────────────────────────────────────────────────────
        info_card = GlassCard(radius=10)
        i_lay = QHBoxLayout(info_card)
        i_lay.setContentsMargins(18, 10, 18, 10)
        self._perf_info_lbl = QLabel()
        self._perf_info_lbl.setStyleSheet(
            "color:rgba(255,255,255,0.35); font-size:11px; background:transparent;"
        )
        self._perf_info_lbl.setTextFormat(Qt.TextFormat.RichText)
        i_lay.addWidget(self._perf_info_lbl)
        root.addWidget(info_card)
        root.addStretch()

        # ── Refresh timer (started/stopped by tab selection) ──────────────
        self._perf_proc  = psutil.Process(os.getpid())
        self._perf_proc.cpu_percent()          # prime the counter
        self._perf_timer = QTimer(self)
        self._perf_timer.timeout.connect(self._refresh_perf)
        return outer
    # ── Internal ──────────────────────────────────────────────────────────────

    def _on_settings_save(self, data: dict) -> None:
        self._settings = data
        self._on_save_settings(data)
        self._refresh_home()

    def _on_tab_changed(self, index: int) -> None:
        if index == 0:
            self._refresh_home()
        elif index == 1:
            self._history_widget.refresh(self._history_store.list())
        if index == 3:
            try:
                self._refresh_hw_card()
            except Exception as e:
                logging.getLogger(__name__).warning("hw_card error: %s", e)
            self._perf_timer.start(2000)
            self._refresh_perf()
        else:
            self._perf_timer.stop()

    def _refresh_home(self) -> None:
        from datetime import date as _date
        _DAYS_FR   = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
        _MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin",
                      "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
        today = _date.today()
        self._home_date_lbl.setText(
            f"{_DAYS_FR[today.weekday()].upper()}  {today.day}"
            f" {_MONTHS_FR[today.month - 1].upper()} {today.year}"
        )
        words, wpm, days = self._compute_stats()
        self._stat_words_lbl.setText(_fmt_k(words))
        self._stat_wpm_lbl.setText(f"{wpm:.0f}" if wpm > 0 else "—")
        self._stat_days_lbl.setText(str(days))
        # Populate mini history list (fill available space)
        try:
            self._home_hist_list.clear()
            entries = self._history_store.list()
            for e in entries[:15]:
                dt   = e.get("created_at", "")[11:16]   # HH:MM
                text = e.get("clean_text", "")
                preview = text[:52] + ("…" if len(text) > 52 else "")
                item = QListWidgetItem(f"{dt}  {preview}")
                self._home_hist_list.addItem(item)
        except Exception:
            pass

    def _tick_clock(self) -> None:
        from datetime import datetime as _dt
        now = _dt.now()
        self._home_clock_lbl.setText(now.strftime("%H:%M"))

    def _refresh_perf(self) -> None:
        try:
            cpu_app = self._perf_proc.cpu_percent()
            ram_app = self._perf_proc.memory_info().rss / 1024 / 1024
            cpu_sys = psutil.cpu_percent()
            vm = psutil.virtual_memory()
            ram_used = vm.used / 1024 ** 3
            ram_total = vm.total / 1024 ** 3
            self._perf_app_cpu.set_value(f"{cpu_app:.1f}%")
            self._perf_app_ram.set_value(f"{ram_app:.0f} MB")
            self._perf_sys_cpu.set_value(f"{cpu_sys:.0f}%")
            self._perf_sys_ram.set_value(f"{ram_used:.1f} GB")
            # ── GPU live stats ────────────────────────────────────────────
            _h = _get_nvml_handle()
            if _h is not None:
                try:
                    import pynvml  # type: ignore[import]
                    pid   = os.getpid()
                    rates = pynvml.nvmlDeviceGetUtilizationRates(_h)
                    mem   = pynvml.nvmlDeviceGetMemoryInfo(_h)
                    self._perf_sys_gpu.set_value(f"{rates.gpu}%")
                    self._perf_sys_vram.set_value(f"{mem.used / 1024**3:.1f} GB")
                    procs = pynvml.nvmlDeviceGetComputeRunningProcesses(_h)
                    app_vram = next(
                        (p.usedGpuMemory for p in procs if p.pid == pid), 0
                    )
                    self._perf_vram_app.set_value(
                        f"{app_vram / 1024**2:.0f} MB" if app_vram else "0 MB"
                    )
                    try:
                        samples = pynvml.nvmlDeviceGetProcessUtilization(_h, 0)
                        app_gpu_pct = next(
                            (s.smUtil for s in samples if s.pid == pid), None
                        )
                        self._perf_gpu_app.set_value(
                            f"{app_gpu_pct}%" if app_gpu_pct is not None else "—"
                        )
                    except Exception:
                        self._perf_gpu_app.set_value("—")
                except Exception:
                    pass
            mk = lambda v: f"<span style='color:#C9A84C'>{v}</span>"
            sep = "<span style='color:#2A221A'>&nbsp;&nbsp;·&nbsp;&nbsp;</span>"
            model = self._settings.get("model", "small")
            pid = os.getpid()
            self._perf_info_lbl.setText(
                f"Modèle: {mk(model)}{sep}PID: {mk(pid)}{sep}"
                f"RAM système: {mk(f'{ram_used:.1f}/{ram_total:.0f} GB')} ({vm.percent:.0f}%)"
            )
        except Exception:
            pass

    def _refresh_hw_card(self) -> None:
        """Populate hardware profile card (auto-detect on first open)."""
        # Force re-analysis when gpu_name or rec_device are missing (old cached profile)
        profile = self._settings.get("hw_profile")
        if not profile or "gpu_name" not in profile or "rec_device" not in profile:
            self._hw_reanalyze()
            return
        cores = profile.get("cpu_cores", 0)
        self._hw_cpu_lbl.setText(f"{profile.get('cpu_name', '—')} · {cores}c")
        self._hw_ram_lbl.setText(f"{profile.get('ram_gb', 0):.0f} GB")
        self._hw_gpu_lbl.setText(profile.get("gpu_name", "—"))
        self._hw_rec_badge.setText(profile.get("rec_model", "—"))
        self._hw_rec_device.setText(profile.get("rec_device", "—"))
        self._hw_rec_reason.setText(profile.get("rec_reason", ""))
        has_gpu = profile.get("cuda_count", 0) > 0
        self._perf_gpu_card.setVisible(has_gpu)

    def _hw_reanalyze(self) -> None:
        """Re-detect hardware, update the card and persist result in settings."""
        profile = _hw_detect()
        self._settings["hw_profile"] = profile
        self._on_save_settings(self._settings)
        cores = profile["cpu_cores"]
        self._hw_cpu_lbl.setText(f"{profile['cpu_name']} · {cores}c")
        self._hw_ram_lbl.setText(f"{profile['ram_gb']:.0f} GB")
        self._hw_gpu_lbl.setText(profile["gpu_name"])
        self._hw_rec_badge.setText(profile["rec_model"])
        self._hw_rec_device.setText(profile["rec_device"])
        self._hw_rec_reason.setText(profile["rec_reason"])
        has_gpu = profile["cuda_count"] > 0
        self._perf_gpu_card.setVisible(has_gpu)

    def _apply_hw_recommendation(self) -> None:
        """Apply the recommended model and compute device to settings."""
        profile = self._settings.get("hw_profile")
        if not profile:
            return
        rec_model  = profile.get("rec_model", "small")
        rec_device = profile.get("rec_device", "CPU")
        # Map human label → settings key
        compute_device = "cuda" if rec_device.upper() == "GPU" else "cpu"
        self._settings["model"]          = rec_model
        self._settings["compute_device"] = compute_device
        self._on_save_settings(self._settings)
        # Refresh the settings panel if it exists so combos stay in sync
        try:
            self._settings_widget.sync_from(self._settings)
        except Exception:
            pass

    def _compute_stats(self) -> tuple[int, float, int]:
        """Returns (total_words, avg_wpm, days_active)."""
        try:
            entries = self._history_store.list()
        except Exception:
            return 0, 0.0, 0
        if not entries:
            return 0, 0.0, 0
        total_words = sum(len(e.get("clean_text", "").split()) for e in entries)
        wpm_vals = [
            len(e.get("clean_text", "").split()) / e["duration_s"] * 60
            for e in entries
            if (e.get("duration_s") or 0) > 1 and e.get("clean_text", "").strip()
        ]
        avg_wpm = sum(wpm_vals) / len(wpm_vals) if wpm_vals else 0.0
        days = len(set(
            e["created_at"][:10] for e in entries if e.get("created_at")
        ))
        return total_words, avg_wpm, days


def _placeholder_icon(size: int) -> QPixmap:
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    m = size // 8
    p.setBrush(QBrush(QColor(201, 168, 76, 200)))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(m, m, size - 2 * m, size - 2 * m)
    f = QFont()
    f.setPointSize(size // 4)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(10, 8, 6))
    p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "WF")
    p.end()
    return px
