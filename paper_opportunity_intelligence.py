"""Conservative, opt-in, fully automatic PAPER-only Alpaca opportunity trader.

No live-trading host, no configurable broker URL, no order retries.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from stock_discovery import DEFAULT_SYMBOLS, build_report, fetch_bars

PAPER = "https://paper-api.alpaca.markets"
DATA = "https://data.alpaca.markets"
PREFIX = "hedgeopsauto"
MAX_ORDER = Decimal("10.00")
MAX_DAILY = Decimal("10.00")
MIN_CASH = Decimal("100.00")
MAX_POSITIONS = 5
CATALYST_WORDS = ("earnings", "guidance", "revenue", "results", "contract",
                  "partnership", "launch", "approval", "upgrade", "outlook")


def money(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Invalid broker monetary amount") from None
    if not result.is_finite() or result < 0:
        raise ValueError("Invalid broker monetary amount")
    return result


def request_json(host, path, key, secret, *, params=None, payload=None, opener=urlopen):
    if host not in (PAPER, DATA) or not path.startswith("/") or "//" in path:
        raise ValueError("Disallowed broker endpoint")
    url = host + path + (("?" + urlencode(params)) if params else "")
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(url, data=data, method="POST" if data is not None else "GET",
                  headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
                           "Accept": "application/json", "Content-Type": "application/json"})
    try:
        with opener(req, timeout=20) as response:
            return json.load(response)
    except HTTPError as exc:
        # Do not echo response bodies or headers, which can contain account information.
        raise RuntimeError(f"Alpaca HTTP {exc.code}") from None
    except (URLError, TimeoutError):
        raise RuntimeError("Alpaca request failed; reconcile broker orders before retrying") from None


def order_id(day, symbol):
    if not re.fullmatch(r"[A-Z]{1,5}", symbol):
        raise ValueError("Invalid symbol")
    return f"{PREFIX}-{day:%Y%m%d}-{symbol.lower()}"


def news_evidence(symbol, key, secret, *, now, get=request_json):
    # Fail closed when recent company news cannot be retrieved.
    start = (now - timedelta(days=7)).isoformat().replace("+00:00", "Z")
    end = now.isoformat().replace("+00:00", "Z")
    response = get(DATA, "/v1beta1/news", key, secret,
                   params={"symbols": symbol, "start": start, "end": end,
                           "limit": 50, "sort": "desc"})
    if not isinstance(response, dict) or not isinstance(response.get("news"), list):
        raise ValueError("News response unavailable")
    found = []
    for item in response["news"]:
        if not isinstance(item, dict):
            continue
        headline = item.get("headline")
        symbols = item.get("symbols")
        if not isinstance(headline, str) or not isinstance(symbols, list) or symbol not in symbols:
            continue
        if any(word in headline.lower() for word in CATALYST_WORDS):
            found.append({"headline": headline[:180], "created_at": str(item.get("created_at", ""))[:25]})
    return found[:3]


def eligible_candidate(report):
    # Heuristics are a conservative filter, not an AI trading recommendation.
    for c in report["candidates"]:
        if (c["score"] >= 60
            and 0 < c["return_5d_pct"] <= 12
            and 0 < c["return_20d_pct"] <= 25
            and 1.2 <= c["relative_volume_1d"] <= 4
            and c["daily_volatility_20d_pct"] <= 3
            and c["max_drawdown_30d_pct"] <= 12
            and c["above_ma20"] is True):
            return c
    return None


def assess(*, now, key, secret, get=request_json, bars_fetch=fetch_bars):
    """Return a decision. No orders are submitted in this function."""
    if os.environ.get("PAPER_AUTO_TRADING_ENABLED") != "true":
        return {"decision": "SKIP", "reason": "Auto trading disabled"}
    if os.environ.get("PAPER_AUTO_KILL_SWITCH") != "false":
        return {"decision": "SKIP", "reason": "Kill switch active or unset"}
    if not key or not secret:
        raise ValueError("Missing paper credentials")

    clock = get(PAPER, "/v2/clock", key, secret)
    if not isinstance(clock, dict) or clock.get("is_open") is not True:
        return {"decision": "SKIP", "reason": "Market closed or clock unavailable"}

    account = get(PAPER, "/v2/account", key, secret)
    if (not isinstance(account, dict) or account.get("status") != "ACTIVE"
        or account.get("trading_blocked") is not False
        or account.get("account_blocked") is not False):
        return {"decision": "SKIP", "reason": "Paper account not confirmed active and unblocked"}
    if min(money(account.get("cash")), money(account.get("buying_power"))) < MIN_CASH:
        return {"decision": "SKIP", "reason": "Insufficient cash reserve or buying power"}

    positions = get(PAPER, "/v2/positions", key, secret)
    if not isinstance(positions, list):
        raise ValueError("Positions response unavailable")
    if len(positions) >= MAX_POSITIONS:
        return {"decision": "SKIP", "reason": "Position-count cap reached"}
    held = {p.get("symbol") for p in positions if isinstance(p, dict)}

    trading_day = now.astimezone(ZoneInfo("America/New_York")).date()
    after = trading_day.isoformat() + "T00:00:00-05:00"
    # Look back 2 days to include open orders from previous sessions.
    after = (trading_day - timedelta(days=2)).isoformat() + "T00:00:00Z"
    orders = get(PAPER, "/v2/orders", key, secret,
                 params={"status": "all", "after": after, "limit": 500, "direction": "desc"})
    if not isinstance(orders, list) or len(orders) >= 500:
        raise ValueError("Order history unavailable or truncated; fail closed")
    active_status = {"new", "accepted", "pending_new", "partially_filled",
                     "held", "accepted_for_bidding", "pending_replace", "pending_cancel"}
    open_symbols = {o.get("symbol") for o in orders if isinstance(o, dict)
                    and o.get("status") in active_status}
    if any(o.get("side") == "buy" and o.get("status") in active_status
           for o in orders if isinstance(o, dict)):
        return {"decision": "SKIP", "reason": "Existing open buy order"}
    today_prefix = f"{PREFIX}-{trading_day:%Y%m%d}-"
    automated_today = [o for o in orders if isinstance(o, dict)
                       and str(o.get("client_order_id", "")).startswith(today_prefix)]
    # Count attempted orders, including cancelled/rejected, to prevent repeated attempts.
    if automated_today:
        return {"decision": "SKIP", "reason": "Daily automated order-attempt cap reached"}

    bars = bars_fetch(DEFAULT_SYMBOLS, key, secret, now=now)
    report = build_report(DEFAULT_SYMBOLS, bars, generated_at=now.isoformat())
    candidate = eligible_candidate(report)
    if candidate is None:
        return {"decision": "SKIP", "reason": "No candidate met conservative risk thresholds"}
    symbol = candidate["symbol"]
    if symbol in held or symbol in open_symbols:
        return {"decision": "SKIP", "reason": "Candidate already held or has open order"}

    try:
        last_bar = datetime.fromisoformat(candidate["last_bar_utc"].replace("Z", "+00:00"))
        if last_bar.tzinfo is None:
            raise ValueError("No timezone")
    except (ValueError, TypeError):
        return {"decision": "SKIP", "reason": "Cannot verify data freshness"}
    if not timedelta(0) <= now - last_bar.astimezone(timezone.utc) <= timedelta(days=5):
        return {"decision": "SKIP", "reason": "Market data stale"}

    asset = get(PAPER, "/v2/assets/" + quote(symbol), key, secret)
    if (not isinstance(asset, dict) or asset.get("status") != "active"
        or asset.get("tradable") is not True or asset.get("fractionable") is not True):
        return {"decision": "SKIP", "reason": "Asset not confirmed fractionable and tradable"}
    evidence = news_evidence(symbol, key, secret, now=now, get=get)
    if not evidence:
        return {"decision": "SKIP", "reason": "No recent identifiable headline catalyst"}

    return {"decision": "READY", "symbol": symbol, "notional_usd": str(MAX_ORDER),
            "client_order_id": order_id(trading_day, symbol),
            "score": candidate["score"], "catalyst_headlines": evidence,
            "reason": "Deterministic risk and news-presence gates passed"}


def execute(decision, *, key, secret, get=request_json):
    if decision["decision"] != "READY":
        return decision
    # Defense in depth: a second check immediately before POST.
    if os.environ.get("PAPER_AUTO_TRADING_ENABLED") != "true" or os.environ.get("PAPER_AUTO_KILL_SWITCH") != "false":
        return {"decision": "SKIP", "reason": "Kill switch or enable flag changed"}
    symbol = decision["symbol"]
    client_id = decision["client_order_id"]
    if money(decision["notional_usd"]) != MAX_ORDER or not client_id.startswith(PREFIX + "-"):
        raise ValueError("Unsafe order parameters")
    # Check broker idempotency key before sending. A 404 is the only allowed absent result.
    try:
        existing = get(PAPER, "/v2/orders:by_client_order_id", key, secret,
                       params={"client_order_id": client_id})
    except RuntimeError as exc:
        if str(exc) != "Alpaca HTTP 404":
            raise
    else:
        return {"decision": "SKIP", "reason": "Order already exists", "broker_status": existing.get("status")}
    # No retry on POST, including network timeouts. Inspect Alpaca before rerunning.
    order = get(PAPER, "/v2/orders", key, secret,
                payload={"symbol": symbol, "notional": str(MAX_ORDER),
                         "side": "buy", "type": "market", "time_in_force": "day",
                         "client_order_id": client_id})
    if not isinstance(order, dict) or not order.get("id"):
        raise RuntimeError("Order acknowledgment ambiguous; check Alpaca before retrying")
    return {"decision": "SUBMITTED", "symbol": symbol, "notional_usd": str(MAX_ORDER),
            "client_order_id": client_id, "broker_status": order.get("status"),
            "order_filled": order.get("status") == "filled"}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="opportunity-intelligence-output")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    result = {"decision": "SKIP", "reason": "Not started"}
    try:
        result = assess(now=now, key=os.getenv("ALPACA_API_KEY", ""),
                        secret=os.getenv("ALPACA_API_SECRET", ""))
        if result["decision"] == "READY":
            result = execute(result, key=os.getenv("ALPACA_API_KEY", ""),
                             secret=os.getenv("ALPACA_API_SECRET", ""))
    except (RuntimeError, ValueError, TypeError) as exc:
        result = {"decision": "ERROR", "reason": str(exc)}
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "decision.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    lines = ["# Paper Opportunity Intelligence", "",
             f"UTC run: {now.isoformat()}", "",
             f"**Decision:** {result['decision']}", "",
             f"Reason: {result.get('reason', 'See decision.json')}", "",
             f"Symbol: {result.get('symbol', '—')}", "",
             f"Broker status: {result.get('broker_status', '—')}", "",
             "This is PAPER ONLY. Submitted does not mean filled.",
             "Do not rerun an ambiguous submission; reconcile in Alpaca."]
    (out / "decision.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Paper opportunity intelligence decision: {result['decision']}")
    return 1 if result["decision"] == "ERROR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
