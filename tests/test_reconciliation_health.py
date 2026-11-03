"""Phase 67 read-only reconciliation health regression tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.reconciliation_health import reconciliation_health
from hedgeops.recovery_reconciliation_outbox import execute_with_reconciliation_outbox

TOKEN = "phase67-operator-token-long-enough"


class HealthTests(unittest.TestCase):
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

    def test_missing_schema_is_unavailable(self):
        status = reconciliation_health(self.authority)
        self.assertEqual(status["status"], "unavailable")

    def test_pending_and_confirmed_counts(self):
        self.execute()
        self.execute()
        status = reconciliation_health(self.authority)
        self.assertEqual(status, {"status": "pending", "pending": 2,
                                  "confirmed": 0, "audit_head": 2})
        with self.authority._connect() as db:
            db.execute("UPDATE recovery_reconciliation_outbox SET confirmed=1")
        self.assertEqual(reconciliation_health(self.authority),
                         {"status": "healthy", "pending": 0,
                          "confirmed": 2, "audit_head": 2})

    def test_hash_mismatch_is_integrity_failure(self):
        self.execute()
        with self.authority._connect() as db:
            db.execute("UPDATE recovery_reconciliation_outbox SET event_hash=?",
                       ("0" * 64,))
        self.assertEqual(reconciliation_health(self.authority)["status"],
                         "integrity_failure")

    def test_confirmation_gap_is_integrity_failure(self):
        self.execute()
        self.execute()
        with self.authority._connect() as db:
            db.execute("UPDATE recovery_reconciliation_outbox "
                       "SET confirmed=1 WHERE sequence=2")
        self.assertEqual(reconciliation_health(self.authority)["status"],
                         "integrity_failure")

    def test_health_has_no_remote_or_mutation_side_effects(self):
        self.execute()
        with patch("hedgeops.recovery_reconciliation_outbox.reconcile_execution_custody",
                   side_effect=AssertionError("remote publication")):
            first = reconciliation_health(self.authority)
            second = reconciliation_health(self.authority)
        self.assertEqual(first, second)
        self.assertEqual(first["pending"], 1)


if __name__ == "__main__":
    unittest.main()
