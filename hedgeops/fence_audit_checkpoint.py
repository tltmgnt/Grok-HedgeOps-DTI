"""Externally retainable HMAC checkpoint for recovery fence issuance audit.

HMAC authenticates contents; rollback detection requires independently
retained trusted checkpoint and protected signing key.
"""
import hashlib
import hmac
import re

from hedgeops.store import canonical

SCHEME = "hedgeops-fence-audit-checkpoint-hmac-sha256-v1"
_HEX = re.compile(r"[0-9a-f]{64}\Z")


def _key(key):
    if type(key) is not bytes or len(key) < 32:
        raise ValueError("Audit checkpoint key must be at least 32 bytes")
    return key


def _body(generation, event_hash):
    return {"scheme": SCHEME, "generation": generation,
            "event_hash": event_hash}


def _tag(body, key):
    return hmac.new(key, canonical(body).encode("utf-8"),
                    hashlib.sha256).hexdigest()


def _validate(checkpoint):
    if (not isinstance(checkpoint, dict) or
            set(checkpoint) != {"scheme", "generation", "event_hash",
                               "authentication_tag"} or
            checkpoint["scheme"] != SCHEME or
            type(checkpoint["generation"]) is not int or
            checkpoint["generation"] < 1 or
            not isinstance(checkpoint["event_hash"], str) or
            _HEX.fullmatch(checkpoint["event_hash"]) is None or
            not isinstance(checkpoint["authentication_tag"], str) or
            _HEX.fullmatch(checkpoint["authentication_tag"]) is None):
        return None
    return _body(checkpoint["generation"], checkpoint["event_hash"])


def create_fence_audit_checkpoint(authority, key):
    """Sign latest verified audited issuance in one SQLite read snapshot."""
    _key(key)
    with authority._connect() as db:
        db.execute("BEGIN")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Fence database integrity check failed")
        rows = db.execute(
            "SELECT generation,operator_digest,previous_hash,event_hash "
            "FROM recovery_fence_issuance ORDER BY generation").fetchall()
        if not rows:
            raise ValueError("No audited fencing issuance to checkpoint")
        previous_hash = "0" * 64
        last_generation = 0
        for generation, operator_digest, predecessor, event_hash in rows:
            if (type(generation) is not int or generation <= last_generation or
                    predecessor != previous_hash or
                    not isinstance(operator_digest, str) or
                    _HEX.fullmatch(operator_digest) is None or
                    not isinstance(event_hash, str) or
                    _HEX.fullmatch(event_hash) is None):
                raise ValueError("Fence issuance audit invalid")
            expected = hashlib.sha256(
                ("hedgeops-fence-issuance-v1:" + str(generation) + ":" +
                 operator_digest + ":" + predecessor).encode()).hexdigest()
            if not hmac.compare_digest(expected, event_hash):
                raise ValueError("Fence issuance audit invalid")
            last_generation, previous_hash = generation, event_hash
        current = db.execute(
            "SELECT generation FROM recovery_fence WHERE id=1").fetchone()
        if current is None or current[0] < last_generation:
            raise ValueError("Fence generation behind audit")
        body = _body(last_generation, previous_hash)
    return {**body, "authentication_tag": _tag(body, key)}


def verify_fence_audit_checkpoint(authority, trusted_checkpoint, key):
    """Reject truncated, diverged, or unauthenticated issuance histories."""
    _key(key)
    body = _validate(trusted_checkpoint)
    if body is None or not hmac.compare_digest(
            _tag(body, key), trusted_checkpoint["authentication_tag"]):
        return False
    try:
        with authority._connect() as db:
            db.execute("BEGIN")
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                return False
            rows = db.execute(
                "SELECT generation,operator_digest,previous_hash,event_hash "
                "FROM recovery_fence_issuance ORDER BY generation").fetchall()
            previous_hash = "0" * 64
            last_generation = 0
            anchored = False
            for generation, operator_digest, predecessor, event_hash in rows:
                if (type(generation) is not int or generation <= last_generation or
                        predecessor != previous_hash or
                        not isinstance(operator_digest, str) or
                        _HEX.fullmatch(operator_digest) is None or
                        not isinstance(event_hash, str) or
                        _HEX.fullmatch(event_hash) is None):
                    return False
                expected = hashlib.sha256(
                    ("hedgeops-fence-issuance-v1:" + str(generation) + ":" +
                     operator_digest + ":" + predecessor).encode()).hexdigest()
                if not hmac.compare_digest(expected, event_hash):
                    return False
                if generation == body["generation"]:
                    anchored = hmac.compare_digest(
                        event_hash, body["event_hash"])
                    if not anchored:
                        return False
                last_generation, previous_hash = generation, event_hash
            current = db.execute(
                "SELECT generation FROM recovery_fence WHERE id=1").fetchone()
            return (anchored and current is not None and
                    current[0] >= last_generation)
    except (ValueError, TypeError, KeyError):
        return False
