from __future__ import annotations
import logging
import os
import sys
import psutil
from pathlib import Path
from PyQt6.QtCore import Qt, QPoint, QRect, QSize, QTimer, pyqtSignal
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
_LOGO        = _ASSETS / "logo.png"
_USE_ACRYLIC = False
_C_BG        = QColor(10, 8, 6, 235)
_C_BORDER    = QColor(201, 168, 76, 200)

# Shared blurred background pixmap — set by MainWindow, read by GlassCard
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


class _StatTile(GlassCard):
    """Compact stat tile: icon / big value / small label."""

    def __init__(self, icon: str, value: str = "—", label: str = "") -> None:
        super().__init__(radius=10)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 14, 10, 14)
        lay.setSpacing(4)
        ic = QLabel(icon)
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic.setStyleSheet("font-size:18px; background: transparent;")
        self._val = QLabel(value)
        self._val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._val.setStyleSheet(
            "color:#E8C96A; font-size:22px; font-weight:700; background: transparent;"
        )
        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            "color:#504840; font-size:9px; letter-spacing:1.3px; background: transparent;"
        )
        lay.addWidget(ic)
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


class _BentoNavCard(GlassCard):
    """
    Full-height navigation card for left/right bento columns.
    Large Glimmer-style icon (text) centred vertically, title + subtitle below.
    Entire card is clickable.
    """

    nav_clicked = pyqtSignal()

    def __init__(self, icon: str, title: str, subtitle: str) -> None:
        super().__init__(radius=14, strong_tint=False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(0)
        lay.addStretch()

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
        self.setFixedHeight(48)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(0)

        # ── Left: minimise button ────────────────────────────────────────
        min_btn = QPushButton("–")
        min_btn.setObjectName("winMinimize")
        min_btn.setToolTip("Réduire")
        min_btn.clicked.connect(parent.showMinimized)
        lay.addWidget(min_btn)

        # ── Centre: logo QPushButton (reliable click) ────────────────────
        lay.addStretch()
        logo_btn = QPushButton()
        logo_btn.setObjectName("titleLogo")
        logo_btn.setFixedSize(32, 32)
        logo_btn.setStyleSheet(
            "QPushButton#titleLogo { border:none; background:transparent; }"
        )
        logo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logo_btn.setToolTip("Accueil")
        logo_btn.clicked.connect(lambda: parent._tabs.setCurrentIndex(0))
        if _LOGO.exists():
            px = QPixmap(str(_LOGO)).scaled(
                28, 28,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo_btn.setIcon(QIcon(px))
            logo_btn.setIconSize(QSize(28, 28))
        lay.addWidget(logo_btn)
        lay.addStretch()

        # ── Right: close button ──────────────────────────────────────────
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
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, _USE_ACRYLIC)
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
                if 0 < local_y <= 49:      # title bar height
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
        sets_card = _BentoNavCard("⚙", "Réglages", "Modèles, raccourcis, options")
        sets_card.nav_clicked.connect(lambda: self._tabs.setCurrentIndex(2))
        grid.addWidget(sets_card, 1, 0)

        # ── Right column: Performances (col 2, spans both rows) ───────────
        perf_card = _BentoNavCard("◈", "Performances", "CPU · RAM · Threads")
        perf_card.nav_clicked.connect(lambda: self._tabs.setCurrentIndex(3))
        grid.addWidget(perf_card, 1, 2)

        # ── Inject Historique mini-list into bottom-centre of centre_wrap ──
        hist_card = GlassCard(radius=14, strong_tint=True)
        h_lay = QVBoxLayout(hist_card)
        h_lay.setContentsMargins(16, 14, 16, 14)
        h_lay.setSpacing(6)
        hist_title = QLabel("HISTORIQUE")
        hist_title.setStyleSheet(
            "color: rgba(201,168,76,0.80); font-size:9px; letter-spacing:1.8px;"
            " font-weight:600; background:transparent;"
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

        # ── App process card ──────────────────────────────────────────────
        app_card = GlassCard(radius=12)
        a_lay = QVBoxLayout(app_card)
        a_lay.setContentsMargins(16, 12, 16, 14)
        a_lay.setSpacing(8)
        t = QLabel("PROCESSUS WHISPERFLOW")
        t.setStyleSheet(
            "color:#C9A84C; font-size:9px; letter-spacing:1.5px;"
            " font-weight:600; background:transparent;"
        )
        a_lay.addWidget(t)
        row_a = QHBoxLayout()
        row_a.setSpacing(8)
        self._perf_app_cpu     = _StatTile("🔲", "—", "CPU APP")
        self._perf_app_ram     = _StatTile("💾", "—", "RAM APP")
        self._perf_app_threads = _StatTile("🧵", "—", "THREADS")
        row_a.addWidget(self._perf_app_cpu)
        row_a.addWidget(self._perf_app_ram)
        row_a.addWidget(self._perf_app_threads)
        a_lay.addLayout(row_a)
        root.addWidget(app_card)

        # ── System card ───────────────────────────────────────────────────
        sys_card = GlassCard(radius=12)
        s_lay = QVBoxLayout(sys_card)
        s_lay.setContentsMargins(16, 12, 16, 14)
        s_lay.setSpacing(8)
        t2 = QLabel("SYSTÈME")
        t2.setStyleSheet(
            "color:#C9A84C; font-size:9px; letter-spacing:1.5px;"
            " font-weight:600; background:transparent;"
        )
        s_lay.addWidget(t2)
        row_s = QHBoxLayout()
        row_s.setSpacing(8)
        self._perf_sys_cpu = _StatTile("⚙️", "—", "CPU SYS")
        self._perf_sys_ram = _StatTile("🖥", "—", "RAM SYS")
        row_s.addWidget(self._perf_sys_cpu)
        row_s.addWidget(self._perf_sys_ram)
        s_lay.addLayout(row_s)
        root.addWidget(sys_card)

        # ── Info row ──────────────────────────────────────────────────────
        info_card = GlassCard(radius=10)
        i_lay = QHBoxLayout(info_card)
        i_lay.setContentsMargins(18, 10, 18, 10)
        self._perf_info_lbl = QLabel()
        self._perf_info_lbl.setStyleSheet(
            "color:#504840; font-size:11px; background:transparent;"
        )
        self._perf_info_lbl.setTextFormat(Qt.TextFormat.RichText)
        i_lay.addWidget(self._perf_info_lbl)
        root.addWidget(info_card)
        root.addStretch()

        # ── Refresh timer (started/stopped by tab selection) ───────────────
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
        # Populate mini history list (last 4 entries)
        try:
            self._home_hist_list.clear()
            entries = self._history_store.list()
            for e in entries[:4]:
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
            threads = self._perf_proc.num_threads()
            cpu_sys = psutil.cpu_percent()
            vm = psutil.virtual_memory()
            ram_used = vm.used / 1024 ** 3
            ram_total = vm.total / 1024 ** 3
            self._perf_app_cpu.set_value(f"{cpu_app:.1f}%")
            self._perf_app_ram.set_value(f"{ram_app:.0f} MB")
            self._perf_app_threads.set_value(str(threads))
            self._perf_sys_cpu.set_value(f"{cpu_sys:.0f}%")
            self._perf_sys_ram.set_value(f"{ram_used:.1f} GB")
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
