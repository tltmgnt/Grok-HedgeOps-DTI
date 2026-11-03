"""Phase 90: final release assessment must fail closed."""
import unittest

from hedgeops.release_gate import REQUIRED
from hedgeops.release_readiness_gate import (
    OPERATIONAL_EVIDENCE, final_release_assessment)

READY = {"ready": True, "reason_code": "READY", "custody_verified": True}
ALL = {name: True for name in REQUIRED + OPERATIONAL_EVIDENCE}


class FinalReleaseAssessmentTests(unittest.TestCase):
    def test_complete_evidence_requires_separate_human_authorization(self):
        result = final_release_assessment(READY, ALL)
        self.assertEqual(result["recommendation"], "REVIEW_FOR_GO")
        self.assertTrue(result["runtime_ready"])
        self.assertEqual(result["missing_evidence"], [])
        self.assertTrue(result["explicit_human_release_authorization_required"])

    def test_missing_each_required_attestation_denies_release(self):
        for name in ALL:
            with self.subTest(name=name):
                evidence = dict(ALL)
                evidence.pop(name)
                result = final_release_assessment(READY, evidence)
                self.assertEqual(result["recommendation"], "NO_GO")
                self.assertIn(name, result["missing_evidence"])

    def test_pending_or_unverified_runtime_denies_release(self):
        for report in (
                {"ready": False, "reason_code": "PENDING_RECONCILIATION",
                 "custody_verified": False},
                {"ready": True, "reason_code": "READY",
                 "custody_verified": False},
                None):
            with self.subTest(report=report):
                result = final_release_assessment(report, ALL)
                self.assertEqual(result["recommendation"], "NO_GO")
                self.assertFalse(result["runtime_ready"])

    def test_malformed_or_truthy_evidence_cannot_bypass_gate(self):
        for evidence in (None, [], {}, {name: 1 for name in ALL},
                         {name: "true" for name in ALL}):
            with self.subTest(evidence=evidence):
                self.assertEqual(
                    final_release_assessment(READY, evidence)["recommendation"],
                    "NO_GO")


if __name__ == "__main__":
    unittest.main()
