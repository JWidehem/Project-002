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


def test_transcribe_file_returns_text(mock_whisper_model):
    from app.engine.transcription import Transcriber
    t = Transcriber("small")
    result = t.transcribe_file("meeting.aac", language="fr")
    assert result == "bonjour"
    # faster-whisper receives the path as a string
    call_args = mock_whisper_model.transcribe.call_args[0]
    assert call_args[0] == "meeting.aac"


def test_transcribe_file_cancel_before_start(mock_whisper_model):
    from app.engine.transcription import Transcriber
    t = Transcriber("small")
    t.cancel()
    result = t.transcribe_file("meeting.aac", language="fr")
    assert result is None
    mock_whisper_model.transcribe.assert_not_called()


def test_transcribe_file_cancel_mid_segments():
    """cancel() mid-iteration stops segment collection and returns None."""
    from app.engine.transcription import Transcriber
    from unittest.mock import MagicMock, patch

    with patch("app.engine.transcription.WhisperModel") as MockModel:
        instance = MockModel.return_value
        t = Transcriber("small")

        # Build a generator that sets cancel after first segment
        def _gen():
            seg1 = MagicMock(); seg1.text = " hello"
            yield seg1
            t.cancel()
            seg2 = MagicMock(); seg2.text = " world"
            yield seg2

        instance.transcribe.return_value = (_gen(), MagicMock())
        result = t.transcribe_file("long.aac", language="fr")
        # Cancelled mid-way → None
        assert result is None


def test_transcribe_file_passes_glossary(mock_whisper_model):
    from app.engine.transcription import Transcriber
    t = Transcriber("small")
    t.transcribe_file("meeting.aac", language="fr", glossary=["CRM", "ERP"])
    call_kwargs = mock_whisper_model.transcribe.call_args[1]
    assert "CRM" in call_kwargs["initial_prompt"]
