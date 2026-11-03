"""Readiness assessment: local outbox integrity plus independent custody evidence."""
from hedgeops.reconciliation_health import reconciliation_health
from hedgeops.recovery_execution_audit import execution_audit_head
from hedgeops.recovery_execution_custody import verify_custodied_execution


def reconciliation_readiness(authority, checkpoint, key, custodian):
    """Fail closed unless local outbox and independently held head agree.

    Read-only: no recovery mutation, custody CAS or outbox confirmation.
    """
    local = reconciliation_health(authority)
    if local["status"] != "healthy":
        return {"ready": False, "status": local["status"],
                "local": local, "custody_verified": False}
    try:
        head = execution_audit_head(authority)
        if (type(checkpoint) is not dict or
                type(checkpoint.get("sequence")) is not int or
                checkpoint["sequence"] != local["audit_head"] or
                checkpoint.get("event_hash") != head["event_hash"]):
            return {"ready": False, "status": "checkpoint_mismatch",
                    "local": local, "custody_verified": False}
        verified = verify_custodied_execution(authority, checkpoint, key, custodian)
        # A concurrent local commit can invalidate a successful remote check.
        after = reconciliation_health(authority)
        final_head = execution_audit_head(authority)
        stable = (after == local and
                  final_head == head)
        return {"ready": bool(verified and stable),
                "status": ("ready" if verified and stable else
                           "local_changed" if not stable else "custody_unverified"),
                "local": after, "custody_verified": bool(verified)}
    except (ValueError, TypeError, KeyError, OSError):
        return {"ready": False, "status": "custody_unverified",
                "local": local, "custody_verified": False}
