"""Offline-only educational paper trading engine.

No API keys, network access, or broker orders. Uses local CSV data or
deterministic synthetic prices. This is a teaching/backtesting tool only.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path
from statistics import mean, pstdev
from typing import Iterable, Iterator

PriceRow = tuple[str, float]


def prices_demo(n: int = 160, seed: int = 42) -> Iterator[PriceRow]:
    """Yield deterministic synthetic (date, close) observations."""
    if type(n) is not int or n < 1:
        raise ValueError("n must be a positive integer")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    rng = random.Random(seed)
    price = 100.0
    for i in range(n):
        price *= math.exp(rng.gauss(0.0002, 0.012))
        yield str(i + 1), price


def prices_csv(path: str | Path) -> Iterator[PriceRow]:
    """Read local CSV data with required close and optional date columns."""
    with Path(path).open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "close" not in reader.fieldnames:
            raise ValueError("CSV requires a close column (optional date column)")
        for i, row in enumerate(reader, start=1):
            try:
                price = float(row["close"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid close price on CSV row {i + 1}") from exc
            if not math.isfinite(price) or price <= 0:
                raise ValueError(f"Close prices must be finite and positive (row {i + 1})")
            date = (row.get("date") or "").strip() or str(i)
            yield date, price


def _validate_prices(prices: Iterable[PriceRow]) -> list[PriceRow]:
    rows: list[PriceRow] = []
    for date, price in prices:
        if isinstance(price, bool):
            raise ValueError("Prices must be numeric, not Boolean")
        try:
            value = float(price)
        except (TypeError, ValueError) as exc:
            raise ValueError("Prices must be numeric") from exc
        if not math.isfinite(value) or value <= 0:
            raise ValueError("Prices must be finite and positive")
        rows.append((str(date), value))
    if not rows:
        raise ValueError("No prices supplied")
    return rows


def simulate(
    prices: Iterable[PriceRow],
    capital: float = 200.0,
    fast: int = 5,
    slow: int = 20,
    fee: float = 0.001,
    max_position: float = 0.25,
) -> dict:
    """Run a long-only moving-average crossover simulation.

    At most max_position of available cash is spent per entry. No leverage,
    shorting, external data, or live orders are supported.
    """
    if isinstance(capital, bool) or not isinstance(capital, (int, float)):
        raise ValueError("Starting capital must be numeric, not Boolean")
    if not math.isfinite(capital) or capital <= 0:
        raise ValueError("Starting capital must be finite and positive")
    if type(fast) is not int or type(slow) is not int or fast < 1 or slow <= fast:
        raise ValueError("Periods must be integers with 1 <= fast < slow")
    if isinstance(fee, bool) or not isinstance(fee, (int, float)):
        raise ValueError("Fee must be numeric, not Boolean")
    if not math.isfinite(fee) or not 0 <= fee < 1:
        raise ValueError("Fee must be finite and in [0, 1)")
    if isinstance(max_position, bool) or not isinstance(max_position, (int, float)):
        raise ValueError("Maximum position must be numeric, not Boolean")
    if not math.isfinite(max_position) or not 0 < max_position <= 1:
        raise ValueError("Maximum position must be in (0, 1]")

    rows = _validate_prices(prices)
    cash = float(capital)
    units = 0.0
    history: list[float] = []
    trades: list[dict] = []
    equity_curve: list[float] = []
    peak = float(capital)
    max_drawdown = 0.0

    for date, price in rows:
        if len(history) >= slow:
            short_avg = mean(history[-fast:])
            long_avg = mean(history[-slow:])
            if short_avg > long_avg and units == 0:
                spend = cash * float(max_position)
                bought = spend * (1.0 - float(fee)) / price
                if spend > 0:
                    units = bought
                    cash -= spend
                    trades.append({
                        "date": date, "side": "BUY", "price": round(price, 6),
                        "cash_amount": round(spend, 2), "units": round(bought, 10),
                    })
            elif short_avg < long_avg and units > 0:
                proceeds = units * price * (1.0 - float(fee))
                sold_units = units
                cash += proceeds
                units = 0.0
                trades.append({
                    "date": date, "side": "SELL", "price": round(price, 6),
                    "cash_amount": round(proceeds, 2), "units": round(sold_units, 10),
                })

        equity = cash + units * price
        equity_curve.append(equity)
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak)
        history.append(price)

    ending = cash + units * rows[-1][1]
    daily_returns = [
        equity_curve[i] / equity_curve[i - 1] - 1
        for i in range(1, len(equity_curve)) if equity_curve[i - 1] > 0
    ]
    volatility = pstdev(daily_returns) if len(daily_returns) > 1 else 0.0
    sharpe = (mean(daily_returns) / volatility * math.sqrt(252)
              if volatility > 0 else 0.0)

    buy_hold = float(capital) * rows[-1][1] / rows[0][1]
    sells = [t for t in trades if t["side"] == "SELL"]
    wins = sum(1 for t in sells if t["cash_amount"] >
               next((b["cash_amount"] for b in reversed(trades[:trades.index(t)])
                     if b["side"] == "BUY"), float("inf")))
    result = {
        "starting": round(float(capital), 2),
        "ending": round(ending, 2),
        "return_pct": round((ending / float(capital) - 1) * 100, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "sharpe_ratio": round(sharpe, 4),
        "buy_hold_ending": round(buy_hold, 2),
        "buy_hold_return_pct": round((buy_hold / float(capital) - 1) * 100, 2),
        "open_units": round(units, 10),
        "trade_count": len(trades),
        "completed_round_trips": len(sells),
        "win_rate_pct": round(100 * wins / len(sells), 2) if sells else 0.0,
        "trades": trades,
    }
    return result


def write_reports(result: dict, json_path: str | Path | None,
                  trades_path: str | Path | None) -> None:
    """Write optional local JSON and CSV reports."""
    if json_path:
        Path(json_path).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if trades_path:
        with Path(trades_path).open("w", newline="", encoding="utf-8") as handle:
            fields = ["date", "side", "price", "cash_amount", "units"]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(result["trades"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline-only $200 paper trading simulator")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true", help="Use deterministic synthetic prices")
    source.add_argument("--csv", type=Path, help="Use local CSV with date,close columns")
    parser.add_argument("--capital", type=float, default=200.0)
    parser.add_argument("--fast", type=int, default=5)
    parser.add_argument("--slow", type=int, default=20)
    parser.add_argument("--fee", type=float, default=0.001)
    parser.add_argument("--max-position", type=float, default=0.25)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--trades-out", type=Path)
    args = parser.parse_args(argv)

    data = prices_demo() if args.demo else prices_csv(args.csv)
    result = simulate(data, args.capital, args.fast, args.slow, args.fee, args.max_position)
    print("PAPER ONLY — OFFLINE — NO API KEYS — NO NETWORK — NO LIVE ORDERS")
    for key in ("starting", "ending", "return_pct", "max_drawdown_pct",
                "sharpe_ratio", "buy_hold_ending", "buy_hold_return_pct",
                "open_units", "trade_count", "completed_round_trips", "win_rate_pct"):
        print(f"{key}: {result[key]}")
    write_reports(result, args.json_out, args.trades_out)
    if args.json_out:
        print(f"json_report: {args.json_out}")
    if args.trades_out:
        print(f"trades_report: {args.trades_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
