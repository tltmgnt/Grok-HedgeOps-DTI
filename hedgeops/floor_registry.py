"""Locally serialized recovery-floor registry.

The registry is not an independent monotonic trust anchor. Operators must
protect its contents and preserve the latest accepted sequence externally.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path

from hedgeops.rollback import create_recovery_floor, verify_recovery_floor
from hedgeops.store import canonical

PREFIX = "floor-"
SUFFIX = ".json"
MAX_RECORD_BYTES = 8192


def _records(directory):
    paths = sorted(directory.glob(PREFIX + "*" + SUFFIX))
    expected = 1
    records = []
    previous = "GENESIS"
    for path in paths:
        if path.name != "{}{:012d}{}".format(PREFIX, expected, SUFFIX):
            raise ValueError("Recovery floor registry has a sequence gap")
        if path.is_symlink():
            raise ValueError("Recovery floor record is a symlink")
        with path.open("rb") as stream:
            data = stream.read(MAX_RECORD_BYTES + 1)
        if len(data) > MAX_RECORD_BYTES:
            raise ValueError("Recovery floor record exceeds size limit")
        try:
            record = json.loads(data.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid recovery floor record") from exc
        if not isinstance(record, dict) or set(record) != {
                "sequence", "previous_record_hash", "floor", "record_hash"}:
            raise ValueError("Invalid recovery floor record schema")
        body = {key: record[key] for key in ("sequence", "previous_record_hash", "floor")}
        digest = hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()
        if (type(record["sequence"]) is not int or record["sequence"] != expected
                or record["previous_record_hash"] != previous
                or record["record_hash"] != digest):
            raise ValueError("Recovery floor registry chain is invalid")
        records.append(record)
        previous = digest
        expected += 1
    return records


def _read_latest(directory, key):
    records = _records(directory)
    last_count = 0
    last_head = None
    for record in records:
        floor = record["floor"]
        if not verify_recovery_floor(floor, key):
            raise ValueError("Invalid authenticated recovery floor")
        count = floor["minimum_event_count"]
        head = floor["minimum_head_hash"]
        if count < last_count or (count == last_count and head != last_head):
            raise ValueError("Recovery floor position regressed or forked")
        last_count, last_head = count, head
    return records


def latest_recovery_floor(directory, key):
    """Load and authenticate the highest local floor; fail if missing."""
    directory = Path(directory)
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("Invalid recovery floor directory")
    records = _read_latest(directory, key)
    if not records:
        raise ValueError("Recovery floor registry is empty")
    return records[-1]["floor"]


def publish_recovery_floor(store, checkpoint, directory, key):
    """Publish a floor only if its journal history extends the last floor."""
    directory = Path(directory)
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("Recovery floor directory must exist and not be a symlink")
    # Serialize cooperating publishers. Keep this lock file in a protected directory.
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    lock_fd = os.open(str(directory / ".floor-registry.lock"), flags, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        records = _read_latest(directory, key)
        floor = create_recovery_floor(checkpoint, key)
        events = store.history()
        count = floor["minimum_event_count"]
        if (not store.verify_chain() or len(events) != count
                or events[-1]["event_hash"] != floor["minimum_head_hash"]):
            raise ValueError("Checkpoint does not describe the current journal")
        if records:
            old = records[-1]["floor"]
            old_count = old["minimum_event_count"]
            if (count <= old_count or
                    events[old_count - 1]["event_hash"] != old["minimum_head_hash"]):
                raise ValueError("Floor must advance the previously trusted history")
        body = {
            "sequence": len(records) + 1,
            "previous_record_hash": records[-1]["record_hash"] if records else "GENESIS",
            "floor": floor,
        }
        record = {**body, "record_hash": hashlib.sha256(
            canonical(body).encode("utf-8")).hexdigest()}
        path = directory / "{}{:012d}{}".format(PREFIX, len(records) + 1, SUFFIX)
        data = (canonical(record) + "\n").encode("utf-8")
        if len(data) > MAX_RECORD_BYTES:
            raise ValueError("Recovery floor record exceeds size limit")
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        dir_fd = os.open(str(directory), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        return floor
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
