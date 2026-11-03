"""Phase 58: legacy executor cannot bypass persistent execution custody policy."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.execution_admission_policy import require_execution_custody
from hedgeops.recovery_execution import RecoveryAdmissionError, execute_fenced_recovery
from hedgeops.recovery_fence import RecoveryFenceAuthority

TOKEN = "phase58-operator-token-long-enough"


class StrictAdmissionEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.authority = RecoveryFenceAuthority(
            Path(self.temp.name) / "fence.db", strict=True)
        self.generation = self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, **kwargs):
        return execute_fenced_recovery(
            self.authority, None, None, None, None, None, None, None,
            self.generation, TOKEN, lambda db: None,
            configured_token=TOKEN, **kwargs)

    def test_legacy_fallback_denied(self):
        require_execution_custody(self.authority)
        with self.assertRaisesRegex(RecoveryAdmissionError, "Execution custody required"):
            self.invoke()

    def test_persists_after_reopen(self):
        require_execution_custody(self.authority)
        self.authority = RecoveryFenceAuthority(self.authority.path)
        with self.assertRaises(RecoveryAdmissionError):
            self.invoke()

    def test_partial_evidence_denied(self):
        require_execution_custody(self.authority)
        with self.assertRaises(RecoveryAdmissionError):
            self.invoke(execution_checkpoint={"sequence": 1})

    def test_complete_evidence_uses_three_namespace_gate(self):
        require_execution_custody(self.authority)
        with patch("hedgeops.recovery_execution.verify_recovery_execution_custody_gate",
                   return_value=False) as gate:
            with self.assertRaisesRegex(RecoveryAdmissionError, "gate rejected"):
                self.invoke(execution_checkpoint={"sequence": 1},
                            execution_key=b"k" * 32, execution_custodian=object())
            self.assertEqual(gate.call_count, 1)

    def test_policy_enabled_during_preflight_blocks_mutation(self):
        def preflight(*args):
            require_execution_custody(self.authority)
            return True

        with patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
                   side_effect=preflight):
            with self.assertRaisesRegex(RecoveryAdmissionError, "Execution custody required"):
                self.invoke()

    def test_policy_off_keeps_legacy_admission_path(self):
        with patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
                   return_value=False) as gate:
            with self.assertRaisesRegex(RecoveryAdmissionError, "gate rejected"):
                self.invoke()
            self.assertEqual(gate.call_count, 1)


if __name__ == "__main__":
    unittest.main()
