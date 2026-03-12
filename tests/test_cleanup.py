# tests/test_cleanup.py
from app.engine.cleanup import clean

FILLERS = ["euh", "hum", "ben", "voilà"]


def test_level_none_returns_unchanged():
    assert clean("euh bonjour", level="none", filler_words=FILLERS) == "euh bonjour"


def test_removes_filler_words():
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
    assert result[0] == "B"


def test_empty_filler_list_does_not_crash():
    result = clean("bonjour", level="light", filler_words=[])
    assert result == "bonjour"


def test_empty_text_returns_empty():
    assert clean("", level="medium", filler_words=FILLERS) == ""
