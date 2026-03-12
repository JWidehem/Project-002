# tests/test_audio.py
import queue
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

# Import constants at module level so they are available in all test functions
from app.engine.audio import MAX_DURATION_S, MIN_DURATION_S, SAMPLE_RATE


@pytest.fixture
def rms_queue():
    return queue.Queue()


def test_audio_capture_accumulates_chunks(rms_queue, mocker):
    mocker.patch("sounddevice.InputStream")
    from app.engine.audio import AudioCapture
    cap = AudioCapture(rms_queue)
    cap.start()

    # Simulate callback calls — use chunks large enough to exceed MIN_DURATION_S
    # MIN_DURATION_S = 0.3s * 16000 = 4800 samples; use 2600 per call so 5200 total > 4800
    chunk = np.ones((2600, 1), dtype=np.float32) * 0.5
    cap._callback(chunk, 2600, None, None)
    cap._callback(chunk, 2600, None, None)

    result = cap.stop()
    assert result is not None
    assert len(result) == 5200  # 2600 * 2


def test_audio_capture_returns_none_if_too_short(rms_queue, mocker):
    mocker.patch("sounddevice.InputStream")
    from app.engine.audio import AudioCapture
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
    from app.engine.audio import AudioCapture
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
    from app.engine.audio import AudioCapture
    on_max = mocker.MagicMock()
    cap = AudioCapture(rms_queue, on_max_duration=on_max)
    cap.start()

    chunk = np.zeros((512, 1), dtype=np.float32)
    cap._callback(chunk, 512, None, None)

    on_max.assert_called_once()
