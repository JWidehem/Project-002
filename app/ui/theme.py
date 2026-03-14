"""
WhisperFlow – Jetpack Compose Glimmer-inspired Dark Gold theme.

Design principles (https://design.google/library/transparent-screens):
  · Dark surfaces → near-black warm base (no white/light backgrounds)
  · Gold content only for actionable / active elements
  · Rim light on top edge of every card (1 px gradient)
  · Typography: large, spaced, always bright on dark
  · Motion: slow entrance, instant feedback
"""
from __future__ import annotations

import ctypes
import sys
from pathlib import Path

# ── Colour constants (also used from Python paint code) ──────────────────────
GOLD        = "#C9A84C"
GOLD_BRIGHT = "#E8C96A"
GOLD_DIM    = "#8A6A28"
TEXT_PRI    = "#F0EDE0"
TEXT_SEC    = "#A89870"
TEXT_MUT    = "#504840"
BG_WIN      = (10,  8,  6, 215)   # rgba – very dark warm
BG_SURFACE  = (22, 19, 12, 185)   # rgba – dark warm surface

# ── Background image path ─────────────────────────────────────────────────────
_ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"
BG_IMAGE    = _ASSETS_DIR / "background00.png"

# ── Glassmorphism helpers ─────────────────────────────────────────────────────
# GLASS_BLUR_RADIUS : stack-blur radius applied to the captured background slice
# GLASS_TINT        : dark warm tint drawn over the blurred slice (RGBA)
# GLASS_TINT_STRONG : stronger tint for cards with lots of text content
GLASS_BLUR_RADIUS  = 18
GLASS_TINT         = (16, 12,  6, 110)   # rgba
GLASS_TINT_STRONG  = (12,  9,  4, 155)   # rgba

# ── Full QSS stylesheet ───────────────────────────────────────────────────────
STYLESHEET = r"""
/* ── Reset ──────────────────────────────────────────────────────────────────── */
* { outline: none; }

QWidget {
    background: transparent;
    color: #F0EDE0;
    font-family: "Segoe UI", "SF Pro Display", sans-serif;
    font-size: 13px;
    selection-background-color: rgba(201,168,76, 0.30);
    selection-color: #F0EDE0;
}
QMainWindow, QDialog { background: transparent; }

/* ── Scrollbars ──────────────────────────────────────────────────────────────── */
QScrollBar:vertical {
    background: transparent; width: 5px; margin: 0;
}
QScrollBar::handle:vertical {
    background: rgba(201,168,76, 0.22);
    border-radius: 2px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: rgba(201,168,76, 0.44); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { height: 0; }

/* ── Tab widget ──────────────────────────────────────────────────────────────── */
QTabWidget::pane  { border: none; background: transparent; }
QTabBar           { background: transparent; }
QTabBar::tab {
    background: transparent;
    color: #605848;
    padding: 10px 24px;
    border: none;
    font-size: 11px;
    letter-spacing: 1.0px;
    text-transform: uppercase;
}
QTabBar::tab:selected {
    color: #C9A84C;
    border-bottom: 2px solid #C9A84C;
    font-weight: 600;
}
QTabBar::tab:hover:!selected { color: #A89870; }

/* ── Group boxes (rendered as glass cards) ───────────────────────────────────── */
QGroupBox {
    background: rgba(22, 19, 12, 0.72);
    border:     1px solid rgba(201,168,76, 0.18);
    border-top: 1px solid rgba(201,168,76, 0.44);
    border-radius: 10px;
    margin-top: 18px;
    padding-top: 10px;
    font-size: 10px;
    letter-spacing: 1.3px;
    text-transform: uppercase;
    color: #C9A84C;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 10px;
    left: 10px; top: 4px;
}

/* ── Buttons ─────────────────────────────────────────────────────────────────── */
QPushButton {
    background: rgba(201,168,76, 0.10);
    color: #C9A84C;
    border: 1px solid rgba(201,168,76, 0.28);
    border-radius: 7px;
    padding: 7px 18px;
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.4px;
}
QPushButton:hover {
    background: rgba(201,168,76, 0.20);
    border-color: rgba(201,168,76, 0.56);
    color: #E8C96A;
}
QPushButton:pressed { background: rgba(201,168,76, 0.32); }
QPushButton:disabled { color: #504840; border-color: rgba(255,255,255,0.06); }

/* ── Text inputs ─────────────────────────────────────────────────────────────── */
QLineEdit, QTextEdit, QPlainTextEdit {
    background: rgba(14, 12, 8, 0.82);
    border:        1px solid rgba(255,255,255, 0.07);
    border-bottom: 1px solid rgba(201,168,76, 0.32);
    border-radius: 7px;
    color: #F0EDE0;
    padding: 7px 10px;
}
QLineEdit:focus, QTextEdit:focus {
    border-color:  rgba(201,168,76, 0.22);
    border-bottom: 2px solid rgba(201,168,76, 0.68);
}

/* ── Combo boxes ─────────────────────────────────────────────────────────────── */
QComboBox {
    background: rgba(14, 12, 8, 0.82);
    border:        1px solid rgba(255,255,255, 0.07);
    border-bottom: 1px solid rgba(201,168,76, 0.32);
    border-radius: 7px;
    color: #F0EDE0;
    padding: 6px 10px;
    min-width: 100px;
}
QComboBox:focus { border-bottom: 2px solid rgba(201,168,76, 0.68); }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: rgba(16, 14, 8, 0.97);
    border: 1px solid rgba(201,168,76, 0.30);
    border-radius: 7px;
    color: #F0EDE0;
    padding: 4px;
    selection-background-color: rgba(201,168,76, 0.22);
}

/* ── List widget (Historique) ────────────────────────────────────────────────── */
QListWidget {
    background: rgba(12, 10, 6, 0.72);
    border:     1px solid rgba(255,255,255, 0.05);
    border-top: 1px solid rgba(201,168,76, 0.22);
    border-radius: 9px;
    color: #C8C0A8;
    padding: 4px;
}
QListWidget::item {
    padding: 9px 12px;
    border-radius: 6px;
    border-bottom: 1px solid rgba(255,255,255, 0.04);
}
QListWidget::item:selected {
    background: rgba(201,168,76, 0.18);
    color: #F0EDE0;
    border: 1px solid rgba(201,168,76, 0.32);
}
QListWidget::item:hover:!selected { background: rgba(255,255,255, 0.03); }

/* ── Checkboxes ──────────────────────────────────────────────────────────────── */
QCheckBox { color: #C8C0A8; spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border-radius: 4px;
    border: 1px solid rgba(201,168,76, 0.40);
    background: rgba(14, 12, 8, 0.8);
}
QCheckBox::indicator:checked {
    background: rgba(201,168,76, 0.55);
    border-color: #C9A84C;
}
QCheckBox::indicator:hover { border-color: rgba(201,168,76, 0.72); }

/* ── Form labels ─────────────────────────────────────────────────────────────── */
QFormLayout QLabel { color: #8A8070; font-size: 12px; }

/* ── Scroll area ─────────────────────────────────────────────────────────────── */
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }

/* ── Separators ──────────────────────────────────────────────────────────────── */
QFrame[frameShape="4"], QFrame[frameShape="5"] {
    color: rgba(201,168,76, 0.25);
    background: rgba(201,168,76, 0.25);
    border: none; max-height: 1px;
}

/* ── Named labels (home tab) ─────────────────────────────────────────────────── */
QLabel#titleLabel {
    color: #C9A84C;
    font-size: 26px; font-weight: 700;
    letter-spacing: 1.0px;
    background: transparent;
}
QLabel#subtitleLabel { color: #504840; font-size: 12px; background: transparent; }
QLabel#infoLabel     { color: #A89870; font-size: 12px; background: transparent; }
QLabel#statsLabel    { color: #504840; font-size: 11px; background: transparent; }

/* ── Window control buttons ──────────────────────────────────────────────────── */
QPushButton#winClose {
    background: transparent; border: none; border-radius: 12px;
    color: #C9A84C; font-size: 16px; font-weight: 600; padding: 0;
    min-width: 28px; max-width: 28px;
    min-height: 28px; max-height: 28px;
}
QPushButton#winClose:hover { background: rgba(200,60,60,0.65); color: #F0EDE0; }

QPushButton#winMinimize {
    background: transparent; border: none; border-radius: 12px;
    color: #C9A84C; font-size: 18px; font-weight: 400; padding: 0;
    min-width: 28px; max-width: 28px;
    min-height: 28px; max-height: 28px;
}
QPushButton#winMinimize:hover { background: rgba(201,168,76,0.22); color: #E8C96A; }
"""


# ── Glassmorphism backdrop-blur helper ───────────────────────────────────────
def blur_pixmap_region(source, rect, radius: int = GLASS_BLUR_RADIUS):
    """
    Extract *rect* from *source*, apply a stack-blur of *radius* pixels,
    and return the blurred slice as a new QPixmap.

    Uses QImage.stackBlur() introduced in Qt 6.5 (we ship PyQt6 6.7).
    Falls back to a plain dark tint if the source is null or rect is empty.
    """
    from PyQt6.QtGui import QPixmap as _QPixmap, QColor as _QColor
    from PyQt6.QtCore import QRect as _QRect

    if source.isNull() or rect.isEmpty():
        fallback = _QPixmap(max(rect.width(), 1), max(rect.height(), 1))
        fallback.fill(_QColor(16, 12, 6, 180))
        return fallback

    # Crop the region from the full background pixmap
    cropped = source.copy(rect)
    img = cropped.toImage()
    # Cheap but effective blur: scale down then scale back up with smooth filter
    # (QImage.stackBlur not exposed in this PyQt6 build)
    from PyQt6.QtCore import Qt as _Qt
    factor = max(2, radius // 4)
    small = img.scaled(
        max(1, img.width() // factor), max(1, img.height() // factor),
        _Qt.AspectRatioMode.IgnoreAspectRatio,
        _Qt.TransformationMode.SmoothTransformation,
    )
    blurred_img = small.scaled(
        img.width(), img.height(),
        _Qt.AspectRatioMode.IgnoreAspectRatio,
        _Qt.TransformationMode.SmoothTransformation,
    )
    return _QPixmap.fromImage(blurred_img)


# ── Windows DWM acrylic blur-behind ──────────────────────────────────────────
def enable_acrylic(hwnd: int, tint_abgr: int = 0xCC080808) -> None:
    """
    Apply Windows acrylic frosted-glass blur behind a frameless window.
    tint_abgr: 0xAA_BB_GG_RR  (ABGR byte order).
    AA = opacity of tint (0 = pure blur, FF = opaque flat color).
    No-op on non-Windows or unsupported builds.
    """
    if sys.platform != "win32":
        return
    try:
        from ctypes import (
            Structure, POINTER, c_int, c_size_t,
            cast, pointer, windll, byref,
        )

        class _Accent(Structure):
            _fields_ = [
                ("AccentState",  c_int),
                ("AccentFlags",  c_int),
                ("GradientColor", c_int),
                ("AnimationId",  c_int),
            ]

        class _WcaData(Structure):
            _fields_ = [
                ("Attribute",   c_int),
                ("Data",        POINTER(c_int)),
                ("SizeOfData",  c_size_t),
            ]

        accent = _Accent()
        accent.AccentState   = 4          # ACCENT_ENABLE_ACRYLICBLURBEHIND
        accent.AccentFlags   = 0x20       # activate gradient colour
        accent.GradientColor = tint_abgr

        data = _WcaData()
        data.Attribute  = 19             # WCA_ACCENT_POLICY
        data.Data       = cast(pointer(accent), POINTER(c_int))
        data.SizeOfData = ctypes.sizeof(accent)

        windll.user32.SetWindowCompositionAttribute(hwnd, byref(data))
    except Exception:
        pass  # graceful fallback on Windows 7 / XP / VM
