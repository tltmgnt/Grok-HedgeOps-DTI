"""Offline paper-trading safety and risk regression tests."""
import math
import unittest

from paper_trader import prices_demo, simulate


class PaperTraderTests(unittest.TestCase):
    def test_repeatable_and_no_leverage(self):
        a = simulate(prices_demo(), capital=200)
        b = simulate(prices_demo(), capital=200)
        self.assertEqual(a, b)
        self.assertGreater(a["ending"], 0)
        self.assertGreaterEqual(a["max_drawdown_pct"], 0)
        self.assertTrue(all(t["side"] in ("BUY", "SELL") for t in a["trades"]))
        self.assertGreaterEqual(a["cash"], -1e-7)
        self.assertGreaterEqual(a["open_units"], 0)

    def test_empty_prices_rejected(self):
        with self.assertRaises(ValueError):
            simulate([])

    def test_invalid_price_rejected(self):
        for price in (-1, 0, math.inf, math.nan, True, "100"):
            with self.subTest(price=price), self.assertRaises(ValueError):
                simulate([("today", price)])

    def test_invalid_config_rejected(self):
        for options in (
            {"capital": -1}, {"capital": math.nan}, {"fee": -0.01},
            {"fee": 1}, {"max_allocation": 0},
            {"max_allocation": 1.1}, {"stop_loss_pct": 0},
            {"stop_loss_pct": 1}, {"fast": True},
            {"slow": 2, "fast": 2}, {"force_liquidate": 1},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                simulate(prices_demo(), **options)

    def test_stop_loss_sells_after_observed_price_drop(self):
        prices = [(str(i), float(100 + i)) for i in range(1, 24)]
        prices.append(("crash", 50.0))
        result = simulate(prices, fast=2, slow=3, stop_loss_pct=0.1)
        self.assertTrue(any(
            t["side"] == "SELL" and t["reason"] == "STOP_LOSS"
            for t in result["trades"]
        ))
        self.assertEqual(result["open_units"], 0)

    def test_allocation_capped_and_no_borrowing(self):
        prices = [(str(i), float(100 + i)) for i in range(1, 30)]
        result = simulate(prices, fast=2, slow=3, max_allocation=0.25)
        buys = [t for t in result["trades"] if t["side"] == "BUY"]
        self.assertTrue(buys)
        self.assertLessEqual(buys[0]["gross"], 200 * 0.25 + 1e-6)
        self.assertGreaterEqual(result["cash"], -1e-7)

    def test_force_liquidation_closes_position(self):
        prices = [(str(i), float(100 + i)) for i in range(1, 30)]
        result = simulate(prices, fast=2, slow=3, force_liquidate=True)
        self.assertEqual(result["open_units"], 0)
        self.assertTrue(any(
            t["reason"] == "END_OF_SIMULATION" for t in result["trades"]
        ))

    def test_no_lookahead_signal(self):
        # The first possible trade occurs only after the slow lookback exists.
        prices = [(str(i), float(100 + i)) for i in range(1, 10)]
        result = simulate(prices, fast=2, slow=3)
        self.assertTrue(result["trades"])
        self.assertGreaterEqual(int(result["trades"][0]["date"]), 4)


if __name__ == "__main__":
    unittest.main()
