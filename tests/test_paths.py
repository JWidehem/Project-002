# tests/test_paths.py
import sys
from pathlib import Path
from unittest.mock import patch


def test_data_dir_exists_after_import():
    from app.engine.paths import DATA_DIR
    assert DATA_DIR.exists()


def test_data_dir_is_absolute():
    from app.engine.paths import DATA_DIR
    assert DATA_DIR.is_absolute()


def test_data_dir_dev_mode_is_relative_to_project(tmp_path, monkeypatch):
    """In non-frozen mode, DATA_DIR should be inside the project root."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    from importlib import reload
    import app.engine.paths as p
    reload(p)
    assert p.DATA_DIR.name == "data"


def test_data_dir_frozen_mode_is_relative_to_executable(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    fake_exe = tmp_path / "whisperflow.exe"
    fake_exe.touch()
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    from importlib import reload
    import app.engine.paths as p
    reload(p)
    assert p.DATA_DIR == tmp_path / "data"
