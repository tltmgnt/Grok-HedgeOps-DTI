"""Tests for fail-closed attested tracking mode and legacy compatibility."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.identity import ReviewerRegistry, record_attested_review
from hedgeops.store import EventStore
from hedgeops.workflow import create_case, propose_prediction, record_review, replay

TOKEN = "attested-tracking-test-operator-secret"
REGISTRY = ReviewerRegistry({"alice": ("approver", b"a" * 32)})

def fake_agent(system, problem):
    return {"hypothesis": "Pilot", "evidence": [],
            "assumptions": ["Capacity"], "risks": ["Delay"],
            "falsification_tests": ["Measure"], "confidence": "unknown"}

class AttestedTrackingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = EventStore(str(Path(self.temp.name) / "cases.sqlite3"))
        self.case_id = create_case(self.store, "Pilot?", fake_agent)
        self.env = patch.dict(os.environ, {"HEDGEOPS_OPERATOR_TOKEN": TOKEN})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.store.close()
        self.temp.cleanup()

    def _propose(self, **kwargs):
        return propose_prediction(self.store, self.case_id, "latency", 100, 10, "ms", **kwargs)

    def test_unsigned_approval_rejected_in_enforced_mode(self):
        record_review(self.store, self.case_id, "approved_for_tracking", "alice",
                      "Pilot only", operator_token=TOKEN)
        count = replay(self.store, self.case_id)["event_count"]
        with self.assertRaises(PermissionError):
            self._propose(require_attestation=True, review_registry=REGISTRY)
        self.assertEqual(replay(self.store, self.case_id)["event_count"], count)
        self.assertTrue(self.store.verify_chain())

    def test_valid_signed_approval_allows_enforced_tracking(self):
        sig = REGISTRY.sign(self.case_id, "approved_for_tracking", "alice", "Pilot only")
        record_attested_review(self.store, self.case_id, "approved_for_tracking",
                               "alice", "Pilot only", signature=sig,
                               registry=REGISTRY, operator_token=TOKEN)
        prediction = self._propose(require_attestation=True, review_registry=REGISTRY)
        self.assertIn(prediction, replay(self.store, self.case_id)["predictions"])

    def test_enforced_mode_requires_registry(self):
        record_review(self.store, self.case_id, "approved_for_tracking", "alice",
                      "Pilot only", operator_token=TOKEN)
        with self.assertRaises(PermissionError):
            self._propose(require_attestation=True)

    def test_wrong_registry_rejected(self):
        sig = REGISTRY.sign(self.case_id, "approved_for_tracking", "alice", "Pilot only")
        record_attested_review(self.store, self.case_id, "approved_for_tracking",
                               "alice", "Pilot only", signature=sig,
                               registry=REGISTRY, operator_token=TOKEN)
        impostor = ReviewerRegistry({"alice": ("approver", b"z" * 32)})
        with self.assertRaises(PermissionError):
            self._propose(require_attestation=True, review_registry=impostor)

    def test_legacy_mode_remains_explicitly_compatible(self):
        record_review(self.store, self.case_id, "approved_for_tracking", "alice",
                      "Pilot only", operator_token=TOKEN)
        self.assertIn(self._propose(), replay(self.store, self.case_id)["predictions"])

if __name__ == "__main__":
    unittest.main()
