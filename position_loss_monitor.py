"""Read-only Alpaca position loss monitoring. Never submits, cancels or changes orders.

Loss thresholds are *alerts*, not stop orders or guaranteed execution prices.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _number(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be numeric") from None
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def validate_thresholds(warning_pct, critical_pct):
    warning = _number(warning_pct, "warning_pct")
    critical = _number(critical_pct, "critical_pct")
    if not 0 < warning < critical <= 100:
        raise ValueError("thresholds must satisfy 0 < warning_pct < critical_pct <= 100")
    return warning, critical


def evaluate_positions(positions, *, warning_pct=5.0, critical_pct=10.0):
    """Evaluate broker-reported unrealized P/L; fail closed on missing data.

    A loss percentage uses the broker's cost basis, not intraday movement.
    No quote is fetched and no order is placed.
    """
    warning, critical = validate_thresholds(warning_pct, critical_pct)
    if not isinstance(positions, list):
        raise ValueError("broker positions response must be a list")
    output = []
    for position in positions:
        if not isinstance(position, dict):
            raise ValueError("invalid broker position")
        symbol = position.get("symbol")
        if not isinstance(symbol, str) or not symbol or len(symbol) > 32:
            raise ValueError("missing or invalid position symbol")
        qty = _number(position.get("qty"), "qty")
        cost_basis = _number(position.get("cost_basis"), "cost_basis")
        market_value = _number(position.get("market_value"), "market_value")
        unrealized_pl = _number(position.get("unrealized_pl"), "unrealized_pl")
        if qty <= 0 or cost_basis <= 0 or market_value < 0:
            raise ValueError("position quantity, cost basis or market value invalid")
        if abs((market_value - cost_basis) - unrealized_pl) > max(0.05, cost_basis * 0.001):
            raise ValueError("broker position values inconsistent")
        loss_pct = max(0.0, -100.0 * unrealized_pl / cost_basis)
        severity = ("critical" if loss_pct >= critical else
                    "warning" if loss_pct >= warning else "ok")
        output.append({
            "symbol": symbol, "quantity": qty,
            "cost_basis_usd": round(cost_basis, 2),
            "market_value_usd": round(market_value, 2),
            "unrealized_pl_usd": round(unrealized_pl, 2),
            "unrealized_loss_pct": round(loss_pct, 4),
            "severity": severity,
            "recommended_action": (
                "REVIEW_POSITION_AND_CONSIDER_BROKER_PROTECTIVE_ORDER"
                if severity == "critical" else
                "REVIEW_POSITION" if severity == "warning" else "MONITOR"
            ),
        })
    return sorted(output, key=lambda item: (-item["unrealized_loss_pct"], item["symbol"]))


def _get_json(base, path, key, secret):
    req = Request(base + path, headers={
        "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
    }, method="GET")
    try:
        with urlopen(req, timeout=15) as response:  # nosec B310 - fixed HTTPS Alpaca host
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"Alpaca read failed (HTTP {exc.code})") from None
    except (URLError, TimeoutError):
        raise RuntimeError("Alpaca read failed or timed out") from None


def monitor(*, mode, key, secret, warning_pct=5.0, critical_pct=10.0):
    warning, critical = validate_thresholds(warning_pct, critical_pct)
    if mode not in ("paper", "live"):
        raise ValueError("mode must be paper or live")
    if not key or not secret:
        raise ValueError("Alpaca credentials missing")
    base = "https://paper-api.alpaca.markets" if mode == "paper" else "https://api.alpaca.markets"
    positions = _get_json(base, "/v2/positions", key, secret)
    assessed = evaluate_positions(positions, warning_pct=warning, critical_pct=critical)
    return {
        "schema_version": "1.0", "mode": mode, "broker": "alpaca",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "thresholds": {"warning_pct": warning, "critical_pct": critical},
        "position_count": len(assessed),
        "warning_count": sum(p["severity"] == "warning" for p in assessed),
        "critical_count": sum(p["severity"] == "critical" for p in assessed),
        "positions": assessed,
        "order_submission_enabled": False,
        "disclaimer": "Read-only broker snapshot; not continuous monitoring, a stop-loss order, or a guaranteed exit.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only Alpaca unrealized-loss monitor")
    parser.add_argument("--mode", choices=("paper", "live"), default="paper")
    parser.add_argument("--warning-pct", type=float, default=5.0)
    parser.add_argument("--critical-pct", type=float, default=10.0)
    parser.add_argument("--output", type=Path, default=Path("position-risk-report.json"))
    args = parser.parse_args(argv)
    try:
        report = monitor(
            mode=args.mode, key=os.getenv("ALPACA_API_KEY", ""),
            secret=os.getenv("ALPACA_API_SECRET", ""),
            warning_pct=args.warning_pct, critical_pct=args.critical_pct,
        )
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(2, f"Monitoring failed: {exc}\n")
    print(f"Warnings: {report['warning_count']}; critical: {report['critical_count']}")
    print("READ ONLY — NO ORDER SUBMITTED")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        lines = ["## Alpaca position-loss monitor", "",
                 f"Warnings: {report['warning_count']}; critical: {report['critical_count']}",
                 "", "Holdings and amounts are omitted from public GitHub logs.",
                 "Read-only snapshot. No orders placed. Broker quotes may be delayed."]
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
            summary.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
