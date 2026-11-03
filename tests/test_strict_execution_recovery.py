"""Strict execution recovery entry point admission tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.execution_admission_policy import require_execution_custody
from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_execution import RecoveryAdmissionError
from hedgeops.strict_execution_recovery import execute_strict_recovery

TOKEN = "strict-execution-operator-token-long"


class StrictExecutionRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.authority = RecoveryFenceAuthority(
            Path(self.tmp.name) / "fence.db", strict=True)

    def tearDown(self):
        self.tmp.cleanup()

    def invoke(self, checkpoint=object(), key=b"k" * 32, custodian=object()):
        return execute_strict_recovery(
            self.authority, None, None, None,
            None, None, None, None,
            1, TOKEN, lambda db: None,
            execution_checkpoint=checkpoint,
            execution_key=key,
            execution_custodian=custodian,
            configured_token=TOKEN)

    def test_policy_required(self):
        with self.assertRaises(RecoveryAdmissionError):
            self.invoke()

    def test_missing_checkpoint_denied(self):
        require_execution_custody(self.authority)
        with self.assertRaises(RecoveryAdmissionError):
            self.invoke(checkpoint=None)

    def test_missing_key_denied(self):
        require_execution_custody(self.authority)
        with self.assertRaises(RecoveryAdmissionError):
            self.invoke(key=None)

    def test_missing_custodian_denied(self):
        require_execution_custody(self.authority)
        with self.assertRaises(RecoveryAdmissionError):
            self.invoke(custodian=None)

    def test_complete_evidence_reaches_executor(self):
        require_execution_custody(self.authority)
        with patch("hedgeops.strict_execution_recovery.execute_fenced_recovery",
                   return_value="delegated") as delegate:
            self.assertEqual(self.invoke(), "delegated")
            self.assertEqual(delegate.call_count, 1)


if __name__ == "__main__":
    unittest.main()
