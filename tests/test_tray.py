# tests/test_tray.py
import pytest
from unittest.mock import MagicMock
from app.engine.state import AppState


@pytest.fixture
def tray(qapp):
    from app.ui.tray import TrayIcon
    on_history = MagicMock()
    on_settings = MagicMock()
    on_quit = MagicMock()
    t = TrayIcon(on_history=on_history, on_settings=on_settings, on_quit=on_quit)
    yield t
    t.hide()


def test_tray_is_visible(tray):
    assert tray.isVisible()


def test_tray_has_context_menu(tray):
    menu = tray.contextMenu()
    assert menu is not None
    actions = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert any("Historique" in a for a in actions)
    assert any("Réglages" in a for a in actions)
    assert any("Quitter" in a for a in actions)


def test_tray_tooltip_updates_on_state(tray):
    tray.on_state_change(AppState.RECORDING)
    assert "Recording" in tray.toolTip() or "recording" in tray.toolTip().lower()
