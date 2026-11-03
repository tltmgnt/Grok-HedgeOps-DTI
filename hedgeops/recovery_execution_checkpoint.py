"""HMAC checkpoint for the recovery execution journal."""
import hashlib
import hmac
import sqlite3

from hedgeops.recovery_execution_audit import _verify_rows
from hedgeops.store import canonical

SCHEME = "hedgeops-execution-checkpoint-hmac-sha256-v1"


def _key(key):
    if type(key) is not bytes or len(key) < 32:
        raise ValueError("Checkpoint key must be at least 32 bytes")


def _body(sequence, digest):
    return {"scheme": SCHEME, "sequence": sequence, "event_hash": digest}


def _tag(body, key):
    return hmac.new(key, canonical(body).encode(), hashlib.sha256).hexdigest()


def _valid(checkpoint):
    return (isinstance(checkpoint, dict) and
            set(checkpoint) == {"scheme", "sequence", "event_hash",
                                "authentication_tag"} and
            checkpoint["scheme"] == SCHEME and
            type(checkpoint["sequence"]) is int and
            checkpoint["sequence"] > 0 and
            all(isinstance(checkpoint[name], str) and
                len(checkpoint[name]) == 64 and
                all(char in "0123456789abcdef" for char in checkpoint[name])
                for name in ("event_hash", "authentication_tag")))


def create_execution_checkpoint(authority, key):
    _key(key)
    with authority._connect() as db:
        db.execute("BEGIN")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Database integrity failed")
        rows = db.execute(
            "SELECT sequence,generation,previous_hash,event_hash "
            "FROM recovery_execution_audit ORDER BY sequence").fetchall()
        if not rows or not _verify_rows(rows):
            raise ValueError("Cannot checkpoint invalid or empty audit")
        body = _body(rows[-1][0], rows[-1][3])
    return dict(body, authentication_tag=_tag(body, key))


def verify_execution_checkpoint(authority, checkpoint, key):
    _key(key)
    if not _valid(checkpoint):
        return False
    body = _body(checkpoint["sequence"], checkpoint["event_hash"])
    if not hmac.compare_digest(_tag(body, key), checkpoint["authentication_tag"]):
        return False
    try:
        with authority._connect() as db:
            db.execute("BEGIN")
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                return False
            rows = db.execute(
                "SELECT sequence,generation,previous_hash,event_hash "
                "FROM recovery_execution_audit ORDER BY sequence").fetchall()
            index = checkpoint["sequence"] - 1
            return (index < len(rows) and _verify_rows(rows) and
                    hmac.compare_digest(rows[index][3], checkpoint["event_hash"]))
    except (sqlite3.Error, ValueError, TypeError):
        return False
