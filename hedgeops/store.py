"""SQLite-backed append-only event journal for DTI Ω.

Events are immutable through this API, not tamper-proof against DB administrators.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)

def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

class EventStore:
    def __init__(self, path="data/hedgeops.sqlite3"):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("""CREATE TABLE IF NOT EXISTS events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            stream TEXT NOT NULL,
            kind TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            previous_hash TEXT NOT NULL,
            event_hash TEXT NOT NULL
        )""")
        self.db.commit()

    def append(self, stream, kind, payload):
        if not isinstance(stream, str) or not stream.strip():
            raise ValueError("stream must be nonempty")
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("kind must be nonempty")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        body = canonical(payload)
        event_id = str(uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        try:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            previous_hash = row[0] if row else "GENESIS"
            event_hash = digest(canonical({
                "event_id": event_id, "stream": stream, "kind": kind,
                "payload": json.loads(body), "created_at": created_at,
                "previous_hash": previous_hash,
            }))
            cursor = self.db.execute(
                "INSERT INTO events(event_id,stream,kind,payload,created_at,previous_hash,event_hash) "
                "VALUES(?,?,?,?,?,?,?)",
                (event_id, stream, kind, body, created_at, previous_hash, event_hash))
            self.db.commit()
            return cursor.lastrowid
        except Exception:
            self.db.rollback()
            raise

    def history(self, stream=None):
        if stream is None:
            rows = self.db.execute("SELECT * FROM events ORDER BY seq").fetchall()
        else:
            rows = self.db.execute("SELECT * FROM events WHERE stream=? ORDER BY seq", (stream,)).fetchall()
        return [{"seq": r[0], "event_id": r[1], "stream": r[2], "kind": r[3],
                 "payload": json.loads(r[4]), "created_at": r[5],
                 "previous_hash": r[6], "event_hash": r[7]} for r in rows]

    def verify_chain(self):
        previous = "GENESIS"
        for event in self.history():
            if event["previous_hash"] != previous:
                return False
            expected = digest(canonical({
                key: event[key] for key in
                ("event_id", "stream", "kind", "payload", "created_at", "previous_hash")
            }))
            if expected != event["event_hash"]:
                return False
            previous = event["event_hash"]
        return True

    def snapshot(self, stream):
        events = self.history(stream)
        return {"stream": stream, "event_count": len(events), "events": events,
                "global_chain_valid": self.verify_chain()}

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
