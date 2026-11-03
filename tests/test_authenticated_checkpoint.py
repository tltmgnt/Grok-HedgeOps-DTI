"""Authenticated checkpoint and backup recovery tests."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.backup import backup_with_checkpoint, verify_restored_journal
from hedgeops.checkpoint_io import save_checkpoint, load_checkpoint, verify_saved_checkpoint
from hedgeops.identity import ReviewerRegistry, record_attested_review
from hedgeops.store import EventStore
from hedgeops.workflow import create_case

TOKEN = "checkpoint-auth-test-operator-token"
KEYS = ReviewerRegistry({"alice": ("approver", b"a" * 32)})
AUTH_KEY = b"c" * 32

def fake_agent(system, problem):
    return {"hypothesis": "Pilot", "evidence": [],
            "assumptions": ["Capacity"], "risks": ["Delay"],
            "falsification_tests": ["Measure"], "confidence": "unknown"}

class AuthenticatedCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.store = EventStore(root / "journal.sqlite3")
        self.checkpoint = root / "checkpoint.json"
        self.backup = root / "backup.sqlite3"
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

    def test_authenticated_checkpoint_verifies(self):
        save_checkpoint(self.store, self.case, KEYS, self.checkpoint,
                        authentication_key=AUTH_KEY)
        self.assertTrue(verify_saved_checkpoint(
            self.store, self.checkpoint, KEYS, authentication_key=AUTH_KEY))

    def test_wrong_or_missing_key_rejected(self):
        save_checkpoint(self.store, self.case, KEYS, self.checkpoint,
                        authentication_key=AUTH_KEY)
        self.assertFalse(verify_saved_checkpoint(self.store, self.checkpoint, KEYS))
        self.assertFalse(verify_saved_checkpoint(
            self.store, self.checkpoint, KEYS, authentication_key=b"z" * 32))

    def test_tampering_rejected(self):
        save_checkpoint(self.store, self.case, KEYS, self.checkpoint,
                        authentication_key=AUTH_KEY)
        value = load_checkpoint(self.checkpoint)
        value["checkpoint"]["global_event_count"] += 1
        import json
        self.checkpoint.write_text(json.dumps(value), encoding="utf-8")
        self.assertFalse(verify_saved_checkpoint(
            self.store, self.checkpoint, KEYS, authentication_key=AUTH_KEY))

    def test_short_key_rejected(self):
        with self.assertRaises(ValueError):
            save_checkpoint(self.store, self.case, KEYS, self.checkpoint,
                            authentication_key=b"short")
        self.assertFalse(self.checkpoint.exists())

    def test_authenticated_backup_pair_verifies(self):
        backup_with_checkpoint(self.store, self.case, KEYS,
                               self.backup, self.checkpoint,
                               authentication_key=AUTH_KEY)
        self.assertTrue(verify_restored_journal(
            self.backup, self.checkpoint, KEYS, authentication_key=AUTH_KEY))
        self.assertFalse(verify_restored_journal(self.backup, self.checkpoint, KEYS))

if __name__ == "__main__":
    unittest.main()
