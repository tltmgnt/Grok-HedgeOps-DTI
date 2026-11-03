"""Safe operator-facing diagnostics for reconciliation readiness.

No credentials, checkpoint tags, event digests or custodian URLs are emitted.
"""
from hedgeops.reconciliation_readiness import reconciliation_readiness

_REASONS = {
    "ready": ("READY", "Local reconciliation and external custody agree."),
    "pending": ("PENDING_RECONCILIATION",
                "Committed recovery audit entries await custody confirmation."),
    "integrity_failure": ("LOCAL_INTEGRITY_FAILURE",
                          "Local reconciliation evidence failed integrity checks."),
    "unavailable": ("LOCAL_STATUS_UNAVAILABLE",
                    "Local reconciliation status could not be read."),
    "checkpoint_mismatch": ("CHECKPOINT_MISMATCH",
                            "The supplied checkpoint does not match the local head."),
    "custody_unverified": ("CUSTODY_UNVERIFIED",
                           "Independent custody confirmation could not be established."),
    "local_changed": ("LOCAL_STATE_CHANGED",
                      "Local state changed during custody verification."),
}


def readiness_diagnostics(authority, checkpoint, key, custodian):
    """Return a bounded, allowlisted operator report; never perform recovery."""
    assessment = reconciliation_readiness(authority, checkpoint, key, custodian)
    status = assessment.get("status")
    code, message = _REASONS.get(
        status, ("READINESS_UNAVAILABLE", "Readiness could not be established."))
    local = assessment.get("local")
    if not isinstance(local, dict):
        local = {}
    def count(field):
        value = local.get(field)
        return value if type(value) is int and value >= 0 else None
    return {
        "ready": assessment.get("ready") is True and status == "ready",
        "reason_code": code,
        "message": message,
        "pending": count("pending"),
        "confirmed": count("confirmed"),
        "audit_head": count("audit_head"),
        "custody_verified": assessment.get("custody_verified") is True,
    }
