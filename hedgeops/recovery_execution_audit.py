"""Locally hash-chained recovery execution commit records.

Records are written in the same SQLite transaction as each controlled
recovery mutation. This is not an external or rollback-resistant audit.
"""
import hashlib
import hmac
import sqlite3

from hedgeops.store import canonical

SCHEME = "hedgeops-recovery-execution-audit-v1"
GENESIS = "0" * 64


def ensure_execution_audit(authority):
    """Initialize the audit schema before beginning a guarded mutation."""
    with authority._connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS recovery_execution_audit (
            sequence INTEGER PRIMARY KEY,
            generation INTEGER NOT NULL CHECK(generation >= 1),
            previous_hash TEXT NOT NULL,
            event_hash TEXT NOT NULL)""")
        db.commit()


def _digest(sequence, generation, previous_hash):
    return hashlib.sha256(canonical({
        "scheme": SCHEME, "sequence": sequence,
        "generation": generation, "previous_hash": previous_hash
    }).encode("utf-8")).hexdigest()


def _verify_rows(rows):
    previous = GENESIS
    for sequence, (actual, generation, predecessor, digest) in enumerate(rows, 1):
        if (type(actual) is not int or actual != sequence or
                type(generation) is not int or generation < 1 or
                predecessor != previous or
                not isinstance(digest, str) or
                not hmac.compare_digest(
                    _digest(sequence, generation, previous), digest)):
            return False
        previous = digest
    return True


def append_execution_event(db, generation):
    """Append inside the caller's active SQLite write transaction."""
    if not db.in_transaction:
        raise ValueError("Execution audit requires an active transaction")
    if type(generation) is not int or generation < 1:
        raise ValueError("Invalid recovery generation")
    rows = db.execute(
        "SELECT sequence,generation,previous_hash,event_hash "
        "FROM recovery_execution_audit ORDER BY sequence").fetchall()
    if not _verify_rows(rows):
        raise ValueError("Recovery execution audit chain invalid")
    sequence = len(rows) + 1
    previous = rows[-1][3] if rows else GENESIS
    digest = _digest(sequence, generation, previous)
    db.execute(
        "INSERT INTO recovery_execution_audit "
        "(sequence,generation,previous_hash,event_hash) VALUES(?,?,?,?)",
        (sequence, generation, previous, digest))
    return {"sequence": sequence, "event_hash": digest}


def verify_execution_audit(authority):
    """Verify local chain continuity and database integrity."""
    try:
        with authority._connect() as db:
            db.execute("BEGIN")
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                return False
            rows = db.execute(
                "SELECT sequence,generation,previous_hash,event_hash "
                "FROM recovery_execution_audit ORDER BY sequence").fetchall()
            return _verify_rows(rows)
    except (sqlite3.Error, ValueError, TypeError):
        return False


def execution_audit_head(authority):
    """Return local audit head; retain externally for rollback detection."""
    with authority._connect() as db:
        row = db.execute(
            "SELECT sequence,event_hash FROM recovery_execution_audit "
            "ORDER BY sequence DESC LIMIT 1").fetchone()
    return {"sequence": row[0], "event_hash": row[1]} if row else {
        "sequence": 0, "event_hash": GENESIS}
