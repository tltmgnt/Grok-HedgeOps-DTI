"""Strict recovery pinned to an independently trusted receipt fingerprint.

The expected digest MUST be obtained from a separate trusted custody channel.
"""
import hashlib
import hmac
import re

from hedgeops.registry_receipt import load_registry_receipt
from hedgeops.store import canonical
from hedgeops.strict_recovery import verify_receipt_gated_recovery

_HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def receipt_fingerprint(receipt):
    """Compute a stable digest over a canonical registry-head receipt."""
    if not isinstance(receipt, dict):
        raise ValueError("Receipt must be an object")
    return hashlib.sha256(canonical(receipt).encode("utf-8")).hexdigest()


def verify_pinned_recovery(
        backup_path, checkpoint_path, reviewer_registry, floor_directory,
        trusted_receipt_path, *, expected_receipt_sha256,
        checkpoint_key, floor_key, receipt_key):
    """Require externally pinned receipt identity before strict recovery."""
    if (not isinstance(expected_receipt_sha256, str) or
            _HEX_SHA256.fullmatch(expected_receipt_sha256) is None):
        return False
    try:
        receipt = load_registry_receipt(trusted_receipt_path)
        actual = receipt_fingerprint(receipt)
        if not hmac.compare_digest(actual, expected_receipt_sha256):
            return False
        return verify_receipt_gated_recovery(
            backup_path, checkpoint_path, reviewer_registry,
            floor_directory, trusted_receipt_path,
            checkpoint_key=checkpoint_key, floor_key=floor_key,
            receipt_key=receipt_key)
    except (OSError, ValueError, TypeError, KeyError):
        return False
