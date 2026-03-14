import atexit
import logging
import os
import queue
import sys
import threading
import warnings
from logging.handlers import RotatingFileHandler
from pathlib import Path

import psutil

# ctranslate2 / Intel MKL DLLs MUST be loaded before PyQt6 DLLs on Windows.
# If Qt initialises its thread infrastructure first, MKL's own thread-pool
# startup causes an access violation (0xC0000005).  Importing Transcriber here
# pulls in faster-whisper → ctranslate2 → MKL before any Qt code is loaded.
from app.engine.transcription import Transcriber  # noqa: E402 (intentional early import)

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon


class _Notifier(QObject):
    """QObject used solely to emit notifications cross-thread safely."""
    notification = pyqtSignal(str, str)

from app.engine.paths import DATA_DIR
from app.engine.state import AppState
from app.engine.storage import Settings, History
from app.engine.audio import AudioCapture, SAMPLE_RATE
from app.engine.cleanup import clean
from app.engine.injector import inject
from app.engine.hotkeys import HotkeyManager
from app.ui.overlay import Overlay
from app.ui.tray import TrayIcon
from app.ui.settings import SettingsWindow
from app.ui.history import HistoryWindow
from app.ui.main_window import MainWindow

LOCKFILE = DATA_DIR / "whisperflow.lock"


def _setup_logging() -> None:
    # Suppress noisy HuggingFace warnings about Windows symlinks
    warnings.filterwarnings("ignore", message=".*symlinks.*", category=UserWarning)
    warnings.filterwarnings("ignore", message=".*cache.*", category=FutureWarning)

    handler = RotatingFileHandler(
        DATA_DIR / "whisperflow.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=1,
        encoding="utf-8",
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=[handler],
    )
    # Silence verbose HTTP logs from huggingface_hub
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def write_lockfile(data_dir: Path) -> None:
    (data_dir / "whisperflow.lock").write_text(str(os.getpid()))


def read_lockfile_pid(data_dir: Path) -> int | None:
    try:
        return int((data_dir / "whisperflow.lock").read_text().strip())
    except Exception:
        return None


def check_single_instance(data_dir: Path) -> bool:
    """Return True if safe to start, False if already running.

    Writes the PID lockfile atomically when claiming the slot.
    """
    pid = read_lockfile_pid(data_dir)
    if pid is not None and pid != os.getpid():
        # Verify the stored PID is still a live WhisperFlow/Python process
        alive = False
        try:
            if psutil.pid_exists(pid):
                proc_name = psutil.Process(pid).name().lower()
                if "python" in proc_name or "whisperflow" in proc_name:
                    alive = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        if alive:
            return False  # another WhisperFlow instance is genuinely running
    # No live instance found — claim the lockfile
    write_lockfile(data_dir)
    return True


def _remove_lockfile() -> None:
    try:
        LOCKFILE.unlink(missing_ok=True)
    except Exception:
        pass


class App:
    def __init__(self, qt_app: QApplication, transcriber: "Transcriber | None" = None) -> None:
        self._qt_app = qt_app
        self._settings_store = Settings(DATA_DIR)
        self._history_store = History(DATA_DIR)
        self._settings = self._settings_store.load()

        self._state = AppState()
        self._rms_queue: queue.Queue = queue.Queue(maxsize=60)

        self._audio = AudioCapture(
            self._rms_queue,
            on_max_duration=self._on_max_duration,
            device=self._settings.get("audio_device"),
        )
        # Reuse pre-loaded transcriber if provided (MKL already initialized before Qt).
        self._transcriber = transcriber or Transcriber(
            self._settings["model"],
            compute_device=self._settings.get("compute_device", "cpu"),
        )

        self._overlay = Overlay(self._rms_queue)

        self._main_window = MainWindow(
            settings=self._settings,
            on_save_settings=self._apply_settings,
            history_store=self._history_store,
            on_record_toggle=self._toggle_recording,
        )

        self._tray = TrayIcon(
            on_open=self._main_window.show_and_raise,
            on_history=self._show_history,
            on_settings=self._show_settings,
            on_quit=qt_app.quit,
        )

        self._hotkeys = HotkeyManager(
            on_start=self._start_recording,
            on_stop=self._stop_recording,
            on_cancel=self._cancel,
        )
        self._hotkeys.set_state(self._state)
        self._hotkeys.configure(
            self._settings["hotkey_hold"],
            self._settings["hotkey_toggle"],
        )

        self._notifier = _Notifier()
        self._notifier.notification.connect(self._tray.notify)

        self._state.state_changed.connect(self._overlay.on_state_change)
        self._state.state_changed.connect(self._tray.on_state_change)
        self._state.state_changed.connect(self._main_window.update_state)

        self._hotkeys.start()
        if self._hotkeys.conflict_detected:
            logging.warning("Hotkey conflict detected on startup")

    def _notify(self, title: str, message: str) -> None:
        """Thread-safe tray notification via pyqtSignal (works from any thread)."""
        self._notifier.notification.emit(title, message)

    def _toggle_recording(self) -> None:
        """Called from the UI dictation button — toggle start/stop."""
        state = self._state.current()
        if state == AppState.IDLE:
            self._start_recording()
        elif state == AppState.RECORDING:
            self._stop_recording()
        # TRANSCRIBING: ignore (button is disabled anyway)

    def _on_max_duration(self) -> None:
        """Called from audio thread when 5min limit is reached."""
        self._stop_recording()

    def _start_recording(self) -> None:
        if self._state.current() != AppState.IDLE:
            return
        self._transcriber.reset_cancel()
        self._state.transition(AppState.RECORDING)
        try:
            self._audio.start()
            logging.info("Recording started")
        except Exception as e:
            logging.error(f"Audio start error: {e}")
            self._notify("WhisperFlow", f"Microphone error: {e}")
            self._state.transition(AppState.IDLE)

    def _stop_recording(self) -> None:
        if self._state.current() != AppState.RECORDING:
            return
        audio = self._audio.stop()
        if audio is None:
            logging.info("Recording discarded (too short < 300ms)")
            self._notify("WhisperFlow", "Enregistrement trop court — maintenez la touche enfoncée")
            self._state.transition(AppState.IDLE)
            return
        duration = len(audio) / SAMPLE_RATE
        logging.info(f"Recording stopped: {duration:.1f}s of audio")
        self._state.transition(AppState.TRANSCRIBING)
        self._run_transcription(audio)

    def _run_transcription(self, audio) -> None:
        def _worker():
            try:
                import numpy as np
                rms = float(np.sqrt(np.mean(audio ** 2)))
                logging.info(f"Transcription started — audio: {len(audio)} samples, RMS={rms:.4f}")
                text = self._transcriber.transcribe(
                    audio,
                    language=self._settings["language"],
                    glossary=self._settings.get("glossary", []),
                )
                logging.info(f"Transcription result: {repr(text)}")
                if text:
                    raw_text = text
                    text = clean(
                        text,
                        level=self._settings.get("cleanup_level", "light"),
                        filler_words=self._settings.get("filler_words", []),
                    )
                    inject(text)
                    self._history_store.save(
                        raw=raw_text, clean=text, duration=len(audio) / SAMPLE_RATE
                    )
                    logging.info(f"Injected: {repr(text)}")
                else:
                    logging.warning("Transcription returned empty (no speech detected or cancelled)")
                    self._notify("WhisperFlow", "Aucune parole détectée — vérifiez votre microphone")
            except Exception as e:
                logging.error(f"Transcription error: {e}", exc_info=True)
                self._notify("WhisperFlow", f"Erreur de transcription: {e}")
            finally:
                if self._state.current() == AppState.TRANSCRIBING:
                    self._state.transition(AppState.IDLE)
                logging.info("Worker thread finished")
        threading.Thread(target=_worker, daemon=True).start()

    def _cancel(self) -> None:
        self._transcriber.cancel()
        if self._state.current() == AppState.RECORDING:
            self._audio.stop()
        if self._state.current() in (AppState.RECORDING, AppState.TRANSCRIBING):
            self._state.transition(AppState.IDLE)

    def _show_settings(self) -> None:
        win = SettingsWindow(settings=self._settings, on_save=self._apply_settings)
        if self._hotkeys.conflict_detected:
            win.show_conflict("\u26a0 Conflit d\u00e9tect\u00e9")
        win.exec()

    def _apply_settings(self, new_settings: dict) -> None:
        self._settings_store.save(new_settings)
        if new_settings.get("model") != self._settings.get("model") \
                or new_settings.get("compute_device") != self._settings.get("compute_device"):
            self._transcriber = Transcriber(
                new_settings["model"],
                compute_device=new_settings.get("compute_device", "cpu"),
            )
        if new_settings.get("audio_device") != self._settings.get("audio_device"):
            self._audio.set_device(new_settings.get("audio_device"))
        self._settings = new_settings
        self._main_window.update_settings(new_settings)
        self._hotkeys.configure(
            new_settings["hotkey_hold"],
            new_settings["hotkey_toggle"],
        )
        self._hotkeys.start()
        # Wire autostart (imported late to avoid circular issues)
        from app.engine.autostart import enable_autostart, disable_autostart
        if new_settings.get("autostart"):
            enable_autostart()  # path resolved inside autostart.py
        else:
            disable_autostart()

    def _show_history(self) -> None:
        entries = self._history_store.list()
        win = HistoryWindow(entries=entries, on_delete=self._history_store.delete)
        win.exec()


def _repair_shortcut() -> None:
    """Keep the desktop shortcut pointing at pythonw.exe (no console window)."""
    if sys.platform != "win32":
        return
    try:
        from pathlib import Path as _Path
        import subprocess
        pythonw = _Path(sys.executable).parent / "pythonw.exe"
        if not pythonw.exists():
            return
        script = str(_Path(__file__).resolve())
        wdir = str(_Path(__file__).parent)
        ico = _Path(__file__).parent / "assets" / "icone00.ico"
        ico_line = f'$lnk.IconLocation = "{ico},0"' if ico.exists() else ""
        ps = (
            f'$sh = New-Object -ComObject WScript.Shell; '
            f'$d = $sh.SpecialFolders("Desktop"); '
            f'$lnk = $sh.CreateShortcut("$d\\WhisperFlow.lnk"); '
            f'$lnk.TargetPath = "{pythonw}"; '
            f'$lnk.Arguments = \'"{script}"\'; '
            f'$lnk.WorkingDirectory = "{wdir}"; '
            f'$lnk.WindowStyle = 7; '
            f'{ico_line} '
            f'$lnk.Save()'
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, timeout=5
        )
    except Exception as e:
        logging.debug(f"Shortcut repair skipped: {e}")


def main() -> None:
    _setup_logging()
    logging.info("Startup: logging initialized")

    if not check_single_instance(DATA_DIR):
        # Another instance is running — write a signal file so it opens its window
        signal_file = DATA_DIR / "whisperflow.show"
        signal_file.touch()
        logging.info("Second instance: wrote show-signal, exiting")
        return

    # Silently keep the desktop shortcut pointing at pythonw.exe
    _repair_shortcut()

    # ctranslate2/MKL DLLs are already loaded (via the early Transcriber
    # import at the top of this file).  The model is loaded here, before
    # QApplication, so MKL's thread pool is fully initialised before Qt
    # starts its own threading infrastructure.
    logging.info("Startup: loading model")
    _preload_settings = Settings(DATA_DIR).load()
    _preload_transcriber = Transcriber(
        _preload_settings["model"],
        compute_device=_preload_settings.get("compute_device", "cpu"),
    )
    _preload_transcriber._ensure_loaded()
    logging.info("Startup: model loaded — starting Qt")

    atexit.register(_remove_lockfile)
    qt_app = QApplication(sys.argv)
    qt_app.setStyle("Fusion")   # consistent QSS rendering on Windows
    qt_app.setQuitOnLastWindowClosed(False)

    # Set Windows AppUserModelID so the taskbar shows our icon, not Python's
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("WhisperFlow.App.1.0")
    except Exception:
        pass
    _ico = Path(__file__).parent / "assets" / "icone00.ico"
    if _ico.exists():
        qt_app.setWindowIcon(QIcon(str(_ico)))
    elif (Path(__file__).parent / "assets" / "logo00.png").exists():
        qt_app.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "logo00.png")))

    try:
        app = App(qt_app, transcriber=_preload_transcriber)
    except Exception:
        logging.critical("Fatal error during App.__init__", exc_info=True)
        sys.exit(1)

    # Show the main window immediately on first launch
    app._main_window.show_and_raise()

    # Poll for show-window signal from a second instance
    _show_signal = DATA_DIR / "whisperflow.show"
    _show_signal.unlink(missing_ok=True)  # clear any leftover
    from PyQt6.QtCore import QTimer as _QTimer
    _poll = _QTimer()
    def _check_show_signal():
        if _show_signal.exists():
            try:
                _show_signal.unlink(missing_ok=True)
            except Exception:
                pass
            app._main_window.show_and_raise()
    _poll.timeout.connect(_check_show_signal)
    _poll.start(500)  # check every 500ms

    sys.exit(qt_app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import logging as _log
        _log.critical("Unhandled exception in main()", exc_info=True)
        sys.exit(1)
