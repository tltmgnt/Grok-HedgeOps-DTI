"""Offline tests: no API key or network access required."""
import unittest
from hedgeops.lab import ROLES, arbitrate, run_lab, validate_report


def report():
    return {
        "hypothesis": "Test this proposal",
        "evidence": ["User-provided scenario"],
        "assumptions": ["Resources are available"],
        "risks": ["Schedule overrun"],
        "falsification_tests": ["Measure deadline variance"],
        "confidence": "medium",
    }


class LabTests(unittest.TestCase):
    def test_all_five_agents_run(self):
        calls = []
        def ask(system, problem):
            calls.append((system, problem))
            return report()
        result = run_lab("Test deployment", ask)
        self.assertEqual(len(calls), 5)
        self.assertEqual(set(result["agents"]), set(ROLES))
        self.assertEqual(result["arbitration"]["status"], "human_review")
        self.assertTrue(result["arbitration"]["human_approval_required"])

    def test_missing_evidence_blocks_review(self):
        reports = {role: report() for role in ROLES}
        reports["risk"]["evidence"] = []
        self.assertEqual(arbitrate(reports)["status"], "investigate")

    def test_invalid_report_rejected(self):
        invalid = report()
        invalid["confidence"] = "certain"
        with self.assertRaises(ValueError):
            validate_report(invalid)

    def test_empty_problem_rejected(self):
        with self.assertRaises(ValueError):
            run_lab(" ", lambda a, b: report())


if __name__ == "__main__":
    unittest.main()
