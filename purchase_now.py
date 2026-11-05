"""Validated, non-executing manual purchase intent for offline paper workflows.

This module *never* creates broker orders, uses account balances, fetches market
data, or implies that an indicated price is an executable quote.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re

_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")


def prepare_purchase(symbol: str, notional: float, *, currency: str = "USD",
                     paper_only: bool = True) -> dict:
    """Prepare a human-reviewable request, not a purchase or trading signal."""
    if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
        raise ValueError("symbol must be an uppercase ticker-like identifier (1-15 characters)")
    if not isinstance(notional, (int, float)) or isinstance(notional, bool) or not math.isfinite(notional):
        raise ValueError("notional must be a finite number")
    if not 0 < notional <= 200:
        raise ValueError("demo purchase notional must be above zero and no more than $200")
    if currency != "USD":
        raise ValueError("only USD is supported by the offline demonstration")
    if paper_only is not True:
        raise ValueError("live purchase execution is not supported")
    return {
        "schema_version": "1.0",
        "request_type": "purchase_now",
        "execution_mode": "paper_only",
        "status": "pending_human_review",
        "symbol": symbol,
        "side": "BUY",
        "requested_notional": round(float(notional), 2),
        "currency": currency,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "broker_order_id": None,
        "order_submitted": False,
        "order_executed": False,
        "requires_human_review": True,
        "disclaimer": "Illustrative purchase request only. No live quote, brokerage connection, cash check, investment recommendation, or actual/paper order execution.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Prepare a manual paper-only Purchase Now request; no trades")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--notional", type=float, required=True)
    parser.add_argument("--output", type=Path, default=Path("purchase-request.json"))
    args = parser.parse_args(argv)
    try:
        request = prepare_purchase(args.symbol, args.notional)
        args.output.write_text(json.dumps(request, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print("PAPER ONLY — PURCHASE REQUEST CREATED — NO ORDER SUBMITTED")
    print("Review the JSON artifact before taking any separate manual action.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
