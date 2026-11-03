import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from hedgeops.store import EventStore
from hedgeops.workflow import create_case, record_review, replay

TOKEN = "phase12-test-token-with-sufficient-length"

def fake_ask(system, problem):
    return {"hypothesis": "Pilot", "evidence": [], "assumptions": ["Stable"],
            "risks": ["Bias"], "falsification_tests": ["Measure"],
            "confidence": "unknown"}

class SecurityBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = EventStore(str(Path(self.temp.name) / "case.sqlite3"))
        self.case = create_case(self.store, "Pilot?", fake_ask)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_direct_review_rejects_missing_token(self):
        with patch.dict(os.environ, {"HEDGEOPS_OPERATOR_TOKEN": TOKEN}):
            with self.assertRaises(PermissionError):
                record_review(self.store, self.case, "approved_for_tracking",
                              "analyst", "Reason")
            self.assertIsNone(replay(self.store, self.case)["review"])

    def test_direct_review_rejects_wrong_token(self):
        with patch.dict(os.environ, {"HEDGEOPS_OPERATOR_TOKEN": TOKEN}):
            with self.assertRaises(PermissionError):
                record_review(self.store, self.case, "approved_for_tracking",
                              "analyst", "Reason", operator_token="incorrect")

    def test_direct_review_accepts_valid_token(self):
        with patch.dict(os.environ, {"HEDGEOPS_OPERATOR_TOKEN": TOKEN}):
            result = record_review(self.store, self.case, "needs_revision",
                                   "analyst", "Need evidence", operator_token=TOKEN)
            self.assertEqual(result["review"]["decision"], "needs_revision")
            self.assertTrue(self.store.verify_chain())

    def test_missing_configuration_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                record_review(self.store, self.case, "rejected",
                              "analyst", "Reason", operator_token=TOKEN)

if __name__ == "__main__":
    unittest.main()
