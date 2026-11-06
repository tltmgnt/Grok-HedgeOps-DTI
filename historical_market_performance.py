"""Historical real-market backtest using read-only Alpaca IEX data. No orders."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path

from paper_trader import simulate
from stock_discovery import fetch_bars

def run(symbol, key, secret, *, now=None, fetcher=fetch_bars):
    if not symbol or not symbol.isascii() or not symbol.isalpha() or len(symbol) > 6 or symbol != symbol.upper():
        raise ValueError("Invalid stock symbol")
    bars = fetcher([symbol], key, secret, now=now)[symbol]
    observations = []
    seen = set()
    for bar in bars:
        if not isinstance(bar, dict):
            raise ValueError("Invalid market bar")
        stamp, close = bar.get("t"), bar.get("c")
        if not isinstance(stamp, str) or not stamp:
            raise ValueError("Invalid bar timestamp")
        try:
            timestamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Invalid bar timestamp") from None
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Bar timestamp must include timezone")
        if isinstance(close, bool) or not isinstance(close, (float, int)) or not math.isfinite(close) or close <= 0:
            raise ValueError("Invalid bar close")
        if timestamp in seen:
            raise ValueError("Duplicate market bar")
        seen.add(timestamp)
        observations.append((timestamp, float(close)))
    observations.sort()
    if len(observations) < 40:
        raise ValueError("Insufficient market history (minimum 40 daily bars)")
    if now is not None:
        cutoff = now.date()
    else:
        cutoff = datetime.now(timezone.utc).date()
    if any(t.astimezone(timezone.utc).date() >= cutoff for t, _ in observations):
        raise ValueError("Incomplete current-day bar detected")
    result = simulate([(t.isoformat(), price) for t, price in observations], capital=200.0, fast=5, slow=20, fee=0.001, max_allocation=0.25)
    return {
        "mode": "HISTORICAL_MARKET_DATA_PAPER_ONLY",
        "source": "Alpaca IEX historical daily bars",
        "symbol": symbol,
        "data_start": observations[0][0].isoformat(),
        "data_end": observations[-1][0].isoformat(),
        "orders_submitted": 0,
        "live_execution_verified": False,
        "results": result,
    }

def main():
    parser = argparse.ArgumentParser(description="Read-only historical real-market backtest; no order endpoints")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--out", type=Path, default=Path("market-performance.json"))
    args = parser.parse_args()
    key = os.environ.get("APCA_API_KEY_ID", "")
    secret = os.environ.get("APCA_API_SECRET_KEY", "")
    if not key or not secret:
        raise SystemExit("Missing read-only Alpaca market data credentials")
    report = run(args.symbol, key, secret)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))
    print("return_pct:", report["results"]["return_pct"])
    print("benchmark_return_pct:", report["results"]["benchmark"]["return_pct"])
    print("PAPER ONLY: NO ORDERS SUBMITTED")

if __name__ == "__main__":
    main()
