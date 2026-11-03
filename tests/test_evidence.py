import unittest
from hedgeops.evidence import Evidence, provenance_for_reports, verification_ledger
from hedgeops.conflicts import compare_hypotheses


class EvidenceTests(unittest.TestCase):
    def test_evidence_record(self):
        item = Evidence("Measured latency", "metrics.csv", "measurement")
        self.assertFalse(item.verified)
        self.assertEqual(len(item.identifier), 16)

    def test_unverified_cannot_be_verified(self):
        with self.assertRaises(ValueError):
            Evidence("Claim", "model output", verified=True)

    def test_legacy_claims_flagged(self):
        reports = {"risk": {"evidence": ["Claim"], "falsification_tests": []}}
        self.assertEqual(provenance_for_reports(reports)[0]["status"], "source_required")

    def test_ledger_deduplicates(self):
        reports = {"a": {"falsification_tests": ["Check latency"]},
                   "b": {"falsification_tests": ["check latency"]}}
        ledger = verification_ledger(reports)
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0]["status"], "pending")

    def test_disagreement_is_only_candidate(self):
        reports = {"a": {"hypothesis": "Launch now"},
                   "b": {"hypothesis": "Wait"}}
        result = compare_hypotheses(reports)
        self.assertTrue(result["potential_disagreement"])
        self.assertFalse(result["semantic_conflicts_verified"])


if __name__ == "__main__":
    unittest.main()
