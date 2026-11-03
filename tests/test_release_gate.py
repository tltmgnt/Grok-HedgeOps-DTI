import unittest
from hedgeops.release_gate import assess_release, REQUIRED

class ReleaseGateTests(unittest.TestCase):
    def test_defaults_fail_closed(self):
        result = assess_release({})
        self.assertFalse(result.eligible)
        self.assertEqual(result.missing, REQUIRED)

    def test_partial_evidence_not_enough(self):
        result = assess_release({"offline_ci_passed": True})
        self.assertFalse(result.eligible)
        self.assertNotIn("offline_ci_passed", result.missing)

    def test_only_explicit_boolean_true_counts(self):
        result = assess_release({name: "true" for name in REQUIRED})
        self.assertFalse(result.eligible)

    def test_all_attestations_allow_review_not_deploy(self):
        result = assess_release({name: True for name in REQUIRED})
        self.assertTrue(result.eligible)
        self.assertEqual(result.missing, ())

if __name__ == "__main__":
    unittest.main()
