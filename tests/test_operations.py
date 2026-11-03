import tempfile
import os
from unittest.mock import patch
import unittest
from pathlib import Path
from hedgeops.store import EventStore
from hedgeops.operations import (
    require_operator_token, recover_analysis, authorized_review)
from hedgeops.workflow import replay

TOKEN = "test-only-operator-token-at-least-24-chars"

def fake_ask(system, prompt):
    return {"hypothesis": "Pilot first", "evidence": [],
            "assumptions": ["Capacity available"], "risks": ["Delay"],
            "falsification_tests": ["Measure latency"], "confidence": "unknown"}

class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.token_patch = patch.dict(os.environ, {"HEDGEOPS_OPERATOR_TOKEN": TOKEN})
        self.token_patch.start()
        self.temp = tempfile.TemporaryDirectory()
        self.store = EventStore(str(Path(self.temp.name) / "test.sqlite3"))
        self.case_id = "recoverable-case"
        self.store.append(self.case_id, "case_created", {"problem": "Pilot?"})

    def tearDown(self):
        self.token_patch.stop()
        self.store.close()
        self.temp.cleanup()

    def test_recovery(self):
        result = recover_analysis(self.store, self.case_id, fake_ask)
        self.assertEqual(len(result["analysis"]["agents"]), 5)
        self.assertTrue(self.store.verify_chain())

    def test_duplicate_recovery_blocked(self):
        recover_analysis(self.store, self.case_id, fake_ask)
        with self.assertRaises(ValueError):
            recover_analysis(self.store, self.case_id, fake_ask)

    def test_token_required(self):
        with self.assertRaises(PermissionError):
            require_operator_token("wrong", TOKEN)
        with self.assertRaises(RuntimeError):
            require_operator_token("anything", "short")
        require_operator_token(TOKEN, TOKEN)

    def test_authorized_review(self):
        recover_analysis(self.store, self.case_id, fake_ask)
        with self.assertRaises(PermissionError):
            authorized_review(self.store, self.case_id, "needs_revision",
                              "operator", "More data", "wrong", TOKEN)
        state = authorized_review(self.store, self.case_id, "needs_revision",
                                  "operator", "More data", TOKEN, TOKEN)
        self.assertEqual(state["review"]["decision"], "needs_revision")

if __name__ == "__main__":
    unittest.main()
