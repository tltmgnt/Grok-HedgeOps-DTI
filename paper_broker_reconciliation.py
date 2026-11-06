"""Paper-only broker reconciliation and deterministic idempotency helpers.

No order submission in this module. Fail closed on missing broker state.
"""
import hashlib
import json
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from paper_order_feedback import request

TERMINAL = {"filled", "canceled", "expired", "rejected", "done_for_day"}

def order_key(strategy, symbol, session, notional):
    if not all(isinstance(v, str) and v for v in (strategy, symbol, session)):
        raise ValueError("missing idempotency identity")
    try:
        amount = Decimal(str(notional)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValueError("invalid notional")
    if not amount.is_finite() or amount <= 0:
        raise ValueError("invalid notional")
    identity = json.dumps([strategy, symbol, session, str(amount)], separators=(",", ":"))
    return "ho-paper-" + hashlib.sha256(identity.encode()).hexdigest()[:36]

def fetch_broker_state(key, secret):
    account = request("/v2/account", key, secret)
    positions = request("/v2/positions", key, secret)
    orders = request("/v2/orders?status=all&limit=500&direction=desc", key, secret)
    clock = request("/v2/clock", key, secret)
    if not isinstance(account, dict) or not isinstance(positions, list) or not isinstance(orders, list) or not isinstance(clock, dict):
        raise ValueError("invalid broker response")
    if len(orders) >= 500:
        raise ValueError("order history pagination needed; fail closed")
    if account.get("status") != "ACTIVE" or account.get("trading_blocked") or account.get("account_blocked"):
        raise ValueError("broker account not eligible")
    if clock.get("is_open") is not True:
        raise ValueError("market is closed")
    return account, positions, orders

def reconcile_symbol(symbol, client_order_id, positions, orders):
    if any(p.get("symbol") == symbol for p in positions):
        return "EXISTING_POSITION"
    for order in orders:
        if order.get("client_order_id") == client_order_id:
            return "DUPLICATE_ORDER"
        if order.get("symbol") == symbol and order.get("status") not in TERMINAL:
            return "OPEN_ORDER"
    return "CLEAR"

def fetch_order_by_client_id(client_order_id, key, secret):
    return request("/v2/orders:by_client_order_id?client_order_id=" + quote(client_order_id, safe=""), key, secret)
