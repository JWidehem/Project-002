# tests/test_settings_ui.py
import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QDialog
from PyQt6.QtCore import Qt


@pytest.fixture
def settings_data():
    return {
        "language": "fr",
        "model": "small",
        "preload_model": False,
        "hotkey_hold": "<ctrl>+<shift>+<space>",
        "hotkey_toggle": "<ctrl>+<shift>+d",
        "cleanup_level": "light",
        "filler_words": ["euh", "hum"],
        "glossary": [],
        "autostart": False,
    }


@pytest.fixture
def settings_win(qapp, settings_data):
    from app.ui.settings import SettingsWindow
    on_save = MagicMock()
    win = SettingsWindow(settings=settings_data, on_save=on_save)
    yield win, on_save
    win.close()


def test_settings_window_is_dialog(settings_win):
    win, _ = settings_win
    assert isinstance(win, QDialog)


def test_settings_window_shows_current_language(settings_win):
    win, _ = settings_win
    assert win.language_combo.currentText() in ("fr", "Français", "French")


def test_settings_window_save_calls_callback(settings_win, qtbot):
    win, on_save = settings_win
    qtbot.mouseClick(win.save_btn, Qt.MouseButton.LeftButton)  # left click
    on_save.assert_called_once()


def test_settings_window_save_returns_dict(settings_win, qtbot):
    win, on_save = settings_win
    qtbot.mouseClick(win.save_btn, Qt.MouseButton.LeftButton)
    saved = on_save.call_args[0][0]
    assert isinstance(saved, dict)
    assert "language" in saved
