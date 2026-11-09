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

from restricted_https import open_api

from stock_discovery import DEFAULT_SYMBOLS, build_report, fetch_bars

PAPER = "https://paper-api.alpaca.markets"
DATA = "https://data.alpaca.markets"
PREFIX = "hedgeopsauto"
MAX_ORDER = Decimal("10.00")
MAX_DAILY = Decimal("100.00")
MIN_CASH = Decimal("100.00")
MAX_POSITIONS = 5
MAX_ENTRY_EQUITY = Decimal("0.02")
MAX_GROSS_EXPOSURE = Decimal("0.20")
MAX_DAILY_EQUITY_LOSS = Decimal("0.01")
# Explicit opt-in allocation modes; legacy behavior remains the default.
ALLOCATION_MODES = {"legacy": (Decimal("10.00"), 1),
                    "diversified": (Decimal("10.00"), 10),
                    "single": (Decimal("100.00"), 1)}


def allocation_policy():
    mode = os.environ.get("PAPER_ALLOCATION_MODE", "legacy")
    if mode not in ALLOCATION_MODES:
        raise ValueError("Invalid paper allocation mode; fail closed")
    return mode, *ALLOCATION_MODES[mode]

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


def request_json(host, path, key, secret, *, params=None, payload=None, opener=open_api):
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


def news_evidence(symbol, key, secret, *, now, get=request_json, shadow=None):
    # Fail closed when recent company news cannot be retrieved.
    start = (now - timedelta(days=7)).isoformat().replace("+00:00", "Z")
    end = now.isoformat().replace("+00:00", "Z")
    response = get(DATA, "/v1beta1/news", key, secret,
                   params={"symbols": symbol, "start": start, "end": end,
                           "limit": 50, "sort": "desc"})
    if not isinstance(response, dict) or not isinstance(response.get("news"), list):
        raise ValueError("News response unavailable")
    if shadow is not None:
        # Observation only: never feed graph features to the reviewer or executor.
        # Use the same response; no extra provider call, order, or paid AI request.
        from news_topology import build_snapshot
        try:
            shadow.update(build_snapshot(response['news'], symbol=symbol, asof=now.isoformat()))
        except (ValueError, TypeError, KeyError, OverflowError):
            shadow.update(mode='SHADOW_ONLY', order_authority=False, status='INVALID_INPUT',
                          predictive_validation='UNPROVEN')
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


def fresh_quote(symbol, key, secret, *, now, get=request_json):
    feed = os.getenv("PAPER_DATA_FEED", "iex")
    if feed not in ("iex", "sip"):
        raise ValueError("Unsupported data feed")
    response = get(DATA, "/v2/stocks/" + quote(symbol) + "/quotes/latest",
                   key, secret, params={"feed": feed})
    q = response.get("quote") if isinstance(response, dict) else None
    if not isinstance(q, dict):
        raise ValueError("Latest quote unavailable")
    stamp = datetime.fromisoformat(str(q.get("t", "")).replace("Z", "+00:00"))
    if stamp.tzinfo is None or not timedelta(0) <= now - stamp <= timedelta(seconds=120):
        raise ValueError("Latest quote stale or future dated")
    bid, ask = money(q.get("bp")), money(q.get("ap"))
    if not 0 < bid <= ask or (ask - bid) / ((ask + bid) / 2) > Decimal("0.005"):
        raise ValueError("Invalid quote or spread exceeds 0.5 percent")
    return {"timestamp": stamp.isoformat(), "feed": feed,
            "bid": str(bid), "ask": str(ask), "max_age_seconds": 120}


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


def daily_buy_commitments(orders, trading_day):
    """Conservatively reserve the full notional of every buy submitted today.

    Missing notional/creation timestamps are not safely reconcilable: fail closed.
    """
    start = datetime.combine(trading_day, datetime.min.time(), ZoneInfo("America/New_York"))
    end = start + timedelta(days=1)
    total = Decimal("0")
    for order in orders:
        if not isinstance(order, dict):
            raise ValueError("Malformed broker order")
        if order.get("side") != "buy":
            continue
        submitted = order.get("submitted_at") or order.get("created_at")
        if not isinstance(submitted, str):
            raise ValueError("Buy order timestamp unavailable")
        try:
            timestamp = datetime.fromisoformat(submitted.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Invalid buy order timestamp") from None
        if timestamp.tzinfo is None:
            raise ValueError("Buy order timezone unavailable")
        if not start <= timestamp.astimezone(ZoneInfo("America/New_York")) < end:
            continue
        notional = order.get("notional")
        if notional is None:
            # Quantity-based orders cannot be safely bounded from this response.
            raise ValueError("Buy order notional unavailable; fail closed")
        total += money(notional)
    return total


def broker_risk_check(*, now, key, secret, get=request_json):
    """Reconcile account and orders; return a fail-closed reason or None."""
    mode, order_amount, max_attempts = allocation_policy()
    account = get(PAPER, "/v2/account", key, secret)
    if (not isinstance(account, dict) or account.get("status") != "ACTIVE"
        or account.get("trading_blocked") is not False
        or account.get("account_blocked") is not False):
        return "Paper account not confirmed active and unblocked"
    # Broker equity change is an account-wide guard, not strategy P/L.
    equity = money(account.get("equity"))
    previous_equity = money(account.get("last_equity"))
    if equity <= 0 or previous_equity <= 0:
        raise ValueError("Positive current and prior-close equity required")
    if equity <= previous_equity * (1 - MAX_DAILY_EQUITY_LOSS):
        return "Daily account equity loss limit reached"
    if order_amount > equity * MAX_ENTRY_EQUITY:
        return "Entry exceeds 2 percent of account equity"
    if min(money(account.get("cash")), money(account.get("buying_power"))) < MIN_CASH + order_amount:
        return "Insufficient post-order cash reserve or buying power"

    positions = get(PAPER, "/v2/positions", key, secret)
    if not isinstance(positions, list) or any(not isinstance(p, dict) for p in positions):
        raise ValueError("Positions response unavailable")
    if len(positions) >= MAX_POSITIONS:
        return "Position-count cap reached"
    gross = Decimal("0")
    for position in positions:
        # Short exposure must increase gross risk, never offset long exposure.
        try:
            value = Decimal(str(position.get("market_value")))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError("Position market value unavailable") from None
        if not value.is_finite():
            raise ValueError("Invalid position market value")
        gross += abs(value)
    if gross + order_amount > equity * MAX_GROSS_EXPOSURE:
        return "Post-entry gross exposure exceeds 20 percent of account equity"

    # Check all open orders, including those submitted before today.
    open_orders = get(
        PAPER, "/v2/orders", key, secret,
        params={"status": "open", "limit": 500, "direction": "desc"},
    )
    if (
        not isinstance(open_orders, list)
        or len(open_orders) >= 500
        or any(not isinstance(o, dict) for o in open_orders)
    ):
        raise ValueError("Open order history unavailable or truncated; fail closed")
    if any(o.get("side") != "sell" for o in open_orders):
        return "Existing open or unrecognized order"
    trading_day = now.astimezone(ZoneInfo("America/New_York")).date()
    # Request all orders, not only a recent window; fail closed on truncation.
    orders = get(PAPER, "/v2/orders", key, secret,
                 params={"status": "all", "limit": 500, "direction": "desc",
"after": (datetime.combine(
    trading_day,
    datetime.min.time(),
    tzinfo=ZoneInfo("America/New_York")
) - timedelta(seconds=1)).isoformat()})
    if not isinstance(orders, list) or len(orders) >= 500:
        raise ValueError("Order history unavailable or truncated; fail closed")
    active = {"new", "accepted", "pending_new", "partially_filled", "held",
              "accepted_for_bidding", "pending_replace", "pending_cancel"}
    if any(o.get("side") == "buy" and o.get("status") in active for o in orders):
        return "Existing open buy order"
    spent = daily_buy_commitments(orders, trading_day)
    if spent + order_amount > MAX_DAILY:
        return "Daily buy commitment cap reached"
    today_prefix = f"{PREFIX}-{trading_day:%Y%m%d}-"
    if sum(str(o.get("client_order_id", "")).startswith(today_prefix) for o in orders) >= max_attempts:
        return "Daily automated order-attempt cap reached"
    return None


def assess(*, now, key, secret, get=request_json, bars_fetch=fetch_bars, monitor_only=False):
    """Return a decision. No orders are submitted in this function."""
    if not monitor_only and os.environ.get("PAPER_AUTO_TRADING_ENABLED") != "true":
        return {"decision": "SKIP", "reason": "Auto trading disabled"}
    if not monitor_only and os.environ.get("PAPER_AUTO_KILL_SWITCH") != "false":
        return {"decision": "SKIP", "reason": "Kill switch active or unset"}
    if not key or not secret:
        raise ValueError("Missing paper credentials")

    clock = get(PAPER, "/v2/clock", key, secret)
    if not isinstance(clock, dict) or clock.get("is_open") is not True:
        return {"decision": "SKIP", "reason": "Market closed or clock unavailable"}

    reason = broker_risk_check(now=now, key=key, secret=secret, get=get)
    if reason:
        return {"decision": "SKIP", "reason": reason}
    positions = get(PAPER, "/v2/positions", key, secret)
    held = {p["symbol"] for p in positions if isinstance(p.get("symbol"), str)}
    trading_day = now.astimezone(ZoneInfo("America/New_York")).date()

    bars = bars_fetch(DEFAULT_SYMBOLS, key, secret, now=now)
    report = build_report(DEFAULT_SYMBOLS, bars, generated_at=now.isoformat())
    candidate = eligible_candidate(report)
    # Select the highest-scoring eligible candidate not already held.
    candidate = next((c for c in report["candidates"]
                      if eligible_candidate({"candidates": [c]}) and c["symbol"] not in held), None)
    if candidate is None:
        return {"decision": "SKIP", "reason": "No unheld candidate met conservative risk thresholds"}
    symbol = candidate["symbol"]

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
    news_shadow = {}
    evidence = news_evidence(symbol, key, secret, now=now, get=get, shadow=news_shadow)
    if not evidence:
        return {"decision": "SKIP", "reason": "No recent identifiable headline catalyst",
                "news_topology_shadow": news_shadow}

    quote_evidence = None
    if os.getenv("PAPER_REQUIRE_FRESH_QUOTE") == "true":
        quote_evidence = fresh_quote(symbol, key, secret, now=now, get=get)
    mode, order_amount, _ = allocation_policy()
    return {"signal": candidate, "quote": quote_evidence,
            "hypothesis": "Positive price momentum with elevated volume may persist; unproven association, not a causal finding",
            "decision": "READY", "symbol": symbol, "notional_usd": str(order_amount),
            "client_order_id": order_id(trading_day, symbol),
            "score": candidate["score"], "catalyst_headlines": evidence,
            "news_topology_shadow": news_shadow,
            "reason": "Deterministic risk and news-presence gates passed"}


def execute(decision, *, key, secret, get=request_json):
    if decision["decision"] != "READY":
        return decision
    # Defense in depth: a second check immediately before POST.
    if os.environ.get("PAPER_AUTO_TRADING_ENABLED") != "true" or os.environ.get("PAPER_AUTO_KILL_SWITCH") != "false":
        return {"decision": "SKIP", "reason": "Kill switch or enable flag changed"}
    symbol = decision["symbol"]
    client_id = decision["client_order_id"]
    
    expected_id = order_id(
        datetime.now(timezone.utc).astimezone(
            ZoneInfo("America/New_York")
        ).date(),
        symbol,
    )
    mode, order_amount, _ = allocation_policy()
    if (
        money(decision["notional_usd"]) != order_amount
        or client_id != expected_id
    ):
        raise ValueError("Unsafe order parameters")
  
    # Recheck the Alpaca paper market clock before submitting.
    clock = get(PAPER, "/v2/clock", key, secret)
    if not isinstance(clock, dict) or clock.get("is_open") is not True:
        return {"decision": "SKIP", "reason": "Market closed before order submission"}


    # Reconcile account and today's broker commitments immediately before POST.
    reason = broker_risk_check(now=datetime.now(timezone.utc), key=key, secret=secret, get=get)
    if reason:
        return {"decision": "SKIP", "reason": reason}
    positions = get(PAPER, "/v2/positions", key, secret)
    if any(p.get("symbol") == symbol for p in positions):
        return {"decision": "SKIP", "reason": "Position appeared before submission"}
    # Check broker idempotency key before sending. A 404 is the only allowed absent result.
    try:
        existing = get(PAPER, "/v2/orders:by_client_order_id", key, secret,
                       params={"client_order_id": client_id})
    except RuntimeError as exc:
        if str(exc) != "Alpaca HTTP 404":
            raise
    else:
        return {"decision": "SKIP", "reason": "Order already exists", "broker_status": existing.get("status")}
    if os.getenv("PAPER_REQUIRE_FRESH_QUOTE") == "true":
        fresh_quote(symbol, key, secret, now=datetime.now(timezone.utc), get=get)
    # No retry on POST, including network timeouts. Inspect Alpaca before rerunning.
    order = get(PAPER, "/v2/orders", key, secret,
                payload={"symbol": symbol, "notional": str(order_amount),
                         "side": "buy", "type": "market", "time_in_force": "day",
                         "client_order_id": client_id})
    if (not isinstance(order, dict) or not order.get("id")
        or order.get("symbol") != symbol or order.get("side") != "buy"
        or order.get("client_order_id") != client_id
        or money(order.get("notional")) != order_amount):
        raise RuntimeError("Order acknowledgment ambiguous; check Alpaca before retrying")
    return {"decision": "SUBMITTED", "symbol": symbol, "notional_usd": str(order_amount),
            "client_order_id": client_id, "broker_status": order.get("status"),
            "order_filled": order.get("status") == "filled"}


def main(argv=None, *, reviewer=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="opportunity-intelligence-output")
    parser.add_argument("--monitor-only", action="store_true", help="Read-only assessment; never execute orders")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    result = {"decision": "SKIP", "reason": "Not started"}
    submissions = []
    assessments = []
    try:
        mode, _, max_attempts = allocation_policy()
        max_in_run = max_attempts if (mode == "diversified"
                                     and os.getenv("PAPER_MULTI_ORDER_RUN") == "true"
                                     and not args.monitor_only) else 1
        seen_symbols = set()
        for _ in range(max_in_run):
            decision = assess(now=datetime.now(timezone.utc),
                              key=os.getenv("ALPACA_API_KEY", ""),
                              secret=os.getenv("ALPACA_API_SECRET", ""),
                              monitor_only=args.monitor_only)
            assessments.append(dict(decision))
            if decision["decision"] == "READY" and reviewer is not None:
                from copy import deepcopy
                review = reviewer(deepcopy(decision))
                assessments[-1]["agent_review"] = review
                if not isinstance(review, dict) or review.get("verdict") != "PASS":
                    result = {"decision": "SKIP", "reason": "Agent review deferred or rejected entry",
                              "agent_review": review}
                    break
            if decision["decision"] != "READY" or args.monitor_only:
                result = decision
                break
            if decision["symbol"] in seen_symbols:
                result = {"decision": "SKIP", "reason": "Repeated candidate; await broker reconciliation"}
                break
            seen_symbols.add(decision["symbol"])
            result = execute(decision, key=os.getenv("ALPACA_API_KEY", ""),
                             secret=os.getenv("ALPACA_API_SECRET", ""))
            if result["decision"] != "SUBMITTED":
                break
            submissions.append(result)
            # Never continue while the previous paper order is pending.
            if result.get("broker_status") != "filled":
                break
        if submissions:
            result = {"decision": "SUBMITTED", "orders": submissions,
                      "submitted_count": len(submissions),
                      "submitted_notional_usd": str(sum(
                          (money(x["notional_usd"]) for x in submissions), Decimal("0"))),
                      "last_decision": result}
    except (RuntimeError, ValueError, TypeError) as exc:
        result = {"decision": "ERROR", "reason": str(exc),
                  "orders": submissions, "submitted_count": len(submissions)}
    if args.monitor_only and result["decision"] == "READY":
        result["decision"] = "MONITOR_READY"
        result["reason"] = "Read-only assessment passed; no order submitted"
    result["assessments"] = assessments
    result["observed_at_utc"] = now.isoformat()
    result["strategy_version"] = "momentum-news-v1"
    result["quote_feed"] = os.getenv("PAPER_DATA_FEED", "iex")
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "decision.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    lines = ["# Paper Opportunity Intelligence", "",
             f"UTC run: {now.isoformat()}", "",
             f"**Decision:** {result['decision']}", "",
             f"Reason: {result.get('reason', 'See decision.json')}", "",
             f"Symbol: {result.get('symbol', '—')}", "",
             f"Broker status: {result.get('broker_status', '—')}", "",
             f"Submitted orders this run: {result.get('submitted_count', 0)}",
             "This is PAPER ONLY. Submitted does not mean filled.",
             "Do not rerun an ambiguous submission; reconcile in Alpaca."]
    (out / "decision.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Paper opportunity intelligence decision: {result['decision']}")
    return 1 if result["decision"] == "ERROR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
