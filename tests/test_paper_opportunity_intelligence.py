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
        from zoneinfo import ZoneInfo
        today = datetime.now(timezone.utc).astimezone(
            ZoneInfo("America/New_York")
        ).date()
        decision = {"decision": "READY", "symbol": "HD", "notional_usd": "10.00",
                        "client_order_id": order_id(today, "HD")}
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
        from zoneinfo import ZoneInfo
        today = datetime.now(timezone.utc).astimezone(
            ZoneInfo("America/New_York")
        ).date()
        decision = {"decision": "READY", "symbol": "HD", "notional_usd": "10.00",
                    "client_order_id": order_id(today, "HD")}
        calls = []
        def get(host, path, key, secret, *, params=None, payload=None):
            calls.append((host, path, payload))
            if path == "/v2/orders:by_client_order_id":
                raise RuntimeError("Alpaca HTTP 404")
            if path != "/v2/orders:by_client_order_id" and payload is None:
                return broker(host, path, key, secret, params=params)
            return {"id": "paper-id", "status": "accepted", "symbol": "HD", "side": "buy",
                    "notional": "10.00", "client_order_id": decision["client_order_id"]}
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
            if args[1] == "/v2/orders" and kwargs.get("params", {}).get("status") == "open":
                return []
            if args[1] == "/v2/orders":
                return [{
                    "side": "buy",
                    "status": "filled",
                    "notional": "95",
                    "submitted_at": "2026-11-04T15:00:00Z",
                }]
            return broker(*args, **kwargs)

        with patch.dict(os.environ, {
            "PAPER_AUTO_TRADING_ENABLED": "true",
            "PAPER_AUTO_KILL_SWITCH": "false",
        }, clear=True):
            result = assess(
                now=NOW,
                key="key",
                secret="secret",
                get=manual_buy,
                bars_fetch=lambda *a, **k: self.fail("Should not scan"),
            )

        self.assertEqual(result["decision"], "SKIP")
        self.assertIn("Daily buy commitment", result["reason"])

    def test_host_allowlist(self):
        with self.assertRaises(ValueError):
            request_json("https://api.alpaca.markets", "/v2/orders", "key", "secret")


    def test_five_positions_block_trading(self):
        def five_positions(*args, **kwargs):
            if args[1] == "/v2/positions":
                return [{"symbol": f"STK{i}"} for i in range(5)]
            return broker(*args, **kwargs)

        with patch.dict(os.environ, {
            "PAPER_AUTO_TRADING_ENABLED": "true",
            "PAPER_AUTO_KILL_SWITCH": "false"
        }, clear=True):
            result = assess(
                now=NOW, key="key", secret="secret",
                get=five_positions,
                bars_fetch=lambda *a, **k: self.fail("Should not scan")
            )
        self.assertEqual(result["decision"], "SKIP")
        self.assertIn("Position-count cap", result["reason"])

    def test_truncated_order_history_fails_closed(self):
        def too_many_orders(*args, **kwargs):
            if args[1] == "/v2/orders":
                return [{} for _ in range(500)]
            return broker(*args, **kwargs)

        with patch.dict(os.environ, {
            "PAPER_AUTO_TRADING_ENABLED": "true",
            "PAPER_AUTO_KILL_SWITCH": "false"
        }, clear=True):
            with self.assertRaisesRegex(ValueError, "truncated"):
                assess(now=NOW, key="key", secret="secret",
                       get=too_many_orders)

    def test_broker_api_failure_never_submits_order(self):
        calls = []

        def failing_broker(host, path, key, secret, *,
                           params=None, payload=None):
            calls.append((host, path, payload))
            raise RuntimeError("Alpaca request failed")

        with patch.dict(os.environ, {
            "PAPER_AUTO_TRADING_ENABLED": "true",
            "PAPER_AUTO_KILL_SWITCH": "false"
        }, clear=True):
            with self.assertRaises(RuntimeError):
                assess(now=NOW, key="key", secret="secret",
                       get=failing_broker)

        self.assertFalse(any(payload is not None
                             for _, _, payload in calls))

    def test_invalid_order_id_never_submits_order(self):
        from datetime import timedelta
        from paper_opportunity_intelligence import order_id

        calls = []

        def recording_broker(host, path, key, secret, *,
                             params=None, payload=None):
            calls.append((path, payload))
            raise AssertionError("Broker must not be called")

        trading_day = NOW.astimezone(
            timezone(timedelta(hours=-5))
        ).date()

        decision = {
            "decision": "READY",
            "symbol": "HD",
            "notional_usd": "10.00",
            "client_order_id": order_id(trading_day, "LOW") ,
        }

        with patch.dict(os.environ, {
            "PAPER_AUTO_TRADING_ENABLED": "true",
            "PAPER_AUTO_KILL_SWITCH": "false",
        }, clear=True):
            with self.assertRaisesRegex(ValueError, "Unsafe order parameters"):
                execute(decision, key="key", secret="secret",
                        get=recording_broker)

        self.assertEqual(calls, [])

    def test_market_closed_recheck_never_submits_order(self):
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        from paper_opportunity_intelligence import execute, order_id

        calls = []

        def fake_broker(host, path, key, secret, *,
                        params=None, payload=None):
            calls.append((path, payload))
            if path == "/v2/clock":
                return {"is_open": False}
            raise AssertionError("No further broker requests allowed")

        today = datetime.now(timezone.utc).astimezone(
            ZoneInfo("America/New_York")
        ).date()

        decision = {
            "decision": "READY",
            "symbol": "HD",
            "notional_usd": "10.00",
            "client_order_id": order_id(today, "HD"),
        }

        with patch.dict(os.environ, {
            "PAPER_AUTO_TRADING_ENABLED": "true",
            "PAPER_AUTO_KILL_SWITCH": "false",
        }, clear=True):
            result = execute(
                decision, key="test", secret="test",
                get=fake_broker,
            )

        self.assertEqual(result["decision"], "SKIP")
        self.assertEqual(calls, [("/v2/clock", None)])

    def test_daily_cap_100_boundary(self):
        from paper_opportunity_intelligence import MAX_DAILY

        self.assertEqual(MAX_DAILY, 100)

        for spent, should_block in [
            ("90.00", False),
            ("90.01", True),
            ("100.00", True),
        ]:
            with self.subTest(spent=spent):
                remaining = MAX_DAILY - daily_buy_commitments(
                    [{
                        "side": "buy",
                        "status": "filled",
                        "notional": spent,
                        "submitted_at": "2026-11-04T15:00:00Z",
                    }],
                    date(2026, 11, 4),
                )
                self.assertEqual(
                    remaining < MAX_ORDER,
                    should_block,
                )

    def test_daily_cap_enforced_by_broker_risk_check(self):
        from paper_opportunity_intelligence import broker_risk_check

        for spent, should_block in [
            ("90.00", False),
            ("90.01", True),
            ("100.00", True),
        ]:
            with self.subTest(spent=spent):
                def fake_broker(host, path, key, secret, *,
                                params=None, payload=None):
                    self.assertEqual(host, PAPER)
                    self.assertIsNone(payload)

                    if path == "/v2/account":
                        return {
                            "status": "ACTIVE",
                            "trading_blocked": False,
                            "account_blocked": False,
                            "cash": "1000",
                            "buying_power": "1000",
                        }
                    if path == "/v2/positions":
                        return []
                    if path == "/v2/orders":
                        return [{
                            "side": "buy",
                            "status": "filled",
                            "notional": spent,
                            "submitted_at": "2026-11-04T15:00:00Z",
                        }]
                    self.fail(f"Unexpected broker path: {path}")

                reason = broker_risk_check(
                    now=NOW,
                    key="key",
                    secret="secret",
                    get=fake_broker,
                 )

                if should_block:
                    self.assertIn("Daily buy commitment", reason)
                else:
                    self.assertIsNone(reason)
    def test_midnight_order_history_boundary(self):
        from paper_opportunity_intelligence import broker_risk_check
        from zoneinfo import ZoneInfo
        from datetime import timedelta

        trading_day = date(2026, 11, 4)
        midnight = datetime.combine(
            trading_day,
            datetime.min.time(),
            tzinfo=ZoneInfo("America/New_York"),
        )
        expected_after = (midnight - timedelta(seconds=1)).isoformat()
        seen_orders = []

        def fake_broker(host, path, key, secret, *,
                        params=None, payload=None):
            self.assertEqual(host, PAPER)
            self.assertIsNone(payload)

            if path == "/v2/account":
                return {
                    "status": "ACTIVE",
                    "trading_blocked": False,
                    "account_blocked": False,
                    "cash": "1000",
                    "buying_power": "1000",
                }
            if path == "/v2/positions":
                return []
            if path == "/v2/orders":
                self.assertEqual(params["after"], expected_after)
                seen_orders.append(True)
                return [{
                    "side": "buy",
                    "status": "filled",
                    "notional": "95.00",
                    "submitted_at": midnight.isoformat(),
                }]
            self.fail(f"Unexpected broker path: {path}")

        reason = broker_risk_check(
            now=NOW,
            key="key",
            secret="secret",
            get=fake_broker,
        )

        self.assertTrue(seen_orders)
        self.assertIn("Daily buy commitment cap reached", reason)
        
if __name__ == "__main__":
    unittest.main()
