"""Consistent SQLite backup and offline restore verification.

Backup files and trusted checkpoints must be stored separately by operators.
"""
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from hedgeops.checkpoint_io import save_checkpoint, verify_saved_checkpoint
from hedgeops.store import EventStore


def backup_journal(store, destination):
    """Snapshot a live SQLite connection without replacing an existing file."""
    path = Path(destination)
    if not path.parent.is_dir():
        raise FileNotFoundError("Backup parent directory must exist")
    if path.exists() or path.is_symlink():
        raise FileExistsError("Backup destination already exists")
    temp_name = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix=".hedgeops-backup-", dir=str(path.parent))
        os.close(fd)
        with closing(sqlite3.connect(temp_name)) as target:
            store.db.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("SQLite backup integrity check failed")
        with open(temp_name, "rb") as source:
            os.fsync(source.fileno())
        os.chmod(temp_name, 0o600)
        os.link(temp_name, path)
        directory_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temp_name is not None:
            os.unlink(temp_name)
    return path


def verify_restored_journal(backup_path, checkpoint_path, registry):
    """Read-only verification of a restored backup against a trusted checkpoint."""
    path = Path(backup_path)
    if not path.is_file():
        return False
    try:
        # SQLite URI mode=ro avoids silently creating missing databases.
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                return False
        # EventStore opens in read/write mode; verify against a separate
        # temporary copy so the original backup is never modified.
        with tempfile.TemporaryDirectory() as directory:
            restored = Path(directory) / "restored.sqlite3"
            with closing(sqlite3.connect(restored)) as target:
                with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as source:
                    source.backup(target)
                target.commit()
            with EventStore(restored) as store:
                return store.verify_chain() and verify_saved_checkpoint(
                    store, checkpoint_path, registry)
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError):
        return False


def backup_with_checkpoint(store, case_id, registry, backup_path, checkpoint_path):
    """Create a snapshot and a checkpoint derived from that exact snapshot.

    Both destinations must be new files. A failure after backup publication
    may leave an unpaired backup, which must not be treated as verified.
    The caller must preserve the checkpoint in independently trusted storage.
    """
    backup = Path(backup_path)
    checkpoint = Path(checkpoint_path)
    if backup.resolve() == checkpoint.resolve():
        raise ValueError("Backup and checkpoint destinations must differ")
    if (backup.exists() or backup.is_symlink() or
            checkpoint.exists() or checkpoint.is_symlink()):
        raise FileExistsError("Backup and checkpoint destinations must be unused")
    backup_journal(store, backup)
    # Open a private copy: EventStore initialization must not alter the
    # published backup, and concurrent live writes are irrelevant.
    with tempfile.TemporaryDirectory() as directory:
        restored = Path(directory) / "snapshot.sqlite3"
        with closing(sqlite3.connect(restored)) as target:
            with closing(sqlite3.connect(backup.resolve().as_uri() + "?mode=ro",
                                         uri=True)) as source:
                source.backup(target)
            target.commit()
        with EventStore(restored) as snapshot:
            save_checkpoint(snapshot, case_id, registry, checkpoint)
    if not verify_restored_journal(backup, checkpoint, registry):
        raise ValueError("Backup/checkpoint verification failed")
    return backup, checkpoint
