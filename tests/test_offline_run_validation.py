import unittest
from scripts.validate_offline_run import validate

def valid():
    return {
        "starting": 200, "ending": 201.5, "return_pct": 0.75,
        "observations": 2, "trade_count": 1,
        "trades": [{"side": "BUY"}], "equity_curve": [200, 201.5],
    }

class OfflineRunValidationTests(unittest.TestCase):
    def test_valid_simulation(self):
        self.assertEqual(validate(valid())["status"], "PASS")
        self.assertEqual(validate(valid())["broker_orders_submitted"], 0)

    def test_missing_fields_fail(self):
        with self.assertRaises(ValueError):
            validate({})

    def test_trade_count_mismatch_fails(self):
        r = valid()
        r["trade_count"] = 2
        with self.assertRaises(ValueError):
            validate(r)

    def test_nonfinite_equity_fails(self):
        r = valid()
        r["equity_curve"][0] = float("nan")
        with self.assertRaises(ValueError):
            validate(r)

    def test_wrong_capital_fails(self):
        r = valid()
        r["starting"] = 500
        with self.assertRaises(ValueError):
            validate(r)

if __name__ == "__main__":
    unittest.main()
