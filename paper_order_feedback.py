"""Separately authorized Alpaca PAPER-only submission and reconciliation."""
import argparse
import json
import os
from datetime import datetime, timezone
import urllib.request
import urllib.error
from pathlib import Path
from restricted_https import open_api

BASE = "https://paper-api.alpaca.markets"
def request(path, key, secret, method="GET", payload=None):
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret, "Content-Type": "application/json"}
    req = urllib.request.Request(BASE + path, headers=headers, method=method, data=json.dumps(payload).encode() if payload else None)
    with open_api(req, timeout=20) as response:
        return json.load(response)

def run(decisions, *, enabled=False, key="", secret=""):
    report = {"mode": "paper", "orders_attempted": 0, "orders_accepted": 0, "orders": []}
    if not enabled:
        report["reason"] = "PAPER_EXECUTION_NOT_AUTHORIZED"
        return report
    if not key or not secret:
        report["reason"] = "MISSING_PAPER_CREDENTIALS"
        return report
    from paper_broker_reconciliation import fetch_broker_state, order_key, reconcile_symbol
    try:
        account, positions, broker_orders = fetch_broker_state(key, secret)
        equity = float(account["equity"])
        buying_power = float(account["buying_power"])
        exposure = sum(abs(float(p["market_value"])) for p in positions)
    except (OSError, ValueError, KeyError, TypeError):
        report["reason"] = "BROKER_RECONCILIATION_FAILED"
        return report
    if equity <= 0 or buying_power < 0 or exposure < 0:
        report["reason"] = "INVALID_BROKER_RISK_STATE"
        return report
    # Execution remains blocked until decision provenance and replay tests are complete.
    report["reason"] = "EXECUTION_BLOCKED_PENDING_PROVENANCE_VALIDATION"
    return report

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--decisions", required=True, type=Path)
    p.add_argument("--output", default="paper-order-feedback.json", type=Path)
    a = p.parse_args()
    enabled = os.getenv("PAPER_EXECUTION_ENABLED") == "true" and os.getenv("PAPER_EXECUTION_CONFIRM") == "I AUTHORIZE PAPER ORDERS"
    report = run(json.loads(a.decisions.read_text()), enabled=enabled,
                 key=os.getenv("ALPACA_PAPER_API_KEY", ""), secret=os.getenv("ALPACA_PAPER_API_SECRET", ""))
    a.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(f"## Alpaca paper order feedback\n\nAttempted: {report['orders_attempted']}  Accepted: {report['orders_accepted']}\n\n")
            for order in report["orders"]:
                f.write(f"- {order['symbol']}: {order['status']} (order ID: {order.get('order_id', 'none')})\n")
            if report.get("reason"):
                f.write(f"\nNo orders submitted: {report['reason']}\n")

if __name__ == "__main__":
    main()
