"""Key-version and revocation tests for local reviewer attestations."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.identity import ReviewerRegistry, record_attested_review, verify_case_review
from hedgeops.store import EventStore
from hedgeops.workflow import create_case, propose_prediction

TOKEN = "key-lifecycle-test-operator-token"

def fake_agent(system, problem):
    return {"hypothesis": "Pilot", "evidence": [],
            "assumptions": ["Capacity"], "risks": ["Delay"],
            "falsification_tests": ["Measure"], "confidence": "unknown"}

def registry(active="v1", revoked=()):
    return ReviewerRegistry({"alice": {
        "role": "approver", "active": active,
        "keys": {"v1": b"a" * 32, "v2": b"b" * 32},
        "revoked": list(revoked),
    }})

class KeyLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = EventStore(str(Path(self.temp.name) / "cases.sqlite3"))
        self.case = create_case(self.store, "Pilot?", fake_agent)
        self.env = patch.dict(os.environ, {"HEDGEOPS_OPERATOR_TOKEN": TOKEN})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.store.close()
        self.temp.cleanup()

    def _approve(self, keys):
        sig = keys.sign(self.case, "approved_for_tracking", "alice", "Pilot")
        record_attested_review(self.store, self.case, "approved_for_tracking",
                               "alice", "Pilot", signature=sig,
                               registry=keys, operator_token=TOKEN)

    def test_rotation_keeps_old_review_verifiable(self):
        self._approve(registry())
        self.assertTrue(verify_case_review(self.store, self.case, registry(active="v2")))
        prediction = propose_prediction(self.store, self.case, "latency", 100, 10, "ms",
                                        review_registry=registry(active="v2"))
        self.assertTrue(prediction)

    def test_revocation_blocks_old_approval_and_tracking(self):
        self._approve(registry())
        revoked = registry(active="v2", revoked=("v1",))
        self.assertFalse(verify_case_review(self.store, self.case, revoked))
        with self.assertRaises(PermissionError):
            propose_prediction(self.store, self.case, "latency", 100, 10, "ms",
                               review_registry=revoked)

    def test_new_key_cannot_impersonate_old_signature(self):
        self._approve(registry())
        altered = ReviewerRegistry({"alice": {
            "role": "approver", "active": "v2",
            "keys": {"v1": b"z" * 32, "v2": b"b" * 32}}})
        self.assertFalse(verify_case_review(self.store, self.case, altered))

    def test_retired_key_cannot_sign_new_review(self):
        rotated = registry(active="v2")
        with self.assertRaises(PermissionError):
            rotated.sign(self.case, "approved_for_tracking", "alice", "Pilot", key_id="v1")

    def test_revoked_active_key_configuration_fails(self):
        with self.assertRaises(ValueError):
            registry(active="v1", revoked=("v1",))

    def test_key_id_is_bound_to_signature(self):
        keys = registry(active="v1")
        sig = keys.sign(self.case, "rejected", "alice", "Pilot")
        self.assertTrue(keys.verify(self.case, "rejected", "alice", "Pilot", sig, key_id="v1"))
        self.assertFalse(keys.verify(self.case, "rejected", "alice", "Pilot", sig, key_id="v2"))

if __name__ == "__main__":
    unittest.main()
