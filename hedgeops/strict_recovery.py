"""Strict receipt-gated offline recovery verification.

The receipt must be independently supplied by a trusted custodian.
"""
from pathlib import Path

from hedgeops.backup import verify_restored_journal
from hedgeops.floor_registry import latest_recovery_floor
from hedgeops.registry_receipt import (
    load_registry_receipt, verify_registry_receipt,
)


def verify_receipt_gated_recovery(
        backup_path, checkpoint_path, reviewer_registry, floor_directory,
        trusted_receipt_path, *, checkpoint_key, floor_key, receipt_key):
    """Require all three independently keyed authentication checks.

    No optional bypass: a valid receipt, complete local floor registry,
    authenticated checkpoint and matching restored journal are mandatory.
    The receipt path must be supplied from an independently trusted source.
    """
    if any(not isinstance(key, bytes) or len(key) < 32
           for key in (checkpoint_key, floor_key, receipt_key)):
        return False
    if len({checkpoint_key, floor_key, receipt_key}) != 3:
        return False
    if not all((backup_path, checkpoint_path, floor_directory, trusted_receipt_path)):
        return False
    try:
        receipt = load_registry_receipt(trusted_receipt_path)
        if not verify_registry_receipt(
                floor_directory, floor_key, receipt, receipt_key):
            return False
        floor = latest_recovery_floor(floor_directory, floor_key)
        if (floor["minimum_event_count"] != receipt["minimum_event_count"]
                or floor["minimum_head_hash"] != receipt["minimum_head_hash"]):
            return False
        return verify_restored_journal(
            backup_path, checkpoint_path, reviewer_registry,
            authentication_key=checkpoint_key,
            trusted_floor=floor, floor_key=floor_key)
    except (OSError, ValueError, TypeError, KeyError):
        return False
