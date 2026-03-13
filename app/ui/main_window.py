from __future__ import annotations
import logging
import os
import sys
import psutil
from pathlib import Path
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QGuiApplication, QIcon, QLinearGradient,
    QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QScrollArea, QSizeGrip,
    QTabWidget, QVBoxLayout, QWidget,
)
from app.ui import theme
from app.ui.history import HistoryWidget
from app.ui.settings import SettingsWidget

_ASSETS = Path(__file__).parent.parent.parent / "assets"
_LOGO   = _ASSETS / "logo.png"
_USE_ACRYLIC = False
_C_BG     = QColor(10, 8, 6, 235)
_C_BORDER = QColor(201, 168, 76, 52)




class GlassCard(QWidget):
    """Dark glass card with gold rim-light — paints own background."""

    def __init__(self, parent=None, radius: int = 12) -> None:
        super().__init__(parent)
        self._radius = radius

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r, rad = self.rect(), float(self._radius)
        path = QPainterPath()
        path.addRoundedRect(
            float(r.x()), float(r.y()), float(r.width()), float(r.height()), rad, rad
        )
        p.fillPath(path, QColor(22, 19, 12, 110))
        rim = QLinearGradient(r.width() * .1, 0, r.width() * .9, 0)
        rim.setColorAt(0.0,  QColor(201, 168, 76, 0))
        rim.setColorAt(0.35, QColor(201, 168, 76, 110))
        rim.setColorAt(0.65, QColor(201, 168, 76, 110))
        rim.setColorAt(1.0,  QColor(201, 168, 76, 0))
        p.setPen(QPen(QBrush(rim), 1.2))
        p.drawLine(int(r.width() * .10), 1, int(r.width() * .90), 1)
        p.setPen(QPen(QColor(201, 168, 76, 40), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(0, 0, -1, -1), rad, rad)


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


class _StatRow(QWidget):
    """Horizontal stat row inside a card: icon  label ... value"""

    def __init__(self, icon: str, value: str, label: str) -> None:
        super().__init__()
        self.setAutoFillBackground(False)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 5, 0, 5)
        lay.setSpacing(10)
        ic = QLabel(icon)
        ic.setStyleSheet("font-size:15px; background:transparent;")
        ic.setFixedWidth(22)
        lbl = QLabel(label)
        lbl.setStyleSheet("color:#504840; font-size:11px; background:transparent;")
        self._val = QLabel(value)
        self._val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._val.setStyleSheet(
            "color:#E8C96A; font-size:17px; font-weight:700; background:transparent;"
        )
        lay.addWidget(ic)
        lay.addWidget(lbl, 1)
        lay.addWidget(self._val)

    def set_value(self, v: str) -> None:
        self._val.setText(v)


class _TitleBar(QWidget):
    """Draggable frameless title bar."""

    def __init__(self, parent: QMainWindow) -> None:
        super().__init__(parent)
        self.setFixedHeight(48)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 0, 12, 0)
        lay.setSpacing(10)
        logo = QLabel()
        if _LOGO.exists():
            px = QPixmap(str(_LOGO)).scaled(
                26, 26,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo.setPixmap(px)
        logo.setFixedSize(26, 26)
        lay.addWidget(logo)
        lbl = QLabel("WhisperFlow")
        f = QFont("Segoe UI", 12)
        f.setWeight(QFont.Weight.DemiBold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        lbl.setFont(f)
        lbl.setStyleSheet("color: #C9A84C; background: transparent;")
        lay.addWidget(lbl)
        lay.addStretch()
        min_btn = QPushButton("–")
        min_btn.setObjectName("winMinimize")
        min_btn.setToolTip("Réduire")
        min_btn.clicked.connect(parent.showMinimized)
        close_btn = QPushButton("×")
        close_btn.setObjectName("winClose")
        close_btn.setToolTip("Masquer")
        close_btn.clicked.connect(parent.hide)
        lay.addWidget(min_btn)
        lay.addWidget(close_btn)

    def mousePressEvent(self, ev) -> None:
        # Buttons handle their own clicks; title-bar drag handled by MainWindow.nativeEvent
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
        self.setMinimumSize(660, 560)
        self.resize(700, 640)
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

        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(201,168,76,0.38);")
        root.addWidget(sep)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
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

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r, rad = self.rect(), 14.0
        path = QPainterPath()
        path.addRoundedRect(
            float(r.x()), float(r.y()), float(r.width()), float(r.height()), rad, rad
        )
        p.fillPath(path, _C_BG)
        rg = QLinearGradient(r.width() * .15, 0, r.width() * .85, 0)
        rg.setColorAt(0.0,  QColor(201, 168, 76, 0))
        rg.setColorAt(0.35, QColor(201, 168, 76, 140))
        rg.setColorAt(0.65, QColor(201, 168, 76, 140))
        rg.setColorAt(1.0,  QColor(201, 168, 76, 0))
        p.setPen(QPen(QBrush(rg), 1.5))
        p.drawLine(int(r.width() * .15), 1, int(r.width() * .85), 1)
        p.setPen(QPen(_C_BORDER, 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(0, 0, -1, -1), rad, rad)

    def showEvent(self, event) -> None:
        super().showEvent(event)
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

    def _make_home_tab(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        # ── Top row: Welcome card (left) + Stats card (right) ─────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        # Welcome card
        welcome = GlassCard(radius=14)
        w_lay = QVBoxLayout(welcome)
        w_lay.setContentsMargins(20, 20, 20, 20)
        w_lay.setSpacing(3)
        logo_lbl = QLabel()
        if _LOGO.exists():
            px = QPixmap(str(_LOGO)).scaled(
                40, 40,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo_lbl.setPixmap(px)
        logo_lbl.setFixedSize(40, 40)
        w_lay.addWidget(logo_lbl)
        w_lay.addStretch()
        greet_lbl = QLabel("Bienvenue 👋")
        greet_lbl.setStyleSheet(
            "color:#504840; font-size:11px; background:transparent; letter-spacing:0.5px;"
        )
        name_lbl = QLabel("Jimmy")
        name_lbl.setStyleSheet(
            "color:#E8C96A; font-size:24px; font-weight:700; background:transparent;"
        )
        self._home_date_lbl = QLabel()
        self._home_date_lbl.setStyleSheet(
            "color:#8A6A28; font-size:11px; background:transparent;"
        )
        w_lay.addWidget(greet_lbl)
        w_lay.addWidget(name_lbl)
        w_lay.addWidget(self._home_date_lbl)
        welcome.setMinimumHeight(152)

        # Stats card
        stats_card = GlassCard(radius=14)
        s_lay = QVBoxLayout(stats_card)
        s_lay.setContentsMargins(18, 16, 18, 16)
        s_lay.setSpacing(2)
        stats_title = QLabel("ACTIVITÉ")
        stats_title.setStyleSheet(
            "color:#C9A84C; font-size:9px; letter-spacing:1.5px;"
            " font-weight:600; background:transparent;"
        )
        s_lay.addWidget(stats_title)
        sep_line = QLabel()
        sep_line.setFixedHeight(1)
        sep_line.setStyleSheet("background: rgba(201,168,76,0.20); margin: 4px 0;")
        s_lay.addWidget(sep_line)
        self._stat_words = _StatRow("📝", "0",  "mots dictés")
        self._stat_wpm   = _StatRow("⚡", "—",  "mots / min")
        self._stat_days  = _StatRow("📅", "0",  "jours actifs")
        s_lay.addWidget(self._stat_words)
        s_lay.addWidget(self._stat_wpm)
        s_lay.addWidget(self._stat_days)
        s_lay.addStretch()
        stats_card.setMinimumHeight(152)

        top_row.addWidget(welcome, 1)
        top_row.addWidget(stats_card, 1)
        root.addLayout(top_row)

        # ── Bottom row: Historique | Réglages | Performances ───────────────
        nav_row = QHBoxLayout()
        nav_row.setSpacing(12)
        hist_card = _NavTile("📜", "Historique", "Toutes vos transcriptions")
        hist_card.nav_clicked.connect(lambda: self._tabs.setCurrentIndex(1))
        sets_card = _NavTile("⚙️", "Réglages", "Modèles, options")
        sets_card.nav_clicked.connect(lambda: self._tabs.setCurrentIndex(2))
        perf_card = _NavTile("📊", "Performances", "CPU, RAM, threads")
        perf_card.nav_clicked.connect(lambda: self._tabs.setCurrentIndex(3))
        nav_row.addWidget(hist_card, 1)
        nav_row.addWidget(sets_card, 1)
        nav_row.addWidget(perf_card, 1)
        root.addLayout(nav_row)

        root.addStretch()
        scroll.setWidget(container)
        self._refresh_home()
        return scroll

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
            f"{_DAYS_FR[today.weekday()]} {today.day}"
            f" {_MONTHS_FR[today.month - 1]} {today.year}"
        )
        words, wpm, days = self._compute_stats()
        self._stat_words.set_value(_fmt_k(words))
        self._stat_wpm.set_value(f"{wpm:.0f}" if wpm > 0 else "—")
        self._stat_days.set_value(str(days))

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
