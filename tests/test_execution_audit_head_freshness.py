"""Phase 60: reject stale execution checkpoints at admission and commit."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.recovery_execution import RecoveryAdmissionError, execute_fenced_recovery
from hedgeops.recovery_execution_audit import (
    append_execution_event, ensure_execution_audit, execution_audit_head)
from hedgeops.recovery_execution_custody_gate import verify_recovery_execution_custody_gate
from hedgeops.recovery_fence import RecoveryFenceAuthority

TOKEN = "phase60-operator-token-long-enough"


class MemoryCustody:
    def __init__(self, record):
        self.record = record

    def read(self):
        return dict(self.record)


class HeadFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.authority = RecoveryFenceAuthority(
            Path(self.temp.name) / "fence.db", strict=True)
        self.generation = self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)
        ensure_execution_audit(self.authority)
        self.advance()
        self.head = execution_audit_head(self.authority)
        self.checkpoint = dict(self.head)
        self.custody = MemoryCustody(
            {"sequence": self.head["sequence"], "checkpoint_sha256": "a" * 64})

    def tearDown(self):
        self.temp.cleanup()

    def advance(self):
        with self.authority._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            append_execution_event(db, self.generation)
            db.commit()

    def gate(self):
        return verify_recovery_execution_custody_gate(
            self.authority, None, None, None, None, None, None, None,
            self.generation, self.checkpoint, b"k" * 32, self.custody)

    def test_gate_accepts_current_head_with_validated_custody(self):
        with patch("hedgeops.recovery_execution_custody_gate.verify_recovery_custody_gate",
                   return_value=True), patch(
                       "hedgeops.recovery_execution_custody_gate.verify_custodied_execution",
                       return_value=True):
            self.assertTrue(self.gate())

    def test_gate_rejects_superseded_local_head(self):
        self.advance()
        with patch("hedgeops.recovery_execution_custody_gate.verify_recovery_custody_gate",
                   return_value=True), patch(
                       "hedgeops.recovery_execution_custody_gate.verify_custodied_execution",
                       return_value=True):
            self.assertFalse(self.gate())

    def test_mutation_rejects_head_advanced_during_preflight(self):
        mutated = []

        def gate(*args):
            self.advance()
            return True

        with patch("hedgeops.recovery_execution.verify_recovery_execution_custody_gate",
                   side_effect=gate):
            with self.assertRaisesRegex(RecoveryAdmissionError, "audit head advanced"):
                execute_fenced_recovery(
                    self.authority, None, None, None, None, None, None, None,
                    self.generation, TOKEN, lambda db: mutated.append(True),
                    configured_token=TOKEN,
                    execution_checkpoint=self.checkpoint,
                    execution_key=b"k" * 32,
                    execution_custodian=self.custody)
        self.assertEqual(mutated, [])

    def test_mutation_rejects_mismatched_digest(self):
        wrong = dict(self.checkpoint, event_hash="0" * 64)
        with patch("hedgeops.recovery_execution.verify_recovery_execution_custody_gate",
                   return_value=True):
            with self.assertRaises(RecoveryAdmissionError):
                execute_fenced_recovery(
                    self.authority, None, None, None, None, None, None, None,
                    self.generation, TOKEN, lambda db: None,
                    configured_token=TOKEN,
                    execution_checkpoint=wrong,
                    execution_key=b"k" * 32,
                    execution_custodian=self.custody)


if __name__ == "__main__":
    unittest.main()
