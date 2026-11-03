"""Authenticated, externally retainable alert-journal checkpoint.

An HMAC proves key possession, not freshness. The trusted checkpoint must
come from independently protected custody to detect local journal rollback.
"""
import hashlib
import hmac
import re

from hedgeops.custody_alert_journal import GENESIS
from hedgeops.store import canonical

SCHEME = "hedgeops-custody-alert-checkpoint-hmac-sha256-v1"
HEX = re.compile(r"[0-9a-f]{64}\Z")


def _key(key):
    if not isinstance(key, bytes) or len(key) < 32:
        raise ValueError("Checkpoint key must be at least 32 bytes")
    return key


def _body(sequence, event_hash):
    return {"scheme": SCHEME, "sequence": sequence, "event_hash": event_hash}


def _tag(body, key):
    return hmac.new(key, canonical(body).encode("utf-8"),
                    hashlib.sha256).hexdigest()


def _validate(checkpoint):
    if (not isinstance(checkpoint, dict) or
            set(checkpoint) != {"scheme", "sequence", "event_hash",
                               "authentication_tag"} or
            checkpoint["scheme"] != SCHEME or
            type(checkpoint["sequence"]) is not int or
            checkpoint["sequence"] < 1 or
            not isinstance(checkpoint["event_hash"], str) or
            HEX.fullmatch(checkpoint["event_hash"]) is None or
            not isinstance(checkpoint["authentication_tag"], str) or
            HEX.fullmatch(checkpoint["authentication_tag"]) is None):
        return None
    return _body(checkpoint["sequence"], checkpoint["event_hash"])


def create_alert_checkpoint(journal, key):
    """Sign the verified head from one consistent SQLite read transaction."""
    _key(key)
    with journal._connect() as db:
        db.execute("BEGIN")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Journal database integrity check failed")
        rows = db.execute(
            "SELECT sequence,previous_hash,payload,event_hash "
            "FROM custody_alert_events ORDER BY sequence").fetchall()
        if not journal._verify_chain(rows):
            raise ValueError("Journal chain invalid")
        if not rows:
            raise ValueError("Cannot checkpoint an empty journal")
        body = _body(rows[-1][0], rows[-1][3])
    return {**body, "authentication_tag": _tag(body, key)}


def verify_alert_checkpoint(journal, trusted_checkpoint, key):
    """Verify authenticated checkpoint and exact historical journal ancestry.

    Later valid journal events are allowed; truncation below the checkpoint
    or divergence at its sequence is rejected.
    """
    _key(key)
    body = _validate(trusted_checkpoint)
    if body is None or not hmac.compare_digest(
            _tag(body, key), trusted_checkpoint["authentication_tag"]):
        return False
    try:
        with journal._connect() as db:
            db.execute("BEGIN")
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                return False
            rows = db.execute(
                "SELECT sequence,previous_hash,payload,event_hash "
                "FROM custody_alert_events ORDER BY sequence").fetchall()
            if not journal._verify_chain(rows):
                return False
            sequence = body["sequence"]
            return (len(rows) >= sequence and
                    hmac.compare_digest(rows[sequence - 1][3],
                                        body["event_hash"]))
    except (ValueError, TypeError, KeyError):
        return False
