"""Phase 68 local and independent custody readiness tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_reconciliation_outbox import (
    execute_with_reconciliation_outbox, reconcile_pending_outbox)
from hedgeops.reconciliation_readiness import reconciliation_readiness

TOKEN = "phase68-operator-token-long-enough"
KEY = b"k" * 32


class Custody:
    def __init__(self):
        self.record = None

    def read(self):
        return None if self.record is None else dict(self.record)

    def compare_and_swap(self, expected, new):
        if expected != self.record:
            return False
        self.record = dict(new)
        return True


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.authority = RecoveryFenceAuthority(
            Path(self.temp.name) / "fence.db", strict=True)
        self.generation = self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)
        self.custody = Custody()

    def tearDown(self):
        self.temp.cleanup()

    def execute(self):
        with patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
                   return_value=True):
            execute_with_reconciliation_outbox(
                self.authority, None, None, None, None, None, None, None,
                self.generation, TOKEN, lambda db: None,
                configured_token=TOKEN)

    def readiness(self, checkpoint):
        return reconciliation_readiness(
            self.authority, checkpoint, KEY, self.custody)

    def test_healthy_and_custodied_is_ready(self):
        self.execute()
        checkpoint = reconcile_pending_outbox(self.authority, KEY, self.custody)
        result = self.readiness(checkpoint)
        self.assertTrue(result["ready"])
        self.assertEqual(result["status"], "ready")

    def test_pending_is_not_ready(self):
        self.execute()
        self.assertEqual(self.readiness({})["status"], "pending")

    def test_checkpoint_mismatch_is_not_ready(self):
        self.execute()
        checkpoint = reconcile_pending_outbox(self.authority, KEY, self.custody)
        self.assertEqual(self.readiness(dict(checkpoint, sequence=99))["status"],
                         "checkpoint_mismatch")

    def test_missing_custody_is_not_ready(self):
        self.execute()
        checkpoint = reconcile_pending_outbox(self.authority, KEY, self.custody)
        self.custody.record = None
        self.assertEqual(self.readiness(checkpoint)["status"],
                         "custody_unverified")

    def test_local_advance_during_verification_is_not_ready(self):
        self.execute()
        checkpoint = reconcile_pending_outbox(self.authority, KEY, self.custody)

        def verify(*args):
            self.execute()
            return True

        with patch("hedgeops.reconciliation_readiness.verify_custodied_execution",
                   side_effect=verify):
            self.assertEqual(self.readiness(checkpoint)["status"],
                             "local_changed")


if __name__ == "__main__":
    unittest.main()
