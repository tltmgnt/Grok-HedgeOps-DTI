"""Authenticated, portable receipts for recovery-floor registry heads.

Receipt freshness is only as strong as independent operator custody.
"""
import hashlib
import hmac
import json
import os
from pathlib import Path

from hedgeops.floor_registry import _read_latest
from hedgeops.store import canonical

RECEIPT_SCHEME = "hedgeops-registry-head-receipt-v1"
MAX_RECEIPT_BYTES = 4096


def _key(key):
    if not isinstance(key, bytes) or len(key) < 32:
        raise ValueError("Receipt authentication key must be at least 32 bytes")
    return key


def _sign(body, key):
    return hmac.new(_key(key), canonical(body).encode("utf-8"),
                    hashlib.sha256).hexdigest()


def export_registry_receipt(directory, floor_key, receipt_key):
    """Create a receipt from a fully validated local registry."""
    directory = Path(directory)
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("Invalid registry directory")
    records = _read_latest(directory, floor_key)
    if not records:
        raise ValueError("Cannot receipt an empty registry")
    last = records[-1]
    body = {
        "scheme": RECEIPT_SCHEME,
        "sequence": last["sequence"],
        "record_hash": last["record_hash"],
        "minimum_event_count": last["floor"]["minimum_event_count"],
        "minimum_head_hash": last["floor"]["minimum_head_hash"],
    }
    return {**body, "authentication_tag": _sign(body, receipt_key)}


def verify_registry_receipt(directory, floor_key, receipt, receipt_key):
    """Require the local registry to match an independently supplied receipt."""
    if not isinstance(receipt, dict) or set(receipt) != {
            "scheme", "sequence", "record_hash", "minimum_event_count",
            "minimum_head_hash", "authentication_tag"}:
        return False
    if (receipt["scheme"] != RECEIPT_SCHEME or
            type(receipt["sequence"]) is not int or receipt["sequence"] < 1 or
            type(receipt["minimum_event_count"]) is not int or
            receipt["minimum_event_count"] < 1 or
            not isinstance(receipt["record_hash"], str) or
            len(receipt["record_hash"]) != 64 or
            not isinstance(receipt["minimum_head_hash"], str) or
            len(receipt["minimum_head_hash"]) != 64 or
            not isinstance(receipt["authentication_tag"], str) or
            len(receipt["authentication_tag"]) != 64):
        return False
    body = {key: value for key, value in receipt.items()
            if key != "authentication_tag"}
    try:
        expected = _sign(body, receipt_key)
        if not hmac.compare_digest(expected, receipt["authentication_tag"]):
            return False
        current = export_registry_receipt(directory, floor_key, receipt_key)
        return current == receipt
    except (ValueError, OSError, TypeError, KeyError):
        return False


def save_registry_receipt(receipt, destination):
    """Create a new receipt file, refusing overwrite and symlink destinations."""
    path = Path(destination)
    if not path.parent.is_dir():
        raise FileNotFoundError("Receipt directory must exist")
    data = (canonical(receipt) + "\n").encode("utf-8")
    if len(data) > MAX_RECEIPT_BYTES:
        raise ValueError("Receipt exceeds size limit")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(path), flags, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    dir_fd = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
    return path


def load_registry_receipt(source):
    path = Path(source)
    if path.is_symlink():
        raise ValueError("Receipt symlinks are not accepted")
    with path.open("rb") as stream:
        data = stream.read(MAX_RECEIPT_BYTES + 1)
    if len(data) > MAX_RECEIPT_BYTES:
        raise ValueError("Receipt exceeds size limit")
    try:
        result = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid receipt JSON") from exc
    if not isinstance(result, dict):
        raise ValueError("Receipt must be an object")
    return result
