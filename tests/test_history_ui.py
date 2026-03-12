# tests/test_history_ui.py
import pytest
from unittest.mock import MagicMock


SAMPLE_ENTRIES = [
    {"id": 2, "created_at": "2026-03-12 15:00:00", "clean_text": "deuxième dictée", "duration_s": 2.1},
    {"id": 1, "created_at": "2026-03-12 14:00:00", "clean_text": "première dictée", "duration_s": 1.5},
]


@pytest.fixture
def history_win(qapp):
    from app.ui.history import HistoryWindow
    on_delete = MagicMock()
    win = HistoryWindow(entries=SAMPLE_ENTRIES, on_delete=on_delete)
    yield win, on_delete
    win.close()


def test_history_window_shows_entries(history_win):
    win, _ = history_win
    assert win.list_widget.count() == len(SAMPLE_ENTRIES)


def test_history_window_newest_first(history_win):
    win, _ = history_win
    first_item = win.list_widget.item(0).text()
    assert "deuxième" in first_item


def test_history_refresh_updates_list(history_win):
    win, _ = history_win
    new_entries = [{"id": 3, "created_at": "2026-03-12 16:00:00", "clean_text": "troisième", "duration_s": 1.0}]
    win.refresh(new_entries)
    assert win.list_widget.count() == 1
