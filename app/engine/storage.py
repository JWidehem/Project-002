import json
import sqlite3
from pathlib import Path

DEFAULTS: dict = {
    "language": "fr",
    "model": "small",
    "compute_device": "cpu",
    "preload_model": False,
    "hotkey_hold": "<ctrl>+<alt>",
    "hotkey_toggle": "<ctrl>+<alt>+<space>",
    "cleanup_level": "light",
    "filler_words": ["euh", "hum", "ben", "voilà", "enfin"],
    "glossary": [],
    "autostart": False,
    "audio_device": None,
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
