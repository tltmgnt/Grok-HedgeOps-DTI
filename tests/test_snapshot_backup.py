"""Snapshot-aligned checkpoint and backup recovery tests."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.backup import backup_with_checkpoint, verify_restored_journal
from hedgeops.checkpoint_io import load_checkpoint
from hedgeops.identity import ReviewerRegistry, record_attested_review
from hedgeops.store import EventStore
from hedgeops.workflow import create_case, propose_prediction

TOKEN = "snapshot-backup-operator-test-secret"
KEYS = ReviewerRegistry({"alice": ("approver", b"a" * 32)})

def fake_agent(system, problem):
    return {"hypothesis": "Pilot", "evidence": [],
            "assumptions": ["Capacity"], "risks": ["Delay"],
            "falsification_tests": ["Measure"], "confidence": "unknown"}

class SnapshotBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.store = EventStore(root / "live.sqlite3")
        self.backup = root / "backup.sqlite3"
        self.checkpoint = root / "checkpoint.json"
        self.case = create_case(self.store, "Pilot?", fake_agent)
        self.env = patch.dict(os.environ, {"HEDGEOPS_OPERATOR_TOKEN": TOKEN})
        self.env.start()
        signature = KEYS.sign(self.case, "approved_for_tracking", "alice", "Pilot")
        record_attested_review(self.store, self.case, "approved_for_tracking",
                               "alice", "Pilot", signature=signature,
                               registry=KEYS, operator_token=TOKEN)

    def tearDown(self):
        self.env.stop()
        self.store.close()
        self.temp.cleanup()

    def test_pair_is_verified(self):
        backup_with_checkpoint(self.store, self.case, KEYS,
                               self.backup, self.checkpoint)
        self.assertTrue(verify_restored_journal(self.backup, self.checkpoint, KEYS))
        self.assertTrue(load_checkpoint(self.checkpoint)["review_attestation_valid"])

    def test_live_append_after_backup_does_not_invalidate_pair(self):
        backup_with_checkpoint(self.store, self.case, KEYS,
                               self.backup, self.checkpoint)
        propose_prediction(self.store, self.case, "latency", 100, 10, "ms",
                           review_registry=KEYS)
        self.assertTrue(verify_restored_journal(self.backup, self.checkpoint, KEYS))

    def test_existing_checkpoint_rejected_before_backup_creation(self):
        self.checkpoint.write_text("existing", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            backup_with_checkpoint(self.store, self.case, KEYS,
                                   self.backup, self.checkpoint)
        self.assertFalse(self.backup.exists())

    def test_identical_destinations_rejected(self):
        with self.assertRaises(ValueError):
            backup_with_checkpoint(self.store, self.case, KEYS,
                                   self.backup, self.backup)

    def test_unknown_case_does_not_produce_verified_pair(self):
        with self.assertRaises(KeyError):
            backup_with_checkpoint(self.store, "missing-case", KEYS,
                                   self.backup, self.checkpoint)
        self.assertFalse(self.checkpoint.exists())

    def test_second_pair_cannot_overwrite(self):
        backup_with_checkpoint(self.store, self.case, KEYS,
                               self.backup, self.checkpoint)
        with self.assertRaises(FileExistsError):
            backup_with_checkpoint(self.store, self.case, KEYS,
                                   self.backup, self.checkpoint)
        self.assertTrue(verify_restored_journal(self.backup, self.checkpoint, KEYS))

if __name__ == "__main__":
    unittest.main()
