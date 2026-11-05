"""Offline-only opportunity decision rehearsal. No credentials, network, or order submission.

All Alpaca responses are deterministic fixtures. This is NOT a live-data scan.
"""
from datetime import datetime, timezone
from unittest.mock import patch
import json
from pathlib import Path

import paper_opportunity_intelligence as trader

NOW = datetime(2026, 11, 4, 19, 0, tzinfo=timezone.utc)
CANDIDATE = {
    "symbol": "HD", "score": 80, "return_5d_pct": 7,
    "return_20d_pct": 15, "relative_volume_1d": 2,
    "daily_volatility_20d_pct": 1.2, "max_drawdown_30d_pct": 6,
    "above_ma20": True, "last_bar_utc": "2026-11-04T18:00:00Z",
}
NEWS = {"news": [{"symbols": ["HD"], "headline": "HD announces earnings results",
                  "created_at": "2026-11-04T17:00:00Z"}]}


def fixture_broker(*, cash="1000", orders=None, positions=None, clock_open=True):
    orders = [] if orders is None else orders
    positions = [] if positions is None else positions

    def get(host, path, key, secret, *, params=None, payload=None):
        if payload is not None:
            raise AssertionError("DRY RUN MUST NEVER POST")
        if host not in (trader.PAPER, trader.DATA):
            raise AssertionError("Unexpected host")
        if path == "/v2/clock":
            return {"is_open": clock_open}
        if path == "/v2/account":
            return {"status": "ACTIVE", "trading_blocked": False,
                    "account_blocked": False, "cash": cash, "buying_power": cash}
        if path == "/v2/positions":
            return positions
        if path == "/v2/orders":
            return orders
        if path == "/v2/assets/HD":
            return {"status": "active", "tradable": True, "fractionable": True}
        if path == "/v1beta1/news":
            return NEWS
        raise AssertionError("Unexpected broker path: " + path)
    return get


def simulate(name, *, enabled="true", kill="false", **broker_options):
    # Enable flags exist ONLY inside this isolated fixture evaluation. No secrets are loaded.
    # Never call execute(), main(), request_json(), or urlopen().
    with patch.dict("os.environ", {
        "PAPER_AUTO_TRADING_ENABLED": enabled,
        "PAPER_AUTO_KILL_SWITCH": kill,
    }, clear=True), patch.object(trader, "build_report", return_value={"candidates": [CANDIDATE]}):
        decision = trader.assess(
            now=NOW, key="fixture-not-a-real-key", secret="fixture-not-a-real-secret",
            get=fixture_broker(**broker_options),
            bars_fetch=lambda *args, **kwargs: {},
        )
    return {"scenario": name, "decision": decision["decision"],
            "reason": decision.get("reason", ""),
            "would_submit": decision["decision"] == "READY"}


def main():
    results = []
    for name, kwargs in [
        ("eligible_fixture", {}),
        ("disabled_flag", {"enabled": "false"}),
        ("kill_switch", {"kill": "true"}),
        ("daily_spending_cap", {"orders": [{"side": "buy", "status": "filled",
            "notional": "5", "submitted_at": "2026-11-04T17:00:00Z"}]}),
        ("pending_buy", {"orders": [{"side": "buy", "status": "accepted",
            "notional": "10", "submitted_at": "2026-11-04T17:00:00Z"}]}),
        ("cash_reserve", {"cash": "105"}),
        ("position_cap", {"positions": [{"symbol": s} for s in
            ["AAPL", "MSFT", "AMZN", "COST", "JPM"]]}),
        ("market_closed", {"clock_open": False}),
    ]:
        results.append(simulate(name, **kwargs))
    try:
        simulate("unknown_buy_notional", orders=[{"side": "buy", "status": "filled",
            "submitted_at": "2026-11-04T17:00:00Z"}])
    except ValueError:
        results.append({"scenario": "unknown_buy_notional", "decision": "ERROR",
                        "reason": "Missing notional fails closed", "would_submit": False})
    else:
        raise AssertionError("Unknown notional was not rejected")

    expected = {"eligible_fixture": "READY", "disabled_flag": "SKIP",
                "kill_switch": "SKIP", "daily_spending_cap": "SKIP",
                "pending_buy": "SKIP", "cash_reserve": "SKIP",
                "position_cap": "SKIP", "market_closed": "SKIP",
                "unknown_buy_notional": "ERROR"}
    assert {r["scenario"]: r["decision"] for r in results} == expected
    assert sum(r["would_submit"] for r in results) == 1
    output = Path("offline-dry-run-output")
    output.mkdir(exist_ok=True)
    (output / "results.json").write_text(json.dumps(
        {"mode": "OFFLINE FIXTURES ONLY", "orders_submitted": 0,
         "real_broker_calls": 0, "scenarios": results}, indent=2) + "\n")
    summary = ["# Paper opportunity dry run", "",
               "**OFFLINE FIXTURES ONLY — no Alpaca calls, no orders.**", "",
               "| Scenario | Decision | Reason |", "|---|---|---|"]
    for r in results:
        summary.append(f"| {r['scenario']} | {r['decision']} | {r['reason']} |")
    summary.extend(["", "An eligible fixture is a hypothetical READY decision, NOT an order.",
                    "This does not validate real-time broker state or live market data."])
    (output / "summary.md").write_text("\n".join(summary) + "\n")
    print("\n".join(summary))


if __name__ == "__main__":
    main()
