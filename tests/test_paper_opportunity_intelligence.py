"""Offline tests; never make a network call or place a broker order."""
import os
import unittest
from datetime import datetime, timezone, date
from unittest.mock import patch

from paper_opportunity_intelligence import (
    DATA, PAPER, MAX_ORDER, assess, eligible_candidate, execute, news_evidence, daily_buy_commitments,
    order_id, request_json,
)


NOW = datetime(2026, 11, 4, 19, 0, tzinfo=timezone.utc)


def candidate(**overrides):
    result = {"symbol": "HD", "score": 80, "return_5d_pct": 7,
              "return_20d_pct": 15, "relative_volume_1d": 2,
              "daily_volatility_20d_pct": 1.2, "max_drawdown_30d_pct": 6,
              "above_ma20": True, "last_bar_utc": "2026-11-03T21:00:00Z"}
    result.update(overrides)
    return result


def broker(host, path, key, secret, *, params=None, payload=None):
    assert host in (PAPER, DATA)
    assert payload is None, "Assess must never POST"
    if path == "/v2/clock":
        return {"is_open": True}
    if path == "/v2/account":
        return {"status": "ACTIVE", "trading_blocked": False,
                "account_blocked": False, "cash": "1000", "buying_power": "1000"}
    if path == "/v2/positions":
        return []
    if path == "/v2/orders":
        return []
    if path == "/v2/assets/HD":
        return {"status": "active", "tradable": True, "fractionable": True}
    if path == "/v1beta1/news":
        return {"news": [{"symbols": ["HD"], "headline": "HD announces earnings results",
                          "created_at": "2026-11-04T16:00:00Z"}]}
    raise AssertionError(path)


class OpportunityTests(unittest.TestCase):
    def test_default_disabled_no_api_calls(self):
        with patch.dict(os.environ, {}, clear=True):
            result = assess(now=NOW, key="key", secret="secret",
                            get=lambda *a, **k: self.fail("Unexpected network"))
        self.assertEqual(result["decision"], "SKIP")

    def test_kill_switch_fails_closed(self):
        with patch.dict(os.environ, {"PAPER_AUTO_TRADING_ENABLED": "true"}, clear=True):
            result = assess(now=NOW, key="key", secret="secret",
                            get=lambda *a, **k: self.fail("Unexpected network"))
        self.assertEqual(result["decision"], "SKIP")

    def test_candidate_selection(self):
        self.assertEqual(eligible_candidate({"candidates": [candidate()]})["symbol"], "HD")
        self.assertIsNone(eligible_candidate({"candidates": [candidate(score=55)]}))
        self.assertIsNone(eligible_candidate({"candidates": [candidate(daily_volatility_20d_pct=5)]}))

    def test_order_id_stable(self):
        self.assertEqual(order_id(NOW.date(), "HD"), "hedgeopsauto-20261104-hd")

    def test_existing_open_order_blocks(self):
        def get(*args, **kwargs):
            if args[1] == "/v2/orders":
                return [{"symbol": "SPY", "side": "buy", "status": "accepted", "notional": "10", "submitted_at": "2026-11-04T18:00:00Z"}]
            return broker(*args, **kwargs)
        with patch.dict(os.environ, {"PAPER_AUTO_TRADING_ENABLED": "true",
                                     "PAPER_AUTO_KILL_SWITCH": "false"}, clear=True):
            result = assess(now=NOW, key="key", secret="secret", get=get,
                            bars_fetch=lambda *a, **k: self.fail("Should not scan"))
        self.assertIn("open buy", result["reason"])

    def test_news_required(self):
        self.assertEqual(len(news_evidence("HD", "key", "secret", now=NOW, get=broker)), 1)
        def no_news(*args, **kwargs):
            if args[1] == "/v1beta1/news":
                return {"news": []}
            return broker(*args, **kwargs)
        self.assertEqual(news_evidence("HD", "key", "secret", now=NOW, get=no_news), [])

    def test_execute_requires_enabled_and_no_duplicate(self):
        decision = {"decision": "READY", "symbol": "HD", "notional_usd": "10.00",
                    "client_order_id": "hedgeopsauto-20261104-hd"}
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(execute(decision, key="key", secret="secret",
                                     get=lambda *a, **k: self.fail("Network"))["decision"], "SKIP")
        with patch.dict(os.environ, {"PAPER_AUTO_TRADING_ENABLED": "true",
                                     "PAPER_AUTO_KILL_SWITCH": "false"}, clear=True):
            def existing(*args, **kwargs):
                if args[1] == "/v2/orders:by_client_order_id":
                    return {"status": "accepted"}
                return broker(*args, **kwargs)
            self.assertEqual(execute(decision, key="key", secret="secret", get=existing)["decision"], "SKIP")

    def test_single_post_paper_only(self):
        decision = {"decision": "READY", "symbol": "HD", "notional_usd": "10.00",
                    "client_order_id": "hedgeopsauto-20261104-hd"}
        calls = []
        def get(host, path, key, secret, *, params=None, payload=None):
            calls.append((host, path, payload))
            if path == "/v2/orders:by_client_order_id":
                raise RuntimeError("Alpaca HTTP 404")
            if path != "/v2/orders:by_client_order_id" and payload is None:\n                return broker(host, path, key, secret, params=params)\n            return {"id": "paper-id", "status": "accepted", "symbol": "HD", "side": "buy",\n                    "notional": "10.00", "client_order_id": decision["client_order_id"]}
        with patch.dict(os.environ, {"PAPER_AUTO_TRADING_ENABLED": "true",
                                     "PAPER_AUTO_KILL_SWITCH": "false"}, clear=True):
            result = execute(decision, key="key", secret="secret", get=get)
        self.assertEqual(result["decision"], "SUBMITTED")
        self.assertEqual(sum(payload is not None for _, _, payload in calls), 1)
        self.assertEqual(calls[-1][0:2], (PAPER, "/v2/orders"))
        self.assertEqual(calls[-1][2]["notional"], str(MAX_ORDER))
        self.assertNotIn("api.alpaca.markets/v2", calls[-1][0])

    def test_daily_spending_includes_manual_buys(self):
        orders = [{"side": "buy", "notional": "4", "submitted_at": "2026-11-04T15:00:00Z"},
                  {"side": "buy", "notional": "6", "submitted_at": "2026-11-04T16:00:00Z"}]
        self.assertEqual(str(daily_buy_commitments(orders, date(2026, 11, 4))), "10")

    def test_missing_notional_fails_closed(self):
        with self.assertRaises(ValueError):
            daily_buy_commitments([{"side": "buy", "submitted_at": "2026-11-04T15:00:00Z"}],
                                  date(2026, 11, 4))

    def test_insufficient_post_order_reserve(self):
        def low_cash(*args, **kwargs):
            if args[1] == "/v2/account":
                return {"status": "ACTIVE", "trading_blocked": False, "account_blocked": False,
                        "cash": "105", "buying_power": "105"}
            return broker(*args, **kwargs)
        with patch.dict(os.environ, {"PAPER_AUTO_TRADING_ENABLED": "true",
                                     "PAPER_AUTO_KILL_SWITCH": "false"}, clear=True):
            result = assess(now=NOW, key="key", secret="secret", get=low_cash)
        self.assertEqual(result["decision"], "SKIP")

    def test_manual_buy_blocks_daily_cap(self):
        def manual_buy(*args, **kwargs):
            if args[1] == "/v2/orders":
                return [{"side": "buy", "status": "filled", "notional": "5",
                         "submitted_at": "2026-11-04T15:00:00Z"}]
            return broker(*args, **kwargs)
        with patch.dict(os.environ, {"PAPER_AUTO_TRADING_ENABLED": "true",
                                     "PAPER_AUTO_KILL_SWITCH": "false"}, clear=True):
            result = assess(now=NOW, key="key", secret="secret", get=manual_buy)
        self.assertIn("Daily buy commitment", result["reason"])

    def test_host_allowlist(self):
        with self.assertRaises(ValueError):
            request_json("https://api.alpaca.markets", "/v2/orders", "key", "secret")


if __name__ == "__main__":
    unittest.main()
