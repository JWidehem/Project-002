# tests/test_overlay.py
import queue
import pytest
from app.engine.state import AppState


@pytest.fixture
def overlay(qapp):
    rms_q = queue.Queue()
    from app.ui.overlay import Overlay
    w = Overlay(rms_queue=rms_q)
    yield w
    w.close()


def test_overlay_hidden_in_idle(overlay):
    overlay.on_state_change(AppState.IDLE)
    assert not overlay.isVisible()


def test_overlay_visible_in_recording(overlay):
    overlay.on_state_change(AppState.RECORDING)
    assert overlay.isVisible()


def test_overlay_visible_in_transcribing(overlay):
    overlay.on_state_change(AppState.TRANSCRIBING)
    assert overlay.isVisible()


def test_overlay_has_no_frame(overlay):
    from PyQt6.QtCore import Qt
    flags = overlay.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint


def test_overlay_stays_on_top(overlay):
    from PyQt6.QtCore import Qt
    flags = overlay.windowFlags()
    assert flags & Qt.WindowType.WindowStaysOnTopHint
