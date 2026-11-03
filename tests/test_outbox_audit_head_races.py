"""Phase 80 regression for an audit head that advances during publication."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_execution_checkpoint import create_execution_checkpoint
from hedgeops.recovery_reconciliation_outbox import (
    execute_with_reconciliation_outbox, reconcile_pending_outbox)

TOKEN = "phase80-operator-token-long-enough"
KEY = b"k" * 32


class NoRead:
    def read(self):
        raise AssertionError("Unexpected final custody read")


class AuditHeadRaceTests(unittest.TestCase):
    def test_audit_advance_blocks_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            authority = RecoveryFenceAuthority(Path(directory) / "fence.db",
                                               strict=True)
            generation = authority.acquire_authorized(
                "operator", TOKEN, configured_token=TOKEN)

            def execute():
                with patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
                           return_value=True):
                    execute_with_reconciliation_outbox(
                        authority, None, None, None, None, None, None, None,
                        generation, TOKEN, lambda db: None,
                        configured_token=TOKEN)

            execute()
            checkpoint = create_execution_checkpoint(authority, KEY)

            def publish(*args):
                execute()
                return checkpoint

            with patch("hedgeops.recovery_reconciliation_outbox.reconcile_execution_custody",
                       side_effect=publish):
                with self.assertRaisesRegex(RuntimeError, "Execution audit advanced"):
                    reconcile_pending_outbox(authority, KEY, NoRead())

            with authority._connect() as db:
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM recovery_execution_audit").fetchone()[0], 2)
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM recovery_reconciliation_outbox "
                    "WHERE confirmed=1").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
