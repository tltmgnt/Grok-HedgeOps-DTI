"""Phase 62 post-commit custody reconciliation tests."""
import tempfile
import unittest
from pathlib import Path

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_execution_audit import ensure_execution_audit, append_execution_event
from hedgeops.recovery_execution_reconciliation import (
    ExecutionReconciliationError, reconcile_execution_custody)

KEY = b"k" * 32


class Custody:
    def __init__(self):
        self.record = None
        self.fail_write = False
        self.fail_read = False

    def read(self):
        if self.fail_read:
            raise OSError("unavailable")
        return None if self.record is None else dict(self.record)

    def compare_and_swap(self, expected, new):
        if self.fail_write:
            raise TimeoutError("uncertain")
        if self.record != expected:
            return False
        self.record = dict(new)
        return True


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.authority = RecoveryFenceAuthority(
            Path(self.temp.name) / "fence.db", strict=True)
        ensure_execution_audit(self.authority)
        self.custody = Custody()
        self.advance()

    def tearDown(self):
        self.temp.cleanup()

    def advance(self):
        with self.authority._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            append_execution_event(db, 1)
            db.commit()

    def reconcile(self):
        return reconcile_execution_custody(self.authority, KEY, self.custody)

    def test_first_publication(self):
        checkpoint = self.reconcile()
        self.assertEqual(self.custody.record["sequence"], checkpoint["sequence"])

    def test_retry_is_idempotent(self):
        self.reconcile()
        self.assertEqual(self.reconcile()["sequence"], 1)

    def test_publish_next_head(self):
        self.reconcile()
        self.advance()
        self.assertEqual(self.reconcile()["sequence"], 2)

    def test_conflicting_same_sequence_denied(self):
        self.reconcile()
        self.custody.record["checkpoint_sha256"] = "0" * 64
        with self.assertRaises(ExecutionReconciliationError):
            self.reconcile()

    def test_future_custody_head_denied(self):
        self.reconcile()
        self.custody.record["sequence"] = 99
        with self.assertRaises(ExecutionReconciliationError):
            self.reconcile()

    def test_publication_timeout_requires_retry(self):
        self.custody.fail_write = True
        with self.assertRaisesRegex(ExecutionReconciliationError, "uncertain"):
            self.reconcile()
        self.custody.fail_write = False
        self.assertEqual(self.reconcile()["sequence"], 1)

    def test_unavailable_custody_requires_retry(self):
        self.custody.fail_read = True
        with self.assertRaises(ExecutionReconciliationError):
            self.reconcile()
        self.custody.fail_read = False
        self.assertEqual(self.reconcile()["sequence"], 1)


if __name__ == "__main__":
    unittest.main()
