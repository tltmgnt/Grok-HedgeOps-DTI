"""Independent custody contract for authenticated execution audit heads."""
import hashlib
import hmac

from hedgeops.recovery_execution_checkpoint import (
    _valid, create_execution_checkpoint, verify_execution_checkpoint)
from hedgeops.store import canonical


class ExecutionCustodyError(ValueError):
    """Invalid, stale or conflicting execution custody record."""


def validate_execution_record(record):
    if (not isinstance(record, dict) or
            set(record) != {"sequence", "checkpoint_sha256"} or
            type(record["sequence"]) is not int or
            record["sequence"] < 1 or
            not isinstance(record["checkpoint_sha256"], str) or
            len(record["checkpoint_sha256"]) != 64 or
            any(c not in "0123456789abcdef"
                for c in record["checkpoint_sha256"])):
        raise ExecutionCustodyError("Invalid execution custody record")
    return record


def execution_checkpoint_fingerprint(checkpoint):
    if not _valid(checkpoint):
        raise ExecutionCustodyError("Invalid execution checkpoint")
    return hashlib.sha256(canonical(checkpoint).encode()).hexdigest()


def publish_execution_checkpoint(authority, key, custodian):
    """Publish the latest authenticated head with a monotonic atomic CAS."""
    checkpoint = create_execution_checkpoint(authority, key)
    record = validate_execution_record({
        "sequence": checkpoint["sequence"],
        "checkpoint_sha256": execution_checkpoint_fingerprint(checkpoint)})
    previous = custodian.read()
    if previous is not None:
        validate_execution_record(previous)
        if record["sequence"] <= previous["sequence"]:
            raise ExecutionCustodyError("Execution custody must advance")
    if not custodian.compare_and_swap(previous, record):
        raise ExecutionCustodyError("Execution custody CAS conflict")
    confirmed = custodian.read()
    if confirmed is None or validate_execution_record(confirmed) != record:
        raise ExecutionCustodyError("Execution custody changed after publication")
    return checkpoint


def verify_custodied_execution(authority, checkpoint, key, custodian):
    """Require authenticated journal ancestry and stable custody readings."""
    try:
        before = custodian.read()
        if before is None:
            return False
        validate_execution_record(before)
        if (not _valid(checkpoint) or
                checkpoint["sequence"] != before["sequence"] or
                not hmac.compare_digest(
                    execution_checkpoint_fingerprint(checkpoint),
                    before["checkpoint_sha256"])):
            return False
        if not verify_execution_checkpoint(authority, checkpoint, key):
            return False
        after = custodian.read()
        return (after is not None and
                validate_execution_record(after) == before)
    except (ExecutionCustodyError, ValueError, TypeError, KeyError, OSError):
        return False
