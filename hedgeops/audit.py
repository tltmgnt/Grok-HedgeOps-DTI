"""Portable, deterministic event-journal audit checkpoints.

A checkpoint is useful only if preserved outside the database in a trusted
location. A digest alone does not establish who created or approved it.
"""
import hashlib
from hedgeops.store import canonical
from hedgeops.identity import verify_case_review

SCHEME = "hedgeops-audit-checkpoint-v1"


def export_checkpoint(store, case_id, registry):
    """Build an immutable-data checkpoint without exporting secrets or case text."""
    if not store.verify_chain():
        raise ValueError("Cannot checkpoint a journal with an invalid hash chain")
    events = store.history()
    case_events = [event for event in events if event["stream"] == case_id]
    if not case_events:
        raise KeyError("Unknown case")
    case_review_valid = verify_case_review(store, case_id, registry)
    body = {
        "scheme": SCHEME,
        "case_id": case_id,
        "global_event_count": len(events),
        "global_head_hash": events[-1]["event_hash"] if events else "GENESIS",
        "case_event_count": len(case_events),
        "case_head_hash": case_events[-1]["event_hash"],
        "review_attestation_valid": case_review_valid,
    }
    body["checkpoint_digest"] = hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()
    return body


def verify_checkpoint(store, checkpoint, registry):
    """Compare a trusted exported checkpoint against the current exact journal.

    Exact match is intentional: any later event requires a new checkpoint.
    """
    if not isinstance(checkpoint, dict):
        return False
    try:
        case_id = checkpoint["case_id"]
        expected = export_checkpoint(store, case_id, registry)
        return checkpoint == expected
    except (KeyError, ValueError, TypeError, PermissionError):
        return False
