"""Offline tests for reviewer-scoped signed approval records."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.identity import ReviewerRegistry, record_attested_review, verify_case_review
from hedgeops.store import EventStore
from hedgeops.workflow import create_case, record_review, replay

TOKEN = "test-operator-token-for-identity-tests"
REGISTRY = ReviewerRegistry({
    "alice": ("approver", b"a" * 32),
    "bob": ("reviewer", b"b" * 32),
})

def fake_agent(system, problem):
    return {"hypothesis": "Pilot", "evidence": [],
            "assumptions": ["Capacity"], "risks": ["Delay"],
            "falsification_tests": ["Measure"], "confidence": "unknown"}

class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "audit.sqlite3")
        self.store = EventStore(self.path)
        self.case_id = create_case(self.store, "Pilot?", fake_agent)
        self.env = patch.dict(os.environ, {"HEDGEOPS_OPERATOR_TOKEN": TOKEN})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.store.close()
        self.temp.cleanup()

    def test_signed_approval_survives_reopen_and_audits(self):
        sig = REGISTRY.sign(self.case_id, "approved_for_tracking", "alice", "Pilot only")
        record_attested_review(self.store, self.case_id, "approved_for_tracking",
                               "alice", "Pilot only", signature=sig,
                               registry=REGISTRY, operator_token=TOKEN)
        self.assertTrue(verify_case_review(self.store, self.case_id, REGISTRY))
        self.assertNotIn(b"a" * 32, Path(self.path).read_bytes())
        self.store.close()
        with EventStore(self.path) as reopened:
            self.assertTrue(verify_case_review(reopened, self.case_id, REGISTRY))
        self.store = EventStore(self.path)

    def test_reviewer_cannot_approve(self):
        with self.assertRaises(PermissionError):
            REGISTRY.sign(self.case_id, "approved_for_tracking", "bob", "Pilot only")

    def test_signature_bound_to_case_and_rationale(self):
        sig = REGISTRY.sign(self.case_id, "rejected", "bob", "No evidence")
        self.assertTrue(REGISTRY.verify(self.case_id, "rejected", "bob", "No evidence", sig))
        self.assertFalse(REGISTRY.verify(self.case_id, "rejected", "bob", "Changed", sig))
        self.assertFalse(REGISTRY.verify("different-case", "rejected", "bob", "No evidence", sig))

    def test_invalid_signature_cannot_append(self):
        before = replay(self.store, self.case_id)["event_count"]
        with self.assertRaises(PermissionError):
            record_attested_review(self.store, self.case_id, "rejected", "bob",
                                   "No evidence", signature="0" * 64,
                                   registry=REGISTRY, operator_token=TOKEN)
        self.assertEqual(replay(self.store, self.case_id)["event_count"], before)

    def test_unsigned_legacy_review_fails_attestation_audit(self):
        record_review(self.store, self.case_id, "rejected", "alice",
                      "No evidence", operator_token=TOKEN)
        self.assertFalse(verify_case_review(self.store, self.case_id, REGISTRY))

    def test_wrong_operator_token_rejected(self):
        sig = REGISTRY.sign(self.case_id, "rejected", "bob", "No evidence")
        with self.assertRaises(PermissionError):
            record_attested_review(self.store, self.case_id, "rejected", "bob",
                                   "No evidence", signature=sig, registry=REGISTRY,
                                   operator_token="wrong")
        self.assertIsNone(replay(self.store, self.case_id)["review"])

if __name__ == "__main__":
    unittest.main()
