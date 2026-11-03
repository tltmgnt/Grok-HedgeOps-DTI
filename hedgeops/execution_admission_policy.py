"""Persistent execution custody admission requirement."""
import sqlite3


def require_execution_custody(authority):
    """Irreversibly enable strict admission in this SQLite authority."""
    with authority._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS execution_admission_policy (id INTEGER PRIMARY KEY, required INTEGER NOT NULL)")
        db.execute("INSERT OR IGNORE INTO execution_admission_policy VALUES (1, 1)")
        db.commit()


def execution_custody_required(db):
    """Return the stored requirement, including across process restarts."""
    try:
        return db.execute(
            "SELECT required FROM execution_admission_policy WHERE id=1"
        ).fetchone() == (1,)
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc):
            raise
        return False
