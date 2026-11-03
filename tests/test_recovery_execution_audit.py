"""Phase 51 transactional recovery execution audit tests."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_execution import execute_fenced_recovery
from hedgeops.recovery_execution_audit import (
    ensure_execution_audit, execution_audit_head, verify_execution_audit)

TOKEN = "phase51-operator-token-long-enough"


class ExecutionAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "fence.sqlite3"
        self.authority = RecoveryFenceAuthority(self.path, strict=True)
        self.generation = self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE recovery_effect(value INTEGER)")
        ensure_execution_audit(self.authority)

    def tearDown(self):
        self.temp.cleanup()

    def run_mutation(self, mutation=None):
        if mutation is None:
            mutation = lambda db: db.execute(
                "INSERT INTO recovery_effect VALUES(1)").rowcount
        return execute_fenced_recovery(
            self.authority, {}, b"a" * 32, object(),
            object(), {}, b"b" * 32, object(),
            self.generation, TOKEN, mutation, configured_token=TOKEN)

    def count(self):
        with sqlite3.connect(self.path) as db:
            return db.execute("SELECT COUNT(*) FROM recovery_effect").fetchone()[0]

    @patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
           return_value=True)
    def test_success_commits_effect_and_audit(self, gate):
        self.assertEqual(self.run_mutation(), 1)
        self.assertEqual(self.count(), 1)
        self.assertEqual(execution_audit_head(self.authority)["sequence"], 1)
        self.assertTrue(verify_execution_audit(self.authority))

    @patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
           return_value=True)
    def test_second_commit_extends_chain(self, gate):
        self.run_mutation()
        first = execution_audit_head(self.authority)
        self.run_mutation()
        self.assertEqual(execution_audit_head(self.authority)["sequence"], 2)
        self.assertNotEqual(first["event_hash"],
                            execution_audit_head(self.authority)["event_hash"])

    @patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
           return_value=True)
    def test_callback_failure_rolls_back_both(self, gate):
        def fail(db):
            db.execute("INSERT INTO recovery_effect VALUES(1)")
            raise RuntimeError("interrupted")
        with self.assertRaises(RuntimeError):
            self.run_mutation(fail)
        self.assertEqual(self.count(), 0)
        self.assertEqual(execution_audit_head(self.authority)["sequence"], 0)

    @patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
           return_value=False)
    def test_gate_denial_no_audit(self, gate):
        with self.assertRaises(PermissionError):
            self.run_mutation()
        self.assertEqual(execution_audit_head(self.authority)["sequence"], 0)

    @patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
           return_value=True)
    def test_audit_failure_rolls_back_mutation(self, gate):
        self.run_mutation()
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE recovery_execution_audit SET event_hash=?",
                       ("f" * 64,))
        with self.assertRaises(ValueError):
            self.run_mutation()
        self.assertEqual(self.count(), 1)
        self.assertEqual(execution_audit_head(self.authority)["sequence"], 1)

    @patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
           return_value=True)
    def test_tampered_audit_detected(self, gate):
        self.run_mutation()
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE recovery_execution_audit SET generation=999")
        self.assertFalse(verify_execution_audit(self.authority))

    @patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
           return_value=True)
    def test_truncated_suffix_not_detectable_without_anchor(self, gate):
        self.run_mutation()
        self.run_mutation()
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM recovery_execution_audit WHERE sequence=2")
        self.assertTrue(verify_execution_audit(self.authority))
        self.assertEqual(execution_audit_head(self.authority)["sequence"], 1)

    def test_empty_audit_valid(self):
        self.assertTrue(verify_execution_audit(self.authority))
        self.assertEqual(execution_audit_head(self.authority)["sequence"], 0)

    def test_missing_table_fails_closed(self):
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TABLE recovery_execution_audit")
        self.assertFalse(verify_execution_audit(self.authority))

    @patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
           return_value=True)
    def test_generation_recorded(self, gate):
        self.run_mutation()
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                "SELECT generation FROM recovery_execution_audit").fetchone()
        self.assertEqual(row, (self.generation,))


if __name__ == "__main__":
    unittest.main()
