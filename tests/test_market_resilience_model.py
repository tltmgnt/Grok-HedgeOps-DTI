import copy
import unittest
from market_resilience_model import evaluate, validate, verify_report

def study():
    return {"version": 1, "mode": "synthetic", "name": "Test", "capacity": 10,
            "source": "Fictional", "review": "", "requests": [
                {"id": "a", "participant": "A", "units": 8},
                {"id": "a", "participant": "A", "units": 8},
                {"id": "b", "participant": "B", "units": 8}],
            "repairs": [{"name": "Repair", "deduplicate": True,
                         "participantCap": 5, "allocation": "pro-rata"}]}

class MarketTests(unittest.TestCase):
    def test_hand_calculated_allocation(self):
        a, b = evaluate(study())["results"]
        self.assertEqual(a["allocations"], {"A": 10, "B": 0})
        self.assertEqual(b["allocations"], {"A": 5, "B": 5})
        self.assertEqual(b["duplicateRequests"], 1)

    def test_deduplication_is_idempotent(self):
        s = study()
        s["repairs"][0]["participantCap"] = None
        before = evaluate(s)["results"][1]["allocations"]
        s["requests"].insert(1, copy.deepcopy(s["requests"][0]))
        self.assertEqual(before, evaluate(s)["results"][1]["allocations"])

    def test_conflicting_duplicate_declared(self):
        s = study()
        s["requests"][1]["units"] = 9
        self.assertEqual(evaluate(s)["results"][1]["conflictingDuplicates"], 1)

    def test_capacity_conservation_all_candidates(self):
        for capacity in (0, 1, 3, 7, 10, 100):
            s = study()
            s["capacity"] = capacity
            for row in evaluate(s)["results"]:
                self.assertEqual(row["allocatedUnits"] + row["unusedCapacity"], capacity)
                self.assertTrue(all(row["invariants"].values()))

    def test_proportional_remainders_stable(self):
        s = study()
        s["capacity"] = 3
        self.assertEqual(evaluate(s)["results"][1]["allocations"], {"A": 2, "B": 1})

    def test_empty_demand(self):
        s = study()
        s["requests"] = []
        self.assertIsNone(evaluate(s)["results"][0]["allocationConcentration"])

    def test_invalid_inputs(self):
        for key, value in (("capacity", True), ("capacity", -1), ("mode", "live")):
            s = study()
            s[key] = value
            with self.assertRaises(ValueError):
                validate(s)

    def test_unknown_candidate_fields_rejected(self):
        s = study()
        s["repairs"][0]["command"] = "ignored?"
        with self.assertRaises(ValueError):
            validate(s)

    def test_tampered_report_rejected(self):
        s = study()
        report = evaluate(s)
        report["results"][0]["allocatedUnits"] = 999
        with self.assertRaises(ValueError):
            verify_report(s, report)

    def test_determinism_no_mutation_or_authority(self):
        s = study()
        original = copy.deepcopy(s)
        a = evaluate(s)
        self.assertEqual(a, evaluate(s))
        self.assertEqual(s, original)
        self.assertFalse(a["executionAuthorized"])

if __name__ == "__main__":
    unittest.main()
