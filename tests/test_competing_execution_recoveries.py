"""Phase 61: competing recoveries against the same authenticated audit head."""
import concurrent.futures
import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.execution_admission_policy import require_execution_custody
from hedgeops.recovery_execution import RecoveryAdmissionError, execute_fenced_recovery
from hedgeops.recovery_execution_audit import (
    append_execution_event, ensure_execution_audit, execution_audit_head)
from hedgeops.recovery_fence import RecoveryFenceAuthority

TOKEN = "phase61-operator-token-long-enough"


class CompetingRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.authority = RecoveryFenceAuthority(
            Path(self.tmp.name) / "fence.db", strict=True)
        self.generation = self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)
        ensure_execution_audit(self.authority)
        with self.authority._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            append_execution_event(db, self.generation)
            db.execute("CREATE TABLE mutation_marker (id INTEGER PRIMARY KEY)")
            db.commit()
        self.checkpoint = execution_audit_head(self.authority)
        require_execution_custody(self.authority)

    def tearDown(self):
        self.tmp.cleanup()

    def execute(self, mutation):
        return execute_fenced_recovery(
            self.authority, None, None, None, None, None, None, None,
            self.generation, TOKEN, mutation, configured_token=TOKEN,
            execution_checkpoint=self.checkpoint,
            execution_key=b"k" * 32,
            execution_custodian=object())

    def test_two_admitted_writers_one_commit(self):
        barrier = threading.Barrier(2)

        def admitted(*args):
            barrier.wait(timeout=10)
            return True

        def mutation(db):
            db.execute("INSERT INTO mutation_marker(id) VALUES(1)")
            return "committed"

        with patch("hedgeops.recovery_execution.verify_recovery_execution_custody_gate",
                   side_effect=admitted):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(self.execute, mutation) for _ in range(2)]
                results = []
                for future in futures:
                    try:
                        results.append(future.result(timeout=15))
                    except RecoveryAdmissionError:
                        results.append("stale")

        self.assertCountEqual(results, ["committed", "stale"])
        with self.authority._connect() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM mutation_marker").fetchone()[0], 1)
        self.assertEqual(execution_audit_head(self.authority)["sequence"], 2)

    def test_replay_after_success_rejected(self):
        with patch("hedgeops.recovery_execution.verify_recovery_execution_custody_gate",
                   return_value=True):
            self.assertEqual(self.execute(lambda db: "first"), "first")
            with self.assertRaisesRegex(RecoveryAdmissionError, "audit head advanced"):
                self.execute(lambda db: "replayed")
        self.assertEqual(execution_audit_head(self.authority)["sequence"], 2)


if __name__ == "__main__":
    unittest.main()
