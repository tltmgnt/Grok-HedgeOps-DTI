"""Scheduled PAPER-only experiment. No live host, LLM orders, or POST retries."""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path

from paper_opportunity_intelligence import (
    PAPER, request_json, money, fresh_quote, main as entry_main,
)

STRATEGY = "momentum-news-v1"


def timestamp(value):
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Broker timestamp has no timezone")
    return stamp


def order_history(key, secret, *, get=request_json):
    """Retrieve complete broker history; never infer ownership from truncated data."""
    output, seen = [], set()
    params = {"status": "all", "limit": 500, "direction": "asc"}
    for _ in range(20):
        batch = get(PAPER, "/v2/orders", key, secret, params=dict(params))
        if not isinstance(batch, list) or any(not isinstance(o, dict) for o in batch):
            raise ValueError("Order history unavailable")
        added = 0
        for order in batch:
            identity = order.get("id")
            if not identity:
                raise ValueError("Order history missing identity")
            if identity not in seen:
                seen.add(identity)
                output.append(order)
                added += 1
        if batch and not added:
            raise ValueError("Order history pagination made no progress")
        if len(batch) < 500:
            return output
        # Overlap page boundaries to retain orders sharing a timestamp.
        params["after"] = (timestamp(batch[-1].get("submitted_at")) - timedelta(microseconds=1)).isoformat()
    raise ValueError("Order history exceeds reconciliation bound")


def exit_plan(position, orders, *, now):
    """Manage only an exact, unmixed lot from our deterministic entry IDs.

    Any manual transaction, partial fill, quantity mismatch, or missing history
    prevents an automatic sale. No inference based on the ticker alone.
    """
    symbol = position.get("symbol")
    if position.get("side") != "long" or not isinstance(symbol, str):
        return None
    qty = money(position.get("qty"))
    if qty <= 0 or money(position.get("qty_available")) != qty:
        return None
    related = [o for o in orders if o.get("symbol") == symbol]
    filled = [o for o in related if money(o.get("filled_qty", "0")) > 0]
    # Intentionally conservative: only a single fully filled buy for this symbol.
    # For a second lifecycle discard completed prior zero-net cycles below.
    net, cycle = Decimal("0"), []
    for order in sorted(filled, key=lambda o: timestamp(o.get("filled_at"))):
        if order.get("status") != "filled" or order.get("side") not in ("buy", "sell"):
            return None
        net += money(order["filled_qty"]) * (1 if order["side"] == "buy" else -1)
        cycle.append(order)
        if net == 0:
            cycle = []
        if net < 0:
            return None
    if net != qty or len(cycle) != 1:
        return None
    buy = cycle[0]
    opened = timestamp(buy.get("filled_at"))
    from paper_opportunity_intelligence import order_id
    from zoneinfo import ZoneInfo
    if buy.get("client_order_id") != order_id(
            timestamp(buy.get("submitted_at")).astimezone(ZoneInfo("America/New_York")).date(), symbol):
        return None
    if any(o.get("status") not in ("filled", "canceled", "expired", "rejected", "replaced")
           for o in related):
        return None
    cost = money(position.get("cost_basis"))
    value = money(position.get("market_value"))
    if cost <= 0 or opened > now:
        raise ValueError("Invalid strategy position")
    ret = value / cost - 1
    reason = ("LOSS_3_PERCENT" if ret <= Decimal("-0.03") else
              "PROFIT_6_PERCENT" if ret >= Decimal("0.06") else
              "HOLDING_5_CALENDAR_DAYS" if now - opened >= timedelta(days=5) else None)
    if reason is None:
        return None
    identity = hashlib.sha256(str(buy["id"]).encode()).hexdigest()[:24]
    return {"symbol": symbol, "qty": str(qty), "side": "sell", "type": "market",
            "time_in_force": "day", "client_order_id": f"ho-exit-{identity}",
            "reason": reason, "observed_return_pct": str(ret * 100)}


def enabled():
    return (os.getenv("PAPER_AUTO_TRADING_ENABLED") == "true"
            and os.getenv("PAPER_AUTO_KILL_SWITCH") == "false")


def manage_exits(key, secret, *, now, get=request_json, monitor_only=False, audit=None):
    orders = order_history(key, secret, get=get)
    positions = get(PAPER, "/v2/positions", key, secret)
    if not isinstance(positions, list) or any(not isinstance(p, dict) for p in positions):
        raise ValueError("Positions unavailable")
    results = []
    for position in positions:
        plan = exit_plan(position, orders, now=now)
        if not plan:
            continue
        record = {"plan": plan, "decision": "MONITOR_EXIT"}
        results.append(record)
        if monitor_only or not enabled():
            continue
        account = get(PAPER, "/v2/account", key, secret)
        if (account.get("status") != "ACTIVE" or account.get("trading_blocked") is not False
                or account.get("account_blocked") is not False):
            raise ValueError("Paper account blocked")
        clock = get(PAPER, "/v2/clock", key, secret)
        if clock.get("is_open") is not True:
            record["decision"] = "MARKET_CLOSED"
            break
        fresh_quote(plan["symbol"], key, secret, now=datetime.now(timezone.utc), get=get)
        # Reconcile immediately before selling; no POST retry on ambiguous responses.
        current_orders = order_history(key, secret, get=get)
        if any(o.get("client_order_id") == plan["client_order_id"] for o in current_orders):
            record["decision"] = "EXIT_ALREADY_EXISTS"
            continue
        current = get(PAPER, "/v2/positions", key, secret)
        p = next((p for p in current if p.get("symbol") == plan["symbol"]), {})
        rechecked = exit_plan(p, current_orders, now=datetime.now(timezone.utc))
        if not rechecked or any(rechecked[k] != plan[k] for k in ("symbol", "qty", "client_order_id")):
            record["decision"] = "POSITION_CHANGED"
            continue
        if not enabled():
            record["decision"] = "DISABLED"
            break
        payload = {k: v for k, v in plan.items() if k not in ("reason", "observed_return_pct")}
        if audit is not None:
            audit({"intent": payload, "observed_at_utc": datetime.now(timezone.utc).isoformat()})
        acknowledgment = get(PAPER, "/v2/orders", key, secret, payload=payload)
        if (not isinstance(acknowledgment, dict) or not acknowledgment.get("id")
                or any(acknowledgment.get(k) != payload[k]
                       for k in ("symbol", "side", "client_order_id"))
                or money(acknowledgment.get("qty")) != money(payload["qty"])):
            raise RuntimeError("Ambiguous paper exit; reconcile broker before retry")
        record.update(decision="EXIT_SUBMITTED", broker_status=acknowledgment.get("status"),
                      order_filled=acknowledgment.get("status") == "filled")
    return results


def performance(history):
    """Account-wide observations, never label these strategy returns."""
    equity = history.get("equity")
    times = history.get("timestamp")
    if not isinstance(equity, list) or not isinstance(times, list) or len(equity) != len(times):
        raise ValueError("Portfolio history malformed")
    points = [(t, money(e)) for t, e in zip(times, equity) if e is not None and money(e) > 0]
    if not points:
        return {"observations": 0, "status": "INSUFFICIENT_HISTORY"}
    peak, drawdown = points[0][1], Decimal("0")
    for _, value in points:
        peak = max(peak, value)
        drawdown = max(drawdown, 1 - value / peak)
    return {"observations": len(points), "first_timestamp": points[0][0],
            "last_timestamp": points[-1][0],
            "account_equity_change_pct": str(100 * (points[-1][1] / points[0][1] - 1)),
            "account_equity_drawdown_pct": str(100 * drawdown),
            "scope": "Entire paper account; cash flows and manual trades can distort these values; not strategy alpha"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="paper-session-output")
    parser.add_argument("--monitor-only", action="store_true")
    args = parser.parse_args(argv)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    key, secret = os.getenv("ALPACA_API_KEY", ""), os.getenv("ALPACA_API_SECRET", "")
    now = datetime.now(timezone.utc)
    report = {"mode": "PAPER_ONLY", "strategy_version": STRATEGY,
              "observed_at_utc": now.isoformat(), "status": "ERROR"}
    code = 1
    def audit(record):
        with (out / "exit-intents.jsonl").open("a") as f:
            f.write(json.dumps(record) + "\n")
            f.flush()
            os.fsync(f.fileno())
    try:
        if not key or not secret:
            raise ValueError("Missing Alpaca paper credentials")
        if os.getenv("PAPER_ALLOCATION_MODE", "legacy") != "legacy":
            raise ValueError("Fixed experiment requires legacy $10 allocation")
        if os.getenv("PAPER_REQUIRE_FRESH_QUOTE") != "true":
            raise ValueError("Fixed experiment requires fresh quote enforcement")
        report["clock"] = request_json(PAPER, "/v2/clock", key, secret)
        report["performance"] = performance(request_json(
            PAPER, "/v2/account/portfolio/history", key, secret,
            params={"period": "1M", "timeframe": "1D", "extended_hours": "false"}))
        if report["clock"].get("is_open") is not True:
            report["status"] = "MARKET_CLOSED"
            code = 0
        else:
            report["exits"] = manage_exits(key, secret, now=now, monitor_only=args.monitor_only, audit=audit)
            entry_args = ["--output-dir", str(out / "entry")]
            if args.monitor_only:
                entry_args.append("--monitor-only")
            code = entry_main(entry_args)
            report["entry"] = json.loads((out / "entry" / "decision.json").read_text())
            report["status"] = "OK" if code == 0 else "ERROR"
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as exc:
        code = 1
        # Do not print broker payloads, credentials, account IDs, or exception bodies.
        report["reason"] = "Broker/data reconciliation failed; inspect paper account before retrying"
        report["error_type"] = type(exc).__name__
    finally:
        (out / "session.json").write_text(json.dumps(report, indent=2) + "\n")
        lines = ["# Autonomous paper experiment", "", f"UTC: {now.isoformat()}",
                 f"Status: {report['status']}", f"Strategy: {STRATEGY}", "",
                 "Paper only. $10 entries; $100 daily cap; 5 positions; $100 cash reserve.",
                 "Exit experiment: -3%, +6%, or five calendar days; no guaranteed stop price.",
                 "Scheduled snapshots are not a continuous real-time service.",
                 "Completed daily-bar momentum and headline presence are not verified fundamentals.",
                 "Hypothesis: momentum with elevated volume may persist; causality and profitability unproven.",
                 "Evaluation: retain losing, winning, skipped and failed runs; compare fixed versions on unseen sessions.",
                 "Account performance is not isolated strategy alpha. Paper fills do not validate live returns."]
        if report.get("entry"):
            entry = report["entry"]
            lines.extend(["", f"Entry: {entry['decision']}",
                          f"Reason: {entry.get('reason', 'See session.json')}",
                          f"Submitted entries: {entry.get('submitted_count', 0)}"])
        (out / "summary.md").write_text("\n".join(lines) + "\n")
        print(f"Paper experiment: {report['status']}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
