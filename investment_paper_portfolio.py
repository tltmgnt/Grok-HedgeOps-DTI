"""Reconcile an offline USD paper-account interval across traced buy orders."""
import argparse
from collections import defaultdict
from datetime import timezone
from decimal import Decimal, localcontext
import json
from pathlib import Path

from investment_paper_accounting import _audit_order_fills, _decimal, _serialize_order_audit
from investment_paper_settlement import reconcile_settlement
from investment_paper_trace import build_trace
from investment_research import timestamp


def _snapshot(record, account_ref):
    if record.get("account_ref") != account_ref or record.get("currency") != "USD":
        raise ValueError("snapshot account or currency mismatch")
    positions = record["positions"]
    if not isinstance(positions, dict) or any(not isinstance(symbol, str) or not symbol.strip() for symbol in positions):
        raise ValueError("positions must map symbols to quantities")
    return (
        timestamp(record["observed_at"]).astimezone(timezone.utc),
        {symbol: _decimal(quantity, signed=True) for symbol, quantity in positions.items()},
        _decimal(record["cash"], signed=True),
    )


def _partition_fills(events):
    by_order = defaultdict(list)
    owner = {}
    for event in events:
        fill_id, broker_id = event["fill_id"], event["broker_order_id"]
        if not isinstance(fill_id, str) or not isinstance(broker_id, str):
            raise ValueError("fill and order IDs must be strings")
        if owner.setdefault(fill_id, broker_id) != broker_id:
            raise ValueError("fill ID reused across orders")
        by_order[broker_id].append(event)
    return by_order


def _cash_movements(events, account_ref, before_at, after_at):
    movements = {}
    for event in events:
        event_id = event["movement_id"]
        if (not isinstance(event_id, str) or not event_id or len(event_id) > 128
                or event.get("account_ref") != account_ref or event.get("currency") != "USD"):
            raise ValueError("invalid cash movement identity")
        occurred_at = timestamp(event["occurred_at"]).astimezone(timezone.utc)
        amount = _decimal(event["amount"], signed=True)
        if not before_at < occurred_at <= after_at or not amount:
            raise ValueError("cash movement must be nonzero and inside the interval")
        record = (occurred_at, event_id, amount)
        if movements.setdefault(event_id, record) != record:
            raise ValueError("conflicting cash movement records")
    return sorted(movements.values())


def reconcile_portfolio(bundle):
    """Replay traced orders and non-trade cash movements from local evidence."""
    account_ref = bundle.get("account_ref")
    if (bundle.get("mode") != "PAPER_ONLY" or bundle.get("complete_interval") is not True
            or not isinstance(account_ref, str) or not account_ref or len(account_ref) > 128):
        raise ValueError("complete paper account evidence is required")
    before_at, before_positions, before_cash = _snapshot(bundle["before"], account_ref)
    after_at, after_positions, after_cash = _snapshot(bundle["after"], account_ref)
    if before_at >= after_at:
        raise ValueError("account snapshots must have increasing timestamps")
    order_records, fill_events, cash_events = (bundle[key] for key in ("orders", "fills", "cash_movements"))
    if any(not isinstance(rows, list) or len(rows) > limit
           for rows, limit in ((order_records, 1000), (fill_events, 10000), (cash_events, 10000))):
        raise ValueError("account evidence exceeds supported record limits")
    by_order = _partition_fills(fill_events)
    movements = _cash_movements(cash_events, account_ref, before_at, after_at)
    order_audits = {}
    client_ids, run_ids = set(), set()
    quantities = defaultdict(Decimal)
    with localcontext() as ctx:
        ctx.prec = 80
        gross = fees = Decimal(0)
        for record in order_records:
            snapshot = record["paper_order_snapshot"]
            submitted_at = timestamp(snapshot["submitted_at"])
            if not before_at < submitted_at <= timestamp(snapshot["updated_at"]) <= after_at:
                raise ValueError("traced orders must be submitted and observed inside the interval")
            trace = build_trace(record["report"], record["intents"], paper_order_snapshot=snapshot)
            order, reconciliation = trace["order_intent"], trace["reconciliation"]
            broker_id, client_id, run_id = reconciliation["broker_order_id"], order["client_order_id"], trace["research_run_id"]
            if broker_id in order_audits or client_id in client_ids or run_id in run_ids:
                raise ValueError("duplicate order or research run")
            client_ids.add(client_id)
            run_ids.add(run_id)
            events = by_order.pop(broker_id, [])
            if any(timestamp(event["executed_at"]) < submitted_at for event in events):
                raise ValueError("a fill precedes order submission")
            audit = _audit_order_fills(
                order, {**reconciliation, "broker_updated_at": snapshot["updated_at"]},
                events, account_ref, before_at, after_at,
            )
            quantities[order["symbol"]] += audit["total_qty"]
            gross += audit["gross_fill_cost"]
            fees += audit["fees"]
            order_audits[broker_id] = {
                "broker_order_id": broker_id, "client_order_id": client_id,
                "research_run_id": run_id, "symbol": order["symbol"],
                **_serialize_order_audit(audit),
                "discrepancies": sorted(set(audit["discrepancies"] + reconciliation["discrepancies"])),
            }
        if by_order:
            raise ValueError("fills supplied for an untraced order")
        cash_movement_total = sum((amount for _, _, amount in movements), Decimal(0))
        expected_cash = before_cash - gross - fees + cash_movement_total
        cash_difference = after_cash - expected_cash
        positions = {}
        for symbol in sorted(before_positions.keys() | after_positions.keys() | quantities.keys()):
            before = before_positions.get(symbol, Decimal(0))
            observed = after_positions.get(symbol, Decimal(0))
            expected = before + quantities[symbol]
            positions[symbol] = {
                "before": str(before), "expected": str(expected),
                "observed": str(observed), "difference": str(observed - expected),
            }
    discrepancies = []
    if any(order["discrepancies"] for order in order_audits.values()):
        discrepancies.append("ORDER_EVIDENCE_MISMATCH")
    if any(Decimal(position["difference"]) for position in positions.values()):
        discrepancies.append("POSITION_QUANTITY_MISMATCH")
    if cash_difference:
        discrepancies.append("CASH_BALANCE_MISMATCH")
    result = {
        "state": "DISCREPANCY" if discrepancies else "BALANCES_MATCH",
        "paper_only": True, "order_authority": False,
        "interval": {"from_exclusive": before_at.isoformat(), "to_inclusive": after_at.isoformat()},
        "orders": [order_audits[broker_id] for broker_id in sorted(order_audits)],
        "positions": positions,
        "cash_usd": {
            "before": str(before_cash), "gross_fill_cost": str(gross), "fees": str(fees),
            "non_trade_movements": str(cash_movement_total), "expected": str(expected_cash),
            "observed": str(after_cash), "difference": str(cash_difference),
        },
        "cash_movements": [
            {"movement_id": event_id, "occurred_at": at.isoformat(), "amount": str(amount)}
            for at, event_id, amount in movements
        ],
        "duplicate_cash_movement_count": len(cash_events) - len(movements),
        "discrepancies": discrepancies,
    }

    if "settlement" in bundle:
        settlement = reconcile_settlement(
            bundle["settlement"], account_ref=account_ref, before_at=before_at, after_at=after_at,
            before_cash=before_cash, after_cash=after_cash, cash_movement_total=cash_movement_total,
            orders=result["orders"],
        )
        result["settlement"] = settlement
        if settlement["discrepancies"]:
            discrepancies.append("SETTLEMENT_MISMATCH")
            result["state"] = "DISCREPANCY"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, help="Normalized paper portfolio evidence JSON")
    args = parser.parse_args(argv)
    try:
        audit = reconcile_portfolio(json.loads(args.evidence.read_text()))
        print(json.dumps(audit, indent=2, allow_nan=False))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        parser.exit(2, f"Unable to reconcile paper portfolio ({type(exc).__name__}). Check the input file.\n")
    return int(audit["state"] == "DISCREPANCY")


if __name__ == "__main__":
    raise SystemExit(main())
