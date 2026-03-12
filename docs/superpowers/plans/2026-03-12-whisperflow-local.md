# WhisperFlow Local Clone — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local voice dictation desktop app for Windows that transcribes speech into any active text field via global hotkeys, with no cloud and no LLM.

**Architecture:** Single Python process with 4 threads (Qt main, hotkeys, audio, ASR). AppState(QObject) is the central state machine passed by dependency injection. UI (PyQt6) communicates with engine via Qt signals.

**Tech Stack:** Python 3.11+, PyQt6, faster-whisper, sounddevice, pynput, pyperclip, keyboard, psutil, pytest, pytest-qt, pytest-mock

**Spec:** `docs/superpowers/specs/2026-03-12-whisperflow-local-design.md`

---

## File Map

| File | Responsibility |
|------|---------------|
| `main.py` | Entry point, DI wiring, lockfile, QApplication |
| `app/engine/paths.py` | DATA_DIR resolution (dev vs packaged) |
| `app/engine/state.py` | AppState(QObject), state machine, signals |
| `app/engine/storage.py` | Settings JSON + SQLite history (rotation 500) |
| `app/engine/cleanup.py` | Text post-processing (3 levels, no LLM) |
| `app/engine/injector.py` | Clipboard + Ctrl+V injection, keyboard fallback |
| `app/engine/audio.py` | sounddevice capture, RMS queue, PCM buffer |
| `app/engine/transcription.py` | faster-whisper wrapper, lazy load, cancel event |
| `app/engine/hotkeys.py` | pynput GlobalHotKeys, conflict detection |
| `app/ui/overlay.py` | Frameless recording indicator + RMS visualizer |
| `app/ui/tray.py` | System tray icon + context menu |
| `app/ui/settings.py` | Settings window (5 sections) |
| `app/ui/history.py` | History window (list + copy/delete) |
| `tests/conftest.py` | pytest fixtures (qapp, tmp_data_dir, mock_state) |
| `tests/test_paths.py` | DATA_DIR resolution |
| `tests/test_state.py` | State machine transitions |
| `tests/test_storage.py` | Settings load/save/defaults, history CRUD |
| `tests/test_cleanup.py` | All 3 cleanup levels + edge cases |
| `tests/test_injector.py` | Clipboard path + exception fallback |
| `tests/test_audio.py` | Buffer accumulation, min/max duration guards |
| `tests/test_transcription.py` | Transcribe call, cancel, glossary prompt |
| `tests/test_hotkeys.py` | Mode routing (hold/toggle/cancel) |
| `requirements.txt` | Pinned dependencies |
| `pytest.ini` | Test configuration |

---

## Chunk 1: Foundation

### Task 1: Project bootstrap

**Files:**
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `tests/conftest.py`
- Create: `app/__init__.py`, `app/engine/__init__.py`, `app/ui/__init__.py`

- [ ] **Step 1: Create directory structure**

```bash
cd D:/Project-002
mkdir -p app/engine app/ui tests assets data
touch app/__init__.py app/engine/__init__.py app/ui/__init__.py tests/__init__.py
```

- [ ] **Step 2: Create `requirements.txt`**

```
faster-whisper==1.1.1
sounddevice==0.5.1
numpy==1.26.4
PyQt6==6.7.1
pynput==1.7.7
pyperclip==1.9.0
keyboard==0.13.5
psutil==6.1.0
pytest==8.3.4
pytest-qt==4.4.0
pytest-mock==3.14.0
```

- [ ] **Step 3: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
qt_api = pyqt6
filterwarnings =
    ignore::DeprecationWarning
```

- [ ] **Step 4: Create `tests/conftest.py`**

```python
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
```

- [ ] **Step 5: Install dependencies**

```bash
pip install -r requirements.txt
```

- [ ] **Step 6: Verify pytest runs**

```bash
pytest --collect-only
```
Expected: "no tests ran" with no errors.

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "chore: bootstrap project structure and dependencies"
```

---

### Task 2: `paths.py` — DATA_DIR resolution

**Files:**
- Create: `app/engine/paths.py`
- Create: `tests/test_paths.py`

- [ ] **Step 1: Write failing test**

```python
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
```

- [ ] **Step 2: Run test to confirm failure**

```bash
pytest tests/test_paths.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.engine.paths'`

- [ ] **Step 3: Implement `app/engine/paths.py`**

```python
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    DATA_DIR = Path(sys.executable).parent / "data"
else:
    DATA_DIR = Path(__file__).parent.parent.parent / "data"

DATA_DIR.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_paths.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/engine/paths.py tests/test_paths.py
git commit -m "feat: add DATA_DIR resolution (dev vs packaged)"
```

---

### Task 3: `state.py` — AppState state machine

**Files:**
- Create: `app/engine/state.py`
- Create: `tests/test_state.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_state.py
import pytest
from app.engine.state import AppState


@pytest.fixture
def state(qapp):
    return AppState()


def test_initial_state_is_idle(state):
    assert state.current() == AppState.IDLE


def test_idle_to_recording(state):
    state.transition(AppState.RECORDING)
    assert state.current() == AppState.RECORDING


def test_recording_to_transcribing(state):
    state.transition(AppState.RECORDING)
    state.transition(AppState.TRANSCRIBING)
    assert state.current() == AppState.TRANSCRIBING


def test_recording_to_idle_allowed(state):
    state.transition(AppState.RECORDING)
    state.transition(AppState.IDLE)
    assert state.current() == AppState.IDLE


def test_transcribing_to_idle(state):
    state.transition(AppState.RECORDING)
    state.transition(AppState.TRANSCRIBING)
    state.transition(AppState.IDLE)
    assert state.current() == AppState.IDLE


def test_invalid_transition_raises(state):
    with pytest.raises(ValueError, match="Invalid transition"):
        state.transition(AppState.TRANSCRIBING)  # IDLE → TRANSCRIBING invalid


def test_state_changed_signal_emitted(state, qtbot):
    with qtbot.waitSignal(state.state_changed, timeout=1000) as blocker:
        state.transition(AppState.RECORDING)
    assert blocker.args == [AppState.RECORDING]


def test_signal_emits_new_state_name(state, qtbot):
    signals = []
    state.state_changed.connect(signals.append)
    state.transition(AppState.RECORDING)
    state.transition(AppState.TRANSCRIBING)
    state.transition(AppState.IDLE)
    assert signals == [AppState.RECORDING, AppState.TRANSCRIBING, AppState.IDLE]
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_state.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.engine.state'`

- [ ] **Step 3: Implement `app/engine/state.py`**

```python
from PyQt6.QtCore import QObject, pyqtSignal


class AppState(QObject):
    state_changed = pyqtSignal(str)

    IDLE = "IDLE"
    RECORDING = "RECORDING"
    TRANSCRIBING = "TRANSCRIBING"

    _VALID_TRANSITIONS: dict[str, set[str]] = {
        IDLE:         {RECORDING},
        RECORDING:    {TRANSCRIBING, IDLE},
        TRANSCRIBING: {IDLE},
    }

    def __init__(self) -> None:
        super().__init__()
        self._current: str = self.IDLE

    def transition(self, new_state: str) -> None:
        allowed = self._VALID_TRANSITIONS.get(self._current, set())
        if new_state not in allowed:
            raise ValueError(
                f"Invalid transition: {self._current} -> {new_state}"
            )
        self._current = new_state
        self.state_changed.emit(new_state)

    def current(self) -> str:
        return self._current
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_state.py -v
```
Expected: all 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/engine/state.py tests/test_state.py
git commit -m "feat: add AppState machine with Qt signals"
```

---

### Task 4: `storage.py` — Settings + History

**Files:**
- Create: `app/engine/storage.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_storage.py
import pytest
import json
from app.engine.storage import Settings, History


# --- Settings ---

@pytest.fixture
def settings(tmp_data_dir):
    return Settings(tmp_data_dir)


def test_settings_defaults_on_first_load(settings):
    s = settings.load()
    assert s["language"] == "fr"
    assert s["model"] == "small"
    assert s["cleanup_level"] == "light"
    assert s["autostart"] is False


def test_settings_save_and_reload(settings):
    s = settings.load()
    s["language"] = "en"
    settings.save(s)
    reloaded = settings.load()
    assert reloaded["language"] == "en"


def test_settings_recreated_on_corrupt_file(tmp_data_dir):
    path = tmp_data_dir / "settings.json"
    path.write_text("not valid json")
    s = Settings(tmp_data_dir)
    loaded = s.load()
    assert loaded["language"] == "fr"  # defaults restored


# --- History ---

@pytest.fixture
def history(tmp_data_dir):
    return History(tmp_data_dir)


def test_history_save_and_list(history):
    history.save(raw="euh bonjour", clean="bonjour", duration=1.2)
    entries = history.list()
    assert len(entries) == 1
    assert entries[0]["clean_text"] == "bonjour"
    assert entries[0]["duration_s"] == pytest.approx(1.2)


def test_history_list_is_newest_first(history):
    history.save(raw="first", clean="first", duration=1.0)
    history.save(raw="second", clean="second", duration=1.0)
    entries = history.list()
    assert entries[0]["clean_text"] == "second"


def test_history_delete(history):
    history.save(raw="x", clean="x", duration=1.0)
    entry_id = history.list()[0]["id"]
    history.delete(entry_id)
    assert history.list() == []


def test_history_rotation_at_500(history):
    for i in range(505):
        history.save(raw=f"r{i}", clean=f"c{i}", duration=0.5)
    entries = history.list()
    assert len(entries) == 500
    # newest are kept
    assert entries[0]["clean_text"] == "c504"
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_storage.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/engine/storage.py`**

```python
import json
import sqlite3
from pathlib import Path

DEFAULTS: dict = {
    "language": "fr",
    "model": "small",
    "preload_model": False,
    "hotkey_hold": "<ctrl>+<shift>+<space>",
    "hotkey_toggle": "<ctrl>+<shift>+d",
    "cleanup_level": "light",
    "filler_words": ["euh", "hum", "ben", "voilà", "enfin"],
    "glossary": [],
    "autostart": False,
}

MAX_HISTORY = 500


class Settings:
    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "settings.json"

    def load(self) -> dict:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            # Merge with defaults to handle missing keys
            return {**DEFAULTS, **data}
        except Exception:
            return dict(DEFAULTS)

    def save(self, data: dict) -> None:
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


class History:
    def __init__(self, data_dir: Path) -> None:
        self._db_path = data_dir / "history.db"
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    raw_text   TEXT,
                    clean_text TEXT,
                    duration_s REAL
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._db_path)
        con.row_factory = sqlite3.Row
        return con

    def save(self, raw: str, clean: str, duration: float) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT INTO history (raw_text, clean_text, duration_s) VALUES (?, ?, ?)",
                (raw, clean, duration),
            )
            # Rotate: keep only the MAX_HISTORY most recent entries
            con.execute("""
                DELETE FROM history WHERE id NOT IN (
                    SELECT id FROM history ORDER BY id DESC LIMIT ?
                )
            """, (MAX_HISTORY,))

    def list(self) -> list[dict]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM history ORDER BY id DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete(self, entry_id: int) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM history WHERE id = ?", (entry_id,))
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_storage.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/engine/storage.py tests/test_storage.py
git commit -m "feat: add Settings and History storage"
```

---

## Chunk 2: Engine Core

### Task 5: `cleanup.py` — Text post-processing

**Files:**
- Create: `app/engine/cleanup.py`
- Create: `tests/test_cleanup.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cleanup.py
from app.engine.cleanup import clean

FILLERS = ["euh", "hum", "ben", "voilà"]


def test_level_none_returns_unchanged():
    assert clean("euh bonjour", level="none", filler_words=FILLERS) == "euh bonjour"


def test_removes_filler_words(  ):
    result = clean("euh bonjour hum", level="light", filler_words=FILLERS)
    assert "euh" not in result
    assert "hum" not in result
    assert "bonjour" in result


def test_filler_removal_case_insensitive():
    result = clean("EUH bonjour", level="light", filler_words=FILLERS)
    assert result.strip().lower() == "bonjour"


def test_deduplication_removes_immediate_repeat():
    result = clean("le le chat", level="light", filler_words=[])
    assert result == "le chat"


def test_deduplication_three_repeats():
    result = clean("et et et donc", level="light", filler_words=[])
    assert result == "et donc"


def test_deduplication_is_case_insensitive():
    result = clean("Le le chat", level="light", filler_words=[])
    assert "le le" not in result.lower()


def test_level_medium_fixes_punctuation_spacing():
    result = clean("bonjour , comment vas-tu ?", level="medium", filler_words=[])
    assert result == "bonjour, comment vas-tu?"


def test_level_medium_capitalizes_after_period():
    result = clean("bonjour. comment vas-tu.", level="medium", filler_words=[])
    assert "B" in result[0]  # first char capitalized


def test_empty_filler_list_does_not_crash():
    result = clean("bonjour", level="light", filler_words=[])
    assert result == "bonjour"


def test_empty_text_returns_empty():
    assert clean("", level="medium", filler_words=FILLERS) == ""
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_cleanup.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/engine/cleanup.py`**

```python
import re

_LEVELS: dict[str, list[int]] = {
    "none":   [],
    "light":  [1, 2],
    "medium": [1, 2, 3],
}


def clean(
    text: str,
    level: str = "light",
    filler_words: list[str] | None = None,
) -> str:
    if not text:
        return text

    passes = _LEVELS.get(level, _LEVELS["light"])

    # Pass 1: remove filler words
    if 1 in passes and filler_words:
        pattern = r'\b(' + "|".join(re.escape(w) for w in filler_words) + r')\b'
        text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.UNICODE)
        text = re.sub(r" {2,}", " ", text).strip()

    # Pass 2: deduplicate immediate repetitions
    if 2 in passes:
        text = re.sub(
            r"\b(\w+)(\s+\1)+\b", r"\1", text,
            flags=re.IGNORECASE | re.UNICODE,
        )

    # Pass 3: punctuation normalisation
    if 3 in passes:
        text = re.sub(r"\s+([,\.!?])", r"\1", text)
        text = re.sub(
            r"([\.!?])\s+(\w)",
            lambda m: m.group(1) + " " + m.group(2).upper(),
            text,
        )
        if text:
            text = text[0].upper() + text[1:]

    return text.strip()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_cleanup.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/engine/cleanup.py tests/test_cleanup.py
git commit -m "feat: add text cleanup (3 levels, no LLM)"
```

---

### Task 6: `injector.py` — Text injection

**Files:**
- Create: `app/engine/injector.py`
- Create: `tests/test_injector.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_injector.py
from unittest.mock import patch, MagicMock, call


def test_clipboard_path_used_by_default(mocker):
    mock_paste = mocker.patch("pyperclip.paste", return_value="previous")
    mock_copy = mocker.patch("pyperclip.copy")
    mock_send = mocker.patch("keyboard.send")
    mocker.patch("time.sleep")

    from app.engine.injector import inject
    inject("hello")

    mock_copy.assert_any_call("hello")
    mock_send.assert_called_once_with("ctrl+v")


def test_previous_clipboard_restored(mocker):
    mocker.patch("pyperclip.paste", return_value="old content")
    mock_copy = mocker.patch("pyperclip.copy")
    mocker.patch("keyboard.send")
    mocker.patch("time.sleep")

    from app.engine.injector import inject
    inject("new text")

    calls = mock_copy.call_args_list
    assert calls[-1] == call("old content")


def test_fallback_keyboard_type_on_pyperclip_exception(mocker):
    mocker.patch("pyperclip.paste", side_effect=Exception("no clipboard"))
    mock_type = mocker.patch("keyboard.type")

    from app.engine.injector import inject
    inject("fallback text")

    mock_type.assert_called_once_with("fallback text")


def test_fallback_on_copy_exception(mocker):
    mocker.patch("pyperclip.paste", return_value="x")
    mocker.patch("pyperclip.copy", side_effect=Exception("clipboard error"))
    mock_type = mocker.patch("keyboard.type")

    from app.engine.injector import inject
    inject("text")

    mock_type.assert_called_once_with("text")
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_injector.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/engine/injector.py`**

```python
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_injector.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/engine/injector.py tests/test_injector.py
git commit -m "feat: add text injector (clipboard + keyboard fallback)"
```

---

### Task 7: `audio.py` — PCM capture

**Files:**
- Create: `app/engine/audio.py`
- Create: `tests/test_audio.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_audio.py
import queue
import numpy as np
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def rms_queue():
    return queue.Queue()


def test_audio_capture_accumulates_chunks(rms_queue, mocker):
    mocker.patch("sounddevice.InputStream")
    from app.engine.audio import AudioCapture
    cap = AudioCapture(rms_queue)
    cap.start()

    # Simulate callback calls
    chunk = np.ones((512, 1), dtype=np.float32) * 0.5
    cap._callback(chunk, 512, None, None)
    cap._callback(chunk, 512, None, None)

    result = cap.stop()
    assert result is not None
    assert len(result) == 1024  # 512 * 2


def test_audio_capture_returns_none_if_too_short(rms_queue, mocker):
    mocker.patch("sounddevice.InputStream")
    from app.engine.audio import AudioCapture, MIN_DURATION_S, SAMPLE_RATE
    cap = AudioCapture(rms_queue)
    cap.start()

    # Simulate 100ms of audio (below 300ms threshold)
    short_chunk = np.ones((int(0.1 * SAMPLE_RATE), 1), dtype=np.float32)
    cap._callback(short_chunk, len(short_chunk), None, None)

    result = cap.stop()
    assert result is None


def test_audio_capture_pushes_rms_to_queue(rms_queue, mocker):
    mocker.patch("sounddevice.InputStream")
    from app.engine.audio import AudioCapture
    cap = AudioCapture(rms_queue)
    cap.start()

    chunk = np.ones((512, 1), dtype=np.float32) * 0.5
    cap._callback(chunk, 512, None, None)

    assert not rms_queue.empty()
    rms_value = rms_queue.get_nowait()
    assert 0.0 <= rms_value <= 1.0


def test_audio_capture_stops_at_max_duration(rms_queue, mocker):
    mocker.patch("sounddevice.InputStream")
    # Simulate wall-clock past MAX_DURATION: start=0, then callback sees time > MAX
    mocker.patch("app.engine.audio.time.monotonic", side_effect=[0.0, MAX_DURATION_S + 1])
    from app.engine.audio import AudioCapture, MAX_DURATION_S, SAMPLE_RATE
    on_max = mocker.MagicMock()
    cap = AudioCapture(rms_queue, on_max_duration=on_max)
    cap.start()

    chunk = np.zeros((512, 1), dtype=np.float32)
    cap._callback(chunk, 512, None, None)

    result = cap.stop()
    # Short chunk appended before stop guard fired — result is the chunk itself
    assert result is None or isinstance(result, np.ndarray)
    on_max.assert_called_once()


def test_on_max_duration_callback_invoked(rms_queue, mocker):
    mocker.patch("sounddevice.InputStream")
    mocker.patch("app.engine.audio.time.monotonic", side_effect=[0.0, MAX_DURATION_S + 1])
    from app.engine.audio import AudioCapture, MAX_DURATION_S, SAMPLE_RATE
    on_max = mocker.MagicMock()
    cap = AudioCapture(rms_queue, on_max_duration=on_max)
    cap.start()

    chunk = np.zeros((512, 1), dtype=np.float32)
    cap._callback(chunk, 512, None, None)

    on_max.assert_called_once()
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_audio.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/engine/audio.py`**

```python
import queue
import threading
import time
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "float32"
MIN_DURATION_S = 0.3
MAX_DURATION_S = 300.0


class AudioCapture:
    def __init__(self, rms_queue: queue.Queue, on_max_duration=None) -> None:
        self._rms_queue = rms_queue
        self._on_max_duration = on_max_duration
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._start_time: float = 0.0
        self._lock = threading.Lock()
        self._stopped = False

    def start(self) -> None:
        with self._lock:
            self._chunks = []
            self._stopped = False
            self._start_time = time.monotonic()
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                callback=self._callback,
            )
            self._stream.start()

    def stop(self) -> np.ndarray | None:
        with self._lock:
            if self._stream:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            if not self._chunks:
                return None
            audio = np.concatenate(self._chunks).flatten()
        duration = len(audio) / SAMPLE_RATE
        if duration < MIN_DURATION_S:
            return None
        return audio

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info,
        status,
    ) -> None:
        chunk = indata.copy()
        with self._lock:
            if self._stopped:
                return
            elapsed = time.monotonic() - self._start_time
            # Enforce max duration
            if elapsed >= MAX_DURATION_S:
                self._stopped = True
                if self._on_max_duration:
                    self._on_max_duration()
                return
            self._chunks.append(chunk)
        # Push RMS level (clamped 0-1) to visualiser queue
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        rms = min(max(rms, 0.0), 1.0)
        try:
            self._rms_queue.put_nowait(rms)
        except queue.Full:
            pass
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_audio.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/engine/audio.py tests/test_audio.py
git commit -m "feat: add audio capture with RMS queue and duration guards"
```

---

### Task 8: `transcription.py` — faster-whisper wrapper

**Files:**
- Create: `app/engine/transcription.py`
- Create: `tests/test_transcription.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_transcription.py
import numpy as np
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_whisper_model():
    with patch("app.engine.transcription.WhisperModel") as MockModel:
        instance = MockModel.return_value
        seg = MagicMock()
        seg.text = " bonjour"
        instance.transcribe.return_value = ([seg], MagicMock())
        yield instance


def test_transcribe_returns_joined_text(mock_whisper_model):
    from app.engine.transcription import Transcriber
    t = Transcriber("small")
    audio = np.zeros(16000, dtype=np.float32)
    result = t.transcribe(audio, language="fr")
    assert result == "bonjour"


def test_transcribe_passes_language(mock_whisper_model):
    from app.engine.transcription import Transcriber
    t = Transcriber("small")
    audio = np.zeros(16000, dtype=np.float32)
    t.transcribe(audio, language="en")
    call_kwargs = mock_whisper_model.transcribe.call_args[1]
    assert call_kwargs["language"] == "en"


def test_transcribe_passes_glossary_as_initial_prompt(mock_whisper_model):
    from app.engine.transcription import Transcriber
    t = Transcriber("small")
    audio = np.zeros(16000, dtype=np.float32)
    t.transcribe(audio, language="fr", glossary=["PyQt6", "whisper"])
    call_kwargs = mock_whisper_model.transcribe.call_args[1]
    assert "PyQt6" in call_kwargs["initial_prompt"]
    assert "whisper" in call_kwargs["initial_prompt"]


def test_transcribe_no_initial_prompt_when_glossary_empty(mock_whisper_model):
    from app.engine.transcription import Transcriber
    t = Transcriber("small")
    audio = np.zeros(16000, dtype=np.float32)
    t.transcribe(audio, language="fr", glossary=[])
    call_kwargs = mock_whisper_model.transcribe.call_args[1]
    assert "initial_prompt" not in call_kwargs


def test_cancel_returns_none(mock_whisper_model):
    """If cancel() is called before transcribe(), result is None."""
    from app.engine.transcription import Transcriber
    t = Transcriber("small")
    t.cancel()
    audio = np.zeros(16000, dtype=np.float32)
    result = t.transcribe(audio, language="fr")
    assert result is None


def test_reset_cancel_allows_next_transcription(mock_whisper_model):
    from app.engine.transcription import Transcriber
    t = Transcriber("small")
    t.cancel()
    t.reset_cancel()
    audio = np.zeros(16000, dtype=np.float32)
    result = t.transcribe(audio, language="fr")
    assert result == "bonjour"
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_transcription.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/engine/transcription.py`**

```python
import threading
import numpy as np
from faster_whisper import WhisperModel


class Transcriber:
    def __init__(self, model_name: str = "small") -> None:
        self._model_name = model_name
        self._model: WhisperModel | None = None
        self._cancel_event = threading.Event()

    def transcribe(
        self,
        audio: np.ndarray,
        language: str = "fr",
        glossary: list[str] | None = None,
    ) -> str | None:
        if self._cancel_event.is_set():
            return None

        self._ensure_loaded()

        kwargs: dict = {
            "language": language,
            "vad_filter": True,
            "word_timestamps": False,
        }
        if glossary:
            kwargs["initial_prompt"] = "Glossaire: " + ", ".join(glossary)

        segments, _ = self._model.transcribe(audio, **kwargs)  # type: ignore[union-attr]

        if self._cancel_event.is_set():
            return None

        return " ".join(s.text for s in segments).strip()

    def cancel(self) -> None:
        self._cancel_event.set()

    def reset_cancel(self) -> None:
        self._cancel_event.clear()

    def _ensure_loaded(self) -> None:
        if self._model is None:
            self._model = WhisperModel(
                self._model_name,
                device="auto",
                compute_type="auto",
            )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_transcription.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/engine/transcription.py tests/test_transcription.py
git commit -m "feat: add Transcriber wrapper (faster-whisper, cancel, glossary)"
```

---

### Task 9: `hotkeys.py` — Global hotkey manager

**Files:**
- Create: `app/engine/hotkeys.py`
- Create: `tests/test_hotkeys.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_hotkeys.py
import pytest
from unittest.mock import MagicMock, patch, call


@pytest.fixture
def callbacks():
    return {
        "on_start": MagicMock(),
        "on_stop": MagicMock(),
        "on_cancel": MagicMock(),
    }


@pytest.fixture
def mgr(callbacks, mocker):
    mocker.patch("pynput.keyboard.Listener")
    from app.engine.hotkeys import HotkeyManager
    m = HotkeyManager(**callbacks)
    m.configure("<ctrl>+<shift>+<space>", "<ctrl>+<shift>+d")
    return m


def test_hold_press_calls_on_start(mgr, callbacks):
    mgr._on_hold_press()
    callbacks["on_start"].assert_called_once()


def test_hold_release_calls_on_stop(mgr, callbacks):
    mgr._on_hold_release()
    callbacks["on_stop"].assert_called_once()


def test_on_press_triggers_hold_when_all_keys_pressed(mgr, callbacks):
    """Simulate pressing all hold-mode keys (canonical form) in sequence."""
    from pynput.keyboard import Key
    # _parse_hotkey maps <ctrl> → Key.ctrl, <shift> → Key.shift, <space> → Key.space
    mgr._on_press(Key.ctrl)
    mgr._on_press(Key.shift)
    mgr._on_press(Key.space)
    callbacks["on_start"].assert_called_once()


def test_on_release_triggers_hold_stop(mgr, callbacks):
    """Simulate releasing a canonical hold-mode key after hold was active."""
    from pynput.keyboard import Key
    mgr._hold_active = True
    mgr._on_release(Key.ctrl)
    callbacks["on_stop"].assert_called_once()


def test_toggle_when_idle_calls_on_start(mgr, callbacks, mock_state):
    from app.engine.state import AppState
    mock_state.current.return_value = AppState.IDLE
    mgr.set_state(mock_state)
    mgr._on_toggle_press()
    callbacks["on_start"].assert_called_once()


def test_toggle_when_recording_calls_on_stop(mgr, callbacks, mock_state):
    from app.engine.state import AppState
    mock_state.current.return_value = AppState.RECORDING
    mgr.set_state(mock_state)
    mgr._on_toggle_press()
    callbacks["on_stop"].assert_called_once()


def test_toggle_when_transcribing_calls_on_cancel(mgr, callbacks, mock_state):
    from app.engine.state import AppState
    mock_state.current.return_value = AppState.TRANSCRIBING
    mgr.set_state(mock_state)
    mgr._on_toggle_press()
    callbacks["on_cancel"].assert_called_once()


def test_conflict_signal_set_on_listener_exception(callbacks, mocker):
    mocker.patch(
        "pynput.keyboard.Listener",
        side_effect=Exception("device access denied"),
    )
    from app.engine.hotkeys import HotkeyManager
    mgr = HotkeyManager(**callbacks)
    mgr.configure("<ctrl>+<shift>+<space>", "<ctrl>+<shift>+d")
    mgr.start()
    assert mgr.conflict_detected is True
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_hotkeys.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/engine/hotkeys.py`**

```python
import threading
from pynput import keyboard as kb
from app.engine.state import AppState


_CANONICAL_MAP: dict = {
    kb.Key.ctrl_l:  kb.Key.ctrl,
    kb.Key.ctrl_r:  kb.Key.ctrl,
    kb.Key.shift_l: kb.Key.shift,
    kb.Key.shift_r: kb.Key.shift,
    kb.Key.alt_l:   kb.Key.alt,
    kb.Key.alt_r:   kb.Key.alt,
    kb.Key.cmd_l:   kb.Key.cmd,
    kb.Key.cmd_r:   kb.Key.cmd,
}


def _parse_hotkey(hotkey_str: str) -> frozenset:
    """Convert '<ctrl>+<shift>+<space>' to a frozenset of canonical pynput keys."""
    parts = hotkey_str.split("+")
    keys = set()
    for part in parts:
        part = part.strip()
        if part.startswith("<") and part.endswith(">"):
            name = part[1:-1]
            keys.add(kb.Key[name] if hasattr(kb.Key, name) else kb.KeyCode.from_char(name))
        else:
            keys.add(kb.KeyCode.from_char(part))
    return frozenset(keys)


class HotkeyManager:
    def __init__(self, on_start, on_stop, on_cancel) -> None:
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_cancel = on_cancel
        self._state: AppState | None = None
        self._listener: kb.Listener | None = None
        self._hold_keys: frozenset = frozenset()
        self._toggle_keys: frozenset = frozenset()
        self._pressed: set = set()
        self._hold_active = False
        self.conflict_detected = False

    def set_state(self, state: AppState) -> None:
        self._state = state

    def configure(self, hold_key: str, toggle_key: str) -> None:
        self._hold_keys = _parse_hotkey(hold_key)
        self._toggle_keys = _parse_hotkey(toggle_key)

    def start(self) -> None:
        self.stop()
        self.conflict_detected = False
        try:
            self._listener = kb.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
            )
            self._listener.start()
        except Exception:
            self.conflict_detected = True

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None
        self._pressed.clear()
        self._hold_active = False

    # --- Internal handlers ---

    def _canonical(self, key):
        """Normalise left/right modifier variants to their canonical form."""
        return _CANONICAL_MAP.get(key, key)

    def _on_press(self, key) -> None:
        key = self._canonical(key)
        self._pressed.add(key)
        current_set = frozenset(self._pressed)

        if current_set == self._hold_keys and not self._hold_active:
            self._hold_active = True
            self._on_hold_press()
        elif current_set == self._toggle_keys:
            self._on_toggle_press()

    def _on_release(self, key) -> None:
        key = self._canonical(key)
        if self._hold_active and key in self._hold_keys:
            self._hold_active = False
            self._on_hold_release()
        self._pressed.discard(key)

    def _on_hold_press(self) -> None:
        self._on_start()

    def _on_hold_release(self) -> None:
        self._on_stop()

    def _on_toggle_press(self) -> None:
        if self._state is None:
            self._on_start()
            return
        current = self._state.current()
        if current == AppState.IDLE:
            self._on_start()
        elif current == AppState.RECORDING:
            self._on_stop()
        elif current == AppState.TRANSCRIBING:
            self._on_cancel()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_hotkeys.py -v
```
Expected: all PASS.

- [ ] **Step 5: Run full engine test suite**

```bash
pytest tests/ -v --ignore=tests/test_paths.py
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add app/engine/hotkeys.py tests/test_hotkeys.py
git commit -m "feat: add HotkeyManager (hold/toggle/cancel, conflict detection)"
```

---

## Chunk 3: UI

> **Note:** UI tests require a running QApplication. The `qapp` and `qtbot` fixtures from `conftest.py` + pytest-qt handle this. Tests that require a visible display are marked with `@pytest.mark.skipif` for headless CI environments where applicable.

### Task 10: `overlay.py` — Recording indicator

**Files:**
- Create: `app/ui/overlay.py`
- Create: `tests/test_overlay.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_overlay.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/ui/overlay.py`**

```python
import queue
import math
from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtGui import QPainter, QColor, QPen
from PyQt6.QtWidgets import QWidget, QApplication
from app.engine.state import AppState

BAR_COUNT = 12
UPDATE_MS = 33  # ~30fps


class Overlay(QWidget):
    def __init__(self, rms_queue: queue.Queue) -> None:
        super().__init__()
        self._rms_queue = rms_queue
        self._rms_values: list[float] = [0.0] * BAR_COUNT
        self._state = AppState.IDLE

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedSize(380, 48)
        self._position_on_active_screen()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_rms)
        self._timer.start(UPDATE_MS)

    def _position_on_active_screen(self) -> None:
        from PyQt6.QtGui import QCursor
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.right() - self.width() - 16, geo.bottom() - self.height() - 16)

    def on_state_change(self, new_state: str) -> None:
        self._state = new_state
        if new_state == AppState.IDLE:
            self.hide()
        else:
            self._position_on_active_screen()
            self.show()
        self.update()

    def _update_rms(self) -> None:
        updated = False
        while not self._rms_queue.empty():
            try:
                val = self._rms_queue.get_nowait()
                self._rms_values = self._rms_values[1:] + [val]
                updated = True
            except queue.Empty:
                break
        if updated:
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.setBrush(QColor(30, 30, 30, 210))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 10, 10)

        if self._state == AppState.RECORDING:
            self._draw_bars(painter)
        elif self._state == AppState.TRANSCRIBING:
            self._draw_spinner(painter)

    def _draw_bars(self, painter: QPainter) -> None:
        bar_color = QColor(220, 60, 60)
        w = self.width()
        h = self.height()
        bar_w = 4
        spacing = (w - BAR_COUNT * bar_w) // (BAR_COUNT + 1)
        for i, rms in enumerate(self._rms_values):
            bar_h = max(4, int(rms * (h - 12)))
            x = spacing + i * (bar_w + spacing)
            y = (h - bar_h) // 2
            painter.setBrush(bar_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(x, y, bar_w, bar_h, 2, 2)

    def _draw_spinner(self, painter: QPainter) -> None:
        painter.setPen(QPen(QColor(200, 200, 200), 2))
        cx, cy = self.width() // 2, self.height() // 2
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Transcription…")
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_overlay.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/ui/overlay.py tests/test_overlay.py
git commit -m "feat: add Overlay widget (recording bars + transcribing indicator)"
```

---

### Task 11: `tray.py` — System tray

**Files:**
- Create: `app/ui/tray.py`
- Create: `tests/test_tray.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_tray.py -v
```

- [ ] **Step 3: Implement `app/ui/tray.py`**

```python
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QColor, QPixmap
from PyQt6.QtCore import QSize
from app.engine.state import AppState

_STATE_COLORS = {
    AppState.IDLE: QColor(150, 150, 150),
    AppState.RECORDING: QColor(220, 60, 60),
    AppState.TRANSCRIBING: QColor(220, 140, 40),
}


def _make_icon(color: QColor) -> QIcon:
    px = QPixmap(QSize(16, 16))
    px.fill(color)
    return QIcon(px)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, on_history, on_settings, on_quit) -> None:
        super().__init__(_make_icon(_STATE_COLORS[AppState.IDLE]))
        self.setToolTip("WhisperFlow — Idle")
        self.show()

        menu = QMenu()
        menu.addAction("📋 Historique", on_history)
        menu.addAction("⚙️ Réglages", on_settings)
        menu.addSeparator()
        menu.addAction("🚪 Quitter", on_quit)
        self.setContextMenu(menu)

    def on_state_change(self, new_state: str) -> None:
        self.setIcon(_make_icon(_STATE_COLORS.get(new_state, _STATE_COLORS[AppState.IDLE])))
        labels = {
            AppState.IDLE: "Idle",
            AppState.RECORDING: "Recording…",
            AppState.TRANSCRIBING: "Transcribing…",
        }
        self.setToolTip(f"WhisperFlow — {labels.get(new_state, new_state)}")
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_tray.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/ui/tray.py tests/test_tray.py
git commit -m "feat: add system tray icon with state-based color"
```

---

### Task 12: `settings.py` — Settings window

**Files:**
- Create: `app/ui/settings.py`
- Create: `tests/test_settings_ui.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_settings_ui.py
import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QDialog


@pytest.fixture
def settings_data():
    return {
        "language": "fr",
        "model": "small",
        "preload_model": False,
        "hotkey_hold": "<ctrl>+<shift>+<space>",
        "hotkey_toggle": "<ctrl>+<shift>+d",
        "cleanup_level": "light",
        "filler_words": ["euh", "hum"],
        "glossary": [],
        "autostart": False,
    }


@pytest.fixture
def settings_win(qapp, settings_data):
    from app.ui.settings import SettingsWindow
    on_save = MagicMock()
    win = SettingsWindow(settings=settings_data, on_save=on_save)
    yield win, on_save
    win.close()


def test_settings_window_is_dialog(settings_win):
    win, _ = settings_win
    assert isinstance(win, QDialog)


def test_settings_window_shows_current_language(settings_win):
    win, _ = settings_win
    assert win.language_combo.currentText() in ("fr", "Français", "French")


def test_settings_window_save_calls_callback(settings_win, qtbot):
    win, on_save = settings_win
    qtbot.mouseClick(win.save_btn, 1)  # left click
    on_save.assert_called_once()


def test_settings_window_save_returns_dict(settings_win, qtbot):
    win, on_save = settings_win
    qtbot.mouseClick(win.save_btn, 1)
    saved = on_save.call_args[0][0]
    assert isinstance(saved, dict)
    assert "language" in saved
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_settings_ui.py -v
```

- [ ] **Step 3: Implement `app/ui/settings.py`**

```python
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QCheckBox, QLineEdit, QTextEdit, QPushButton, QGroupBox, QFormLayout,
)
from PyQt6.QtCore import Qt

LANGUAGES = [("fr", "Français"), ("en", "English"), ("es", "Español")]
MODELS = ["tiny", "base", "small", "medium", "large-v3"]
CLEANUP_LEVELS = [("none", "Aucun"), ("light", "Léger"), ("medium", "Moyen")]


class SettingsWindow(QDialog):
    def __init__(self, settings: dict, on_save) -> None:
        super().__init__()
        self._on_save = on_save
        self.setWindowTitle("Réglages — WhisperFlow")
        self.setMinimumWidth(440)
        self._build_ui(settings)

    def _build_ui(self, s: dict) -> None:
        layout = QVBoxLayout(self)

        # General
        gen = QGroupBox("Général")
        gen_form = QFormLayout(gen)
        self.autostart_cb = QCheckBox()
        self.autostart_cb.setChecked(s.get("autostart", False))
        self.language_combo = QComboBox()
        for code, label in LANGUAGES:
            self.language_combo.addItem(label, code)
        idx = next((i for i, (c, _) in enumerate(LANGUAGES) if c == s.get("language", "fr")), 0)
        self.language_combo.setCurrentIndex(idx)
        gen_form.addRow("Lancer au démarrage", self.autostart_cb)
        gen_form.addRow("Langue", self.language_combo)
        layout.addWidget(gen)

        # Hotkeys
        hk = QGroupBox("Hotkeys")
        hk_form = QFormLayout(hk)
        self.hold_edit = QLineEdit(s.get("hotkey_hold", ""))
        self.toggle_edit = QLineEdit(s.get("hotkey_toggle", ""))
        self.conflict_label = QLabel("")
        self.conflict_label.setStyleSheet("color: red")
        hk_form.addRow("Mode maintien", self.hold_edit)
        hk_form.addRow("Mode toggle", self.toggle_edit)
        hk_form.addRow("", self.conflict_label)
        layout.addWidget(hk)

        # Model
        mdl = QGroupBox("Modèle")
        mdl_form = QFormLayout(mdl)
        self.model_combo = QComboBox()
        for m in MODELS:
            self.model_combo.addItem(m, m)
        midx = MODELS.index(s.get("model", "small")) if s.get("model", "small") in MODELS else 2
        self.model_combo.setCurrentIndex(midx)
        self.preload_cb = QCheckBox()
        self.preload_cb.setChecked(s.get("preload_model", False))
        mdl_form.addRow("Modèle Whisper", self.model_combo)
        mdl_form.addRow("Charger au démarrage", self.preload_cb)
        layout.addWidget(mdl)

        # Cleanup
        cl = QGroupBox("Nettoyage")
        cl_form = QFormLayout(cl)
        self.cleanup_combo = QComboBox()
        for code, label in CLEANUP_LEVELS:
            self.cleanup_combo.addItem(label, code)
        cidx = next((i for i, (c, _) in enumerate(CLEANUP_LEVELS) if c == s.get("cleanup_level", "light")), 1)
        self.cleanup_combo.setCurrentIndex(cidx)
        self.fillers_edit = QLineEdit(", ".join(s.get("filler_words", [])))
        cl_form.addRow("Niveau", self.cleanup_combo)
        cl_form.addRow("Mots à ignorer", self.fillers_edit)
        layout.addWidget(cl)

        # Glossary
        gl = QGroupBox("Glossaire")
        gl_layout = QVBoxLayout(gl)
        self.glossary_edit = QTextEdit()
        self.glossary_edit.setPlainText("\n".join(s.get("glossary", [])))
        self.glossary_edit.setFixedHeight(80)
        gl_layout.addWidget(self.glossary_edit)
        layout.addWidget(gl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.save_btn = QPushButton("Enregistrer")
        self.save_btn.clicked.connect(self._save)
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

    def _save(self) -> None:
        data = {
            "autostart": self.autostart_cb.isChecked(),
            "language": self.language_combo.currentData(),
            "hotkey_hold": self.hold_edit.text().strip(),
            "hotkey_toggle": self.toggle_edit.text().strip(),
            "model": self.model_combo.currentData(),
            "preload_model": self.preload_cb.isChecked(),
            "cleanup_level": self.cleanup_combo.currentData(),
            "filler_words": [w.strip() for w in self.fillers_edit.text().split(",") if w.strip()],
            "glossary": [w.strip() for w in self.glossary_edit.toPlainText().splitlines() if w.strip()],
        }
        self._on_save(data)
        self.accept()

    def show_conflict(self, message: str) -> None:
        self.conflict_label.setText(message)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_settings_ui.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/ui/settings.py tests/test_settings_ui.py
git commit -m "feat: add SettingsWindow (5 sections, save callback)"
```

---

### Task 13: `history.py` — History window

**Files:**
- Create: `app/ui/history.py`
- Create: `tests/test_history_ui.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_history_ui.py -v
```

- [ ] **Step 3: Implement `app/ui/history.py`**

```python
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel,
)
from PyQt6.QtCore import Qt
import pyperclip


class HistoryWindow(QDialog):
    def __init__(self, entries: list[dict], on_delete) -> None:
        super().__init__()
        self._on_delete = on_delete
        self._entries: list[dict] = []
        self.setWindowTitle("Historique — WhisperFlow")
        self.setMinimumSize(500, 400)
        self._build_ui()
        self.refresh(entries)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Historique des dictées"))
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        self.copy_btn = QPushButton("📋 Copier")
        self.copy_btn.clicked.connect(self._copy_selected)
        self.delete_btn = QPushButton("🗑 Supprimer")
        self.delete_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(self.copy_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def refresh(self, entries: list[dict]) -> None:
        self._entries = entries
        self.list_widget.clear()
        for e in entries:
            dt = e.get("created_at", "")[:16]
            text = e.get("clean_text", "")
            preview = text[:60] + ("…" if len(text) > 60 else "")
            self.list_widget.addItem(f"{dt}  {preview}")

    def _on_row_changed(self, row: int) -> None:
        enabled = 0 <= row < len(self._entries)
        self.copy_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)

    def _copy_selected(self) -> None:
        row = self.list_widget.currentRow()
        if 0 <= row < len(self._entries):
            pyperclip.copy(self._entries[row].get("clean_text", ""))

    def _delete_selected(self) -> None:
        row = self.list_widget.currentRow()
        if 0 <= row < len(self._entries):
            entry_id = self._entries[row]["id"]
            self._on_delete(entry_id)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_history_ui.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/ui/history.py tests/test_history_ui.py
git commit -m "feat: add HistoryWindow (list, copy, delete)"
```

---

## Chunk 4: Integration

### Task 14: `main.py` — Wiring + lockfile + pipeline

**Files:**
- Create: `main.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write failing tests**

```python
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


def test_active_lockfile_signals_already_running(tmp_data_dir):
    import os
    lockfile = tmp_data_dir / "whisperflow.lock"
    lockfile.write_text(str(os.getpid()))  # current PID = alive
    from main import check_single_instance
    result = check_single_instance(tmp_data_dir)
    assert result is False  # already running
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_main.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement `main.py`**

```python
import atexit
import logging
import os
import queue
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import psutil
from PyQt6.QtWidgets import QApplication

from app.engine.paths import DATA_DIR
from app.engine.state import AppState
from app.engine.storage import Settings, History
from app.engine.audio import AudioCapture
from app.engine.transcription import Transcriber
from app.engine.cleanup import clean
from app.engine.injector import inject
from app.engine.hotkeys import HotkeyManager
from app.ui.overlay import Overlay
from app.ui.tray import TrayIcon
from app.ui.settings import SettingsWindow
from app.ui.history import HistoryWindow

LOCKFILE = DATA_DIR / "whisperflow.lock"


def _setup_logging() -> None:
    handler = RotatingFileHandler(
        DATA_DIR / "whisperflow.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=1,
        encoding="utf-8",
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=[handler],
    )


def write_lockfile(data_dir: Path) -> None:
    (data_dir / "whisperflow.lock").write_text(str(os.getpid()))


def read_lockfile_pid(data_dir: Path) -> int | None:
    try:
        return int((data_dir / "whisperflow.lock").read_text().strip())
    except Exception:
        return None


def check_single_instance(data_dir: Path) -> bool:
    """Return True if safe to start, False if already running."""
    pid = read_lockfile_pid(data_dir)
    if pid is None:
        write_lockfile(data_dir)
        return True
    if pid == os.getpid() or not psutil.pid_exists(pid):
        write_lockfile(data_dir)
        return True
    return False  # another instance is running


def _remove_lockfile() -> None:
    try:
        LOCKFILE.unlink(missing_ok=True)
    except Exception:
        pass


class App:
    def __init__(self, qt_app: QApplication) -> None:
        self._qt_app = qt_app
        self._settings_store = Settings(DATA_DIR)
        self._history_store = History(DATA_DIR)
        self._settings = self._settings_store.load()

        self._state = AppState()
        self._rms_queue: queue.Queue = queue.Queue(maxsize=60)

        self._audio = AudioCapture(self._rms_queue)
        self._transcriber = Transcriber(self._settings["model"])

        self._overlay = Overlay(self._rms_queue)
        self._tray = TrayIcon(
            on_history=self._show_history,
            on_settings=self._show_settings,
            on_quit=qt_app.quit,
        )

        self._hotkeys = HotkeyManager(
            on_start=self._start_recording,
            on_stop=self._stop_recording,
            on_cancel=self._cancel,
        )
        self._hotkeys.set_state(self._state)
        self._hotkeys.configure(
            self._settings["hotkey_hold"],
            self._settings["hotkey_toggle"],
        )

        self._state.state_changed.connect(self._overlay.on_state_change)
        self._state.state_changed.connect(self._tray.on_state_change)

        self._hotkeys.start()
        if self._hotkeys.conflict_detected:
            logging.warning("Hotkey conflict detected on startup")

        if self._settings.get("preload_model"):
            self._transcriber._ensure_loaded()

    def _start_recording(self) -> None:
        if self._state.current() != AppState.IDLE:
            return
        self._transcriber.reset_cancel()
        self._state.transition(AppState.RECORDING)
        self._audio.start()

    def _stop_recording(self) -> None:
        if self._state.current() != AppState.RECORDING:
            return
        audio = self._audio.stop()
        if audio is None:
            self._state.transition(AppState.IDLE)
            return
        self._state.transition(AppState.TRANSCRIBING)
        self._run_transcription(audio)

    def _run_transcription(self, audio) -> None:
        import threading
        def _worker():
            try:
                text = self._transcriber.transcribe(
                    audio,
                    language=self._settings["language"],
                    glossary=self._settings.get("glossary", []),
                )
                if text:
                    text = clean(
                        text,
                        level=self._settings.get("cleanup_level", "light"),
                        filler_words=self._settings.get("filler_words", []),
                    )
                    inject(text)
                    self._history_store.save(
                        raw=text, clean=text, duration=len(audio) / 16000
                    )
            except Exception as e:
                logging.error(f"Transcription error: {e}")
            finally:
                if self._state.current() == AppState.TRANSCRIBING:
                    self._state.transition(AppState.IDLE)
        threading.Thread(target=_worker, daemon=True).start()

    def _cancel(self) -> None:
        self._transcriber.cancel()
        if self._state.current() == AppState.RECORDING:
            self._audio.stop()
        self._state.transition(AppState.IDLE)

    def _show_settings(self) -> None:
        win = SettingsWindow(settings=self._settings, on_save=self._apply_settings)
        if self._hotkeys.conflict_detected:
            win.show_conflict("⚠ Conflit détecté")
        win.exec()

    def _apply_settings(self, new_settings: dict) -> None:
        self._settings_store.save(new_settings)
        self._settings = new_settings
        self._hotkeys.configure(
            new_settings["hotkey_hold"],
            new_settings["hotkey_toggle"],
        )
        self._hotkeys.start()

    def _show_history(self) -> None:
        entries = self._history_store.list()
        win = HistoryWindow(entries=entries, on_delete=self._history_store.delete)
        win.exec()


def main() -> None:
    _setup_logging()
    if not check_single_instance(DATA_DIR):
        # Another instance running — show balloon and exit
        # QApplication needed for tray notification
        qt_app = QApplication(sys.argv)
        tray = TrayIcon(on_history=qt_app.quit, on_settings=qt_app.quit, on_quit=qt_app.quit)
        tray.showMessage("WhisperFlow", "Already running.", TrayIcon.MessageIcon.Information, 2000)
        qt_app.quit()
        return

    atexit.register(_remove_lockfile)
    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)
    App(qt_app)
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_main.py -v
```
Expected: all PASS.

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: add main.py with DI wiring, lockfile, pipeline"
```

---

### Task 15: Autostart + smoke test

**Files:**
- Create: `app/engine/autostart.py`
- Create: `tests/test_autostart.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Implement `app/engine/autostart.py`**

```python
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
```

- [ ] **Step 3: Run all tests**

```bash
pytest tests/ -v
```
Expected: all PASS (autostart tests skipped on non-Windows).

- [ ] **Step 4: Wire autostart into settings save in `main.py`**

In `App._apply_settings()`, add:

```python
from app.engine.autostart import enable_autostart, disable_autostart

if new_settings.get("autostart"):
    enable_autostart(sys.executable)
else:
    disable_autostart()
```

- [ ] **Step 5: Manual smoke test**

```bash
python main.py
```

Verify:
- App starts, tray icon appears in system tray
- `Ctrl+Shift+Space` held → overlay appears with bars
- Release → overlay shows "Transcription…" → text inserted in active field
- Tray menu opens Settings and History windows
- Quit exits cleanly

- [ ] **Step 6: Final commit**

```bash
git add app/engine/autostart.py tests/test_autostart.py main.py
git commit -m "feat: add autostart (Windows registry) and complete integration"
```

---

## Done

All tasks complete. WhisperFlow Local is functional end-to-end.

**Run full test suite one last time:**

```bash
pytest tests/ -v --tb=short
```

**Push and update PR:**

```bash
git push
```
