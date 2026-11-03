"""Atomic local checkpoint files with strict loading and verification.

The destination is operator-controlled storage; this is not a remote trust anchor.
"""
import json
import os
import tempfile
from pathlib import Path

from hedgeops.audit import export_checkpoint, verify_checkpoint
from hedgeops.store import canonical

MAX_CHECKPOINT_BYTES = 16384


def save_checkpoint(store, case_id, registry, destination):
    """Create a new checkpoint file without overwriting an existing one.

    A temporary file is fully written and synced first; a hard link then
    publishes it without replacing an existing destination. On POSIX local
    filesystems this prevents readers from observing a partial file.
    """
    path = Path(destination)
    if not path.parent.is_dir():
        raise FileNotFoundError("Checkpoint parent directory must already exist")
    data = (canonical(export_checkpoint(store, case_id, registry)) + "\n").encode("utf-8")
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


def verify_saved_checkpoint(store, source, registry):
    """Fail closed for corrupted or outdated checkpoint files."""
    try:
        return verify_checkpoint(store, load_checkpoint(source), registry)
    except (OSError, ValueError, TypeError):
        return False
