import sqlite3
import tempfile
import unittest
from pathlib import Path

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_execution_audit import ensure_execution_audit, append_execution_event
from hedgeops.recovery_execution_checkpoint import create_execution_checkpoint, verify_execution_checkpoint

KEY = b"k" * 32


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "db.sqlite"
        self.authority = RecoveryFenceAuthority(self.path, strict=True)
        ensure_execution_audit(self.authority)

    def tearDown(self):
        self.tmp.cleanup()

    def append(self):
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            append_execution_event(db, 1)
            db.commit()

    def test_empty(self):
        with self.assertRaises(ValueError):
            create_execution_checkpoint(self.authority, KEY)

    def test_valid_suffix(self):
        self.append()
        checkpoint = create_execution_checkpoint(self.authority, KEY)
        self.assertTrue(verify_execution_checkpoint(self.authority, checkpoint, KEY))
        self.append()
        self.assertTrue(verify_execution_checkpoint(self.authority, checkpoint, KEY))

    def test_truncation(self):
        self.append()
        self.append()
        checkpoint = create_execution_checkpoint(self.authority, KEY)
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM recovery_execution_audit WHERE sequence=2")
        self.assertFalse(verify_execution_checkpoint(self.authority, checkpoint, KEY))

    def test_wrong_key(self):
        self.append()
        checkpoint = create_execution_checkpoint(self.authority, KEY)
        self.assertFalse(verify_execution_checkpoint(self.authority, checkpoint, b"x" * 32))

    def test_tampering(self):
        self.append()
        checkpoint = create_execution_checkpoint(self.authority, KEY)
        checkpoint["event_hash"] = "0" * 64
        self.assertFalse(verify_execution_checkpoint(self.authority, checkpoint, KEY))

    def test_extra_field(self):
        self.append()
        checkpoint = create_execution_checkpoint(self.authority, KEY)
        checkpoint["extra"] = True
        self.assertFalse(verify_execution_checkpoint(self.authority, checkpoint, KEY))

    def test_corrupt_journal(self):
        self.append()
        checkpoint = create_execution_checkpoint(self.authority, KEY)
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE recovery_execution_audit SET generation=2")
        self.assertFalse(verify_execution_checkpoint(self.authority, checkpoint, KEY))


if __name__ == "__main__":
    unittest.main()
