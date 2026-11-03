"""Checkpoint file preservation and recovery regressions."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.checkpoint_io import (
    save_checkpoint, load_checkpoint, verify_saved_checkpoint)
from hedgeops.identity import ReviewerRegistry, record_attested_review
from hedgeops.store import EventStore
from hedgeops.workflow import create_case, propose_prediction

TOKEN = "checkpoint-persistence-operator-secret"
KEYS = ReviewerRegistry({"alice": ("approver", b"a" * 32)})

def fake_agent(system, problem):
    return {"hypothesis": "Pilot", "evidence": [],
            "assumptions": ["Capacity"], "risks": ["Delay"],
            "falsification_tests": ["Measure"], "confidence": "unknown"}

class CheckpointIOTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "journal.sqlite3")
        self.checkpoint = Path(self.temp.name) / "checkpoint.json"
        self.store = EventStore(self.path)
        self.case = create_case(self.store, "Pilot?", fake_agent)
        self.env = patch.dict(os.environ, {"HEDGEOPS_OPERATOR_TOKEN": TOKEN})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.store.close()
        self.temp.cleanup()

    def _approve(self):
        sig = KEYS.sign(self.case, "approved_for_tracking", "alice", "Pilot")
        record_attested_review(self.store, self.case, "approved_for_tracking",
                               "alice", "Pilot", signature=sig,
                               registry=KEYS, operator_token=TOKEN)

    def test_save_load_and_verify_after_restart(self):
        self._approve()
        save_checkpoint(self.store, self.case, KEYS, self.checkpoint)
        self.assertTrue(verify_saved_checkpoint(self.store, self.checkpoint, KEYS))
        self.assertEqual(load_checkpoint(self.checkpoint)["case_id"], self.case)
        self.store.close()
        with EventStore(self.path) as reopened:
            self.assertTrue(verify_saved_checkpoint(reopened, self.checkpoint, KEYS))
        self.store = EventStore(self.path)

    def test_existing_checkpoint_cannot_be_overwritten(self):
        save_checkpoint(self.store, self.case, KEYS, self.checkpoint)
        original = self.checkpoint.read_bytes()
        with self.assertRaises(FileExistsError):
            save_checkpoint(self.store, self.case, KEYS, self.checkpoint)
        self.assertEqual(self.checkpoint.read_bytes(), original)

    def test_corrupted_checkpoint_rejected(self):
        self.checkpoint.write_bytes(b"not json")
        self.assertFalse(verify_saved_checkpoint(self.store, self.checkpoint, KEYS))

    def test_stale_checkpoint_rejected(self):
        self._approve()
        save_checkpoint(self.store, self.case, KEYS, self.checkpoint)
        propose_prediction(self.store, self.case, "latency", 100, 10, "ms",
                           review_registry=KEYS)
        self.assertFalse(verify_saved_checkpoint(self.store, self.checkpoint, KEYS))

    def test_missing_checkpoint_rejected(self):
        self.assertFalse(verify_saved_checkpoint(self.store, self.checkpoint, KEYS))

    def test_oversized_checkpoint_rejected(self):
        self.checkpoint.write_bytes(b"x" * 16385)
        with self.assertRaises(ValueError):
            load_checkpoint(self.checkpoint)
        self.assertFalse(verify_saved_checkpoint(self.store, self.checkpoint, KEYS))

    def test_file_is_owner_only(self):
        save_checkpoint(self.store, self.case, KEYS, self.checkpoint)
        self.assertEqual(self.checkpoint.stat().st_mode & 0o777, 0o600)

if __name__ == "__main__":
    unittest.main()
