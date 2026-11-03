"""Independent monotonic custody for authenticated recovery-fence audit heads.

The custodian must provide independently protected atomic compare-and-swap
and rollback resistance. A local in-memory fake is only a test double.
"""
import hashlib
import hmac
import re

from hedgeops.fence_audit_checkpoint import (
    _key, _validate, create_fence_audit_checkpoint,
    verify_fence_audit_checkpoint)
from hedgeops.store import canonical

_HEX = re.compile(r"[0-9a-f]{64}\Z")


class FenceAuditCustodyError(ValueError):
    pass


def _record(record):
    if (not isinstance(record, dict) or
            set(record) != {"generation", "audit_sha256"} or
            type(record["generation"]) is not int or
            record["generation"] < 1 or
            not isinstance(record["audit_sha256"], str) or
            _HEX.fullmatch(record["audit_sha256"]) is None):
        raise FenceAuditCustodyError("Invalid fence audit custody record")
    return record


def audit_fingerprint(checkpoint):
    if _validate(checkpoint) is None:
        raise FenceAuditCustodyError("Invalid fence audit checkpoint")
    return hashlib.sha256(canonical(checkpoint).encode("utf-8")).hexdigest()


def publish_fence_audit_checkpoint(authority, key, custodian):
    """Publish authenticated head via strictly monotonic custody CAS."""
    checkpoint = create_fence_audit_checkpoint(authority, key)
    new = _record({"generation": checkpoint["generation"],
                   "audit_sha256": audit_fingerprint(checkpoint)})
    old = custodian.read()
    if old is not None:
        _record(old)
        if new["generation"] <= old["generation"]:
            raise FenceAuditCustodyError("Fence audit custody must advance")
    if not custodian.compare_and_swap(old, new):
        raise FenceAuditCustodyError("Fence audit custody CAS conflict")
    confirmed = custodian.read()
    if confirmed is None or _record(confirmed) != new:
        raise FenceAuditCustodyError("Fence audit custody changed after publication")
    return checkpoint


def verify_custodied_fence_audit(authority, trusted_checkpoint, key, custodian):
    """Fail closed if custody differs before/after audit verification."""
    try:
        _key(key)
        record = custodian.read()
        if record is None:
            return False
        _record(record)
        if (_validate(trusted_checkpoint) is None or
                trusted_checkpoint["generation"] != record["generation"] or
                not hmac.compare_digest(
                    audit_fingerprint(trusted_checkpoint),
                    record["audit_sha256"])):
            return False
        if not verify_fence_audit_checkpoint(
                authority, trusted_checkpoint, key):
            return False
        confirmed = custodian.read()
        return confirmed is not None and _record(confirmed) == record
    except (FenceAuditCustodyError, ValueError, TypeError, KeyError, OSError):
        return False
