"""Phase 78 shared outbox integrity and publication admission tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_reconciliation_outbox import (
    execute_with_reconciliation_outbox, reconcile_pending_outbox)
from hedgeops.recovery_outbox_integrity import (
    OutboxIntegrityError, verify_reconciliation_outbox)
from hedgeops.reconciliation_health import reconciliation_health

TOKEN = "phase78-operator-token-long-enough"


class NoRemote:
    def read(self):
        raise AssertionError("No custody reads permitted for invalid outbox")


class SharedIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.authority = RecoveryFenceAuthority(
            Path(self.temp.name) / "fence.db", strict=True)
        generation = self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)
        for _ in range(3):
            with patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
                       return_value=True):
                execute_with_reconciliation_outbox(
                    self.authority, None, None, None, None, None, None, None,
                    generation, TOKEN, lambda db: None,
                    configured_token=TOKEN)

    def tearDown(self):
        self.temp.cleanup()

    def assert_rejected(self):
        self.assertFalse(verify_reconciliation_outbox(self.authority))
        self.assertEqual(reconciliation_health(self.authority)["status"],
                         "integrity_failure")
        with self.assertRaises(OutboxIntegrityError):
            reconcile_pending_outbox(self.authority, b"k" * 32, NoRemote())

    def test_complete_prefix_accepted(self):
        self.assertTrue(verify_reconciliation_outbox(self.authority))

    def test_missing_first_rejected_before_remote(self):
        with self.authority._connect() as db:
            db.execute("DELETE FROM recovery_reconciliation_outbox WHERE sequence=1")
        self.assert_rejected()

    def test_missing_middle_rejected_before_remote(self):
        with self.authority._connect() as db:
            db.execute("DELETE FROM recovery_reconciliation_outbox WHERE sequence=2")
        self.assert_rejected()

    def test_missing_tail_is_valid_prefix(self):
        with self.authority._connect() as db:
            db.execute("DELETE FROM recovery_reconciliation_outbox WHERE sequence=3")
        self.assertTrue(verify_reconciliation_outbox(self.authority))

    def test_corrupted_digest_rejected_before_remote(self):
        with self.authority._connect() as db:
            db.execute("UPDATE recovery_reconciliation_outbox SET event_hash=? "
                       "WHERE sequence=2", ("0" * 64,))
        self.assert_rejected()


if __name__ == "__main__":
    unittest.main()
