"""Phase 86: partial publication failure amid competing reconciliation workers."""
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

TOKEN = "phase86-operator-token-long-enough"
KEY = b"k" * 32


class PartialFailureCustody:
    def __init__(self):
        self.lock = threading.Lock()
        self.initial_reads = threading.Barrier(2, timeout=15)
        self.record = None
        self.read_count = 0
        self.cas_count = 0
        self.successful_writes = 0

    def read(self):
        with self.lock:
            self.read_count += 1
            first_round = self.read_count <= 2
            result = None if self.record is None else dict(self.record)
        if first_round:
            self.initial_reads.wait()
        return result

    def compare_and_swap(self, expected, new):
        with self.lock:
            self.cas_count += 1
            if self.cas_count == 1:
                raise TimeoutError("publication failed before commit")
            if self.record != expected:
                return False
            self.record = dict(new)
            self.successful_writes += 1
            return True


class CompetingPartialFailureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.authority = RecoveryFenceAuthority(
            Path(self.temp.name) / "fence.db", strict=True)
        self.mutations = 0
        generation = self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)

        def mutation(db):
            self.mutations += 1

        with patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
                   return_value=True):
            execute_with_reconciliation_outbox(
                self.authority, None, None, None, None, None, None, None,
                generation, TOKEN, mutation, configured_token=TOKEN)

    def tearDown(self):
        self.temp.cleanup()

    def test_failed_and_successful_workers_converge_after_explicit_retry(self):
        custody = PartialFailureCustody()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(reconcile_pending_outbox,
                                   self.authority, KEY, custody)
                       for _ in range(2)]
            outcomes = []
            for future in futures:
                try:
                    outcomes.append(future.result(timeout=25)["sequence"])
                except ExecutionReconciliationError:
                    outcomes.append("retry")
        self.assertCountEqual(outcomes, [1, "retry"])
        self.assertEqual(custody.successful_writes, 1)
        self.assertEqual(custody.cas_count, 2)
        self.assertEqual(self.mutations, 1)
        self.assertEqual(pending_reconciliations(self.authority), [])
        self.assertEqual(reconcile_pending_outbox(
            self.authority, KEY, custody)["sequence"], 1)
        self.assertEqual(custody.cas_count, 2)
        self.assertEqual(self.mutations, 1)
        with self.authority._connect() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM recovery_execution_audit").fetchone()[0], 1)
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM recovery_reconciliation_outbox "
                "WHERE confirmed=1").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
