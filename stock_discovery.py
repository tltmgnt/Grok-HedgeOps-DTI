"""Read-only Alpaca IEX daily-bar discovery scanner. No order endpoints."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from restricted_https import open_api

# Explicit, auditable universe; not a scan of the entire U.S. market.
DEFAULT_SYMBOLS = (
    "AAPL", "AMD", "AMZN", "AVGO", "COST", "CRM", "GOOGL", "HD",
    "IWM", "JPM", "META", "MSFT", "MU", "NFLX", "NVDA", "QQQ",
    "SMH", "SPY", "TSLA", "V",
)
BASE_URL = "https://data.alpaca.markets/v2/stocks/bars"


def fetch_bars(symbols, key, secret, *, now=None, opener=open_api):
    """GET historical daily IEX bars, excluding the current UTC calendar day."""
    now = now or datetime.now(timezone.utc)
    if not key or not secret:
        raise ValueError("Missing Alpaca paper market-data credentials")
    end = now.date()
    start = end - timedelta(days=120)
    params = {
        "symbols": ",".join(symbols), "timeframe": "1Day",
        "start": start.isoformat(), "end": end.isoformat(),
        "adjustment": "raw", "feed": "iex", "limit": 10000,
        "sort": "asc",
    }
    output = {symbol: [] for symbol in symbols}
    seen_tokens = set()
    while True:
        request = Request(
            BASE_URL + "?" + urlencode(params),
            headers={
                "APCA-API-KEY-ID": key,
                "APCA-API-SECRET-KEY": secret,
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with opener(request, timeout=30) as response:
                payload = json.load(response)
        except HTTPError as exc:
            if exc.code == 401:
                raise RuntimeError(
                    "Alpaca market data HTTP 401: credentials rejected. "
                    "Verify or rotate matching ALPACA_API_KEY and "
                    "ALPACA_API_SECRET repository Actions secrets. "
                    "Do not share keys or retry unchanged credentials."
                ) from None
            raise RuntimeError(f"Alpaca market data HTTP {exc.code}") from None
        except (URLError, TimeoutError) as exc:
            raise RuntimeError("Alpaca market data connection failed") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("bars"), dict):
            raise RuntimeError("Unexpected Alpaca market data response")
        for symbol, bars in payload["bars"].items():
            if symbol in output and isinstance(bars, list):
                output[symbol].extend(bars)
        token = payload.get("next_page_token")
        if not token:
            break
        if not isinstance(token, str) or token in seen_tokens:
            raise RuntimeError("Invalid or repeated pagination token")
        seen_tokens.add(token)
        params["page_token"] = token
    return output


def evaluate(symbol, bars):
    """Score observations; insufficient or malformed history is never ranked."""
    by_time = {}
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        try:
            timestamp = str(bar["t"])
            close = float(bar["c"])
            volume = float(bar["v"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if not timestamp or not math.isfinite(close) or close <= 0:
            continue
        if not math.isfinite(volume) or volume < 0:
            continue
        by_time[timestamp] = (close, volume)
    ordered = sorted(by_time.items())
    if len(ordered) < 31:
        return None
    recent = ordered[-31:]
    prices = [row[1][0] for row in recent]
    volumes = [row[1][1] for row in recent]
    if sum(volumes[-21:-1]) <= 0:
        return None
    r5 = prices[-1] / prices[-6] - 1
    r20 = prices[-1] / prices[-21] - 1
    volume_ratio = volumes[-1] / (sum(volumes[-21:-1]) / 20)
    ma20 = sum(prices[-20:]) / 20
    above_ma = prices[-1] > ma20
    daily = [b / a - 1 for a, b in zip(prices[-21:-1], prices[-20:])]
    mean = sum(daily) / len(daily)
    volatility = math.sqrt(sum((x - mean) ** 2 for x in daily) / len(daily))
    peak = prices[0]
    max_drawdown = 0.0
    for price in prices:
        peak = max(peak, price)
        max_drawdown = max(max_drawdown, 1 - price / peak)
    # Transparent heuristic; score is NOT a probability or return forecast.
    score = round(
        40 * max(-1, min(1, r20 / 0.20))
        + 25 * max(-1, min(1, r5 / 0.08))
        + 20 * max(0, min(1, (volume_ratio - 1) / 2))
        + (15 if above_ma else 0)
        - 15 * min(1, volatility / 0.06),
        2,
    )
    return {
        "symbol": symbol, "last_bar_utc": ordered[-1][0],
        "close": round(prices[-1], 4),
        "return_5d_pct": round(100 * r5, 2),
        "return_20d_pct": round(100 * r20, 2),
        "relative_volume_1d": round(volume_ratio, 2),
        "above_ma20": above_ma,
        "daily_volatility_20d_pct": round(100 * volatility, 2),
        "max_drawdown_30d_pct": round(100 * max_drawdown, 2),
        "score": score,
        "observations": len(ordered),
    }


def build_report(symbols, bars, *, generated_at):
    candidates = []
    skipped = []
    for symbol in symbols:
        result = evaluate(symbol, bars.get(symbol, []))
        if result is None:
            skipped.append(symbol)
        else:
            candidates.append(result)
    candidates.sort(key=lambda x: (-x["score"], x["symbol"]))
    return {
        "generated_at_utc": generated_at,
        "data_source": "Alpaca IEX feed, raw historical 1Day bars",
        "universe": list(symbols),
        "universe_size": len(symbols),
        "ranked_count": min(10, len(candidates)),
        "skipped_insufficient_data": skipped,
        "candidates": candidates[:10],
        "disclaimer": (
            "Read-only watchlist research, not financial advice or a return forecast. "
            "IEX volume is not consolidated market volume. Prices are unadjusted. "
            "No news, fundamentals, or catalyst verification is included."
        ),
    }


def markdown(report):
    lines = [
        "# Daily Stock Discovery — Read-only Watchlist",
        "",
        f"Generated (UTC): {report['generated_at_utc']}",
        "",
        f"Source: {report['data_source']}. Universe: {report['universe_size']} predefined symbols.",
        "",
        "| Rank | Symbol | Score | 5d % | 20d % | IEX rel. vol. | Above MA20 | 20d vol. % | 30d drawdown % | Last bar (UTC) |",
        "|---:|---|---:|---:|---:|---:|---|---:|---:|---|",
    ]
    for index, c in enumerate(report["candidates"], 1):
        lines.append(
            f"| {index} | {c['symbol']} | {c['score']} | {c['return_5d_pct']} "
            f"| {c['return_20d_pct']} | {c['relative_volume_1d']} "
            f"| {'Yes' if c['above_ma20'] else 'No'} "
            f"| {c['daily_volatility_20d_pct']} | {c['max_drawdown_30d_pct']} "
            f"| {c['last_bar_utc']} |"
        )
    if not report["candidates"]:
        lines.append("| — | No candidates with sufficient data | — | — | — | — | — | — | — | — |")
    lines.extend([
        "",
        "## Interpretation",
        "",
        "Scores are transparent relative heuristics, not probabilities of future gains.",
        "Relative volume compares the latest IEX daily bar with its previous 20 IEX daily bars.",
        "A high score can coincide with substantial downside risk. Check data freshness and independently verify catalysts.",
        "",
        "## Coverage",
        "",
        "Skipped for insufficient data: " + (", ".join(report["skipped_insufficient_data"]) or "None"),
        "",
        report["disclaimer"],
        "",
        "**No orders were submitted.**",
    ])
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="stock-discovery-output")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    symbols = DEFAULT_SYMBOLS
    try:
        bars = fetch_bars(
            symbols, os.getenv("ALPACA_API_KEY", ""),
            os.getenv("ALPACA_API_SECRET", ""), now=now,
        )
    except (ValueError, RuntimeError) as exc:
        parser.exit(1, f"Discovery failed: {exc}\n")
    report = build_report(symbols, bars, generated_at=now.isoformat())
    if not report["candidates"]:
        parser.exit(1, "Discovery failed: no candidates with sufficient daily bars\n")
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "watchlist.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (out / "watchlist.md").write_text(markdown(report), encoding="utf-8")
    print(f"Ranked {len(report['candidates'])} of {len(symbols)} symbols. Read-only; no orders submitted.")


if __name__ == "__main__":
    main()
