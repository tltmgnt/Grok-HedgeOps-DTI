"""Phase 77 outbox contiguity and tamper detection."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_reconciliation_outbox import execute_with_reconciliation_outbox
from hedgeops.reconciliation_health import reconciliation_health

TOKEN = "phase77-operator-token-long-enough"


class ContiguityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.authority = RecoveryFenceAuthority(
            Path(self.temp.name) / "fence.db", strict=True)
        self.generation = self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)
        for _ in range(3):
            with patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
                       return_value=True):
                execute_with_reconciliation_outbox(
                    self.authority, None, None, None, None, None, None, None,
                    self.generation, TOKEN, lambda db: None,
                    configured_token=TOKEN)

    def tearDown(self):
        self.temp.cleanup()

    def test_complete_outbox_is_pending(self):
        self.assertEqual(reconciliation_health(self.authority)["status"], "pending")

    def test_missing_middle_row_is_integrity_failure(self):
        with self.authority._connect() as db:
            db.execute("DELETE FROM recovery_reconciliation_outbox WHERE sequence=2")
        self.assertEqual(reconciliation_health(self.authority)["status"],
                         "integrity_failure")

    def test_missing_first_row_is_integrity_failure(self):
        with self.authority._connect() as db:
            db.execute("DELETE FROM recovery_reconciliation_outbox WHERE sequence=1")
        self.assertEqual(reconciliation_health(self.authority)["status"],
                         "integrity_failure")

    def test_missing_tail_remains_untracked(self):
        with self.authority._connect() as db:
            db.execute("DELETE FROM recovery_reconciliation_outbox WHERE sequence=3")
            db.execute("UPDATE recovery_reconciliation_outbox SET confirmed=1")
        health = reconciliation_health(self.authority)
        self.assertEqual(health["status"], "healthy")
        self.assertEqual(health["confirmed"], 2)
        self.assertEqual(health["audit_head"], 3)

    def test_reordered_digest_is_integrity_failure(self):
        with self.authority._connect() as db:
            db.execute("UPDATE recovery_reconciliation_outbox SET event_hash="
                       "(SELECT event_hash FROM recovery_execution_audit "
                       "WHERE sequence=1) WHERE sequence=2")
        self.assertEqual(reconciliation_health(self.authority)["status"],
                         "integrity_failure")


if __name__ == "__main__":
    unittest.main()
