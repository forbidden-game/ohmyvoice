import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transcriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_created_at ON transcriptions(id DESC);
"""

class HistoryDB:
    def __init__(self, db_path: Path | None = None):
        if db_path is None:
            db_path = Path.home() / ".local" / "share" / "ohmyvoice" / "history.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def add(self, text: str, duration: float) -> int:
        cur = self._conn.execute(
            "INSERT INTO transcriptions (text, duration_seconds) VALUES (?, ?)",
            (text, duration),
        )
        self._conn.commit()
        return cur.lastrowid

    def recent(self, limit: int = 10) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, text, duration_seconds, created_at "
            "FROM transcriptions ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get(self, record_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT id, text, duration_seconds, created_at "
            "FROM transcriptions WHERE id = ?",
            (record_id,),
        ).fetchone()
        return dict(row) if row else None

    def search(self, query: str, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, text, duration_seconds, created_at "
            "FROM transcriptions WHERE text LIKE ? "
            "ORDER BY id DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def prune(self, max_entries: int = 1000):
        self._conn.execute(
            "DELETE FROM transcriptions WHERE id NOT IN "
            "(SELECT id FROM transcriptions ORDER BY id DESC LIMIT ?)",
            (max_entries,),
        )
        self._conn.commit()

    def clear(self):
        self._conn.execute("DELETE FROM transcriptions")
        self._conn.commit()

    def close(self):
        self._conn.close()
