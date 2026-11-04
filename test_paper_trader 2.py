"""Unit tests for the offline paper trading engine."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

import paper_trader as pt


class PaperTraderTests(unittest.TestCase):
    def test_demo_is_deterministic(self):
        self.assertEqual(list(pt.prices_demo()), list(pt.prices_demo()))

    def test_demo_length(self):
        self.assertEqual(len(list(pt.prices_demo(12))), 12)

    def test_demo_rejects_bad_length(self):
        with self.assertRaises(ValueError):
            list(pt.prices_demo(0))

    def test_csv_reads_date_and_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "prices.csv"
            p.write_text("date,close\n2026-01-01,10\n", encoding="utf-8")
            self.assertEqual(list(pt.prices_csv(p)), [("2026-01-01", 10.0)])

    def test_csv_requires_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.csv"
            p.write_text("date,open\n2026-01-01,10\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                list(pt.prices_csv(p))

    def test_csv_rejects_nonpositive_price(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.csv"
            p.write_text("close\n0\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                list(pt.prices_csv(p))

    def test_rejects_empty_prices(self):
        with self.assertRaises(ValueError):
            pt.simulate([])

    def test_rejects_invalid_capital(self):
        for value in (0, -1, float("nan"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                pt.simulate(pt.prices_demo(), capital=value)

    def test_rejects_invalid_periods(self):
        for fast, slow in ((0, 20), (5, 5), (6, 5), (True, 20)):
            with self.subTest(fast=fast, slow=slow), self.assertRaises(ValueError):
                pt.simulate(pt.prices_demo(), fast=fast, slow=slow)

    def test_rejects_invalid_fee(self):
        for fee in (-0.1, 1, float("nan"), True):
            with self.subTest(fee=fee), self.assertRaises(ValueError):
                pt.simulate(pt.prices_demo(), fee=fee)

    def test_rejects_invalid_max_position(self):
        for fraction in (0, -0.1, 1.1, True):
            with self.subTest(fraction=fraction), self.assertRaises(ValueError):
                pt.simulate(pt.prices_demo(), max_position=fraction)

    def test_rejects_invalid_price(self):
        with self.assertRaises(ValueError):
            pt.simulate([("1", 10), ("2", float("inf"))])

    def test_result_has_expected_fields_and_capital(self):
        result = pt.simulate(pt.prices_demo(), capital=200)
        self.assertEqual(result["starting"], 200.0)
        self.assertIn("max_drawdown_pct", result)
        self.assertIn("buy_hold_return_pct", result)
        self.assertIn("sharpe_ratio", result)

    def test_position_never_exceeds_configured_entry_fraction(self):
        result = pt.simulate(pt.prices_demo(), capital=200, max_position=0.25)
        buys = [t for t in result["trades"] if t["side"] == "BUY"]
        self.assertTrue(all(t["cash_amount"] <= 50.00 for t in buys))

    def test_report_files_are_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = pt.simulate(pt.prices_demo())
            jp, cp = Path(tmp) / "result.json", Path(tmp) / "trades.csv"
            pt.write_reports(result, jp, cp)
            self.assertEqual(json.loads(jp.read_text())["starting"], 200.0)
            with cp.open(newline="") as f:
                self.assertEqual(next(csv.DictReader(f)).keys(),
                                 {"date", "side", "price", "cash_amount", "units"})


if __name__ == "__main__":
    unittest.main()
