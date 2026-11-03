"""Phase 79: race between preflight integrity and confirmation transaction."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_reconciliation_outbox import (
    execute_with_reconciliation_outbox, reconcile_pending_outbox)
from hedgeops.recovery_outbox_integrity import verify_reconciliation_outbox
from hedgeops.recovery_execution_checkpoint import create_execution_checkpoint

TOKEN = "phase79-operator-token-long-enough"
KEY = b"k" * 32


class NoFinalRead:
    def read(self):
        raise AssertionError("Invalid outbox must fail before final custody read")


class RaceTests(unittest.TestCase):
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

    def run_race(self, sql, params=()):
        self.assertTrue(verify_reconciliation_outbox(self.authority))
        calls = []
        checkpoint = create_execution_checkpoint(self.authority, KEY)

        def intervening_publication(*args):
            calls.append("publication")
            with self.authority._connect() as db:
                db.execute(sql, params)
            return checkpoint

        with patch("hedgeops.recovery_reconciliation_outbox.reconcile_execution_custody",
                   side_effect=intervening_publication):
            with self.assertRaises(ValueError):
                reconcile_pending_outbox(self.authority, KEY, NoFinalRead())
        self.assertEqual(calls, ["publication"])
        with self.authority._connect() as db:
            confirmed = db.execute(
                "SELECT COUNT(*) FROM recovery_reconciliation_outbox "
                "WHERE confirmed=1").fetchone()[0]
        self.assertEqual(confirmed, 1 if "confirmed=1" in sql else 0)

    def test_missing_middle_after_preflight(self):
        self.run_race(
            "DELETE FROM recovery_reconciliation_outbox WHERE sequence=2")

    def test_missing_first_after_preflight(self):
        self.run_race(
            "DELETE FROM recovery_reconciliation_outbox WHERE sequence=1")

    def test_digest_changed_after_preflight(self):
        self.run_race(
            "UPDATE recovery_reconciliation_outbox SET event_hash=? "
            "WHERE sequence=2", ("0" * 64,))

    def test_confirmation_gap_after_preflight(self):
        self.run_race(
            "UPDATE recovery_reconciliation_outbox SET confirmed=1 "
            "WHERE sequence=3")


if __name__ == "__main__":
    unittest.main()
