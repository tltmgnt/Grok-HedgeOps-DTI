import csv
import math
import tempfile
import unittest
from pathlib import Path

from paper_trader import (
    DEFAULT_CAPITAL,
    prices_csv,
    prices_demo,
    simulate,
)


class PaperTraderTests(unittest.TestCase):
    def test_default_starting_capital_is_200(self):
        result = simulate([("day-1", 100.0)])
        self.assertEqual(result["starting"], 200.0)
        self.assertEqual(result["ending"], 200.0)

    def test_demo_prices_are_repeatable(self):
        self.assertEqual(list(prices_demo()), list(prices_demo()))
        self.assertEqual(len(list(prices_demo(n=12))), 12)

    def test_demo_rejects_bad_count_and_seed(self):
        for count in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                list(prices_demo(n=count))
        with self.assertRaises(ValueError):
            list(prices_demo(seed="42"))

    def test_simulation_is_repeatable_and_trade_schema_is_named(self):
        first = simulate(prices_demo(), capital=200)
        second = simulate(prices_demo(), capital=200)
        self.assertEqual(first, second)
        for trade in first["trades"]:
            self.assertIn(trade["side"], ("BUY", "SELL"))
            self.assertIn("date", trade)
            self.assertIn("price", trade)
            self.assertIn("notional", trade)
            self.assertIn("units", trade)
            self.assertIn("fee", trade)

    def test_no_leverage_and_position_is_capped(self):
        result = simulate(prices_demo())
        self.assertGreaterEqual(result["cash"], -1e-8)
        for trade in result["trades"]:
            if trade["side"] == "BUY":
                self.assertLessEqual(trade["notional"] + trade["fee"],
                                     DEFAULT_CAPITAL * 0.25 + 1e-6)

    def test_empty_prices_rejected(self):
        with self.assertRaisesRegex(ValueError, "No prices"):
            simulate([])

    def test_invalid_price_rejected(self):
        for bad in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(price=bad):
                with self.assertRaises(ValueError):
                    simulate([("d1", bad)])

    def test_non_numeric_price_rejected(self):
        with self.assertRaises(ValueError):
            simulate([("d1", "100")])

    def test_malformed_price_row_rejected(self):
        with self.assertRaisesRegex(ValueError, "Price row"):
            simulate([("d1", 100), ("bad-row",)])

    def test_invalid_capital_rejected(self):
        for capital in (0, -1, float("nan"), float("inf"), True, "200"):
            with self.subTest(capital=capital):
                with self.assertRaises(ValueError):
                    simulate([("d1", 100)], capital=capital)

    def test_invalid_periods_rejected(self):
        for fast, slow in ((0, 20), (5, 5), (6, 5), (1.5, 20), (True, 20)):
            with self.subTest(fast=fast, slow=slow):
                with self.assertRaises(ValueError):
                    simulate([("d1", 100)], fast=fast, slow=slow)

    def test_invalid_fee_rejected(self):
        for fee in (-0.1, 1, float("nan"), float("inf"), True, "0.01"):
            with self.subTest(fee=fee):
                with self.assertRaises(ValueError):
                    simulate([("d1", 100)], fee=fee)

    def test_fee_zero_keeps_full_budget_in_position(self):
        # A rising series creates a BUY after the first slow-period window.
        prices = [(str(i), float(v)) for i, v in enumerate(
            [10, 9, 8, 7, 6, 7, 8, 9, 10, 11, 12, 13], start=1
        )]
        result = simulate(prices, capital=200, fast=2, slow=4, fee=0)
        buys = [trade for trade in result["trades"] if trade["side"] == "BUY"]
        if buys:
            self.assertAlmostEqual(buys[0]["notional"], 50.0, places=6)

    def test_csv_reads_date_and_close(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prices.csv"
            path.write_text("date,close\n2025-01-01,10\n2025-01-02,11\n",
                            encoding="utf-8")
            self.assertEqual(list(prices_csv(path)),
                             [("2025-01-01", 10.0), ("2025-01-02", 11.0)])

    def test_csv_allows_missing_date_column(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prices.csv"
            path.write_text("close\n10\n11\n", encoding="utf-8")
            self.assertEqual(list(prices_csv(path)),
                             [("1", 10.0), ("2", 11.0)])

    def test_csv_requires_close_column(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prices.csv"
            path.write_text("date,price\n2025-01-01,10\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "close column"):
                list(prices_csv(path))

    def test_csv_rejects_bad_prices(self):
        for value in ("abc", "0", "-1", "nan", "inf", ""):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "prices.csv"
                path.write_text(f"date,close\nd1,{value}\n", encoding="utf-8")
                with self.subTest(value=value):
                    with self.assertRaises(ValueError):
                        list(prices_csv(path))

    def test_csv_missing_file_is_a_clear_value_error(self):
        with self.assertRaisesRegex(ValueError, "Cannot open CSV"):
            list(prices_csv("this-file-should-not-exist-12345.csv"))


if __name__ == "__main__":
    unittest.main()
