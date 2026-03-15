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


# Below this RMS the audio is considered too quiet and will be boosted.
_NORMALIZE_THRESHOLD = 0.02
# Target RMS level after normalization (Whisper works well around 0.05).
_NORMALIZE_TARGET = 0.05
# Maximum amplification factor to avoid boosting pure silence into noise.
_NORMALIZE_MAX_GAIN = 10.0


class AudioCapture:
    def __init__(self, rms_queue: queue.Queue, on_max_duration=None,
                 device: int | None = None, on_error=None) -> None:
        self._rms_queue = rms_queue
        self._on_max_duration = on_max_duration
        self._on_error = on_error
        self._device = device
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._start_time: float = 0.0
        self._lock = threading.Lock()
        self._stopped = False
        self._error_reported = False

    def set_device(self, device: int | None) -> None:
        """Update the capture device; takes effect on the next start() call."""
        self._device = device

    def start(self) -> None:
        with self._lock:
            self._chunks = []
            self._stopped = False
            self._error_reported = False
            self._start_time = time.monotonic()
            try:
                self._stream = sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype=DTYPE,
                    device=self._device,
                    callback=self._callback,
                )
                self._stream.start()
            except sd.PortAudioError as e:
                self._stream = None
                raise

    def stop(self) -> np.ndarray | None:
        with self._lock:
            if self._stream:
                try:
                    self._stream.stop()
                    self._stream.close()
                except sd.PortAudioError:
                    pass
                self._stream = None
            if not self._chunks:
                return None
            audio = np.concatenate(self._chunks).flatten()
        duration = len(audio) / SAMPLE_RATE
        if duration < MIN_DURATION_S:
            return None
        # Normalize: boost quiet recordings so Whisper can hear them clearly.
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if 0 < rms < _NORMALIZE_THRESHOLD:
            gain = min(_NORMALIZE_TARGET / rms, _NORMALIZE_MAX_GAIN)
            audio = np.clip(audio * gain, -1.0, 1.0)
        return audio

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info,
        status,
    ) -> None:
        if status and not self._error_reported and self._on_error:
            self._error_reported = True
            threading.Thread(
                target=self._on_error, args=(str(status),), daemon=True
            ).start()
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
