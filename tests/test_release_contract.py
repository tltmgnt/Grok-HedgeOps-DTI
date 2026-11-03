"""Release smoke tests for offline core components."""
import tempfile
import unittest
from pathlib import Path
from hedgeops.store import EventStore
from hedgeops.workflow import create_case, replay

def fake_agent(system, prompt):
    return {"hypothesis": "Pilot", "evidence": [],
            "assumptions": ["Capacity exists"], "risks": ["Delay"],
            "falsification_tests": ["Measure result"], "confidence": "unknown"}

class ReleaseContractTests(unittest.TestCase):
    def test_analysis_survives_restart_with_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            db = str(Path(directory) / "release.sqlite3")
            with EventStore(db) as store:
                case_id = create_case(store, "Pilot release?", fake_agent)
                self.assertEqual(len(replay(store, case_id)["analysis"]["agents"]), 5)
            with EventStore(db) as store:
                self.assertTrue(store.verify_chain())
                self.assertEqual(replay(store, case_id)["event_count"], 2)

    def test_arbitration_requires_investigation_for_unsourced_claims(self):
        with tempfile.TemporaryDirectory() as directory:
            with EventStore(str(Path(directory) / "release.sqlite3")) as store:
                case_id = create_case(store, "Pilot release?", fake_agent)
                result = replay(store, case_id)["analysis"]
                self.assertEqual(result["arbitration"]["status"], "investigate")
                self.assertTrue(result["arbitration"]["human_approval_required"])

if __name__ == "__main__":
    unittest.main()
