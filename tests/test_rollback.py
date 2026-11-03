"""Rollback and fork detection with externally retained recovery floors."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.audit import export_checkpoint
from hedgeops.backup import backup_with_checkpoint, verify_restored_journal
from hedgeops.identity import ReviewerRegistry, record_attested_review
from hedgeops.rollback import create_recovery_floor, verify_recovery_floor, verify_recovery_position
from hedgeops.store import EventStore
from hedgeops.workflow import create_case, propose_prediction

TOKEN = "rollback-test-operator-secret-long"
KEYS = ReviewerRegistry({"alice": ("approver", b"a" * 32)})
FLOOR_KEY = b"f" * 32
CHECKPOINT_KEY = b"c" * 32

def fake_agent(system, problem):
    return {"hypothesis": "Pilot", "evidence": [],
            "assumptions": ["Capacity"], "risks": ["Delay"],
            "falsification_tests": ["Measure"], "confidence": "unknown"}

class RollbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.store = EventStore(root / "live.sqlite3")
        self.backup = root / "old.sqlite3"
        self.checkpoint = root / "old.json"
        self.case = create_case(self.store, "Pilot?", fake_agent)
        self.env = patch.dict(os.environ, {"HEDGEOPS_OPERATOR_TOKEN": TOKEN})
        self.env.start()
        sig = KEYS.sign(self.case, "approved_for_tracking", "alice", "Pilot")
        record_attested_review(self.store, self.case, "approved_for_tracking",
                               "alice", "Pilot", signature=sig,
                               registry=KEYS, operator_token=TOKEN)

    def tearDown(self):
        self.env.stop()
        self.store.close()
        self.temp.cleanup()

    def _floor(self):
        return create_recovery_floor(export_checkpoint(self.store, self.case, KEYS),
                                     FLOOR_KEY)

    def test_old_authenticated_pair_rejected_by_newer_floor(self):
        backup_with_checkpoint(self.store, self.case, KEYS, self.backup,
                               self.checkpoint, authentication_key=CHECKPOINT_KEY)
        propose_prediction(self.store, self.case, "latency", 100, 10, "ms",
                           review_registry=KEYS)
        floor = self._floor()
        self.assertTrue(verify_restored_journal(
            self.backup, self.checkpoint, KEYS, authentication_key=CHECKPOINT_KEY))
        self.assertFalse(verify_restored_journal(
            self.backup, self.checkpoint, KEYS, authentication_key=CHECKPOINT_KEY,
            trusted_floor=floor, floor_key=FLOOR_KEY))

    def test_matching_floor_accepted(self):
        floor = self._floor()
        backup_with_checkpoint(self.store, self.case, KEYS, self.backup,
                               self.checkpoint, authentication_key=CHECKPOINT_KEY)
        self.assertTrue(verify_restored_journal(
            self.backup, self.checkpoint, KEYS, authentication_key=CHECKPOINT_KEY,
            trusted_floor=floor, floor_key=FLOOR_KEY))

    def test_newer_journal_preserves_floor_ancestry(self):
        floor = self._floor()
        propose_prediction(self.store, self.case, "latency", 100, 10, "ms",
                           review_registry=KEYS)
        self.assertTrue(verify_recovery_position(
            self.store, export_checkpoint(self.store, self.case, KEYS),
            floor, FLOOR_KEY))

    def test_tampered_floor_rejected(self):
        floor = self._floor()
        floor["minimum_event_count"] += 1
        self.assertFalse(verify_recovery_floor(floor, FLOOR_KEY))

    def test_wrong_floor_key_rejected(self):
        self.assertFalse(verify_recovery_floor(self._floor(), b"z" * 32))

    def test_short_key_rejected(self):
        with self.assertRaises(ValueError):
            create_recovery_floor(export_checkpoint(self.store, self.case, KEYS),
                                  b"short")

if __name__ == "__main__":
    unittest.main()
