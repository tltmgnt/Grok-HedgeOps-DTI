"""Phase 66 outbox tampering regression tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_reconciliation_outbox import (
    execute_with_reconciliation_outbox, reconcile_pending_outbox)
from hedgeops.recovery_outbox_integrity import (
    OutboxIntegrityError, verify_reconciliation_outbox)

TOKEN = "phase66-operator-token-long-enough"


class NoPublish:
    def read(self):
        raise AssertionError("Publication must not be attempted")


class OutboxIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.authority = RecoveryFenceAuthority(
            Path(self.temp.name) / "fence.db", strict=True)
        self.generation = self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)

    def tearDown(self):
        self.temp.cleanup()

    def execute(self):
        with patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
                   return_value=True):
            execute_with_reconciliation_outbox(
                self.authority, None, None, None, None, None, None, None,
                self.generation, TOKEN, lambda db: None,
                configured_token=TOKEN)

    def assert_denied(self):
        self.assertFalse(verify_reconciliation_outbox(self.authority))
        with self.assertRaises(OutboxIntegrityError):
            reconcile_pending_outbox(self.authority, b"k" * 32, NoPublish())

    def test_untampered_outbox(self):
        self.execute()
        self.assertTrue(verify_reconciliation_outbox(self.authority))

    def test_substituted_outbox_digest(self):
        self.execute()
        with self.authority._connect() as db:
            db.execute("UPDATE recovery_reconciliation_outbox SET event_hash=?",
                       ("0" * 64,))
        self.assert_denied()

    def test_missing_execution_audit_entry(self):
        self.execute()
        with self.authority._connect() as db:
            db.execute("DELETE FROM recovery_execution_audit WHERE sequence=1")
        self.assert_denied()

    def test_confirmation_gap(self):
        self.execute()
        self.execute()
        with self.authority._connect() as db:
            db.execute(
                "UPDATE recovery_reconciliation_outbox SET confirmed=1 "
                "WHERE sequence=2")
        self.assert_denied()

    def test_corrupt_audit_hash(self):
        self.execute()
        with self.authority._connect() as db:
            db.execute("UPDATE recovery_execution_audit SET event_hash=?",
                       ("f" * 64,))
        self.assert_denied()


if __name__ == "__main__":
    unittest.main()
