import sys
import logging

APP_NAME = "WhisperFlow"
REG_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"


def enable_autostart(exe_path: str) -> None:
    if sys.platform != "win32":
        return
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, exe_path)
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
