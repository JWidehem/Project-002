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


def test_export_csv_creates_file(history, tmp_path):
    history.save(raw="euh bonjour monde", clean="bonjour monde", duration=1.5)
    history.save(raw="euh merci", clean="merci", duration=0.8)
    dest = tmp_path / "export.csv"
    count = history.export_csv(dest)
    assert count == 2
    assert dest.exists()
    lines = dest.read_text(encoding="utf-8-sig").splitlines()
    assert lines[0] == "date;durée_s;brut;nettoyé"
    assert "bonjour monde" in lines[1]  # oldest first
    assert "merci" in lines[2]


def test_export_csv_empty_history(history, tmp_path):
    dest = tmp_path / "export_empty.csv"
    count = history.export_csv(dest)
    assert count == 0
    lines = dest.read_text(encoding="utf-8-sig").splitlines()
    assert lines[0] == "date;durée_s;brut;nettoyé"
    assert len(lines) == 1
