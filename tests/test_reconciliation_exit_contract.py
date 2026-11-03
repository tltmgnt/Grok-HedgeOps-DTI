"""Stable monitoring exit code contract tests."""
import unittest
from hedgeops.reconciliation_cli import readiness_exit_code


class ExitCodeTests(unittest.TestCase):
    def test_ready(self):
        self.assertEqual(readiness_exit_code(
            {"ready": True, "reason_code": "READY", "custody_verified": True}), 0)

    def test_denials(self):
        for reason in ("PENDING_RECONCILIATION", "LOCAL_INTEGRITY_FAILURE",
                       "CHECKPOINT_MISMATCH", "CUSTODY_UNVERIFIED",
                       "LOCAL_STATE_CHANGED"):
            with self.subTest(reason=reason):
                self.assertEqual(readiness_exit_code(
                    {"ready": False, "reason_code": reason}), 2)

    def test_errors(self):
        for reason in ("LOCAL_STATUS_UNAVAILABLE", "READINESS_UNAVAILABLE"):
            with self.subTest(reason=reason):
                self.assertEqual(readiness_exit_code(
                    {"ready": False, "reason_code": reason}), 3)

    def test_invalid_reports(self):
        for report in (None, {}, {"ready": True, "reason_code": "READY"},
                       {"ready": False, "reason_code": "READY"},
                       {"ready": True, "reason_code": "CUSTODY_UNVERIFIED"},
                       {"ready": 1, "reason_code": "READY"}):
            with self.subTest(report=report):
                self.assertEqual(readiness_exit_code(report), 3)


if __name__ == "__main__":
    unittest.main()
