import copy
import unittest
from market_resilience_model import evaluate
from market_resilience_review import review_bundle

def bundle():
    s = {"version": 1, "mode": "synthetic", "name": "Review fixture", "capacity": 1,
         "source": "Fictional", "review": "", "requests": [
             {"id": "a", "participant": "A", "units": 2}],
         "repairs": [{"name": "Bounded", "deduplicate": True,
                      "participantCap": 1, "allocation": "pro-rata"}]}
    return {"study": s, "report": evaluate(s)}

class ReviewTests(unittest.TestCase):
    def test_recomputed_bundle_is_unverified_and_not_authorized(self):
        result = review_bundle(bundle())
        self.assertFalse(result["executionAuthorized"])
        self.assertFalse(result["evidenceVerified"])
        self.assertEqual(result["status"], "human_review_required")

    def test_tampered_report_and_modified_study_rejected(self):
        for field in ("study", "report"):
            b = bundle()
            if field == "study":
                b[field]["capacity"] = 2
            else:
                b[field]["executionAuthorized"] = True
            with self.assertRaises(ValueError):
                review_bundle(b)

    def test_callback_is_opt_in_proposal_only(self):
        called = []
        def ask(prompt):
            called.append(prompt)
            return "Unverified proposed critique."
        result = review_bundle(bundle(), ask=ask)
        self.assertEqual(len(called), 1)
        self.assertFalse(result["critique"]["verified"])
        self.assertFalse(result["executionAuthorized"])

    def test_callback_cannot_return_an_action_object(self):
        with self.assertRaises(ValueError):
            review_bundle(bundle(), ask=lambda _: {"execute": True})

    def test_extra_bundle_fields_rejected_and_no_input_mutation(self):
        b = bundle()
        original = copy.deepcopy(b)
        review_bundle(b)
        self.assertEqual(b, original)
        b["execute"] = True
        with self.assertRaises(ValueError):
            review_bundle(b)

if __name__ == "__main__":
    unittest.main()
