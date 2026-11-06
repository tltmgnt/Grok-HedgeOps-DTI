"""Fail-closed deterministic trade qualification; Grok input is advisory only."""
import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from multidimensional_risk import assess

def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)

def qualify(data, account, positions, orders, *, now=None):
    now = now or datetime.now(timezone.utc)
    result = {"timestamp": now.isoformat(), "mode": "dry_run", "decisions": [], "orders_attempted": 0, "orders_accepted": 0}
    if not isinstance(account, dict) or not isinstance(positions, list) or not isinstance(orders, list):
        return {**result, "reason": "INVALID_PORTFOLIO_SNAPSHOT"}
    if not all(isinstance(p, dict) for p in positions) or not all(isinstance(o, dict) for o in orders):
        return {**result, "reason": "INVALID_PORTFOLIO_SNAPSHOT"}
    if any(not finite(p.get("market_value")) or p["market_value"] < 0 for p in positions):
        return {**result, "reason": "INVALID_POSITION_VALUES"}
    if not isinstance(data, list):
        raise ValueError("signals must be an array")
    equity = account.get("equity", 0)
    buying_power = account.get("buying_power", 0)
    daily_pnl = account.get("daily_pnl", 0)
    if not all(finite(v) for v in (equity, buying_power, daily_pnl)) or equity <= 0 or buying_power < 0:
        return {**result, "reason": "INVALID_ACCOUNT_DATA"}
    if daily_pnl <= -0.01 * equity:
        return {**result, "reason": "DAILY_LOSS_LIMIT"}
    held = {p.get("symbol") for p in positions}
    pending = {o.get("symbol") for o in orders if o.get("status") not in ("canceled", "rejected", "filled", "expired")}
    exposure = sum(float(p.get("market_value", 0)) for p in positions if finite(p.get("market_value", 0)) and p.get("side", "long") == "long")
    for s in data:
        if not isinstance(s, dict):
            result["decisions"].append({"symbol": "", "status": "SKIPPED", "reasons": ["INVALID_SIGNAL"], "notional_usd": 0})
            continue
        symbol = s.get("symbol", "")
        reasons = []
        if not isinstance(symbol, str) or not symbol.isascii() or not symbol.replace(".", "").isalpha() or len(symbol) > 10:
            reasons.append("INVALID_SYMBOL")
        required = ("price", "sma20", "sma50", "volume", "avg_volume", "spread_bps")
        if not all(finite(s.get(k)) for k in required):
            reasons.append("INVALID_MARKET_DATA")
        else:
            if min(s["price"], s["sma20"], s["sma50"], s["avg_volume"]) <= 0 or s["volume"] < 0:
                reasons.append("INVALID_MARKET_DATA")
            if not (s["price"] > s["sma20"] > s["sma50"]):
                reasons.append("TREND_NOT_CONFIRMED")
            if s["volume"] < s["avg_volume"]:
                reasons.append("VOLUME_NOT_CONFIRMED")
            if not 0 <= s["spread_bps"] <= 20:
                reasons.append("SPREAD_TOO_WIDE")
        try:
            observed = datetime.fromisoformat(s["asof"].replace("Z", "+00:00"))
            if observed.tzinfo is None or abs((now - observed).total_seconds()) > 900:
                reasons.append("STALE_DATA")
        except (KeyError, TypeError, ValueError, AttributeError):
            reasons.append("MISSING_TIMESTAMP")
        if s.get("market_open") is not True:
            reasons.append("MARKET_CLOSED")
        if s.get("tradable") is not True:
            reasons.append("NOT_TRADABLE")
        if s.get("grok_veto") is True:
            reasons.append("GROK_VETO")
        if symbol in held or symbol in pending:
            reasons.append("EXISTING_POSITION_OR_ORDER")
        if len(held) >= 5:
            reasons.append("POSITION_COUNT_LIMIT")
        notional = round(min(200.0, equity * 0.02, buying_power), 2)
        if notional < 1 or exposure + notional > equity * 0.20:
            reasons.append("EXPOSURE_OR_BUYING_POWER_LIMIT")
        diagnostic = assess(s, now=now)
        if diagnostic["decision"] in ("REJECT", "DEFER"):
            reasons.append("MULTIDIMENSIONAL_RISK_" + diagnostic["decision"])
        elif diagnostic["decision"] == "REDUCE_SIZE" and not reasons:
            notional = round(notional * diagnostic["suggested_size_factor"], 2)
            if notional < 1:
                reasons.append("REDUCED_SIZE_BELOW_MINIMUM")
        result["decisions"].append({"symbol": symbol, "status": "QUALIFIED" if not reasons else "SKIPPED", "reasons": reasons, "notional_usd": notional if not reasons else 0, "risk_diagnostics": diagnostic})
        if not reasons:
            exposure += notional
            buying_power -= notional
            held.add(symbol)
    if not result["decisions"]:
        result["reason"] = "NO_SIGNALS"
    elif not any(d["status"] == "QUALIFIED" for d in result["decisions"]):
        result["reason"] = "NO_QUALIFYING_TRADES"
    return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", default="trade-decisions.json", type=Path)
    a = p.parse_args()
    payload = json.loads(a.input.read_text())
    report = qualify(payload["signals"], payload["account"], payload.get("positions", []), payload.get("orders", []))
    a.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write("## Paper trade qualification (dry run)\n\n")
            f.write("| Symbol | Decision | Reason | Notional USD |\n|---|---|---|---|\n")
            for d in report["decisions"]:
                f.write(f"| {d['symbol']} | {d['status']} | {', '.join(d['reasons']) or 'PASS'} | {d['notional_usd']} |\n")
            f.write("\\n### Risk diagnostics\\n")
            for d in report["decisions"]:
                diagnostic = d.get("risk_diagnostics")
                if diagnostic:
                    f.write(f"\\n**{d['symbol']}** — {diagnostic['decision']}\\n\\n")
                    f.write("| Category | Severity | Code |\\n|---|---|---|\\n")
                    for category, item in diagnostic["categories"].items():
                        f.write(f"| {category} | {item['severity']} | {item['code']} |\\n")
            f.write(f"\n**Orders submitted: 0 (dry-run)**. {report.get('reason', '')}\n")

if __name__ == "__main__":
    main()
