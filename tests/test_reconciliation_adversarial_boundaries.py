"""Phase 87 adversarial reconciliation boundary security regressions."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_execution_checkpoint import create_execution_checkpoint
from hedgeops.recovery_execution_custody import execution_checkpoint_fingerprint
from hedgeops.recovery_execution_reconciliation import ExecutionReconciliationError
from hedgeops.recovery_outbox_integrity import OutboxIntegrityError
from hedgeops.recovery_reconciliation_outbox import (
    execute_with_reconciliation_outbox, pending_reconciliations,
    reconcile_pending_outbox)

TOKEN = "phase87-operator-token-long-enough"
KEY = b"k" * 32


class ReadOnlyCustody:
    def __init__(self, record):
        self.record = record
        self.reads = 0

    def read(self):
        self.reads += 1
        return self.record

    def compare_and_swap(self, expected, new):
        raise AssertionError("Unexpected custody write")


class AdversarialBoundaryTests(unittest.TestCase):
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
        self.checkpoint = create_execution_checkpoint(self.authority, KEY)
        self.record = {
            "sequence": self.checkpoint["sequence"],
            "checkpoint_sha256": execution_checkpoint_fingerprint(self.checkpoint)}

    def tearDown(self):
        self.temp.cleanup()

    def test_same_sequence_forged_digest_is_denied(self):
        forged = dict(self.record, checkpoint_sha256="0" * 64)
        custody = ReadOnlyCustody(forged)
        with self.assertRaises(ExecutionReconciliationError):
            reconcile_pending_outbox(self.authority, KEY, custody)
        self.assertEqual(custody.reads, 1)
        self.assertEqual(len(pending_reconciliations(self.authority)), 1)

    def test_rollback_to_missing_custody_is_denied_at_final_boundary(self):
        custody = ReadOnlyCustody(None)
        with patch("hedgeops.recovery_reconciliation_outbox.reconcile_execution_custody",
                   return_value=self.checkpoint):
            with self.assertRaises(ExecutionReconciliationError):
                reconcile_pending_outbox(self.authority, KEY, custody)
        self.assertEqual(len(pending_reconciliations(self.authority)), 1)

    def test_outbox_digest_tampering_blocks_custody_io(self):
        with self.authority._connect() as db:
            db.execute("UPDATE recovery_reconciliation_outbox "
                       "SET event_hash=? WHERE sequence=1", ("f" * 64,))
        custody = ReadOnlyCustody(self.record)
        with self.assertRaises(OutboxIntegrityError):
            reconcile_pending_outbox(self.authority, KEY, custody)
        self.assertEqual(custody.reads, 0)

    def test_execution_audit_tampering_blocks_custody_io(self):
        with self.authority._connect() as db:
            db.execute("UPDATE recovery_execution_audit "
                       "SET event_hash=? WHERE sequence=1", ("f" * 64,))
        custody = ReadOnlyCustody(self.record)
        with self.assertRaises(OutboxIntegrityError):
            reconcile_pending_outbox(self.authority, KEY, custody)
        self.assertEqual(custody.reads, 0)

    def test_confirmed_prefix_forgery_blocks_custody_io(self):
        with self.authority._connect() as db:
            db.execute("UPDATE recovery_reconciliation_outbox "
                       "SET confirmed=1 WHERE sequence=1")
            db.execute("UPDATE recovery_reconciliation_outbox "
                       "SET event_hash=? WHERE sequence=1", ("f" * 64,))
        custody = ReadOnlyCustody(self.record)
        with self.assertRaises(OutboxIntegrityError):
            reconcile_pending_outbox(self.authority, KEY, custody)
        self.assertEqual(custody.reads, 0)


if __name__ == "__main__":
    unittest.main()
