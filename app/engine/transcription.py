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
            # Natural sentence prompt conditions Whisper better than a raw word list.
            terms = ", ".join(t for t in glossary if len(t) <= 25)[:400]
            kwargs["initial_prompt"] = (
                f"Développeur français utilisant l'IA quotidiennement, dictée vocale professionnelle. "
                f"Termes techniques: {terms}."
            )

        segments, _ = self._model.transcribe(audio, **kwargs)  # type: ignore[union-attr]

        if self._cancel_event.is_set():
            return None

        return " ".join(s.text for s in segments).strip()

    def transcribe_file(
        self,
        path: str,
        language: str = "fr",
        glossary: list[str] | None = None,
    ) -> str | None:
        """Transcribe an audio file (mp3, m4a, aac, wav, ogg, …).

        faster-whisper handles file loading internally via ffmpeg.
        Cancellation is checked between each segment so long files can be
        interrupted cleanly.
        """
        if self._cancel_event.is_set():
            return None

        self._ensure_loaded()

        kwargs: dict = {
            "language": language,
            "vad_filter": True,
            "word_timestamps": False,
        }
        if glossary:
            terms = ", ".join(t for t in glossary if len(t) <= 25)[:400]
            kwargs["initial_prompt"] = (
                f"Développeur français utilisant l'IA quotidiennement, dictée vocale professionnelle. "
                f"Termes techniques: {terms}."
            )

        segments, _ = self._model.transcribe(str(path), **kwargs)  # type: ignore[union-attr]

        parts: list[str] = []
        for s in segments:
            if self._cancel_event.is_set():
                return None
            parts.append(s.text)

        return " ".join(parts).strip() or None

    def cancel(self) -> None:
        self._cancel_event.set()

    def reset_cancel(self) -> None:
        self._cancel_event.clear()

    def _ensure_loaded(self) -> None:
        if self._model is None:
            device, compute_type = _DEVICE_MAP.get(
                self._compute_device, ("cpu", "int8")
            )
            try:
                self._model = WhisperModel(
                    self._model_name,
                    device=device,
                    compute_type=compute_type,
                )
            except Exception as exc:
                if device != "cpu":
                    import logging
                    logging.warning(
                        f"Failed to load model on {device} ({exc}); falling back to CPU."
                    )
                    self._model = WhisperModel(
                        self._model_name,
                        device="cpu",
                        compute_type="int8",
                    )
                else:
                    raise
