"""Regression tests for independently held execution audit heads."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_execution_audit import ensure_execution_audit, append_execution_event
from hedgeops.recovery_execution_custody import (
    ExecutionCustodyError, publish_execution_checkpoint,
    verify_custodied_execution, validate_execution_record)

KEY = b"k" * 32


class MemoryCustody:
    def __init__(self):
        self.record = None
        self.reads = 0
        self.change_on_read = None

    def read(self):
        self.reads += 1
        if self.reads == self.change_on_read and self.record is not None:
            self.record = dict(self.record, sequence=self.record["sequence"] + 1)
        return None if self.record is None else dict(self.record)

    def compare_and_swap(self, expected, new):
        if self.record != expected:
            return False
        self.record = dict(new)
        return True


class ExecutionCustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "audit.db"
        self.authority = RecoveryFenceAuthority(self.path, strict=True)
        ensure_execution_audit(self.authority)
        self.custody = MemoryCustody()

    def tearDown(self):
        self.tmp.cleanup()

    def append(self):
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            append_execution_event(db, 1)
            db.commit()

    def publish(self):
        return publish_execution_checkpoint(self.authority, KEY, self.custody)

    def test_publish_and_verify(self):
        self.append()
        checkpoint = self.publish()
        self.assertTrue(verify_custodied_execution(
            self.authority, checkpoint, KEY, self.custody))

    def test_monotonic_advance(self):
        self.append()
        self.publish()
        self.append()
        checkpoint = self.publish()
        self.assertEqual(checkpoint["sequence"], 2)

    def test_same_sequence_denied(self):
        self.append()
        self.publish()
        with self.assertRaises(ExecutionCustodyError):
            self.publish()

    def test_missing_custody_denied(self):
        self.append()
        checkpoint = self.publish()
        self.custody.record = None
        self.assertFalse(verify_custodied_execution(
            self.authority, checkpoint, KEY, self.custody))

    def test_substituted_digest_denied(self):
        self.append()
        checkpoint = self.publish()
        self.custody.record["checkpoint_sha256"] = "0" * 64
        self.assertFalse(verify_custodied_execution(
            self.authority, checkpoint, KEY, self.custody))

    def test_wrong_key_denied(self):
        self.append()
        checkpoint = self.publish()
        self.assertFalse(verify_custodied_execution(
            self.authority, checkpoint, b"x" * 32, self.custody))

    def test_truncated_journal_denied(self):
        self.append()
        self.append()
        checkpoint = self.publish()
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM recovery_execution_audit WHERE sequence=2")
        self.assertFalse(verify_custodied_execution(
            self.authority, checkpoint, KEY, self.custody))

    def test_changed_custody_denied(self):
        self.append()
        checkpoint = self.publish()
        self.custody.reads = 0
        self.custody.change_on_read = 2
        self.assertFalse(verify_custodied_execution(
            self.authority, checkpoint, KEY, self.custody))

    def test_boolean_sequence_denied(self):
        with self.assertRaises(ExecutionCustodyError):
            validate_execution_record({
                "sequence": True, "checkpoint_sha256": "0" * 64})

    def test_extra_field_denied(self):
        with self.assertRaises(ExecutionCustodyError):
            validate_execution_record({
                "sequence": 1, "checkpoint_sha256": "0" * 64, "extra": 1})


if __name__ == "__main__":
    unittest.main()
