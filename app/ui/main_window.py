from __future__ import annotations
import logging
import os
import sys
import psutil
from pathlib import Path
from PyQt6.QtCore import Qt, QPoint, QSize, QTimer
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QGuiApplication, QIcon, QLinearGradient,
    QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidgetItem,
    QMainWindow, QPushButton, QSizeGrip,
    QTabWidget, QVBoxLayout, QWidget,
)
from app.ui import theme
import app.ui.glass_card as _gc_mod
from app.ui.history import HistoryWidget
from app.ui.settings import SettingsWidget

_ASSETS      = Path(__file__).parent.parent.parent / "assets"
_LOGO        = _ASSETS / "logo00.png"
_USE_ACRYLIC = False
_C_BG        = QColor(10, 8, 6, 235)
_C_BORDER    = QColor(201, 168, 76, 200)


def _fmt_k(n: int) -> str:
    """Format integer with K/M suffix for large numbers."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


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
                 on_record_toggle=None, on_export=None,
                 on_transcribe_file=None) -> None:
        super().__init__()
        self._settings = settings
        self._on_save_settings = on_save_settings
        self._history_store = history_store
        self._on_record_toggle = on_record_toggle  # callable(current_state) -> None
        self._on_export = on_export
        self._on_transcribe_file = on_transcribe_file

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

        self._bg_cache_timer = QTimer(self)
        self._bg_cache_timer.setSingleShot(True)
        self._bg_cache_timer.timeout.connect(self._rebuild_bg_cache)

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
        """Scale raw background to current window size and push to all bg caches."""
        import app.ui.settings as _settings_mod
        import app.ui.history as _history_mod
        cache = (
            self._raw_bg.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            if not self._raw_bg.isNull() else None
        )
        _gc_mod._bg_pixmap_cache = cache
        _settings_mod._settings_bg_cache = cache
        _history_mod._history_bg_cache = cache

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
        _cache = _gc_mod._bg_pixmap_cache
        if _cache is not None and not _cache.isNull():
            # Centre-crop if scaled bigger than window
            bw, bh = _cache.width(), _cache.height()
            ox = (bw - r.width())  // 2
            oy = (bh - r.height()) // 2
            p.drawPixmap(0, 0, _cache, ox, oy, r.width(), r.height())
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
        self._bg_cache_timer.start(100)

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
        from app.ui.home_tab import build_home_tab
        return build_home_tab(self, on_transcribe_file=self._on_transcribe_file)
    def _make_history_tab(self) -> QWidget:
        self._history_widget = HistoryWidget(
            entries=self._history_store.list(),
            on_delete=self._history_store.delete,
            on_export=self._on_export,
        )
        return self._history_widget

    def _make_settings_tab(self) -> QWidget:
        self._settings_widget = SettingsWidget(
            settings=self._settings,
            on_save=self._on_settings_save,
        )
        return self._settings_widget
    def _make_perf_tab(self) -> QWidget:
        from app.ui.perf_tab import build_perf_tab
        return build_perf_tab(self)

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
        from app.ui.perf_tab import _get_nvml_handle
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
        from app.ui.perf_tab import _hw_detect
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
