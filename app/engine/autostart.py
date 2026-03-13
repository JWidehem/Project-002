import sys
import logging
from pathlib import Path

APP_NAME = "WhisperFlow"
REG_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"


def _pythonw_path() -> str:
    """Return pythonw.exe next to the current interpreter (no console window)."""
    py = Path(sys.executable)
    pythonw = py.parent / "pythonw.exe"
    return str(pythonw) if pythonw.exists() else str(py)


def _main_script() -> str:
    """Absolute path to main.py (two levels up from this file)."""
    return str(Path(__file__).parent.parent.parent / "main.py")


def enable_autostart(_ignored_exe_path: str = "") -> None:
    """Register WhisperFlow in the Windows Startup registry key (no console)."""
    if sys.platform != "win32":
        return
    try:
        import winreg
        value = f'"{_pythonw_path()}" "{_main_script()}"'
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, value)
        winreg.CloseKey(key)
    except Exception as e:
        logging.error(f"Failed to enable autostart: {e}")


def disable_autostart() -> None:
    if sys.platform != "win32":
        return
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass  # key didn't exist, that's fine
    except Exception as e:
        logging.error(f"Failed to disable autostart: {e}")
