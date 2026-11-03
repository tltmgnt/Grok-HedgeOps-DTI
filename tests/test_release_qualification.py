"""Phase 89 release qualification: operator diagnostics and exit contract."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_reconciliation_outbox import (
    execute_with_reconciliation_outbox, reconcile_pending_outbox)
from hedgeops.recovery_execution_checkpoint import create_execution_checkpoint
from hedgeops.reconciliation_diagnostics import readiness_diagnostics
from hedgeops.reconciliation_cli import (
    EXIT_READY, EXIT_DENIED, EXIT_ERROR, readiness_exit_code)

TOKEN = "phase89-operator-token-long-enough"
KEY = b"k" * 32


class Custody:
    def __init__(self):
        self.record = None
        self.writes = 0

    def read(self):
        return None if self.record is None else dict(self.record)

    def compare_and_swap(self, expected, new):
        self.writes += 1
        if self.record != expected:
            return False
        self.record = dict(new)
        return True


class ReleaseQualificationTests(unittest.TestCase):
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

    def report(self, checkpoint):
        return readiness_diagnostics(
            self.authority, checkpoint, KEY, self.custody)

    def test_pending_to_ready_operator_exit_contract(self):
        self.execute()
        checkpoint = create_execution_checkpoint(self.authority, KEY)
        pending = self.report(checkpoint)
        self.assertEqual(pending["reason_code"], "PENDING_RECONCILIATION")
        self.assertEqual(readiness_exit_code(pending), EXIT_DENIED)
        self.assertEqual(self.custody.writes, 0)
        reconcile_pending_outbox(self.authority, KEY, self.custody)
        writes = self.custody.writes
        ready = self.report(checkpoint)
        self.assertEqual(ready["reason_code"], "READY")
        self.assertTrue(ready["custody_verified"])
        self.assertEqual(readiness_exit_code(ready), EXIT_READY)
        self.assertEqual(self.custody.writes, writes)
        self.assertEqual(set(ready), {
            "ready", "reason_code", "message", "pending",
            "confirmed", "audit_head", "custody_verified"})

    def test_custody_mismatch_is_release_blocker(self):
        self.execute()
        checkpoint = reconcile_pending_outbox(
            self.authority, KEY, self.custody)
        self.custody.record["checkpoint_sha256"] = "f" * 64
        report = self.report(checkpoint)
        self.assertFalse(report["ready"])
        self.assertEqual(report["reason_code"], "CUSTODY_UNVERIFIED")
        self.assertEqual(readiness_exit_code(report), EXIT_DENIED)

    def test_new_unconfirmed_execution_blocks_release(self):
        self.execute()
        old = reconcile_pending_outbox(self.authority, KEY, self.custody)
        self.execute()
        report = self.report(old)
        self.assertEqual(report["reason_code"], "PENDING_RECONCILIATION")
        self.assertEqual(readiness_exit_code(report), EXIT_DENIED)

    def test_malformed_monitoring_report_never_returns_ready(self):
        for report in (
                None, {}, {"ready": True, "reason_code": "READY"},
                {"ready": False, "reason_code": "READY"},
                {"ready": True, "reason_code": "PENDING_RECONCILIATION"},
                {"ready": "true", "reason_code": "READY",
                 "custody_verified": True}):
            with self.subTest(report=report):
                self.assertEqual(readiness_exit_code(report), EXIT_ERROR)


if __name__ == "__main__":
    unittest.main()
