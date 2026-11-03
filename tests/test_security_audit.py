"""Security regressions for review authorization and journal confidentiality."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.store import EventStore
from hedgeops.workflow import create_case, record_review, replay

TOKEN = "phase13-synthetic-secret-long-enough"

def fake_agent(system, problem):
    return {"hypothesis": "Pilot first", "evidence": [],
            "assumptions": ["Capacity"], "risks": ["Delay"],
            "falsification_tests": ["Measure"], "confidence": "unknown"}

class SecurityAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "journal.sqlite3")
        self.store = EventStore(self.path)
        self.case = create_case(self.store, "Pilot?", fake_agent)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_unauthorized_review_does_not_append_event(self):
        before = replay(self.store, self.case)["event_count"]
        with patch.dict(os.environ, {"HEDGEOPS_OPERATOR_TOKEN": TOKEN}):
            with self.assertRaises(PermissionError):
                record_review(self.store, self.case, "approved_for_tracking",
                              "unknown", "No permission", operator_token="wrong")
        state = replay(self.store, self.case)
        self.assertEqual(state["event_count"], before)
        self.assertIsNone(state["review"])
        self.assertTrue(self.store.verify_chain())

    def test_secret_not_written_to_journal(self):
        with patch.dict(os.environ, {"HEDGEOPS_OPERATOR_TOKEN": TOKEN}):
            record_review(self.store, self.case, "needs_revision",
                          "operator", "More evidence", operator_token=TOKEN)
        self.assertTrue(self.store.verify_chain())
        # Inspect the committed event data, then inspect the finalized DB file.
        self.assertNotIn(TOKEN, repr(self.store.history()))
        self.store.close()
        self.assertNotIn(TOKEN.encode("utf-8"), Path(self.path).read_bytes())
        self.store = EventStore(self.path)

    def test_valid_review_survives_reopen(self):
        with patch.dict(os.environ, {"HEDGEOPS_OPERATOR_TOKEN": TOKEN}):
            record_review(self.store, self.case, "rejected",
                          "operator", "Unverified", operator_token=TOKEN)
        self.store.close()
        with EventStore(self.path) as reopened:
            self.assertEqual(replay(reopened, self.case)["review"]["decision"],
                             "rejected")
            self.assertTrue(reopened.verify_chain())
        self.store = EventStore(self.path)

if __name__ == "__main__":
    unittest.main()
