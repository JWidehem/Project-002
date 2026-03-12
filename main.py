import atexit
import logging
import os
import queue
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

import psutil
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

from app.engine.paths import DATA_DIR
from app.engine.state import AppState
from app.engine.storage import Settings, History
from app.engine.audio import AudioCapture
from app.engine.transcription import Transcriber
from app.engine.cleanup import clean
from app.engine.injector import inject
from app.engine.hotkeys import HotkeyManager
from app.ui.overlay import Overlay
from app.ui.tray import TrayIcon
from app.ui.settings import SettingsWindow
from app.ui.history import HistoryWindow

LOCKFILE = DATA_DIR / "whisperflow.lock"


def _setup_logging() -> None:
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


def write_lockfile(data_dir: Path) -> None:
    (data_dir / "whisperflow.lock").write_text(str(os.getpid()))


def read_lockfile_pid(data_dir: Path) -> int | None:
    try:
        return int((data_dir / "whisperflow.lock").read_text().strip())
    except Exception:
        return None


def check_single_instance(data_dir: Path) -> bool:
    """Return True if safe to start, False if already running."""
    pid = read_lockfile_pid(data_dir)
    if pid is None:
        write_lockfile(data_dir)
        return True
    if not psutil.pid_exists(pid):
        write_lockfile(data_dir)
        return True
    return False  # another instance is running


def _remove_lockfile() -> None:
    try:
        LOCKFILE.unlink(missing_ok=True)
    except Exception:
        pass


class App:
    def __init__(self, qt_app: QApplication) -> None:
        self._qt_app = qt_app
        self._settings_store = Settings(DATA_DIR)
        self._history_store = History(DATA_DIR)
        self._settings = self._settings_store.load()

        self._state = AppState()
        self._rms_queue: queue.Queue = queue.Queue(maxsize=60)

        self._audio = AudioCapture(self._rms_queue, on_max_duration=self._on_max_duration)
        self._transcriber = Transcriber(self._settings["model"])

        self._overlay = Overlay(self._rms_queue)
        self._tray = TrayIcon(
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

        self._state.state_changed.connect(self._overlay.on_state_change)
        self._state.state_changed.connect(self._tray.on_state_change)

        self._hotkeys.start()
        if self._hotkeys.conflict_detected:
            logging.warning("Hotkey conflict detected on startup")

        if self._settings.get("preload_model"):
            self._transcriber._ensure_loaded()

    def _on_max_duration(self) -> None:
        """Called from audio thread when 5min limit is reached."""
        self._stop_recording()

    def _start_recording(self) -> None:
        if self._state.current() != AppState.IDLE:
            return
        self._transcriber.reset_cancel()
        self._state.transition(AppState.RECORDING)
        self._audio.start()

    def _stop_recording(self) -> None:
        if self._state.current() != AppState.RECORDING:
            return
        audio = self._audio.stop()
        if audio is None:
            self._state.transition(AppState.IDLE)
            return
        self._state.transition(AppState.TRANSCRIBING)
        self._run_transcription(audio)

    def _run_transcription(self, audio) -> None:
        def _worker():
            try:
                text = self._transcriber.transcribe(
                    audio,
                    language=self._settings["language"],
                    glossary=self._settings.get("glossary", []),
                )
                if text:
                    text = clean(
                        text,
                        level=self._settings.get("cleanup_level", "light"),
                        filler_words=self._settings.get("filler_words", []),
                    )
                    inject(text)
                    self._history_store.save(
                        raw=text, clean=text, duration=len(audio) / 16000
                    )
            except Exception as e:
                logging.error(f"Transcription error: {e}")
            finally:
                if self._state.current() == AppState.TRANSCRIBING:
                    self._state.transition(AppState.IDLE)
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
        self._settings = new_settings
        self._hotkeys.configure(
            new_settings["hotkey_hold"],
            new_settings["hotkey_toggle"],
        )
        self._hotkeys.start()
        # Wire autostart (imported late to avoid circular issues)
        from app.engine.autostart import enable_autostart, disable_autostart
        if new_settings.get("autostart"):
            enable_autostart(sys.executable)
        else:
            disable_autostart()

    def _show_history(self) -> None:
        entries = self._history_store.list()
        win = HistoryWindow(entries=entries, on_delete=self._history_store.delete)
        win.exec()


def main() -> None:
    _setup_logging()
    if not check_single_instance(DATA_DIR):
        # Another instance running — show balloon and exit
        qt_app = QApplication(sys.argv)
        tray = TrayIcon(on_history=qt_app.quit, on_settings=qt_app.quit, on_quit=qt_app.quit)
        tray.showMessage("WhisperFlow", "Already running.", QSystemTrayIcon.MessageIcon.Information, 2000)
        qt_app.quit()
        return

    atexit.register(_remove_lockfile)
    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)
    App(qt_app)
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
