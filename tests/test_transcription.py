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
