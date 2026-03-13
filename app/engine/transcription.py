import threading
import numpy as np
from faster_whisper import WhisperModel

# Mapping from user-facing device name to faster-whisper (device, compute_type)
_DEVICE_MAP: dict[str, tuple[str, str]] = {
    "cpu":  ("cpu",  "int8"),
    "cuda": ("cuda", "float16"),
    "auto": ("auto", "int8"),
}


class Transcriber:
    def __init__(self, model_name: str = "small", compute_device: str = "cpu") -> None:
        self._model_name = model_name
        self._compute_device = compute_device
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
            device, compute_type = _DEVICE_MAP.get(
                self._compute_device, ("cpu", "int8")
            )
            self._model = WhisperModel(
                self._model_name,
                device=device,
                compute_type=compute_type,
            )
