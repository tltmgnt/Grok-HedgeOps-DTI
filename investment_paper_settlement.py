"""Replay settlement of explicitly identified paper-account cash obligations."""
from datetime import timezone
from decimal import Decimal, localcontext

from investment_paper_accounting import _decimal
from investment_research import timestamp


def _obligations(value):
    if not isinstance(value, dict) or len(value) > 10000:
        raise ValueError("obligations must map IDs to signed cash amounts")
    result = {}
    for key, raw in value.items():
        if not isinstance(key, str) or not key or len(key) > 128:
            raise ValueError("stable obligation ID is required")
        amount = _decimal(raw, signed=True)
        if not amount:
            raise ValueError("open obligations must have nonzero amounts")
        result[key] = amount
    return result


def reconcile_settlement(evidence, *, account_ref, before_at, after_at, before_cash,
                         after_cash, cash_movement_total, orders):
    """Reconcile supplied settled cash and outstanding obligations on both cutoffs."""
    before, after = evidence["before"], evidence["after"]
    for snapshot, cutoff in ((before, before_at), (after, after_at)):
        if (snapshot.get("account_ref") != account_ref or snapshot.get("currency") != "USD"
                or timestamp(snapshot["observed_at"]) != cutoff):
            raise ValueError("settlement snapshots must match the paper account and balance cutoffs")
    opening = _obligations(before["obligations"])
    ending = _obligations(after["obligations"])
    opening_cash = _decimal(before["settled_cash"], signed=True)
    observed_cash = _decimal(after["settled_cash"], signed=True)
    balances = dict(opening)
    available_at = dict.fromkeys(opening, before_at)

    with localcontext() as ctx:
        ctx.prec = 80
        for order in orders:
            for fill in order["fills"]:
                key = fill["fill_id"]
                if key in balances:
                    raise ValueError("fill ID overlaps an opening obligation")
                balances[key] = -(Decimal(fill["qty"]) * Decimal(fill["price"]) + Decimal(fill["fee"]))
                available_at[key] = timestamp(fill["executed_at"])

        records = evidence["events"]
        if not isinstance(records, list) or len(records) > 10000:
            raise ValueError("settlement events must be a bounded list")
        events = {}
        for event in records:
            event_id, key = event["settlement_id"], event["obligation_id"]
            if (not isinstance(event_id, str) or not event_id or len(event_id) > 128
                    or event.get("account_ref") != account_ref or event.get("currency") != "USD"
                    or not isinstance(key, str) or key not in balances):
                raise ValueError("settlement event must identify a known paper obligation")
            when = timestamp(event["settled_at"]).astimezone(timezone.utc)
            amount = _decimal(event["amount"], signed=True)
            if not before_at < when <= after_at or when < available_at[key] or not amount:
                raise ValueError("settlement event is outside the obligation's valid interval")
            record = (when, event_id, key, amount)
            if events.setdefault(event_id, record) != record:
                raise ValueError("conflicting settlement event records")

        ordered = sorted(events.values())
        for _, _, key, amount in ordered:
            remaining = balances[key]
            if not remaining or (amount < 0) != (remaining < 0) or abs(amount) > abs(remaining):
                raise ValueError("settlement amount exceeds or reverses its outstanding obligation")
            balances[key] -= amount

        settled_total = sum((amount for _, _, _, amount in ordered), Decimal(0))
        expected_cash = opening_cash + cash_movement_total + settled_total
        cash_difference = observed_cash - expected_cash
        obligation_differences = {}
        for key in sorted(balances.keys() | ending.keys()):
            expected = balances.get(key, Decimal(0))
            observed = ending.get(key, Decimal(0))
            if expected != observed:
                obligation_differences[key] = {
                    "expected": str(expected), "observed": str(observed),
                    "difference": str(observed - expected),
                }
        discrepancies = []
        if opening_cash + sum(opening.values(), Decimal(0)) != before_cash:
            discrepancies.append("OPENING_TRADE_CASH_BRIDGE_MISMATCH")
        if observed_cash + sum(ending.values(), Decimal(0)) != after_cash:
            discrepancies.append("ENDING_TRADE_CASH_BRIDGE_MISMATCH")
        if cash_difference:
            discrepancies.append("SETTLED_CASH_MISMATCH")
        if obligation_differences:
            discrepancies.append("OPEN_OBLIGATION_MISMATCH")
    return {
        "state": "DISCREPANCY" if discrepancies else "SETTLEMENT_MATCHES",
        "settled_cash_usd": {"before": str(opening_cash), "expected": str(expected_cash),
                             "observed": str(observed_cash), "difference": str(cash_difference)},
        "expected_open_obligations": {key: str(value) for key, value in sorted(balances.items()) if value},
        "obligation_differences": obligation_differences,
        "events": [
            {"settlement_id": event_id, "obligation_id": key, "settled_at": when.isoformat(), "amount": str(amount)}
            for when, event_id, key, amount in ordered
        ],
        "duplicate_settlement_count": len(records) - len(ordered),
        "discrepancies": discrepancies,
    }
