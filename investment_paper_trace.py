"""Build an offline audit trace from investment research and paper broker evidence."""
import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from investment_paper_accounting import reconcile_fills


def _amount(value):
    try:
        amount = Decimal(str(value))
        if amount.is_finite() and amount >= 0:
            return amount
    except InvalidOperation:
        pass
    return None


def _match_intent(report, intent, execution):
    assessment, order = intent["assessment"], intent["order"]
    if (not isinstance(intent.get("policy_sha256"), str)
            or intent.get("event") != "PAPER_ENTRY_INTENT"
            or intent.get("policy_sha256") != report.get("policy_sha256")
            or intent.get("horizon") != assessment.get("horizon")
            or assessment.get("symbol") != order.get("symbol")
            or assessment.get("status") != "REVIEW_READY"
            or assessment.get("failed_gates") != []
            or assessment.get("order_authority") is not False
            or order.get("side") != "buy" or order.get("type") != "limit"
            or not isinstance(order.get("client_order_id"), str)
            or not order["client_order_id"].startswith("ho-invest-")
            or not _amount(order.get("notional"))
            or not _amount(order.get("limit_price"))):
        raise ValueError("intent does not match the paper research decision")
    if execution and (execution.get("client_order_id") != order["client_order_id"]
                      or execution.get("policy_sha256") != intent["policy_sha256"]
                      or execution.get("horizon") != intent["horizon"]
                      or execution.get("decision") not in {"SUBMITTED", "UNKNOWN_RECONCILE"}):
        raise ValueError("execution result does not match the paper intent")
    return assessment, order


def _reconcile_order(order, execution, snapshot):
    if snapshot is None:
        return {"state": "BROKER_EVIDENCE_MISSING", "discrepancies": []}
    if (snapshot.get("client_order_id") != order["client_order_id"]
            or not isinstance(snapshot.get("id"), str) or not snapshot["id"]):
        raise ValueError("broker snapshot does not identify the paper order")
    discrepancies = [
        f"{field.upper()}_MISMATCH" for field in ("symbol", "side", "type", "time_in_force")
        if snapshot.get(field) != order.get(field)
    ]
    expected_id = execution.get("broker_order_id")
    if expected_id is not None and expected_id != snapshot["id"]:
        discrepancies.append("BROKER_ORDER_ID_MISMATCH")
    for field in ("notional", "limit_price"):
        expected, actual = _amount(order.get(field)), _amount(snapshot.get(field))
        if expected is None or actual != expected:
            discrepancies.append(f"{field.upper()}_MISMATCH")
    status = snapshot.get("status")
    qty, avg_price = _amount(snapshot.get("filled_qty")), _amount(snapshot.get("filled_avg_price"))
    cap = _amount(order.get("limit_price"))
    if qty is None:
        discrepancies.append("FILL_QUANTITY_UNAVAILABLE")
    elif qty > 0:
        if avg_price is None or avg_price == 0:
            discrepancies.append("FILL_PRICE_UNAVAILABLE")
        elif cap is not None and avg_price > cap:
            discrepancies.append("FILL_PRICE_ABOVE_LIMIT")
    elif status in ("filled", "partially_filled"):
        discrepancies.append("FILL_STATUS_WITHOUT_QUANTITY")
    if not isinstance(status, str) or not status:
        discrepancies.append("BROKER_STATUS_UNAVAILABLE")
    elif status == "rejected" and qty:
        discrepancies.append("REJECTED_ORDER_HAS_FILL")
    return {
        "state": "DISCREPANCY" if discrepancies else "MATCHED_SNAPSHOT",
        "broker_order_id": snapshot["id"],
        "broker_status": status,
        "cumulative_filled_qty": str(qty) if qty is not None else None,
        "average_fill_price": str(avg_price) if avg_price is not None else None,
        "discrepancies": discrepancies,
    }


def build_trace(report, intents=(), *, paper_order_snapshot=None, accounting_evidence=None):
    """Join one tagged research run, its optional intent, and a paper order snapshot."""
    run_id = report.get("research_run_id")
    if not isinstance(run_id, str) or not run_id or report.get("order_authority") is not False:
        raise ValueError("a tagged research report without order authority is required")
    execution = report.get("execution", {})
    if execution and execution.get("mode") != "PAPER_ONLY":
        raise ValueError("paper execution evidence is required")
    matching = [event for event in intents if event.get("research_run_id") == run_id]
    if len(matching) > 1:
        raise ValueError("multiple intents for a single investment research run")
    trace = {
        "research_run_id": run_id,
        "policy_sha256": report.get("policy_sha256"),
        "research_origin": report.get("origin"),
        "generated_at_utc": report.get("generated_at_utc"),
        "assessments": [
            {key: row.get(key) for key in ("symbol", "horizon", "status", "failed_gates", "quote")}
            for row in report.get("assessments", ())
        ],
        "paper_only": True,
        "order_authority": False,
        "execution_decision": execution.get("decision"),
        "execution_reason": execution.get("reason"),
        "acknowledged_broker_status": execution.get("broker_status"),
    }
    if not matching:
        if paper_order_snapshot is not None or accounting_evidence is not None:
            raise ValueError("broker snapshot requires an intent from the same research run")
        decision = execution.get("decision")
        state = {
            "SKIP": "NO_SUBMISSION",
            "ALREADY_EXISTS": "EXISTING_ORDER_NOT_LINKED",
        }.get(decision, "INTENT_UNAVAILABLE")
        if decision is None and report.get("paper_entry_requested") is False:
            state = "PAPER_ENTRY_NOT_REQUESTED"
        return {**trace, "reconciliation": {"state": state, "discrepancies": []}}
    assessment, order = _match_intent(report, matching[0], execution)
    reconciliation = _reconcile_order(order, execution, paper_order_snapshot)
    trace.update(submission_assessment=assessment, order_intent=order, reconciliation=reconciliation)
    if accounting_evidence is not None:
        if paper_order_snapshot is None:
            raise ValueError("accounting requires a paper order snapshot")
        accounting_order = {**reconciliation, "broker_updated_at": paper_order_snapshot.get("updated_at")}
        trace["accounting"] = reconcile_fills(order, accounting_order, accounting_evidence)
    return trace


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Tagged research.json")
    parser.add_argument("--intents", type=Path, help="entry-intents.jsonl")
    parser.add_argument("--paper-order-snapshot", type=Path, help="Saved paper order JSON")
    parser.add_argument("--accounting-evidence", type=Path, help="Normalized paper fill and balance JSON")
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text())
        intents = [json.loads(line) for line in args.intents.read_text().splitlines() if line.strip()] if args.intents else []
        snapshot = json.loads(args.paper_order_snapshot.read_text()) if args.paper_order_snapshot else None
        accounting = json.loads(args.accounting_evidence.read_text()) if args.accounting_evidence else None
        trace = build_trace(report, intents, paper_order_snapshot=snapshot, accounting_evidence=accounting)
        print(json.dumps(trace, indent=2, allow_nan=False))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        parser.exit(2, f"Unable to build paper trace ({type(exc).__name__}). Check the input files.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
