"""Offline SQLite backup and checkpoint restore regression tests."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.backup import backup_journal, verify_restored_journal
from hedgeops.checkpoint_io import save_checkpoint
from hedgeops.identity import ReviewerRegistry, record_attested_review
from hedgeops.store import EventStore
from hedgeops.workflow import create_case, propose_prediction

TOKEN = "backup-recovery-test-operator-token"
KEYS = ReviewerRegistry({"alice": ("approver", b"a" * 32)})

def fake_agent(system, problem):
    return {"hypothesis": "Pilot", "evidence": [],
            "assumptions": ["Capacity"], "risks": ["Delay"],
            "falsification_tests": ["Measure"], "confidence": "unknown"}

class BackupTests(unittest.TestCase):
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

    def test_backup_matches_trusted_checkpoint(self):
        save_checkpoint(self.store, self.case, KEYS, self.checkpoint)
        backup_journal(self.store, self.backup)
        self.assertTrue(verify_restored_journal(self.backup, self.checkpoint, KEYS))
        self.assertEqual(self.backup.stat().st_mode & 0o777, 0o600)

    def test_live_changes_do_not_change_snapshot(self):
        save_checkpoint(self.store, self.case, KEYS, self.checkpoint)
        backup_journal(self.store, self.backup)
        propose_prediction(self.store, self.case, "latency", 100, 10, "ms",
                           review_registry=KEYS)
        self.assertTrue(verify_restored_journal(self.backup, self.checkpoint, KEYS))

    def test_stale_checkpoint_rejected(self):
        save_checkpoint(self.store, self.case, KEYS, self.checkpoint)
        propose_prediction(self.store, self.case, "latency", 100, 10, "ms",
                           review_registry=KEYS)
        backup_journal(self.store, self.backup)
        self.assertFalse(verify_restored_journal(self.backup, self.checkpoint, KEYS))

    def test_existing_backup_cannot_be_overwritten(self):
        backup_journal(self.store, self.backup)
        original = self.backup.read_bytes()
        with self.assertRaises(FileExistsError):
            backup_journal(self.store, self.backup)
        self.assertEqual(self.backup.read_bytes(), original)

    def test_corrupted_backup_rejected(self):
        self.backup.write_bytes(b"not a sqlite database")
        self.assertFalse(verify_restored_journal(self.backup, self.checkpoint, KEYS))

    def test_missing_backup_rejected(self):
        self.assertFalse(verify_restored_journal(self.backup, self.checkpoint, KEYS))

if __name__ == "__main__":
    unittest.main()
