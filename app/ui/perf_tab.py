"""Performances tab builder: hardware profile, CPU/RAM/GPU live stats."""
from __future__ import annotations

import math
import os
import platform
import subprocess
import sys

import psutil
from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer
from PyQt6.QtGui import (
    QBrush, QColor, QPainter, QPainterPath, QPen,
)
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from app.ui.glass_card import GlassCard


# ── Hardware detection ─────────────────────────────────────────────────────────

def _hw_detect() -> dict:
    """Detect CPU friendly name, RAM, GPU name + CUDA. Returns a profile dict."""
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

    gpu_name = "—"
    try:
        r = subprocess.run(
            ["wmic", "path", "win32_videocontroller", "get", "name", "/format:value"],
            capture_output=True, text=True, timeout=5,
            creationflags=0x08000000,
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


# ── GPU live monitoring via pynvml ─────────────────────────────────────────────

_nvml_handle = None  # None = untried, False = unavailable, otherwise device handle


def _get_nvml_handle():
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


# ── Tile icons (28×28 QPainter widgets) ───────────────────────────────────────

class _TileIcon(QWidget):
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
    def paintEvent(self, _) -> None:
        p = self._painter()
        sz = self._SIZE
        cx, cy = sz / 2, sz / 2
        bw = sz * 0.44
        body = QRectF(cx - bw, cy - bw, bw * 2, bw * 2)
        p.setPen(QPen(self._gold(210), sz * 0.07))
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawRoundedRect(body, sz * 0.08, sz * 0.08)
        core = body.adjusted(sz * 0.12, sz * 0.12, -sz * 0.12, -sz * 0.12)
        p.setPen(QPen(self._gold(160), sz * 0.055))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(core)
        for i in range(3):
            t = (i + 1) / 4
            y = cy - bw + bw * 2 * t
            p.setPen(QPen(self._white(160), sz * 0.055))
            p.drawLine(QPointF(cx - bw - sz * 0.17, y), QPointF(cx - bw, y))
            p.drawLine(QPointF(cx + bw, y), QPointF(cx + bw + sz * 0.17, y))
        p.setPen(QPen(self._gold(240), sz * 0.07))
        arr_x, arr_y1, arr_y2 = cx, cy - sz * 0.07, cy + sz * 0.07
        p.drawLine(QPointF(arr_x, arr_y1), QPointF(arr_x, arr_y2))
        p.drawLine(QPointF(arr_x - sz * 0.1, arr_y2 - sz * 0.08), QPointF(arr_x, arr_y2))
        p.drawLine(QPointF(arr_x + sz * 0.1, arr_y2 - sz * 0.08), QPointF(arr_x, arr_y2))
        p.end()


class _CpuSysIcon(_TileIcon):
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
    def paintEvent(self, _) -> None:
        p = self._painter()
        sz = self._SIZE
        cx, cy = sz / 2, sz / 2
        sw, sh = sz * 0.62, sz * 0.28
        stick = QRectF(cx - sw / 2, cy - sh / 2 - sz * 0.04, sw, sh)
        p.setPen(QPen(self._gold(210), sz * 0.065))
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawRoundedRect(stick, sz * 0.055, sz * 0.055)
        p.setPen(QPen(self._gold(160), sz * 0.05))
        for xf in (-0.16, 0.0, 0.16):
            cr = QRectF(cx + sz * xf - sz * 0.055, stick.top() + sz * 0.04, sz * 0.11, sh - sz * 0.08)
            p.setBrush(QColor(201, 168, 76, 40))
            p.drawRect(cr)
        p.setPen(QPen(self._white(150), sz * 0.05))
        for xf in (-0.20, -0.08, 0.08, 0.20):
            px = cx + sz * xf
            p.drawLine(QPointF(px, stick.bottom()), QPointF(px, stick.bottom() + sz * 0.14))
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
    def paintEvent(self, _) -> None:
        p = self._painter()
        sz = self._SIZE
        cx, cy = sz / 2, sz / 2
        bw, bh = sz * 0.44, sz * 0.32
        body = QRectF(cx - bw, cy - bh - sz * 0.02, bw * 2, bh * 2)
        p.setPen(QPen(self._gold(210), sz * 0.07))
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawRoundedRect(body, sz * 0.09, sz * 0.09)
        for dx in (-sz * 0.13, sz * 0.13):
            p.setPen(QPen(self._white(140), sz * 0.055))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx + dx, body.center().y()), sz * 0.10, sz * 0.10)
        p.setPen(QPen(self._white(160), sz * 0.06))
        for xf in (-0.25, -0.10, 0.10, 0.25):
            px = cx + sz * xf
            p.drawLine(QPointF(px, body.bottom()), QPointF(px, body.bottom() + sz * 0.15))
        p.setPen(QPen(self._gold(240), sz * 0.075))
        arr_y2 = cy - sz * 0.04
        arr_y1 = arr_y2 - sz * 0.12
        p.drawLine(QPointF(cx, arr_y1), QPointF(cx, arr_y2))
        p.drawLine(QPointF(cx - sz * 0.09, arr_y2 - sz * 0.07), QPointF(cx, arr_y2))
        p.drawLine(QPointF(cx + sz * 0.09, arr_y2 - sz * 0.07), QPointF(cx, arr_y2))
        p.end()


class _GpuSysIcon(_TileIcon):
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
    def paintEvent(self, _) -> None:
        p = self._painter()
        sz = self._SIZE
        cx, cy = sz / 2, sz / 2
        fw = sz * 0.38
        frame = QRectF(cx - fw, cy - fw, fw * 2, fw * 2)
        p.setPen(QPen(self._gold(180), sz * 0.065))
        p.setBrush(QColor(201, 168, 76, 18))
        p.drawRoundedRect(frame, sz * 0.08, sz * 0.08)
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
    def paintEvent(self, _) -> None:
        p = self._painter()
        sz = self._SIZE
        cx, cy = sz / 2, sz / 2
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


# ── Stat tile (used in CPU/RAM/GPU cards) ──────────────────────────────────────

class _HoverTip(QWidget):
    """Singleton glassmorphism hint popup shown when hovering a stat tile."""

    _instance: "_HoverTip | None" = None

    @classmethod
    def instance(cls) -> "_HoverTip":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        from PyQt6.QtGui import QGuiApplication
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
        pass

    def show_for(self, widget: QWidget, text: str) -> None:
        from PyQt6.QtCore import QPoint
        from PyQt6.QtGui import QGuiApplication
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

    def show_for_point(self, global_pt, text: str) -> None:
        from PyQt6.QtGui import QGuiApplication
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
    """Compact stat tile: painted-icon / big value / small label + optional hint badge."""

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


# ── Tab builder ────────────────────────────────────────────────────────────────

def build_perf_tab(window) -> QWidget:
    """
    Build and return the Performances tab widget.
    Stores widget/timer references on *window* so that _refresh_perf(),
    _refresh_hw_card(), _hw_reanalyze(), etc. can update them later.
    """
    outer = QWidget()
    root = QVBoxLayout(outer)
    root.setContentsMargins(16, 14, 16, 14)
    root.setSpacing(10)

    # ── Hardware profile card ─────────────────────────────────────────────
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
    reanalyze_btn.clicked.connect(window._hw_reanalyze)
    title_row.addWidget(reanalyze_btn)
    hw_lay.addLayout(title_row)

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
    cpu_pill, window._hw_cpu_lbl = _pill("PROCESSEUR")
    ram_pill, window._hw_ram_lbl = _pill("MÉMOIRE")
    gpu_pill, window._hw_gpu_lbl = _pill("CARTE GRAPHIQUE")
    pills_row.addWidget(cpu_pill, 3)
    pills_row.addWidget(ram_pill, 2)
    pills_row.addWidget(gpu_pill, 3)
    hw_lay.addLayout(pills_row)

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

    window._hw_rec_badge  = _rec_row("Modèle recommandé")
    window._hw_rec_device = _rec_row("Exécution conseillée")

    window._hw_rec_reason = QLabel("—")
    window._hw_rec_reason.setStyleSheet(
        "color:rgba(255,255,255,0.32); font-size:10px;"
        " background:transparent; border:none;"
    )
    rec_lay.addWidget(window._hw_rec_reason)

    apply_btn = QPushButton("▶  Appliquer cette recommandation")
    apply_btn.setFixedHeight(26)
    apply_btn.setStyleSheet(
        "QPushButton { border:1px solid rgba(201,168,76,0.55); border-radius:6px;"
        " color:rgba(201,168,76,0.90); background:rgba(201,168,76,0.10); font-size:11px;"
        " font-weight:600; padding:0 12px; }"
        "QPushButton:hover { background:rgba(201,168,76,0.20); color:#E8C96A; }"
        "QPushButton:pressed { background:rgba(201,168,76,0.32); }"
    )
    apply_btn.clicked.connect(window._apply_hw_recommendation)
    rec_lay.addWidget(apply_btn)
    hw_lay.addWidget(rec_band)
    root.addWidget(hw_card)

    # ── CPU & RAM card ────────────────────────────────────────────────────
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
    window._perf_app_cpu = _StatTile(_CpuAppIcon(), "—", "CPU APP",
        hint="Pourcentage du CPU utilisé par WhisperFlow uniquement.\nMonte pendant la transcription, retombe ensuite.")
    window._perf_sys_cpu = _StatTile(_CpuSysIcon(), "—", "CPU SYS",
        hint="Charge globale du processeur, tous programmes confondus.\nSi > 80% en permanence, le PC est sous pression.")
    window._perf_app_ram = _StatTile(_RamAppIcon(), "—", "RAM APP",
        hint="Mémoire vive occupée par l'application.\nInclut le modèle Whisper chargé en cache.")
    window._perf_sys_ram = _StatTile(_RamSysIcon(), "—", "RAM SYS",
        hint="Mémoire vive totale utilisée par l'ensemble du système.\nLe reste est disponible pour d'autres applications.")
    row_cr.addWidget(window._perf_app_cpu)
    row_cr.addWidget(window._perf_sys_cpu)
    row_cr.addWidget(window._perf_app_ram)
    row_cr.addWidget(window._perf_sys_ram)
    cr_lay.addLayout(row_cr)
    root.addWidget(cpu_ram_card)

    # ── GPU & VRAM card ───────────────────────────────────────────────────
    window._perf_gpu_card = GlassCard(radius=12)
    window._perf_gpu_card.setVisible(False)
    gv_lay = QVBoxLayout(window._perf_gpu_card)
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
    window._perf_gpu_app  = _StatTile(_GpuAppIcon(), "—", "GPU APP",
        hint="Utilisation du cœur GPU par WhisperFlow pendant la transcription.\nRevient à 0 % entre les dictées.")
    window._perf_sys_gpu  = _StatTile(_GpuSysIcon(), "—", "GPU SYS",
        hint="Utilisation du GPU en pourcentage, tous programmes confondus.\nWhisperFlow l'utilise activement pendant la transcription.")
    window._perf_vram_app = _StatTile(_VramAppIcon(), "—", "VRAM APP",
        hint="Mémoire vidéo allouée par WhisperFlow pour charger le modèle.\nReste stable tant que le modèle est en cache.")
    window._perf_sys_vram = _StatTile(_VramSysIcon(), "—", "VRAM SYS",
        hint="Mémoire vidéo totale occupée sur la carte graphique.\nInclut les jeux, navigateurs et autres apps GPU.")
    row_gv.addWidget(window._perf_gpu_app)
    row_gv.addWidget(window._perf_sys_gpu)
    row_gv.addWidget(window._perf_vram_app)
    row_gv.addWidget(window._perf_sys_vram)
    gv_lay.addLayout(row_gv)
    root.addWidget(window._perf_gpu_card)

    # ── Info row ──────────────────────────────────────────────────────────
    info_card = GlassCard(radius=10)
    i_lay = QHBoxLayout(info_card)
    i_lay.setContentsMargins(18, 10, 18, 10)
    window._perf_info_lbl = QLabel()
    window._perf_info_lbl.setStyleSheet(
        "color:rgba(255,255,255,0.35); font-size:11px; background:transparent;"
    )
    window._perf_info_lbl.setTextFormat(Qt.TextFormat.RichText)
    i_lay.addWidget(window._perf_info_lbl)
    root.addWidget(info_card)
    root.addStretch()

    # ── Refresh timer (started/stopped by tab selection) ──────────────────
    window._perf_proc  = psutil.Process(os.getpid())
    window._perf_proc.cpu_percent()
    window._perf_timer = QTimer(window)
    window._perf_timer.timeout.connect(window._refresh_perf)
    return outer
