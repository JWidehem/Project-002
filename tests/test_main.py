# tests/test_main.py
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path


def test_lockfile_written_on_start(tmp_data_dir, mocker):
    mocker.patch("app.engine.paths.DATA_DIR", tmp_data_dir)
    import os, sys
    from main import write_lockfile, read_lockfile_pid
    write_lockfile(tmp_data_dir)
    pid = read_lockfile_pid(tmp_data_dir)
    assert pid == os.getpid()


def test_stale_lockfile_overwritten(tmp_data_dir):
    lockfile = tmp_data_dir / "whisperflow.lock"
    lockfile.write_text("99999999")  # non-existent PID
    from main import check_single_instance
    result = check_single_instance(tmp_data_dir)
    assert result is True  # should continue normally


def test_active_lockfile_signals_already_running(tmp_data_dir, mocker):
    import os
    fake_pid = os.getpid() + 1000  # un PID différent du nôtre
    lockfile = tmp_data_dir / "whisperflow.lock"
    lockfile.write_text(str(fake_pid))
    # Simuler un process python vivant à ce PID
    mocker.patch("psutil.pid_exists", return_value=True)
    mock_proc = mocker.MagicMock()
    mock_proc.name.return_value = "python.exe"
    mocker.patch("psutil.Process", return_value=mock_proc)
    from main import check_single_instance
    result = check_single_instance(tmp_data_dir)
    assert result is False  # already running
