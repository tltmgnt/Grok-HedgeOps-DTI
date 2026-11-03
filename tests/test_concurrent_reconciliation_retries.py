"""Phase 85: deterministic concurrent reconciliation retry convergence."""
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

TOKEN = "phase85-operator-token-long-enough"
KEY = b"k" * 32


class RacingCustody:
    def __init__(self, contenders):
        self.lock = threading.Lock()
        self.barrier = threading.Barrier(contenders, timeout=15)
        self.record = None
        self.writes = 0
        self.successful_writes = 0

    def read(self):
        with self.lock:
            return None if self.record is None else dict(self.record)

    def compare_and_swap(self, expected, record):
        # Force all contenders to observe the same absent remote head.
        self.barrier.wait()
        with self.lock:
            self.writes += 1
            if self.record != expected:
                return False
            self.record = dict(record)
            self.successful_writes += 1
            return True


class ConcurrentRetryTests(unittest.TestCase):
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

    def test_four_competing_publishers_converge_on_one_custody_write(self):
        custody = RacingCustody(4)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(reconcile_pending_outbox,
                                   self.authority, KEY, custody)
                       for _ in range(4)]
            results = [future.result(timeout=25) for future in futures]
        self.assertEqual([checkpoint["sequence"] for checkpoint in results],
                         [1, 1, 1, 1])
        self.assertEqual(custody.writes, 4)
        self.assertEqual(custody.successful_writes, 1)
        self.assertEqual(pending_reconciliations(self.authority), [])
        self.assertEqual(self.mutations, 1)
        with self.authority._connect() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM recovery_execution_audit").fetchone()[0], 1)
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM recovery_reconciliation_outbox "
                "WHERE confirmed=1").fetchone()[0], 1)

    def test_later_retry_is_idempotent(self):
        custody = RacingCustody(4)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(reconcile_pending_outbox,
                                   self.authority, KEY, custody)
                       for _ in range(4)]
            for future in futures:
                future.result(timeout=25)
        writes = custody.writes
        self.assertEqual(reconcile_pending_outbox(
            self.authority, KEY, custody)["sequence"], 1)
        self.assertEqual(custody.writes, writes)
        self.assertEqual(self.mutations, 1)


if __name__ == "__main__":
    unittest.main()
