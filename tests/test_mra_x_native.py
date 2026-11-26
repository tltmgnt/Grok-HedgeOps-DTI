import unittest
from hedgeops_team.core import DecisionReport
from hedgeops_team.mra_x_review import review_research_record
from tools.mra_x_tga import example


class NativeMraReviewTests(unittest.TestCase):
    def test_advisory_snapshot_preserves_report(self):
        report = DecisionReport("HOLD", 0.5, ("synthetic",), (), "synthetic")
        before = report.to_dict()
        record = example()
        result = review_research_record(report, record)
        self.assertEqual(result["status"], "REVIEW_CANDIDATE")
        self.assertFalse(result["trade_authorized"])
        self.assertFalse(result["authorizes_execution"])
        self.assertFalse(result["theorem_promoted"])
        self.assertEqual(report.to_dict(), before)
        self.assertEqual(len(record["evidence"]), 1)

    def test_invalid_record_stays_blocked(self):
        report = DecisionReport("HOLD", 0.5, (), (), "synthetic")
        record = example()
        record["evidence"][0]["sha256"] = "0" * 64
        self.assertEqual(review_research_record(report, record)["status"], "STOP")
