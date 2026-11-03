"""Phase 88 operational readiness validation across real local state."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_reconciliation_outbox import (
    execute_with_reconciliation_outbox, reconcile_pending_outbox,
    pending_reconciliations)
from hedgeops.recovery_execution_checkpoint import create_execution_checkpoint
from hedgeops.reconciliation_readiness import reconciliation_readiness

TOKEN = "phase88-operator-token-long-enough"
KEY = b"k" * 32


class Custody:
    def __init__(self):
        self.record = None
        self.writes = 0
        self.reads = 0

    def read(self):
        self.reads += 1
        return None if self.record is None else dict(self.record)

    def compare_and_swap(self, expected, new):
        self.writes += 1
        if self.record != expected:
            return False
        self.record = dict(new)
        return True


class OperationalReadinessTests(unittest.TestCase):
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

    def assess(self, checkpoint):
        return reconciliation_readiness(
            self.authority, checkpoint, KEY, self.custody)

    def test_readiness_lifecycle_and_read_only_observation(self):
        self.execute()
        checkpoint = create_execution_checkpoint(self.authority, KEY)
        self.assertEqual(self.assess(checkpoint)["status"], "pending")
        self.assertEqual(self.custody.reads, 0)
        self.assertEqual(self.custody.writes, 0)
        reconcile_pending_outbox(self.authority, KEY, self.custody)
        writes = self.custody.writes
        before = pending_reconciliations(self.authority)
        result = self.assess(checkpoint)
        self.assertTrue(result["ready"])
        self.assertEqual(result["status"], "ready")
        self.assertEqual(self.custody.writes, writes)
        self.assertEqual(pending_reconciliations(self.authority), before)
        self.execute()
        self.assertEqual(self.assess(checkpoint)["status"], "pending")
        self.assertEqual(self.custody.writes, writes)
        latest = reconcile_pending_outbox(self.authority, KEY, self.custody)
        self.assertTrue(self.assess(latest)["ready"])
        self.assertEqual(latest["sequence"], 2)

    def test_custody_tampering_denies_readiness_without_writes(self):
        self.execute()
        checkpoint = reconcile_pending_outbox(
            self.authority, KEY, self.custody)
        writes = self.custody.writes
        self.custody.record["checkpoint_sha256"] = "f" * 64
        result = self.assess(checkpoint)
        self.assertFalse(result["ready"])
        self.assertEqual(self.custody.writes, writes)
        self.assertEqual(pending_reconciliations(self.authority), [])


if __name__ == "__main__":
    unittest.main()
