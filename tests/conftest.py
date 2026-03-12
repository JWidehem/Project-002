import pytest
from pathlib import Path
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication
import sys


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Redirect DATA_DIR to a temp directory for all storage tests."""
    monkeypatch.setattr("app.engine.paths.DATA_DIR", tmp_path)
    (tmp_path).mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def mock_state():
    from unittest.mock import MagicMock
    from app.engine.state import AppState
    s = MagicMock()
    s.current.return_value = AppState.IDLE
    return s
