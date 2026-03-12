import time
import pyperclip
import keyboard


def inject(text: str) -> None:
    """Inject text into the active field via clipboard+paste, fallback to typing."""
    try:
        previous = pyperclip.paste()
        pyperclip.copy(text)
        keyboard.send("ctrl+v")
        time.sleep(0.1)
        pyperclip.copy(previous)
    except Exception:
        keyboard.type(text)
