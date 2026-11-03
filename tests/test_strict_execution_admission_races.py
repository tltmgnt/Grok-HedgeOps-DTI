"""Phase 59: strict recovery admission race and supersession regression tests."""
import concurrent.futures
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.execution_admission_policy import require_execution_custody
from hedgeops.recovery_execution import RecoveryAdmissionError, execute_fenced_recovery
from hedgeops.recovery_execution_custody_gate import verify_recovery_execution_custody_gate
from hedgeops.recovery_fence import RecoveryFenceAuthority

TOKEN = "phase59-operator-token-long-enough"


class MutableCustodian:
    def __init__(self, record):
        self.record = record
        self.read_count = 0
        self.supersede_at = None

    def read(self):
        self.read_count += 1
        if self.read_count == self.supersede_at:
            self.record = dict(self.record, sequence=self.record["sequence"] + 1)
        return None if self.record is None else dict(self.record)


class AdmissionRaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.authority = RecoveryFenceAuthority(
            Path(self.tmp.name) / "fence.db", strict=True)
        self.generation = self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)

    def tearDown(self):
        self.tmp.cleanup()

    def execute(self, mutation, **kwargs):
        return execute_fenced_recovery(
            self.authority, None, None, None, None, None, None, None,
            self.generation, TOKEN, mutation, configured_token=TOKEN, **kwargs)

    def test_concurrent_policy_activation_blocks_fallback(self):
        entered = threading.Event()
        resume = threading.Event()
        mutations = []

        def preflight(*args):
            entered.set()
            self.assertTrue(resume.wait(timeout=5))
            return True

        with patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
                   side_effect=preflight):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                pending = pool.submit(self.execute, lambda db: mutations.append(True))
                self.assertTrue(entered.wait(timeout=5))
                require_execution_custody(self.authority)
                resume.set()
                with self.assertRaises(RecoveryAdmissionError):
                    pending.result(timeout=10)
        self.assertEqual(mutations, [])

    def test_simultaneous_fallback_attempts_denied(self):
        require_execution_custody(self.authority)
        mutations = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(self.execute,
                                   lambda db: mutations.append(True))
                       for _ in range(10)]
            for future in futures:
                with self.assertRaises(RecoveryAdmissionError):
                    future.result(timeout=10)
        self.assertEqual(mutations, [])

    def test_execution_custody_superseded_during_gate(self):
        custody = MutableCustodian(
            {"sequence": 1, "checkpoint_sha256": "a" * 64})
        custody.supersede_at = 3
        with patch("hedgeops.recovery_execution_custody_gate.verify_recovery_custody_gate",
                   return_value=True), patch(
                       "hedgeops.recovery_execution_custody_gate.verify_custodied_execution",
                       return_value=True):
            self.assertFalse(verify_recovery_execution_custody_gate(
                self.authority, None, None, None, None, None, None, None,
                self.generation, None, None, custody))

    def test_execution_custody_missing_denied(self):
        with patch("hedgeops.recovery_execution_custody_gate.verify_recovery_custody_gate",
                   return_value=True):
            self.assertFalse(verify_recovery_execution_custody_gate(
                self.authority, None, None, None, None, None, None, None,
                self.generation, None, None, MutableCustodian(None)))

    def test_complete_evidence_does_not_use_legacy_gate(self):
        require_execution_custody(self.authority)
        with patch("hedgeops.recovery_execution.verify_recovery_execution_custody_gate",
                   return_value=False) as triple, patch(
                       "hedgeops.recovery_execution.verify_recovery_custody_gate",
                       side_effect=AssertionError("legacy bypass")):
            with self.assertRaises(RecoveryAdmissionError):
                self.execute(lambda db: None,
                             execution_checkpoint={"sequence": 1},
                             execution_key=b"k" * 32,
                             execution_custodian=object())
            self.assertEqual(triple.call_count, 1)


if __name__ == "__main__":
    unittest.main()
