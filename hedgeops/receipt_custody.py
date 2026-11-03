"""Receipt custody contract with monotonic compare-and-swap semantics.

A production custodian MUST independently enforce atomic CAS and durable
monotonicity. This module does not implement a remote custody service.
"""
import re

from hedgeops.pinned_recovery import receipt_fingerprint, verify_pinned_recovery
from hedgeops.registry_receipt import load_registry_receipt, verify_registry_receipt

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class CustodyError(ValueError):
    """A custody record is absent, malformed, stale or untrusted."""


def _validate(record):
    if (not isinstance(record, dict) or set(record) !=
            {"sequence", "receipt_sha256"} or
            type(record["sequence"]) is not int or record["sequence"] < 1 or
            not isinstance(record["receipt_sha256"], str) or
            _DIGEST.fullmatch(record["receipt_sha256"]) is None):
        raise CustodyError("Invalid custody record")
    return record


def publish_receipt_to_custodian(
        floor_directory, trusted_receipt_path, floor_key, receipt_key, custodian):
    """Publish only a validated local receipt through the custodian's CAS API.

    The custodian must implement read() -> record|None and
    compare_and_swap(expected_record, new_record) -> bool, atomically.
    No retries: concurrent updates require a new trusted read and review.
    """
    receipt = load_registry_receipt(trusted_receipt_path)
    if not verify_registry_receipt(
            floor_directory, floor_key, receipt, receipt_key):
        raise CustodyError("Receipt does not match authenticated registry")
    new = _validate({
        "sequence": receipt["sequence"],
        "receipt_sha256": receipt_fingerprint(receipt),
    })
    old = custodian.read()
    if old is not None:
        _validate(old)
        if new["sequence"] <= old["sequence"]:
            raise CustodyError("Custody sequence must advance")
    if not custodian.compare_and_swap(old, new):
        raise CustodyError("Custody publication conflict")
    return new


def trusted_receipt_fingerprint(custodian):
    """Read a validated record from the independently trusted custodian."""
    record = custodian.read()
    if record is None:
        raise CustodyError("No independently retained receipt fingerprint")
    return _validate(record)["receipt_sha256"]


def verify_custodied_recovery(
        backup_path, checkpoint_path, reviewer_registry, floor_directory,
        trusted_receipt_path, custodian, *, checkpoint_key, floor_key, receipt_key):
    """Fail closed unless the custodian supplies the exact pinned fingerprint."""
    try:
        record = custodian.read()
        if record is None:
            return False
        _validate(record)
        receipt = load_registry_receipt(trusted_receipt_path)
        if receipt.get("sequence") != record["sequence"]:
            return False
        return verify_pinned_recovery(
            backup_path, checkpoint_path, reviewer_registry, floor_directory,
            trusted_receipt_path,
            expected_receipt_sha256=record["receipt_sha256"],
            checkpoint_key=checkpoint_key, floor_key=floor_key,
            receipt_key=receipt_key)
    except (CustodyError, OSError, ValueError, TypeError, KeyError):
        return False
