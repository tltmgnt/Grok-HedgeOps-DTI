"""Multi-connection SQLite regression tests for atomic stream preconditions."""
import tempfile
import unittest
from pathlib import Path
from hedgeops.store import EventStore
from hedgeops.operations import recover_analysis
from hedgeops.workflow import replay

def fake_agent(system, problem):
    return {"hypothesis": "Pilot", "evidence": [],
            "assumptions": ["Stable"], "risks": ["Bias"],
            "falsification_tests": ["Measure"], "confidence": "unknown"}

class ConcurrentTransitionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "cases.sqlite3")
        self.first = EventStore(self.path)
        self.second = EventStore(self.path)

    def tearDown(self):
        self.second.close()
        self.first.close()
        self.temp.cleanup()

    def test_stale_write_does_not_change_global_chain(self):
        self.first.append("case", "case_created", {"problem": "Pilot"},
                          expected_stream_events=0)
        original = self.first.history("case")
        with self.assertRaises(ValueError):
            self.second.append("case", "case_created", {"problem": "Other"},
                               expected_stream_events=0)
        self.assertEqual(self.second.history("case"), original)
        self.assertTrue(self.second.verify_chain())

    def test_unrelated_stream_does_not_conflict(self):
        self.first.append("case-a", "created", {}, expected_stream_events=0)
        self.second.append("case-b", "created", {}, expected_stream_events=0)
        self.assertEqual(len(self.first.history("case-a")), 1)
        self.assertEqual(len(self.first.history("case-b")), 1)
        self.assertTrue(self.first.verify_chain())

    def test_recovery_detects_intervening_write(self):
        case_id = "recoverable"
        self.first.append(case_id, "case_created", {"problem": "Pilot"})
        def competing_agent(system, problem):
            if len(self.second.history(case_id)) == 1:
                self.second.append(case_id, "analysis_completed",
                                   {"result": {"agents": {}, "arbitration": {}}},
                                   expected_stream_events=1)
            return fake_agent(system, problem)
        with self.assertRaises(ValueError):
            recover_analysis(self.first, case_id, competing_agent)
        self.assertEqual(replay(self.first, case_id)["event_count"], 2)
        self.assertTrue(self.first.verify_chain())

    def test_two_connections_share_latest_event_count(self):
        self.first.append("case", "created", {}, expected_stream_events=0)
        self.second.append("case", "step", {}, expected_stream_events=1)
        self.first.append("case", "step", {}, expected_stream_events=2)
        self.assertEqual(len(self.second.history("case")), 3)
        self.assertTrue(self.second.verify_chain())

if __name__ == "__main__":
    unittest.main()
