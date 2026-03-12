# tests/test_autostart.py
import sys
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_enable_autostart_writes_registry(mocker):
    mock_reg = mocker.patch("winreg.OpenKey")
    mock_set = mocker.patch("winreg.SetValueEx")
    from app.engine.autostart import enable_autostart
    enable_autostart("C:\\whisperflow\\whisperflow.exe")
    mock_set.assert_called_once()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_disable_autostart_deletes_registry_value(mocker):
    mock_reg = mocker.patch("winreg.OpenKey")
    mock_del = mocker.patch("winreg.DeleteValue")
    from app.engine.autostart import disable_autostart
    disable_autostart()
    mock_del.assert_called_once()
