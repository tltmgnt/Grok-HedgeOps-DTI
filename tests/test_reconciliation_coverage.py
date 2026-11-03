"""Phase 76 readiness requires complete confirmed execution coverage."""
import unittest
from unittest.mock import patch

from hedgeops.reconciliation_readiness import reconciliation_readiness
from hedgeops.reconciliation_diagnostics import readiness_diagnostics
from hedgeops.reconciliation_cli import readiness_exit_code


class NoRemoteRead:
    def read(self):
        raise AssertionError("Remote custody must not be contacted")


class CoverageTests(unittest.TestCase):
    def assess(self, local):
        with patch("hedgeops.reconciliation_readiness.reconciliation_health",
                   return_value=local), patch(
                   "hedgeops.reconciliation_readiness.execution_audit_head",
                   side_effect=AssertionError("Head read not expected")):
            return reconciliation_readiness(object(), {}, b"k" * 32, NoRemoteRead())

    def test_empty_execution_history_denied(self):
        result = self.assess({
            "status": "healthy", "audit_head": 0, "confirmed": 0, "pending": 0})
        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "no_executions")

    def test_missing_outbox_rows_denied(self):
        result = self.assess({
            "status": "healthy", "audit_head": 3, "confirmed": 2, "pending": 0})
        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "untracked_audit")

    def test_all_audit_rows_untracked_denied(self):
        result = self.assess({
            "status": "healthy", "audit_head": 2, "confirmed": 0, "pending": 0})
        self.assertEqual(result["status"], "untracked_audit")

    def test_monitoring_exit_contract(self):
        for reason in ("NO_EXECUTIONS", "UNTRACKED_AUDIT"):
            self.assertEqual(readiness_exit_code({
                "ready": False, "reason_code": reason}), 2)

    def test_safe_diagnostic_reason(self):
        with patch("hedgeops.reconciliation_diagnostics.reconciliation_readiness",
                   return_value={
                       "ready": False, "status": "untracked_audit",
                       "local": {"audit_head": 4, "confirmed": 1, "pending": 0},
                       "custody_verified": False}):
            report = readiness_diagnostics(object(), {}, b"k" * 32, NoRemoteRead())
        self.assertEqual(report["reason_code"], "UNTRACKED_AUDIT")
        self.assertFalse(report["ready"])
        self.assertEqual(report["audit_head"], 4)


if __name__ == "__main__":
    unittest.main()
