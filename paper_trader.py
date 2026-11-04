"""Offline-only educational paper trading and backtesting.

No API keys, network access, broker connections, or live orders.
Signals are calculated from previously observed prices and executed at
the current observation's price (one-observation execution lag).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path
from typing import Iterable, Iterator, Sequence


def _finite_number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value


def prices_demo(n: int = 160, seed: int = 42) -> Iterator[tuple[str, float]]:
    """Yield deterministic synthetic prices for offline demonstrations."""
    if type(n) is not int or n < 1:
        raise ValueError("n must be a positive integer")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    rng = random.Random(seed)
    price = 100.0
    for i in range(n):
        price *= math.exp(rng.gauss(0.0002, 0.012))
        yield str(i + 1), price


def prices_csv(path: str | Path) -> Iterator[tuple[str, float]]:
    """Read a CSV containing a required close column and optional date column."""
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "close" not in reader.fieldnames:
            raise ValueError("CSV requires a close column (optional date column)")
        for row_number, row in enumerate(reader, start=2):
            raw = row.get("close")
            try:
                price = float(raw)
            except (TypeError, ValueError):
                raise ValueError(
                    f"Invalid close price on CSV row {row_number}: {raw!r}"
                ) from None
            if not math.isfinite(price) or price <= 0:
                raise ValueError(
                    f"Price on CSV row {row_number} must be finite and positive"
                )
            date = (row.get("date") or "").strip() or str(row_number - 1)
            yield date, price


def _validate_prices(prices: Iterable[tuple[str, float]]):
    for index, item in enumerate(prices, start=1):
        try:
            date, raw_price = item
        except (TypeError, ValueError):
            raise ValueError(
                f"Price observation {index} must be a (date, price) pair"
            ) from None
        if not isinstance(date, str) or not date.strip():
            raise ValueError(f"Date at observation {index} must be a non-empty string")
        price = _finite_number(raw_price, f"Price at observation {index}")
        if price <= 0:
            raise ValueError(f"Price at observation {index} must be positive")
        yield date.strip(), price


def _performance_metrics(equity_curve: Sequence[float], starting: float):
    returns = []
    for previous, current in zip(equity_curve, equity_curve[1:]):
        if previous > 0:
            returns.append(current / previous - 1.0)

    if len(returns) > 1:
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
        volatility = math.sqrt(variance)
        sharpe = (
            mean_return / volatility * math.sqrt(252)
            if volatility > 0 else 0.0
        )
    else:
        sharpe = 0.0

    peak = starting
    max_drawdown = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)

    return {
        "max_drawdown_pct": round(max_drawdown * 100, 4),
        "sharpe_ratio": round(sharpe, 4),
        "observations": len(equity_curve),
    }


def _benchmark(prices: Sequence[tuple[str, float]], capital: float, fee: float):
    """Buy-and-hold benchmark with entry and final liquidation fees."""
    first_price = prices[0][1]
    last_price = prices[-1][1]
    units = capital / (first_price * (1.0 + fee))
    ending = units * last_price * (1.0 - fee)
    return {
        "ending": round(ending, 2),
        "return_pct": round((ending / capital - 1.0) * 100, 4),
    }


def simulate(
    prices: Iterable[tuple[str, float]],
    capital: float = 200.0,
    fast: int = 5,
    slow: int = 20,
    fee: float = 0.001,
    max_allocation: float = 0.25,
    stop_loss_pct: float | None = None,
    force_liquidate: bool = False,
):
    """Run a long-only moving-average paper simulation.

    The moving-average regime is computed from observations before the
    current one. Orders execute at the current price. Allocation is capped
    as a fraction of portfolio equity; fees are charged on both sides.
    """
    capital = _finite_number(capital, "Starting capital")
    fee = _finite_number(fee, "Fee")
    max_allocation = _finite_number(max_allocation, "Maximum allocation")

    if type(fast) is not int or type(slow) is not int:
        raise ValueError("Moving-average periods must be integers")
    if fast < 1 or slow <= fast:
        raise ValueError("Periods must satisfy 1 <= fast < slow")
    if capital <= 0:
        raise ValueError("Starting capital must be positive")
    if not 0 <= fee < 1:
        raise ValueError("Fee must satisfy 0 <= fee < 1")
    if not 0 < max_allocation <= 1:
        raise ValueError("Maximum allocation must satisfy 0 < allocation <= 1")
    if stop_loss_pct is not None:
        stop_loss_pct = _finite_number(stop_loss_pct, "Stop-loss percentage")
        if not 0 < stop_loss_pct < 1:
            raise ValueError("Stop-loss percentage must satisfy 0 < stop_loss < 1")
    if type(force_liquidate) is not bool:
        raise ValueError("force_liquidate must be Boolean")

    observations = list(_validate_prices(prices))
    if not observations:
        raise ValueError("No prices supplied")

    cash = capital
    units = 0.0
    entry_price = None
    history: list[float] = []
    trades: list[dict] = []
    equity_curve: list[float] = []
    peak = capital
    max_drawdown = 0.0

    for date, price in observations:
        # Signals use only earlier observations; execution occurs at this price.
        if len(history) >= slow:
            fast_avg = sum(history[-fast:]) / fast
            slow_avg = sum(history[-slow:]) / slow
            bullish = fast_avg > slow_avg
            bearish = fast_avg < slow_avg

            stop_triggered = (
                units > 0
                and stop_loss_pct is not None
                and entry_price is not None
                and price <= entry_price * (1.0 - stop_loss_pct)
            )

            if units > 0 and (bearish or stop_triggered):
                gross = units * price
                fee_paid = gross * fee
                proceeds = gross - fee_paid
                trades.append({
                    "date": date, "side": "SELL", "price": round(price, 8),
                    "units": round(units, 10), "gross": round(gross, 8),
                    "fee": round(fee_paid, 8),
                    "reason": "STOP_LOSS" if stop_triggered else "SIGNAL",
                })
                cash += proceeds
                units = 0.0
                entry_price = None

            elif units == 0 and bullish:
                equity_before = cash
                target_value = equity_before * max_allocation
                affordable_units = cash / (price * (1.0 + fee))
                target_units = target_value / price
                buy_units = min(affordable_units, target_units)
                if buy_units > 0:
                    gross = buy_units * price
                    fee_paid = gross * fee
                    total_cost = gross + fee_paid
                    cash -= total_cost
                    units = buy_units
                    entry_price = price
                    trades.append({
                        "date": date, "side": "BUY", "price": round(price, 8),
                        "units": round(units, 10), "gross": round(gross, 8),
                        "fee": round(fee_paid, 8), "reason": "SIGNAL",
                    })

        equity = cash + units * price
        equity_curve.append(equity)
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
        history.append(price)

    if force_liquidate and units > 0:
        date, final_price = observations[-1]
        gross = units * final_price
        fee_paid = gross * fee
        cash += gross - fee_paid
        trades.append({
            "date": date, "side": "SELL", "price": round(final_price, 8),
            "units": round(units, 10), "gross": round(gross, 8),
            "fee": round(fee_paid, 8), "reason": "END_OF_SIMULATION",
        })
        units = 0.0
        entry_price = None
        equity_curve[-1] = cash
        peak = max(peak, cash)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - cash) / peak)

    ending = cash + units * observations[-1][1]
    metrics = _performance_metrics(equity_curve, capital)
    closed_trades = sum(1 for trade in trades if trade["side"] == "SELL")
    winning_trades = 0
    completed_returns = []
    buy_price = None
    for trade in trades:
        if trade["side"] == "BUY":
            buy_price = trade["price"]
        elif trade["side"] == "SELL" and buy_price is not None:
            trade_return = (
                trade["price"] * (1.0 - fee)
                / (buy_price * (1.0 + fee)) - 1.0
            )
            completed_returns.append(trade_return)
            if trade_return > 0:
                winning_trades += 1
            buy_price = None

    result = {
        "starting": round(capital, 2),
        "ending": round(ending, 2),
        "return_pct": round((ending / capital - 1.0) * 100, 4),
        "max_drawdown_pct": round(max_drawdown * 100, 4),
        "sharpe_ratio": metrics["sharpe_ratio"],
        "benchmark": _benchmark(observations, capital, fee),
        "benchmark_excess_return_pct": round(
            (ending / capital - 1.0) * 100
            - _benchmark(observations, capital, fee)["return_pct"], 4
        ),
        "open_units": round(units, 10),
        "cash": round(cash, 8),
        "trades": trades,
        "trade_count": len(trades),
        "closed_trades": closed_trades,
        "win_rate_pct": round(
            winning_trades / closed_trades * 100, 4
        ) if closed_trades else 0.0,
        "profit_factor": (
            round(
                sum(r for r in completed_returns if r > 0)
                / abs(sum(r for r in completed_returns if r < 0)), 4
            ) if any(r < 0 for r in completed_returns)
            else (None if not any(r > 0 for r in completed_returns) else "inf")
        ),
        "observations": len(observations),
        "equity_curve": [round(value, 8) for value in equity_curve],
        "configuration": {
            "fast": fast, "slow": slow, "fee": fee,
            "max_allocation": max_allocation,
            "stop_loss_pct": stop_loss_pct,
            "force_liquidate": force_liquidate,
        },
    }
    return result


def write_trade_csv(path: str | Path, trades: Sequence[dict]) -> None:
    fields = ["date", "side", "price", "units", "gross", "fee", "reason"]
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(trades)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline-only educational paper trading; no live orders."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true",
                        help="Use deterministic synthetic prices")
    source.add_argument("--csv", type=Path, help="CSV with date,close columns")
    parser.add_argument("--capital", type=float, default=200.0)
    parser.add_argument("--fast", type=int, default=5)
    parser.add_argument("--slow", type=int, default=20)
    parser.add_argument("--fee", type=float, default=0.001)
    parser.add_argument("--max-allocation", type=float, default=0.25)
    parser.add_argument("--stop-loss", type=float, default=None,
                        help="Optional stop-loss fraction, e.g. 0.08 for 8%%")
    parser.add_argument("--force-liquidate", action="store_true",
                        help="Close any open position at the final price")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--trades-out", type=Path, default=None)
    args = parser.parse_args(argv)

    prices = prices_demo() if args.demo else prices_csv(args.csv)
    result = simulate(
        prices, capital=args.capital, fast=args.fast, slow=args.slow,
        fee=args.fee, max_allocation=args.max_allocation,
        stop_loss_pct=args.stop_loss, force_liquidate=args.force_liquidate,
    )
    print("PAPER ONLY — NO LIVE ORDERS — NO NETWORK OR BROKER CONNECTIONS")
    for key in (
        "starting", "ending", "return_pct", "max_drawdown_pct",
        "sharpe_ratio", "open_units", "cash", "trade_count",
        "closed_trades", "win_rate_pct",
    ):
        print(f"{key}: {result[key]}")
    print(f"buy_hold_ending: {result['benchmark']['ending']}")
    print(f"buy_hold_return_pct: {result['benchmark']['return_pct']}")
    print(f"benchmark_excess_return_pct: {result['benchmark_excess_return_pct']}")

    if args.json_out:
        args.json_out.write_text(
            json.dumps(result, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    if args.trades_out:
        write_trade_csv(args.trades_out, result["trades"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
