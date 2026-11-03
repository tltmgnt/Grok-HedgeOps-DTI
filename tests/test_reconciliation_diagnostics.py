"""Phase 69 safe operator diagnostics regression tests."""
import unittest
from unittest.mock import patch

from hedgeops.reconciliation_diagnostics import readiness_diagnostics


class DiagnosticsTests(unittest.TestCase):
    def report(self, assessment):
        with patch("hedgeops.reconciliation_diagnostics.reconciliation_readiness",
                   return_value=assessment):
            return readiness_diagnostics(None, {"authentication_tag": "SECRET"},
                                         b"SECRET_KEY", object())

    def test_ready_report(self):
        report = self.report({
            "ready": True, "status": "ready", "custody_verified": True,
            "local": {"pending": 0, "confirmed": 2, "audit_head": 2}})
        self.assertEqual(report["reason_code"], "READY")
        self.assertTrue(report["ready"])
        self.assertEqual(report["confirmed"], 2)

    def test_all_denial_reasons_are_explicit(self):
        cases = {
            "pending": "PENDING_RECONCILIATION",
            "integrity_failure": "LOCAL_INTEGRITY_FAILURE",
            "unavailable": "LOCAL_STATUS_UNAVAILABLE",
            "checkpoint_mismatch": "CHECKPOINT_MISMATCH",
            "custody_unverified": "CUSTODY_UNVERIFIED",
            "local_changed": "LOCAL_STATE_CHANGED",
        }
        for status, expected in cases.items():
            with self.subTest(status=status):
                report = self.report({
                    "ready": False, "status": status,
                    "custody_verified": False, "local": {}})
                self.assertFalse(report["ready"])
                self.assertEqual(report["reason_code"], expected)

    def test_never_leaks_secret_or_unapproved_fields(self):
        report = self.report({
            "ready": False, "status": "custody_unverified",
            "custody_verified": False,
            "authentication_tag": "SECRET",
            "custody_url": "https://secret.invalid",
            "local": {"pending": 1, "confirmed": 0, "audit_head": 1,
                      "event_hash": "SECRET", "token": "SECRET"}})
        self.assertNotIn("SECRET", repr(report))
        self.assertNotIn("secret.invalid", repr(report))
        self.assertEqual(set(report), {
            "ready", "reason_code", "message", "pending", "confirmed",
            "audit_head", "custody_verified"})

    def test_unknown_status_fails_closed(self):
        report = self.report({
            "ready": True, "status": "unexpected", "custody_verified": True,
            "local": {"pending": -1, "confirmed": "invalid",
                      "audit_head": None}})
        self.assertFalse(report["ready"])
        self.assertEqual(report["reason_code"], "READINESS_UNAVAILABLE")
        self.assertIsNone(report["pending"])
        self.assertIsNone(report["confirmed"])

    def test_diagnostics_only_calls_readiness(self):
        with patch("hedgeops.reconciliation_diagnostics.reconciliation_readiness",
                   return_value={"ready": False, "status": "pending",
                                 "local": {"pending": 1},
                                 "custody_verified": False}) as checker:
            report = readiness_diagnostics("authority", "checkpoint",
                                           "key", "custodian")
        checker.assert_called_once_with(
            "authority", "checkpoint", "key", "custodian")
        self.assertEqual(report["pending"], 1)


if __name__ == "__main__":
    unittest.main()
