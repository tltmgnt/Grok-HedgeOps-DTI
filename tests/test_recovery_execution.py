"""Phase 50 controlled recovery execution tests."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.recovery_fence import RecoveryFenceAuthority, StaleRecoveryFence
from hedgeops.recovery_execution import (
    RecoveryAdmissionError, execute_fenced_recovery)

TOKEN = "phase50-operator-token-sufficient-length"


class ControlledRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "fence.sqlite3"
        self.authority = RecoveryFenceAuthority(self.path, strict=True)
        self.generation = self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE recovery_effect (value INTEGER NOT NULL)")

    def tearDown(self):
        self.temp.cleanup()

    def run_recovery(self, mutation=None, token=TOKEN, generation=None):
        if mutation is None:
            mutation = lambda db: db.execute(
                "INSERT INTO recovery_effect VALUES(1)").rowcount
        return execute_fenced_recovery(
            self.authority, {}, b"a" * 32, object(),
            object(), {}, b"b" * 32, object(),
            self.generation if generation is None else generation,
            token, mutation, configured_token=TOKEN)

    def count(self):
        with sqlite3.connect(self.path) as db:
            return db.execute("SELECT COUNT(*) FROM recovery_effect").fetchone()[0]

    @patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
           return_value=True)
    def test_authorized_transaction_commits(self, gate):
        self.assertEqual(self.run_recovery(), 1)
        self.assertEqual(self.count(), 1)
        gate.assert_called_once()

    @patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
           return_value=False)
    def test_gate_rejection_no_write(self, gate):
        with self.assertRaises(RecoveryAdmissionError):
            self.run_recovery()
        self.assertEqual(self.count(), 0)

    @patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
           return_value=True)
    def test_invalid_token_denied_before_gate(self, gate):
        with self.assertRaises(PermissionError):
            self.run_recovery(token="wrong")
        gate.assert_not_called()
        self.assertEqual(self.count(), 0)

    @patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
           return_value=True)
    def test_stale_generation_rejected_at_commit(self, gate):
        self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)
        with self.assertRaises(StaleRecoveryFence):
            self.run_recovery()
        self.assertEqual(self.count(), 0)

    @patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
           return_value=True)
    def test_race_after_gate_rejected(self, gate):
        def advance(*args):
            self.authority.acquire_authorized(
                "operator", TOKEN, configured_token=TOKEN)
            return True
        gate.side_effect = advance
        with self.assertRaises(StaleRecoveryFence):
            self.run_recovery()
        self.assertEqual(self.count(), 0)

    @patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
           return_value=True)
    def test_callback_failure_rolls_back(self, gate):
        def fail(db):
            db.execute("INSERT INTO recovery_effect VALUES(1)")
            raise RuntimeError("interrupted")
        with self.assertRaises(RuntimeError):
            self.run_recovery(mutation=fail)
        self.assertEqual(self.count(), 0)

    @patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
           return_value=True)
    def test_invalid_generation_denied(self, gate):
        with self.assertRaises(RecoveryAdmissionError):
            self.run_recovery(generation=0)
        self.assertEqual(self.count(), 0)

    @patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
           return_value=True)
    def test_mutation_must_be_callable(self, gate):
        with self.assertRaises(TypeError):
            self.run_recovery(mutation="not callable")

    @patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
           return_value=True)
    def test_legacy_authority_denied(self, gate):
        other = RecoveryFenceAuthority(
            Path(self.temp.name) / "legacy.sqlite3")
        with self.assertRaises(RecoveryAdmissionError):
            execute_fenced_recovery(
                other, {}, b"a" * 32, object(), object(), {},
                b"b" * 32, object(), 1, TOKEN,
                lambda db: None, configured_token=TOKEN)
        gate.assert_not_called()

    @patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
           return_value=True)
    def test_policy_removed_after_gate_denied(self, gate):
        def remove(*args):
            with sqlite3.connect(self.path) as db:
                db.execute("DELETE FROM recovery_fence_policy")
            return True
        gate.side_effect = remove
        with self.assertRaises(RecoveryAdmissionError):
            self.run_recovery()
        self.assertEqual(self.count(), 0)


if __name__ == "__main__":
    unittest.main()
