"""Phase 65 concurrency and custody-change regression tests."""
import concurrent.futures
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_reconciliation_outbox import (
    execute_with_reconciliation_outbox, pending_reconciliations,
    reconcile_pending_outbox)
from hedgeops.recovery_execution_reconciliation import ExecutionReconciliationError

TOKEN = "phase65-operator-token-long-enough"
KEY = b"k" * 32


class Custody:
    def __init__(self):
        self.lock = threading.Lock()
        self.record = None
        self.reads = 0
        self.change_on_read = None

    def read(self):
        with self.lock:
            self.reads += 1
            if self.reads == self.change_on_read and self.record is not None:
                self.record = dict(self.record, sequence=self.record["sequence"] + 1)
            return None if self.record is None else dict(self.record)

    def compare_and_swap(self, expected, new):
        with self.lock:
            if self.record != expected:
                return False
            self.record = dict(new)
            return True


class ReconciliationRaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.authority = RecoveryFenceAuthority(
            Path(self.temp.name) / "fence.db", strict=True)
        self.generation = self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)
        self.custody = Custody()

    def tearDown(self):
        self.temp.cleanup()

    def execute(self):
        with patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
                   return_value=True):
            return execute_with_reconciliation_outbox(
                self.authority, None, None, None, None, None, None, None,
                self.generation, TOKEN, lambda db: "done",
                configured_token=TOKEN)

    def test_concurrent_publishers_converge(self):
        self.execute()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(reconcile_pending_outbox,
                                   self.authority, KEY, self.custody)
                       for _ in range(2)]
            results = [future.result(timeout=10) for future in futures]
        self.assertEqual([item["sequence"] for item in results], [1, 1])
        self.assertEqual(pending_reconciliations(self.authority), [])

    def test_custody_changes_before_confirmation(self):
        self.execute()
        # First read is pre-CAS; second read confirms publication;
        # third read occurs before the local outbox confirmation.
        self.custody.change_on_read = 3
        with self.assertRaises(ExecutionReconciliationError):
            reconcile_pending_outbox(self.authority, KEY, self.custody)
        self.assertEqual(len(pending_reconciliations(self.authority)), 1)

    def test_local_head_advances_during_remote_publication(self):
        self.execute()
        original = self.custody.compare_and_swap

        def advance(expected, record):
            self.execute()
            return original(expected, record)

        with patch.object(self.custody, "compare_and_swap", side_effect=advance):
            checkpoint = reconcile_pending_outbox(
                self.authority, KEY, self.custody)
        self.assertEqual(checkpoint["sequence"], 1)
        pending = pending_reconciliations(self.authority)
        self.assertEqual([item["sequence"] for item in pending], [2])
        self.assertEqual(reconcile_pending_outbox(
            self.authority, KEY, self.custody)["sequence"], 2)
        self.assertEqual(pending_reconciliations(self.authority), [])


if __name__ == "__main__":
    unittest.main()
