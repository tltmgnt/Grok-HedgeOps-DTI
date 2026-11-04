"""Offline-only educational paper trading.

This module uses only local/synthetic price data. It has no API keys, network
access, broker integration, or live-order capability.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path
from typing import Iterable, Iterator, Any


DEFAULT_CAPITAL = 200.0
DEFAULT_FAST = 5
DEFAULT_SLOW = 20
DEFAULT_FEE = 0.001
MAX_POSITION_FRACTION = 0.25


def prices_demo(n: int = 160, seed: int = 42) -> Iterator[tuple[str, float]]:
    """Yield deterministic synthetic closing prices."""
    if type(n) is not int or n < 1:
        raise ValueError("Demo price count must be a positive integer")
    if type(seed) is not int:
        raise ValueError("Demo seed must be an integer")

    rng = random.Random(seed)
    price = 100.0
    for i in range(n):
        price *= math.exp(rng.gauss(0.0002, 0.012))
        yield str(i + 1), price


def prices_csv(path: str | Path) -> Iterator[tuple[str, float]]:
    """Read local CSV data with required `close` and optional `date` columns."""
    csv_path = Path(path)
    try:
        handle = csv_path.open("r", newline="", encoding="utf-8-sig")
    except OSError as exc:
        raise ValueError(f"Cannot open CSV file {csv_path}: {exc}") from exc

    with handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "close" not in reader.fieldnames:
            raise ValueError("CSV requires a close column (optional date column)")

        for line_number, row in enumerate(reader, start=2):
            if not row or all(value is None or not str(value).strip()
                              for value in row.values()):
                continue
            raw_price = row.get("close")
            try:
                price = float(raw_price)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid close price on CSV line {line_number}: {raw_price!r}"
                ) from exc
            if not math.isfinite(price) or price <= 0:
                raise ValueError(
                    f"Close price on CSV line {line_number} must be finite and positive"
                )
            date = (row.get("date") or "").strip() or str(line_number - 1)
            yield date, price


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def simulate(
    prices: Iterable[tuple[str, float]],
    capital: float = DEFAULT_CAPITAL,
    fast: int = DEFAULT_FAST,
    slow: int = DEFAULT_SLOW,
    fee: float = DEFAULT_FEE,
) -> dict[str, Any]:
    """Run a long-only moving-average paper simulation.

    A BUY uses at most 25% of current equity (including the fee). A SELL closes
    the entire paper position. Trades are dictionaries with stable named fields.
    Open positions are marked to market at the final close; they are not forcibly
    liquidated at the end of the input.
    """
    capital_value = _finite_number(capital, "Starting capital")
    fee_value = _finite_number(fee, "Fee")
    if capital_value <= 0:
        raise ValueError("Starting capital must be positive")
    if type(fast) is not int or type(slow) is not int:
        raise ValueError("Moving-average periods must be integers")
    if fast < 1 or slow <= fast:
        raise ValueError("Periods must satisfy 1 <= fast < slow")
    if not 0 <= fee_value < 1:
        raise ValueError("Fee must satisfy 0 <= fee < 1")

    cash = capital_value
    units = 0.0
    history: list[float] = []
    trades: list[dict[str, Any]] = []
    peak = capital_value
    max_drawdown = 0.0
    last_price: float | None = None

    for index, item in enumerate(prices, start=1):
        try:
            date, raw_price = item
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Price row {index} must contain (date, close)") from exc
        if isinstance(raw_price, bool) or not isinstance(raw_price, (int, float)):
            raise ValueError(f"Price on row {index} must be numeric")
        price = float(raw_price)
        if not math.isfinite(price) or price <= 0:
            raise ValueError(f"Price on row {index} must be finite and positive")

        if len(history) >= slow:
            short_avg = sum(history[-fast:]) / fast
            long_avg = sum(history[-slow:]) / slow

            if short_avg > long_avg and units == 0:
                equity_before_trade = cash + units * price
                budget = min(cash, equity_before_trade * MAX_POSITION_FRACTION)
                # Budget includes the transaction fee, so cash never goes negative.
                purchased_units = budget / (price * (1.0 + fee_value))
                gross_notional = purchased_units * price
                fee_paid = gross_notional * fee_value
                cash -= gross_notional + fee_paid
                units = purchased_units
                trades.append({
                    "date": str(date),
                    "side": "BUY",
                    "price": round(price, 8),
                    "notional": round(gross_notional, 8),
                    "units": round(purchased_units, 12),
                    "fee": round(fee_paid, 8),
                })
            elif short_avg < long_avg and units > 0:
                gross_notional = units * price
                fee_paid = gross_notional * fee_value
                proceeds = gross_notional - fee_paid
                cash += proceeds
                trades.append({
                    "date": str(date),
                    "side": "SELL",
                    "price": round(price, 8),
                    "notional": round(gross_notional, 8),
                    "units": round(units, 12),
                    "fee": round(fee_paid, 8),
                })
                units = 0.0

        equity = cash + units * price
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
        history.append(price)
        last_price = price

    if last_price is None:
        raise ValueError("No prices supplied")

    ending = cash + units * last_price
    return {
        "starting": round(capital_value, 8),
        "ending": round(ending, 8),
        "return_pct": round(100.0 * (ending / capital_value - 1.0), 8),
        "max_drawdown_pct": round(max_drawdown * 100.0, 8),
        "cash": round(cash, 8),
        "open_units": round(units, 12),
        "trades": trades,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline-only educational paper trading simulator"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true",
                        help="Use deterministic synthetic prices")
    source.add_argument("--csv", type=Path,
                        help="Read a local CSV with date,close columns")
    parser.add_argument("--capital", type=float, default=DEFAULT_CAPITAL)
    parser.add_argument("--fast", type=int, default=DEFAULT_FAST)
    parser.add_argument("--slow", type=int, default=DEFAULT_SLOW)
    parser.add_argument("--fee", type=float, default=DEFAULT_FEE)
    parser.add_argument("--json", action="store_true",
                        help="Print the complete result as JSON")
    args = parser.parse_args(argv)

    try:
        price_rows = prices_demo() if args.demo else prices_csv(args.csv)
        result = simulate(price_rows, args.capital, args.fast, args.slow, args.fee)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))

    print("PAPER ONLY — NO LIVE ORDERS — NO API CALLS — OFFLINE DATA ONLY")
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for key in ("starting", "ending", "return_pct",
                    "max_drawdown_pct", "cash", "open_units"):
            print(f"{key}: {result[key]}")
        print(f"trades: {len(result['trades'])}")
        for trade in result["trades"]:
            print(
                trade["date"], trade["side"], trade["price"],
                trade["notional"], trade["units"], trade["fee"],
                sep=", ",
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
