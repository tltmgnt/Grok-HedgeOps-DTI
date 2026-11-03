"""Phase 81 custody supersession at the final confirmation boundary."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_reconciliation_outbox import (
    execute_with_reconciliation_outbox, reconcile_pending_outbox,
    pending_reconciliations)
from hedgeops.recovery_execution_reconciliation import ExecutionReconciliationError
from hedgeops.recovery_execution_custody import execution_checkpoint_fingerprint

TOKEN = "phase81-operator-token-long-enough"
KEY = b"k" * 32


class Custody:
    def __init__(self, replacement=None):
        self.record = None
        self.reads = 0
        self.replacement = replacement

    def read(self):
        self.reads += 1
        if self.reads == 3:
            return self.replacement
        return None if self.record is None else dict(self.record)

    def compare_and_swap(self, expected, record):
        if expected != self.record:
            return False
        self.record = dict(record)
        return True


class CustodySupersessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.authority = RecoveryFenceAuthority(
            Path(self.temp.name) / "fence.db", strict=True)
        generation = self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)
        with patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
                   return_value=True):
            execute_with_reconciliation_outbox(
                self.authority, None, None, None, None, None, None, None,
                generation, TOKEN, lambda db: None,
                configured_token=TOKEN)

    def tearDown(self):
        self.temp.cleanup()

    def assert_no_confirmation(self):
        self.assertEqual([x["sequence"] for x in
                          pending_reconciliations(self.authority)], [1])

    def test_custody_disappears_before_confirmation(self):
        with self.assertRaises(ExecutionReconciliationError):
            reconcile_pending_outbox(self.authority, KEY, Custody(None))
        self.assert_no_confirmation()

    def test_custody_advances_before_confirmation(self):
        custodian = Custody({"sequence": 2, "checkpoint_sha256": "a" * 64})
        with self.assertRaises(ExecutionReconciliationError):
            reconcile_pending_outbox(self.authority, KEY, custodian)
        self.assert_no_confirmation()

    def test_custody_same_sequence_digest_changes(self):
        custodian = Custody({"sequence": 1, "checkpoint_sha256": "b" * 64})
        with self.assertRaises(ExecutionReconciliationError):
            reconcile_pending_outbox(self.authority, KEY, custodian)
        self.assert_no_confirmation()

    def test_unchanged_custody_confirms(self):
        custodian = Custody()
        custodian.replacement = None
        # Return the published record on the third read.
        original = custodian.read
        def stable_read():
            if custodian.reads == 2:
                return dict(custodian.record)
            return original()
        custodian.read = stable_read
        checkpoint = reconcile_pending_outbox(self.authority, KEY, custodian)
        self.assertEqual(checkpoint["sequence"], 1)
        self.assertEqual(custodian.record["checkpoint_sha256"],
                         execution_checkpoint_fingerprint(checkpoint))
        self.assertEqual(pending_reconciliations(self.authority), [])


if __name__ == "__main__":
    unittest.main()
