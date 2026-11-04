"""Offline-only educational paper trading. No API keys, network or broker orders."""
import argparse
import csv
import math
import random
from pathlib import Path

def prices_demo(n=160, seed=42):
    rng = random.Random(seed)
    price = 100.0
    for i in range(n):
        price *= math.exp(rng.gauss(0.0002, 0.012))
        yield str(i + 1), price

def prices_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "close" not in reader.fieldnames:
            raise ValueError("CSV requires a close column (optional date column)")
        for i, row in enumerate(reader):
            value = float(row["close"])
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Prices must be finite and positive")
            yield row.get("date") or str(i + 1), value

def simulate(prices, capital=200.0, fast=5, slow=20, fee=0.001):
    if type(fast) is not int or type(slow) is not int:
        raise ValueError("Moving-average periods must be integers")
    if isinstance(fee, bool):
        raise ValueError("Fee must be numeric, not Boolean")
    if isinstance(capital, bool):
        raise ValueError("Starting capital must be numeric, not Boolean")
    if not math.isfinite(capital) or capital <= 0 or fast < 1 or slow <= fast or not 0 <= fee < 1:
        raise ValueError("Invalid configuration")
    cash, units = float(capital), 0.0
    history, trades = [], []
    peak, max_drawdown = cash, 0.0
    for date, price in prices:
        if isinstance(price, bool) or not math.isfinite(price) or price <= 0:
            raise ValueError("Prices must be finite and positive")
        
        if len(history) >= slow:
            short_avg = sum(history[-fast:]) / fast
            long_avg = sum(history[-slow:]) / slow
            if short_avg > long_avg and units == 0:
                # Maximum position: 25% of account equity; never borrow.
                spend = cash * 0.25
                units = spend * (1 - fee) / price
                cash -= spend
                trades.append((date, "BUY", round(price, 4), round(spend, 2)))
            elif short_avg < long_avg and units > 0:
                proceeds = units * price * (1 - fee)
                cash += proceeds
                trades.append((date, "SELL", round(price, 4), round(proceeds, 2)))
                units = 0.0
        equity = cash + units * price
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak)
        history.append(price)
    if not history:
        raise ValueError("No prices supplied")
    final = cash + units * history[-1]
    return {"starting": capital, "ending": round(final, 2),
            "return_pct": round(100 * (final / capital - 1), 2),
            "max_drawdown_pct": round(max_drawdown * 100, 2),
            "open_units": round(units, 8), "trades": trades}

def main():
    parser = argparse.ArgumentParser(description="Offline-only $200 paper trading demo")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true", help="Deterministic synthetic prices")
    source.add_argument("--csv", type=Path, help="CSV with date,close columns")
    parser.add_argument("--capital", type=float, default=200.0)
    args = parser.parse_args()
    result = simulate(prices_demo() if args.demo else prices_csv(args.csv), args.capital)
    print("PAPER ONLY — NO LIVE ORDERS — NO GROK API CALLS")
    for key in ("starting", "ending", "return_pct", "max_drawdown_pct", "open_units"):
        print(f"{key}: {result[key]}")
    print(f"trades: {len(result['trades'])}")
    for trade in result["trades"]:
        print(*trade, sep=", ")

if __name__ == "__main__":
    main()
