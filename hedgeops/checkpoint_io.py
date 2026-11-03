"""Atomic local checkpoint files with strict loading and verification.

The destination is operator-controlled storage; this is not a remote trust anchor.
"""
import json
import hashlib
import hmac
import os
import tempfile
from pathlib import Path

from hedgeops.audit import export_checkpoint, verify_checkpoint
from hedgeops.store import canonical

MAX_CHECKPOINT_BYTES = 16384
AUTH_SCHEME = "hedgeops-checkpoint-hmac-sha256-v1"


def _authentication_key(key):
    if not isinstance(key, bytes) or len(key) < 32:
        raise ValueError("Checkpoint authentication key must be at least 32 bytes")
    return key


def _authenticate(checkpoint, key):
    body = {"scheme": AUTH_SCHEME, "checkpoint": checkpoint}
    signature = hmac.new(_authentication_key(key), canonical(body).encode("utf-8"),
                         hashlib.sha256).hexdigest()
    return {**body, "authentication_tag": signature}


def _verify_authentication(value, key):
    if not isinstance(value, dict) or set(value) != {"scheme", "checkpoint", "authentication_tag"}:
        return False
    if value["scheme"] != AUTH_SCHEME or not isinstance(value["authentication_tag"], str):
        return False
    expected = _authenticate(value["checkpoint"], key)["authentication_tag"]
    return hmac.compare_digest(expected, value["authentication_tag"])



def save_checkpoint(store, case_id, registry, destination, *, authentication_key=None):
    """Create a new checkpoint file without overwriting an existing one.

    A temporary file is fully written and synced first; a hard link then
    publishes it without replacing an existing destination. On POSIX local
    filesystems this prevents readers from observing a partial file.
    """
    path = Path(destination)
    if not path.parent.is_dir():
        raise FileNotFoundError("Checkpoint parent directory must already exist")
    checkpoint = export_checkpoint(store, case_id, registry)
    if authentication_key is not None:
        checkpoint = _authenticate(checkpoint, authentication_key)
    data = (canonical(checkpoint) + "\n").encode("utf-8")
    if len(data) > MAX_CHECKPOINT_BYTES:
        raise ValueError("Checkpoint exceeds size limit")
    temp_name = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix=".checkpoint-", dir=str(path.parent))
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.link(temp_name, path)
        # Best-effort directory fsync for crash consistency on POSIX.
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if temp_name is not None:
            os.unlink(temp_name)
    return path


def load_checkpoint(source):
    """Read a size-bounded checkpoint JSON object, rejecting malformed data."""
    path = Path(source)
    with path.open("rb") as stream:
        raw = stream.read(MAX_CHECKPOINT_BYTES + 1)
    if len(raw) > MAX_CHECKPOINT_BYTES:
        raise ValueError("Checkpoint exceeds size limit")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid checkpoint JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("Checkpoint must be a JSON object")
    return value


def verify_saved_checkpoint(store, source, registry, *, authentication_key=None):
    """Fail closed for corrupted or outdated checkpoint files."""
    try:
        checkpoint = load_checkpoint(source)
        if authentication_key is not None:
            if not _verify_authentication(checkpoint, authentication_key):
                return False
            checkpoint = checkpoint["checkpoint"]
        elif isinstance(checkpoint, dict) and checkpoint.get("scheme") == AUTH_SCHEME:
            return False  # Authenticated checkpoints require the authentication key.
        return verify_checkpoint(store, checkpoint, registry)
    except (OSError, ValueError, TypeError):
        return False
