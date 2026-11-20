"""Reconcile normalized paper fill evidence against an isolated balance interval."""
from datetime import timezone
from decimal import Decimal, InvalidOperation, localcontext

from investment_research import timestamp


def _decimal(value, *, signed=False):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("accounting amounts must be decimal strings")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("invalid accounting amount") from exc
    if (not result.is_finite() or abs(result) > 10**15 or result.as_tuple().exponent < -12
            or (not signed and result < 0)):
        raise ValueError("accounting amount outside supported range")
    return result.normalize() if result else Decimal(0)


def _balance(snapshot, symbol, account_ref):
    if (snapshot.get("symbol") != symbol or snapshot.get("account_ref") != account_ref
            or snapshot.get("currency") != "USD"):
        raise ValueError("balance evidence must match the paper account, symbol, and USD currency")
    return (timestamp(snapshot["observed_at"]).astimezone(timezone.utc), _decimal(snapshot["position_qty"]),
            _decimal(snapshot["cash"], signed=True))


def _audit_order_fills(order, reconciliation, activity, account_ref, before_at, after_at):
    if (reconciliation.get("broker_order_id") is None
            or "BROKER_ORDER_ID_MISMATCH" in reconciliation["discrepancies"]):
        raise ValueError("accounting requires an identified broker snapshot")
    order_updated_at = timestamp(reconciliation["broker_updated_at"])
    if order_updated_at > after_at:
        raise ValueError("broker order snapshot is newer than the balance interval")

    fills = {}
    if not isinstance(activity, list) or len(activity) > 10000:
        raise ValueError("fills must be a list of at most 10000 events")
    for event in activity:
        event_id = event.get("fill_id")
        if not isinstance(event_id, str) or not event_id or len(event_id) > 128:
            raise ValueError("stable fill ID is required")
        if (event.get("broker_order_id") != reconciliation["broker_order_id"]
                or event.get("symbol") != order["symbol"] or event.get("side") != order["side"]
                or event.get("account_ref") != account_ref or event.get("currency") != "USD"):
            raise ValueError("fill identity does not match the paper order")
        at = timestamp(event["executed_at"]).astimezone(timezone.utc)
        qty, price, fee = (_decimal(event[field]) for field in ("qty", "price", "fee"))
        if not before_at < at <= order_updated_at or not qty or not price:
            raise ValueError("fill must have positive quantity and price inside the snapshot window")
        record = (at, event_id, qty, price, fee)
        if event_id in fills and fills[event_id] != record:
            raise ValueError("conflicting records for a fill ID")
        fills[event_id] = record

    ordered = sorted(fills.values())
    with localcontext() as ctx:
        ctx.prec = 80
        total_qty = sum((qty for _, _, qty, _, _ in ordered), Decimal(0))
        gross = sum((qty * price for _, _, qty, price, _ in ordered), Decimal(0))
        fees = sum((fee for _, _, _, _, fee in ordered), Decimal(0))
    discrepancies = []
    broker_qty = reconciliation["cumulative_filled_qty"]
    if broker_qty is None or total_qty != _decimal(broker_qty):
        discrepancies.append("FILL_TOTAL_VS_ORDER_SNAPSHOT")
    limit = _decimal(order["limit_price"])
    if any(price > limit for _, _, _, price, _ in ordered):
        discrepancies.append("INDIVIDUAL_FILL_PRICE_ABOVE_LIMIT")
    return {
        "fills": ordered, "duplicate_fill_count": len(activity) - len(ordered),
        "total_qty": total_qty, "gross_fill_cost": gross, "fees": fees,
        "discrepancies": discrepancies,
    }


def _serialize_order_audit(audit):
    return {
        "fills": [
            {"fill_id": event_id, "executed_at": at.isoformat(), "qty": str(qty),
             "price": str(price), "fee": str(fee)}
            for at, event_id, qty, price, fee in audit["fills"]
        ],
        "duplicate_fill_count": audit["duplicate_fill_count"],
        "total_qty": str(audit["total_qty"]),
        "gross_fill_cost": str(audit["gross_fill_cost"]),
        "fees": str(audit["fees"]),
    }


def reconcile_fills(order, reconciliation, evidence):
    """Replay one paper buy order against its declared isolated account interval.

    Source authenticity and interval completeness are the caller's responsibility.
    Activity IDs identify executions and must be stable across exports.
    """
    if evidence.get("mode") != "PAPER_ONLY" or evidence.get("isolated_interval") is not True:
        raise ValueError("normalized paper evidence must declare an isolated interval")
    account_ref = evidence.get("account_ref")
    if not isinstance(account_ref, str) or not account_ref or len(account_ref) > 128:
        raise ValueError("paper account reference is required")
    before_at, before_qty, before_cash = _balance(evidence["before"], order["symbol"], account_ref)
    after_at, after_qty, after_cash = _balance(evidence["after"], order["symbol"], account_ref)
    if before_at >= after_at:
        raise ValueError("accounting snapshots must have increasing timestamps")

    audit = _audit_order_fills(order, reconciliation, evidence["fills"], account_ref, before_at, after_at)
    with localcontext() as ctx:
        ctx.prec = 80
        expected_qty = before_qty + audit["total_qty"]
        expected_cash = before_cash - audit["gross_fill_cost"] - audit["fees"]
        position_difference = after_qty - expected_qty
        cash_difference = after_cash - expected_cash

    discrepancies = audit["discrepancies"]
    if position_difference:
        discrepancies.append("POSITION_QUANTITY_MISMATCH")
    if cash_difference:
        discrepancies.append("CASH_BALANCE_MISMATCH")
    return {
        "state": "DISCREPANCY" if discrepancies or reconciliation["discrepancies"] else "BALANCES_MATCH",
        "interval": {"from_exclusive": before_at.isoformat(), "to_inclusive": after_at.isoformat()},
        **_serialize_order_audit(audit),
        "position": {"before": str(before_qty), "expected": str(expected_qty),
                     "observed": str(after_qty), "difference": str(position_difference)},
        "cash_usd": {"before": str(before_cash), "expected": str(expected_cash),
                     "observed": str(after_cash), "difference": str(cash_difference)},
        "discrepancies": discrepancies,
    }
