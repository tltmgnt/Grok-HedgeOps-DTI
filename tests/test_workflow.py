import tempfile
import os
from unittest.mock import patch
import unittest
from pathlib import Path
from hedgeops.store import EventStore
from hedgeops.workflow import (
    create_case, record_review, propose_prediction, record_measurement, replay)

def fake_ask(system, problem):
    return {"hypothesis": "Test deployment", "evidence": ["Unsourced claim"],
            "assumptions": ["Traffic stable"], "risks": ["Delay"],
            "falsification_tests": ["Measure latency"], "confidence": "medium"}

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.token_patch = patch.dict(os.environ, {"HEDGEOPS_OPERATOR_TOKEN": "test-token-with-at-least-24-characters"})
        self.token_patch.start()
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "cases.sqlite3")
        self.store = EventStore(self.path)
        self.case = create_case(self.store, "Test a deployment", fake_ask)

    def tearDown(self):
        self.token_patch.stop()
        self.store.close()
        self.temp.cleanup()

    def test_end_to_end_and_restart(self):
        state = replay(self.store, self.case)
        self.assertEqual(len(state["analysis"]["agents"]), 5)
        self.assertIsNone(state["review"])
        record_review(self.store, self.case, "approved_for_tracking",
                      "human-analyst", "Track a bounded measurement", operator_token=os.environ["HEDGEOPS_OPERATOR_TOKEN"])
        prediction = propose_prediction(self.store, self.case, "latency", 100, 10, "ms", require_attestation=False)
        state = record_measurement(self.store, self.case, prediction, 105,
                                   "metrics.csv", "human-analyst")
        self.assertEqual(state["predictions"][prediction]["status"], "within_tolerance")
        self.store.close()
        with EventStore(self.path) as reopened:
            self.assertTrue(reopened.verify_chain())
            self.assertEqual(replay(reopened, self.case)["event_count"], 5)
        self.store = EventStore(self.path)

    def test_approval_gate(self):
        with self.assertRaises(PermissionError):
            propose_prediction(self.store, self.case, "latency", 100, 10, "ms", require_attestation=False)

    def test_rejection_blocks_tracking(self):
        record_review(self.store, self.case, "rejected", "analyst", "Not justified", operator_token=os.environ["HEDGEOPS_OPERATOR_TOKEN"])
        with self.assertRaises(PermissionError):
            propose_prediction(self.store, self.case, "latency", 100, 10, "ms", require_attestation=False)

    def test_review_cannot_be_replaced(self):
        record_review(self.store, self.case, "needs_revision", "analyst", "More data", operator_token=os.environ["HEDGEOPS_OPERATOR_TOKEN"])
        with self.assertRaises(ValueError):
            record_review(self.store, self.case, "approved_for_tracking", "analyst", "Override", operator_token=os.environ["HEDGEOPS_OPERATOR_TOKEN"])

    def test_duplicate_measurement_rejected(self):
        record_review(self.store, self.case, "approved_for_tracking", "analyst", "Test", operator_token=os.environ["HEDGEOPS_OPERATOR_TOKEN"])
        prediction = propose_prediction(self.store, self.case, "latency", 100, 10, "ms", require_attestation=False)
        record_measurement(self.store, self.case, prediction, 95, "metrics.csv", "analyst")
        with self.assertRaises(ValueError):
            record_measurement(self.store, self.case, prediction, 96, "metrics.csv", "analyst")

if __name__ == "__main__":
    unittest.main()
