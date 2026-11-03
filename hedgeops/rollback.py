"""Fail-closed recovery rollback floor for externally retained journal positions.

A trusted floor must be distributed from an independently controlled source.
This module never promotes an untrusted local file into an authority.
"""
import hashlib
import hmac

from hedgeops.store import canonical

FLOOR_SCHEME = "hedgeops-recovery-floor-v1"


def create_recovery_floor(checkpoint, authentication_key):
    """Authenticate a checkpoint's global position for external retention."""
    if not isinstance(authentication_key, bytes) or len(authentication_key) < 32:
        raise ValueError("Recovery floor key must be at least 32 bytes")
    if not isinstance(checkpoint, dict):
        raise ValueError("Invalid checkpoint")
    count = checkpoint.get("global_event_count")
    head = checkpoint.get("global_head_hash")
    if type(count) is not int or count < 1 or not isinstance(head, str) or len(head) != 64:
        raise ValueError("Invalid checkpoint position")
    body = {"scheme": FLOOR_SCHEME, "minimum_event_count": count,
            "minimum_head_hash": head}
    tag = hmac.new(authentication_key, canonical(body).encode("utf-8"),
                   hashlib.sha256).hexdigest()
    return {**body, "authentication_tag": tag}


def verify_recovery_floor(floor, authentication_key):
    if not isinstance(authentication_key, bytes) or len(authentication_key) < 32:
        return False
    if not isinstance(floor, dict) or set(floor) != {
            "scheme", "minimum_event_count", "minimum_head_hash", "authentication_tag"}:
        return False
    count = floor["minimum_event_count"]
    head = floor["minimum_head_hash"]
    tag = floor["authentication_tag"]
    if (floor["scheme"] != FLOOR_SCHEME or type(count) is not int or count < 1
            or not isinstance(head, str) or len(head) != 64
            or not isinstance(tag, str) or len(tag) != 64):
        return False
    body = {k: floor[k] for k in ("scheme", "minimum_event_count", "minimum_head_hash")}
    expected = hmac.new(authentication_key, canonical(body).encode("utf-8"),
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, tag)


def verify_recovery_position(store, checkpoint, trusted_floor, authentication_key):
    """Reject rollback and forked history at the externally trusted floor."""
    if not verify_recovery_floor(trusted_floor, authentication_key):
        return False
    if not isinstance(checkpoint, dict) or not store.verify_chain():
        return False
    count = checkpoint.get("global_event_count")
    floor_count = trusted_floor["minimum_event_count"]
    if type(count) is not int or count < floor_count:
        return False
    events = store.history()
    if len(events) != count or len(events) < floor_count:
        return False
    return events[floor_count - 1]["event_hash"] == trusted_floor["minimum_head_hash"]
