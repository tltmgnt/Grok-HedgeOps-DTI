"""Opt-in Alpaca stock purchase submission with bounded deterministic checks.

Never runs unless explicitly invoked with LIVE mode, the exact confirmation
phrase, and configured credentials. No LLM decides execution authority.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.]{0,14}$")
CONFIRMATION = "I AUTHORIZE LIVE BUY"


def _request(base: str, path: str, key: str, secret: str, *, payload=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(base + path, data=body, headers={
        "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
        "Content-Type": "application/json", "Accept": "application/json",
    }, method="POST" if body is not None else "GET")
    try:
        with urlopen(request, timeout=15) as response:  # nosec B310 - fixed HTTPS Alpaca host, validated path
            return json.load(response)
    except HTTPError as exc:
        # Never print raw broker response, which may contain sensitive data.
        raise RuntimeError(f"Broker rejected request (HTTP {exc.code})") from None
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("Broker request failed or timed out; check order status before retrying") from None


def purchase_alpaca(symbol: str, notional: float, *, mode: str,
                    confirmation: str = "", key: str = "", secret: str = "",
                    max_notional: float = 200.0, request_id: str = "") -> dict:
    if mode not in ("paper", "live"):
        raise ValueError("mode must be paper or live")
    if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
        raise ValueError("invalid symbol")
    if (isinstance(notional, bool) or not isinstance(notional, (int, float))
            or not math.isfinite(notional) or not 1 <= notional <= max_notional):
        raise ValueError("notional outside permitted USD order bounds")
    if mode == "live" and confirmation != CONFIRMATION:
        raise PermissionError("explicit live purchase confirmation required")
    if not key or not secret:
        raise ValueError("Alpaca credentials missing")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,48}", request_id):
        raise ValueError("stable unique request_id required for order idempotency")

    base = "https://api.alpaca.markets" if mode == "live" else "https://paper-api.alpaca.markets"
    account = _request(base, "/v2/account", key, secret)
    if account.get("trading_blocked") is not False or account.get("account_blocked") is not False:
        raise PermissionError("broker account blocked or status unavailable")
    if account.get("status") != "ACTIVE":
        raise PermissionError("broker account is not active")
    try:
        buying_power = float(account["buying_power"])
        cash = float(account["cash"])
    except (KeyError, TypeError, ValueError):
        raise PermissionError("broker balance unavailable") from None
    if not all(map(math.isfinite, (buying_power, cash))) or min(buying_power, cash) < notional:
        raise PermissionError("insufficient confirmed buying power or cash")

    asset = _request(base, "/v2/assets/" + symbol, key, secret)
    if asset.get("tradable") is not True or asset.get("status") != "active":
        raise PermissionError("instrument is not confirmed tradable")
    if asset.get("fractionable") is not True:
        raise PermissionError("instrument does not support fractional notional purchases")

    # Never retry an ambiguous POST automatically. client_order_id supports
    # broker-side duplicate detection if a workflow is re-run.
    order = _request(base, "/v2/orders", key, secret, payload={
        "symbol": symbol, "notional": f"{notional:.2f}", "side": "buy",
        "type": "market", "time_in_force": "day",
        "client_order_id": request_id,
    })
    return {
        "broker": "alpaca", "mode": mode, "symbol": symbol,
        "notional_usd": round(float(notional), 2),
        "order_id": order.get("id"), "client_order_id": request_id,
        "broker_status": order.get("status"),
        "order_submitted": bool(order.get("id")),
        "order_filled": order.get("status") == "filled",
        "warning": "Submitted does not mean filled; reconcile in broker account.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Explicitly authorized Alpaca purchase")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--notional", required=True, type=float)
    parser.add_argument("--mode", required=True, choices=["paper", "live"])
    parser.add_argument("--request-id", required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode == "live" and os.getenv("ALPACA_LIVE_TRADING_ENABLED") != "true":
            raise PermissionError("live trading is disabled; configure ALPACA_LIVE_TRADING_ENABLED=true in protected environment")
        result = purchase_alpaca(
            args.symbol, args.notional, mode=args.mode,
            confirmation=os.getenv("LIVE_PURCHASE_CONFIRMATION", ""),
            key=os.getenv("ALPACA_API_KEY", ""), secret=os.getenv("ALPACA_API_SECRET", ""),
            request_id=args.request_id,
        )
    except (ValueError, PermissionError, RuntimeError) as exc:
        print(f"Purchase rejected: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
