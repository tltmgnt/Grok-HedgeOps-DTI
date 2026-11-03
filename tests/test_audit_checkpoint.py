"""Offline checkpoint integrity and external-retention contract tests."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.audit import export_checkpoint, verify_checkpoint
from hedgeops.identity import ReviewerRegistry, record_attested_review
from hedgeops.store import EventStore
from hedgeops.workflow import create_case, propose_prediction

TOKEN = "audit-checkpoint-operator-token-long"
KEYS = ReviewerRegistry({"alice": ("approver", b"a" * 32)})

def fake_agent(system, problem):
    return {"hypothesis": "Pilot", "evidence": [],
            "assumptions": ["Capacity"], "risks": ["Delay"],
            "falsification_tests": ["Measure"], "confidence": "unknown"}

class AuditCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "journal.sqlite3")
        self.store = EventStore(self.path)
        self.case_id = create_case(self.store, "Pilot?", fake_agent)
        self.env = patch.dict(os.environ, {"HEDGEOPS_OPERATOR_TOKEN": TOKEN})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.store.close()
        self.temp.cleanup()

    def _approve(self):
        sig = KEYS.sign(self.case_id, "approved_for_tracking", "alice", "Pilot")
        record_attested_review(self.store, self.case_id, "approved_for_tracking",
                               "alice", "Pilot", signature=sig,
                               registry=KEYS, operator_token=TOKEN)

    def test_checkpoint_is_stable_across_restart(self):
        self._approve()
        checkpoint = export_checkpoint(self.store, self.case_id, KEYS)
        self.assertTrue(checkpoint["review_attestation_valid"])
        self.assertTrue(verify_checkpoint(self.store, checkpoint, KEYS))
        self.store.close()
        with EventStore(self.path) as reopened:
            self.assertTrue(verify_checkpoint(reopened, checkpoint, KEYS))
        self.store = EventStore(self.path)

    def test_new_event_requires_new_checkpoint(self):
        self._approve()
        checkpoint = export_checkpoint(self.store, self.case_id, KEYS)
        propose_prediction(self.store, self.case_id, "latency", 100, 10, "ms",
                           review_registry=KEYS)
        self.assertFalse(verify_checkpoint(self.store, checkpoint, KEYS))
        self.assertTrue(verify_checkpoint(
            self.store, export_checkpoint(self.store, self.case_id, KEYS), KEYS))

    def test_checkpoint_field_tampering_detected(self):
        self._approve()
        checkpoint = export_checkpoint(self.store, self.case_id, KEYS)
        checkpoint["case_event_count"] += 1
        self.assertFalse(verify_checkpoint(self.store, checkpoint, KEYS))

    def test_unsigned_review_marked_unverified(self):
        checkpoint = export_checkpoint(self.store, self.case_id, KEYS)
        self.assertFalse(checkpoint["review_attestation_valid"])
        self.assertTrue(verify_checkpoint(self.store, checkpoint, KEYS))

    def test_unknown_case_rejected(self):
        with self.assertRaises(KeyError):
            export_checkpoint(self.store, "not-a-case", KEYS)

    def test_revoked_signing_key_changes_checkpoint_status(self):
        versioned = ReviewerRegistry({"alice": {"role": "approver", "active": "v1",
            "keys": {"v1": b"a" * 32, "v2": b"b" * 32}}})
        sig = versioned.sign(self.case_id, "approved_for_tracking", "alice", "Pilot")
        record_attested_review(self.store, self.case_id, "approved_for_tracking",
                               "alice", "Pilot", signature=sig,
                               registry=versioned, operator_token=TOKEN)
        checkpoint = export_checkpoint(self.store, self.case_id, versioned)
        revoked = ReviewerRegistry({"alice": {"role": "approver", "active": "v2",
            "keys": {"v1": b"a" * 32, "v2": b"b" * 32}, "revoked": ["v1"]}})
        self.assertFalse(verify_checkpoint(self.store, checkpoint, revoked))

if __name__ == "__main__":
    unittest.main()
