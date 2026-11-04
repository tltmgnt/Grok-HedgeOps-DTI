import unittest
from paper_trader import prices_demo, simulate


class PaperTraderTests(unittest.TestCase):
    def test_repeatable_and_no_leverage(self):
        a = simulate(prices_demo(), capital=200)
        b = simulate(prices_demo(), capital=200)
        self.assertEqual(a, b)
        self.assertGreater(a["ending"], 0)
        self.assertGreaterEqual(a["max_drawdown_pct"], 0)
        self.assertTrue(
        all(t["side"] in ("BUY", "SELL") for t in a["trades"])
)

    def test_empty_prices_rejected(self):
        with self.assertRaises(ValueError):
            simulate([])

    def test_invalid_price_rejected(self):
        with self.assertRaises(ValueError):
            simulate([("today", -1)])

    def test_invalid_config_rejected(self):
        with self.assertRaises(ValueError):
            simulate(prices_demo(), capital=-1)


if __name__ == "__main__":
    unittest.main()
