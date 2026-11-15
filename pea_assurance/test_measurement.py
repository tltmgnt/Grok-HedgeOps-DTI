import math
import unittest
from pea_assurance import calibration, agreement, scoped_decision


class MeasurementTests(unittest.TestCase):
    def test_perfect_and_wrong(self):
        self.assertEqual(calibration([0, 1], [0, 1])["brier"], 0)
        self.assertEqual(calibration([1, 0], [0, 1])["brier"], 1)

    def test_hand_calculated(self):
        r = calibration([0.2, 0.8], [0, 1], bins=2)
        self.assertAlmostEqual(r["brier"], 0.04)
        self.assertAlmostEqual(r["ece"], 0.2)

    def test_empty_and_endpoint(self):
        self.assertIsNone(calibration([], [])["brier"])
        self.assertEqual(calibration([1], [1])["bins"][-1]["n"], 1)

    def test_invalid_probability(self):
        for x in [math.nan, math.inf, -0.1, 1.1, True, "0.5"]:
            with self.subTest(x=x), self.assertRaises(ValueError):
                calibration([x], [1])

    def test_invalid_labels_lengths_bins(self):
        for p, y, b in [([0], [], 2), ([0], [None], 2), ([0], [True], 2), ([0], [2], 2), ([], [], 0), ([], [], True)]:
            with self.assertRaises(ValueError):
                calibration(p, y, b)

    def test_kappa(self):
        self.assertEqual(agreement(["a", "b"], ["a", "b"])["kappa"], 1)
        self.assertEqual(agreement(["a", "b"], ["b", "a"])["kappa"], -1)
        self.assertIsNone(agreement(["a"], ["a"])["kappa"])
        self.assertIsNone(agreement([], [])["observed_agreement"])

    def test_rating_validation(self):
        for a, b in [(["a"], []), ([None], ["a"]), ([""], ["a"])]:
            with self.assertRaises(ValueError):
                agreement(a, b)

    def decision(self, **kwargs):
        args = {"claim_id": "synthetic-c1", "scope": "synthetic arithmetic only",
                "policy_version": "test-v1", "evidence_refs": ["fixture:e1"],
                "checks": {k: "PASS" for k in ("validity", "calibration", "provenance", "reproduction", "adversarial", "governance")}}
        args.update(kwargs)
        return scoped_decision(**args)

    def test_scoped_acceptance(self):
        r = self.decision()
        self.assertEqual(r["decision"], "accepted")
        self.assertTrue(r["advisory_only"])
        self.assertFalse(r["empirically_validated"])

    def test_missing_never_accepts(self):
        self.assertEqual(self.decision(checks={})["decision"], "uncertain")
        self.assertEqual(self.decision(evidence_refs=[])["decision"], "uncertain")

    def test_statuses_and_failure_precedence(self):
        for status in ("UNCERTAIN", "ERROR", "SKIPPED"):
            self.assertEqual(self.decision(checks={"validity": status})["decision"], "uncertain")
        self.assertEqual(self.decision(checks={"validity": "FAIL", "calibration": "ERROR"})["decision"], "rejected")

    def test_no_scope_or_unknown_check(self):
        for args in [{"scope": ""}, {"checks": {"truth": "PASS"}}, {"checks": {"validity": "yes"}}, {"evidence_refs": "e1"}]:
            with self.assertRaises(ValueError):
                self.decision(**args)


if __name__ == "__main__":
    unittest.main()
