import csv
import json
import math
import tempfile
import unittest
from pathlib import Path

from paper_trader import prices_csv, prices_demo, simulate, write_trade_csv


class PaperTraderTests(unittest.TestCase):
    def test_demo_is_deterministic(self):
        self.assertEqual(list(prices_demo(10, 7)), list(prices_demo(10, 7)))

    def test_demo_rejects_invalid_length(self):
        with self.assertRaises(ValueError):
            list(prices_demo(0))

    def test_empty_prices_rejected(self):
        with self.assertRaisesRegex(ValueError, "No prices"):
            simulate([])

    def test_invalid_price_rejected(self):
        for value in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    simulate([("d1", 100), ("d2", value)])

    def test_invalid_configuration_rejected(self):
        invalid = [
            {"capital": 0}, {"capital": float("nan")}, {"capital": True},
            {"fast": 0}, {"slow": 5, "fast": 5}, {"fast": 1.5},
            {"fee": 1}, {"fee": -0.1}, {"fee": True},
            {"max_allocation": 0}, {"max_allocation": 1.1},
            {"max_allocation": True}, {"stop_loss_pct": 0},
            {"stop_loss_pct": 1}, {"stop_loss_pct": float("nan")},
            {"force_liquidate": 1},
        ]
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    simulate([("d1", 100)], **kwargs)

    def test_no_trade_when_not_enough_history(self):
        result = simulate([("1", 100), ("2", 101)], fast=1, slow=3)
        self.assertEqual(result["trade_count"], 0)
        self.assertEqual(result["ending"], 200.0)

    def test_allocation_is_capped_at_25_percent_of_equity(self):
        # A rising series creates a bullish regime and one entry.
        prices = [(str(i), 100 + i) for i in range(1, 40)]
        result = simulate(prices, fast=2, slow=4, fee=0)
        buys = [trade for trade in result["trades"] if trade["side"] == "BUY"]
        self.assertTrue(buys)
        first_buy = buys[0]
        self.assertLessEqual(first_buy["gross"], 50.000001)

    def test_fee_reduces_buying_power(self):
        prices = [(str(i), 100 + i) for i in range(1, 20)]
        result = simulate(prices, fast=2, slow=4, fee=0.01)
        buys = [t for t in result["trades"] if t["side"] == "BUY"]
        if buys:
            self.assertGreater(buys[0]["fee"], 0)
            self.assertLess(result["cash"], 200)

    def test_force_liquidation_closes_position(self):
        prices = [(str(i), 100 + i) for i in range(1, 40)]
        result = simulate(prices, fast=2, slow=4, fee=0, force_liquidate=True)
        self.assertEqual(result["open_units"], 0)
        if result["trades"]:
            self.assertEqual(result["trades"][-1]["reason"], "END_OF_SIMULATION")

    def test_result_has_benchmark_and_metrics(self):
        result = simulate(list(prices_demo()), capital=200)
        self.assertIn("benchmark", result)
        self.assertIn("sharpe_ratio", result)
        self.assertIn("max_drawdown_pct", result)
        self.assertGreaterEqual(result["max_drawdown_pct"], 0)
        self.assertEqual(result["observations"], 160)

    def test_csv_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prices.csv"
            path.write_text("date,close\n2025-01-01,100\n2025-01-02,101\n",
                            encoding="utf-8")
            self.assertEqual(list(prices_csv(path)),
                             [("2025-01-01", 100.0), ("2025-01-02", 101.0)])

    def test_csv_rejects_missing_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text("date,open\n2025-01-01,100\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "close column"):
                list(prices_csv(path))

    def test_csv_rejects_bad_price(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text("date,close\n2025-01-01,abc\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "row 2"):
                list(prices_csv(path))

    def test_trade_csv_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trades.csv"
            write_trade_csv(path, [{
                "date": "d1", "side": "BUY", "price": 10,
                "units": 1, "gross": 10, "fee": 0.01, "reason": "SIGNAL"
            }])
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["side"], "BUY")


if __name__ == "__main__":
    unittest.main()
