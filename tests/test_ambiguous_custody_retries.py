"""Phase 84: ambiguous CAS outcomes require explicit, safe reconciliation."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_reconciliation_outbox import (
    execute_with_reconciliation_outbox, pending_reconciliations,
    reconcile_pending_outbox)
from hedgeops.recovery_execution_reconciliation import ExecutionReconciliationError

TOKEN = "phase84-operator-token-long-enough"
KEY = b"k" * 32


class AmbiguousCustody:
    def __init__(self, mode):
        self.mode = mode
        self.record = None
        self.writes = 0
        self.reads = 0

    def read(self):
        self.reads += 1
        return None if self.record is None else dict(self.record)

    def compare_and_swap(self, expected, record):
        self.writes += 1
        if self.mode == "committed_timeout":
            self.record = dict(record)
            self.mode = "normal"
            raise TimeoutError("response lost after commit")
        if self.mode == "not_committed_timeout":
            self.mode = "normal"
            raise TimeoutError("request lost before commit")
        if self.mode == "cas_conflict":
            self.mode = "normal"
            return False
        if self.record != expected:
            return False
        self.record = dict(record)
        return True


class AmbiguousPublicationTests(unittest.TestCase):
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

    def test_explicit_retry_after_uncertain_cas(self):
        for mode, expected_writes in (
                ("committed_timeout", 1),
                ("not_committed_timeout", 2),
                ("cas_conflict", 2)):
            with self.subTest(mode=mode):
                custody = AmbiguousCustody(mode)
                with self.assertRaises(ExecutionReconciliationError):
                    reconcile_pending_outbox(self.authority, KEY, custody)
                self.assertEqual(len(pending_reconciliations(self.authority)), 1)
                self.assertEqual(self.mutations, 1)
                checkpoint = reconcile_pending_outbox(self.authority, KEY, custody)
                self.assertEqual(checkpoint["sequence"], 1)
                self.assertEqual(custody.writes, expected_writes)
                self.assertEqual(pending_reconciliations(self.authority), [])
                self.assertEqual(self.mutations, 1)
                # Restore the pending flag to exercise each independent outcome.
                with self.authority._connect() as db:
                    db.execute("UPDATE recovery_reconciliation_outbox "
                               "SET confirmed=0 WHERE sequence=1")

    def test_idempotent_retry_after_confirmation(self):
        custody = AmbiguousCustody("committed_timeout")
        with self.assertRaises(ExecutionReconciliationError):
            reconcile_pending_outbox(self.authority, KEY, custody)
        reconcile_pending_outbox(self.authority, KEY, custody)
        writes = custody.writes
        reconcile_pending_outbox(self.authority, KEY, custody)
        self.assertEqual(custody.writes, writes)
        self.assertEqual(self.mutations, 1)


if __name__ == "__main__":
    unittest.main()
