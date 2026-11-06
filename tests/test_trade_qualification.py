import unittest
from datetime import datetime, timezone
from trade_qualification import qualify

class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.account = {"equity": 10000, "buying_power": 1000, "daily_pnl": 0}
        self.signal = {"symbol": "SPY", "price": 110, "sma20": 105, "sma50": 100,
                       "volume": 200000, "avg_volume": 100000, "spread_bps": 4,
                       "asof": self.now.isoformat(), "market_open": True, "tradable": True, "kill_switch": False, "volatility_pct": 1, "estimated_slippage_bps": 2, "portfolio_exposure_pct": 1, "daily_loss_pct": 0, "grok_veto": False, "event_within_24h": False}
    def check(self, signal=None, account=None):
        return qualify([signal or self.signal], account or self.account, [], [], now=self.now)["decisions"][0]
    def test_qualifies(self):
        self.assertEqual(self.check()["status"], "QUALIFIED")
    def test_missing_evidence_defers(self):
        s = dict(self.signal)
        del s["event_within_24h"]
        self.assertEqual(self.check(s)["risk_diagnostics"]["decision"], "DEFER")
    def test_volatility_reduces_size(self):
        s = dict(self.signal, volatility_pct=5)
        d = self.check(s)
        self.assertEqual(d["status"], "QUALIFIED")
        self.assertEqual(d["notional_usd"], 100)
    def test_kill_switch_rejects(self):
        s = dict(self.signal, kill_switch=True)
        self.assertEqual(self.check(s)["risk_diagnostics"]["decision"], "REJECT")
    def test_stale(self):
        s = dict(self.signal, asof="2020-01-01T00:00:00+00:00")
        self.assertIn("STALE_DATA", self.check(s)["reasons"])
    def test_market_closed(self):
        self.assertIn("MARKET_CLOSED", self.check(dict(self.signal, market_open=False))["reasons"])
    def test_grok_cannot_override(self):
        self.assertIn("TREND_NOT_CONFIRMED", self.check(dict(self.signal, price=90, grok_confidence=1))["reasons"])
    def test_loss_limit(self):
        self.assertEqual(qualify([self.signal], dict(self.account, daily_pnl=-150), [], [], now=self.now)["reason"], "DAILY_LOSS_LIMIT")

if __name__ == "__main__":
    unittest.main()
