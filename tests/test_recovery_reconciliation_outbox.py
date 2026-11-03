"""Phase 64 durable recovery reconciliation outbox tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_execution_audit import execution_audit_head
from hedgeops.recovery_reconciliation_outbox import (
    execute_with_reconciliation_outbox, pending_reconciliations,
    reconcile_pending_outbox)

TOKEN = "phase64-operator-token-long-enough"
KEY = b"k" * 32


class Custody:
    def __init__(self):
        self.record = None
        self.fail = False

    def read(self):
        return None if self.record is None else dict(self.record)

    def compare_and_swap(self, old, new):
        if self.fail:
            raise OSError("offline")
        if old != self.record:
            return False
        self.record = dict(new)
        return True


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "fence.db"
        self.authority = RecoveryFenceAuthority(self.path, strict=True)
        self.generation = self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)
        self.custody = Custody()

    def tearDown(self):
        self.temp.cleanup()

    def execute(self, mutation=None):
        with patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
                   return_value=True):
            return execute_with_reconciliation_outbox(
                self.authority, None, None, None, None, None, None, None,
                self.generation, TOKEN, mutation or (lambda db: "done"),
                configured_token=TOKEN)

    def test_pending_survives_reopen(self):
        self.assertEqual(self.execute(), "done")
        self.authority = RecoveryFenceAuthority(self.path)
        self.assertEqual(len(pending_reconciliations(self.authority)), 1)
        self.assertEqual(pending_reconciliations(self.authority)[0],
                         execution_audit_head(self.authority))

    def test_reconcile_confirms_and_is_idempotent(self):
        self.execute()
        checkpoint = reconcile_pending_outbox(self.authority, KEY, self.custody)
        self.assertEqual(checkpoint["sequence"], 1)
        self.assertEqual(pending_reconciliations(self.authority), [])
        self.assertEqual(reconcile_pending_outbox(
            self.authority, KEY, self.custody)["sequence"], 1)

    def test_publication_failure_retains_pending(self):
        self.execute()
        self.custody.fail = True
        with self.assertRaises(Exception):
            reconcile_pending_outbox(self.authority, KEY, self.custody)
        self.assertEqual(len(pending_reconciliations(self.authority)), 1)
        self.custody.fail = False
        reconcile_pending_outbox(self.authority, KEY, self.custody)
        self.assertEqual(pending_reconciliations(self.authority), [])

    def test_mutation_failure_rolls_back_outbox(self):
        def reject(db):
            raise ValueError("mutation failed")
        with self.assertRaises(ValueError):
            self.execute(reject)
        self.assertEqual(pending_reconciliations(self.authority), [])
        self.assertEqual(execution_audit_head(self.authority)["sequence"], 0)

    def test_multiple_commits_reconciled_by_latest_head(self):
        self.execute()
        self.execute()
        self.assertEqual(len(pending_reconciliations(self.authority)), 2)
        checkpoint = reconcile_pending_outbox(self.authority, KEY, self.custody)
        self.assertEqual(checkpoint["sequence"], 2)
        self.assertEqual(pending_reconciliations(self.authority), [])


if __name__ == "__main__":
    unittest.main()
