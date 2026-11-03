import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


class Ledger:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with closing(self.connect()) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS records (
                    key TEXT PRIMARY KEY, payload TEXT NOT NULL,
                    response TEXT NOT NULL, created_at TEXT NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS records_created ON records(created_at)")

    def connect(self):
        return sqlite3.connect(self.path)

    def find(self, key):
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT payload, response FROM records WHERE key = ?", (key,)
            ).fetchone()
        if row:
            return {"payload": json.loads(row[0]), "resposta": json.loads(row[1])}
        return None

    def save(self, key, payload, response):
        with closing(self.connect()) as db, db:
            db.execute("INSERT INTO records VALUES (?, ?, ?, ?)", (
                key, json.dumps(payload), json.dumps(response),
                datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            ))

    def window(self, start, end):
        with closing(self.connect()) as db:
            rows = db.execute(
                "SELECT key, payload FROM records WHERE created_at >= ? AND created_at < ? ORDER BY key",
                (start, end),
            ).fetchall()
        return [{"key": key, "amount": json.loads(payload)["valor"]} for key, payload in rows]
