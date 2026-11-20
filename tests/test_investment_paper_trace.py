"""Replay research, journal, and paper reconciliation evidence without network."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from investment_paper_execution import execute_one
from investment_paper_trace import build_trace
from investment_research import main
from tests.test_investment_paper_execution import Broker, ENV
from tests.test_investment_research import NOW, policy, quote, reviewed_policy


class PaperTraceTests(unittest.TestCase):
    def run_fixture(self, research_policy):
        broker = Broker()

        def execute(p, horizon, **kwargs):
            return execute_one(p, horizon, **kwargs, get=broker, clock=lambda: NOW)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy_path = root / "policy.json"
            policy_path.write_text(json.dumps(research_policy))
            env = dict(ENV, ALPACA_API_KEY="fixture", ALPACA_API_SECRET="fixture")
            with patch.dict("os.environ", env, clear=True), patch(
                "investment_research.collect_quotes", return_value=({"MSFT": quote()}, [])
            ), patch("investment_paper_execution.execute_one", side_effect=execute):
                self.assertEqual(main(["--policy", str(policy_path), "--output", tmp, "--paper-entry"]), 0)
            report = json.loads((root / "research.json").read_text())
            intents = [json.loads(line) for line in (root / "entry-intents.jsonl").read_text().splitlines()]
        return report, intents, broker.posts

    def test_blocked_research_has_no_submission(self):
        report, intents, posts = self.run_fixture(policy())
        trace = build_trace(report, intents)
        self.assertEqual((intents, posts), ([], []))
        self.assertEqual(trace["execution_decision"], "SKIP")
        self.assertEqual(trace["reconciliation"]["state"], "NO_SUBMISSION")
        self.assertTrue(any(row["failed_gates"] for row in trace["assessments"]))
        self.assertFalse(trace["order_authority"])

    def test_partial_fill_and_reconciliation_discrepancy(self):
        report, intents, posts = self.run_fixture(reviewed_policy())
        self.assertEqual(len(posts), 1)
        self.assertEqual(intents[0]["research_run_id"], report["research_run_id"])
        snapshot = dict(posts[0], id="synthetic-order", status="partially_filled",
                        filled_qty="0.01", filled_avg_price="521.00")
        trace = build_trace(report, intents, paper_order_snapshot=snapshot)
        self.assertEqual(trace["submission_assessment"]["status"], "REVIEW_READY")
        self.assertEqual(trace["acknowledged_broker_status"], "accepted")
        self.assertEqual(trace["reconciliation"], {
            "state": "DISCREPANCY", "broker_order_id": "synthetic-order",
            "broker_status": "partially_filled", "cumulative_filled_qty": "0.01",
            "average_fill_price": "521.00", "discrepancies": ["FILL_PRICE_ABOVE_LIMIT"],
        })
        matched = build_trace(report, intents, paper_order_snapshot=dict(snapshot, filled_avg_price="510"))
        self.assertEqual(matched["reconciliation"]["state"], "MATCHED_SNAPSHOT")
        missing = build_trace(report, intents)
        self.assertEqual(missing["reconciliation"]["state"], "BROKER_EVIDENCE_MISSING")

    def test_unrelated_and_ambiguous_records_fail_closed(self):
        report, intents, posts = self.run_fixture(reviewed_policy())
        unrelated = dict(intents[0], research_run_id="other-run")
        self.assertEqual(build_trace(report, [unrelated])["reconciliation"]["state"], "INTENT_UNAVAILABLE")
        with self.assertRaisesRegex(ValueError, "multiple intents"):
            build_trace(report, intents * 2)
        with self.assertRaisesRegex(ValueError, "snapshot does not identify"):
            build_trace(report, intents, paper_order_snapshot=dict(
                posts[0], client_order_id="unrelated", id="other"
            ))
        live = {**report, "execution": {**report["execution"], "mode": "LIVE"}}
        with self.assertRaisesRegex(ValueError, "paper execution evidence"):
            build_trace(live, intents)

    def test_fill_accounting_replays_duplicates_and_reconciles_balances(self):
        report, intents, posts = self.run_fixture(reviewed_policy())
        snapshot = dict(posts[0], id="synthetic-order", status="partially_filled",
                        filled_qty="0.01", filled_avg_price="500", updated_at="2026-11-10T15:03:00Z")
        identity = {"symbol": "MSFT", "account_ref": "paper-fixture", "currency": "USD"}
        order = {**identity, "broker_order_id": snapshot["id"], "side": "buy",
                 "qty": "0.005", "price": "500", "fee": "0.01"}
        first = dict(order, fill_id="a", executed_at="2026-11-10T15:01:00Z")
        second = dict(order, fill_id="b", executed_at="2026-11-10T15:02:00Z")
        evidence = {
            "mode": "PAPER_ONLY", "isolated_interval": True, "account_ref": "paper-fixture",
            "before": dict(identity, observed_at="2026-11-10T15:00:00Z", position_qty="0", cash="100"),
            "after": dict(identity, observed_at="2026-11-10T15:04:00Z", position_qty="0.01", cash="94.98"),
            "fills": [second, first, dict(first, qty="0.0050")],
        }
        audit = build_trace(report, intents, paper_order_snapshot=snapshot, accounting_evidence=evidence)["accounting"]
        self.assertEqual(audit["state"], "BALANCES_MATCH")
        self.assertEqual([fill["fill_id"] for fill in audit["fills"]], ["a", "b"])
        self.assertEqual(audit["duplicate_fill_count"], 1)
        self.assertEqual(audit["fees"], "0.02")
        self.assertEqual(audit["cash_usd"]["expected"], "94.98")

        changed = dict(evidence, after=dict(evidence["after"], position_qty="0.02", cash="94.97"))
        audit = build_trace(report, intents, paper_order_snapshot=snapshot, accounting_evidence=changed)["accounting"]
        self.assertEqual(audit["state"], "DISCREPANCY")
        self.assertEqual(audit["discrepancies"], ["POSITION_QUANTITY_MISMATCH", "CASH_BALANCE_MISMATCH"])

        changed = dict(evidence, fills=[first])
        audit = build_trace(report, intents, paper_order_snapshot=snapshot, accounting_evidence=changed)["accounting"]
        self.assertIn("FILL_TOTAL_VS_ORDER_SNAPSHOT", audit["discrepancies"])

        with self.assertRaisesRegex(ValueError, "conflicting records"):
            build_trace(report, intents, paper_order_snapshot=snapshot, accounting_evidence=dict(
                evidence, fills=[first, dict(first, fee="0.02")]
            ))
        with self.assertRaisesRegex(ValueError, "fill identity"):
            build_trace(report, intents, paper_order_snapshot=snapshot, accounting_evidence=dict(
                evidence, fills=[dict(first, account_ref="other-paper-account")]
            ))
        with self.assertRaisesRegex(ValueError, "snapshot window"):
            build_trace(report, intents, paper_order_snapshot=snapshot, accounting_evidence=dict(
                evidence, fills=[dict(first, executed_at="2026-11-10T15:04:00Z")]
            ))

    def test_account_interval_reconciles_overlapping_orders_and_transfers(self):
        from investment_paper_portfolio import reconcile_portfolio

        report, intents, posts = self.run_fixture(reviewed_policy())
        first = dict(posts[0], id="synthetic-order", status="filled", filled_qty="0.01",
                     filled_avg_price="500", submitted_at="2026-11-10T15:01:00Z",
                     updated_at="2026-11-10T15:04:00Z")
        second_id = posts[0]["client_order_id"].replace("1-2y", "5y")
        second = dict(first, id="second-order", client_order_id=second_id,
                      submitted_at="2026-11-10T15:02:00Z", updated_at="2026-11-10T15:03:00Z")
        second_report = {**report, "research_run_id": "second-run", "execution": {
            **report["execution"], "broker_order_id": second["id"], "client_order_id": second_id,
            "horizon": "5y",
        }}
        second_intent = {**intents[0], "research_run_id": "second-run", "horizon": "5y",
                         "assessment": {**intents[0]["assessment"], "horizon": "5y"},
                         "order": dict(posts[0], client_order_id=second_id)}
        identity = {"account_ref": "fixture", "currency": "USD"}
        fill = dict(identity, symbol="MSFT", side="buy", qty="0.01", price="500", fee="0.01")
        cash = dict(identity, movement_id="deposit", amount="15", occurred_at="2026-11-10T15:02:30Z")
        bundle = {
            "mode": "PAPER_ONLY", "complete_interval": True, "account_ref": "fixture",
            "before": dict(identity, observed_at="2026-11-10T15:00:00Z", cash="100", positions={"AAPL": "1"}),
            "after": dict(identity, observed_at="2026-11-10T15:05:00Z", cash="104.98",
                          positions={"AAPL": "1", "MSFT": "0.02"}),
            "orders": [
                {"report": report, "intents": intents, "paper_order_snapshot": first},
                {"report": second_report, "intents": [second_intent], "paper_order_snapshot": second},
            ],
            "fills": [
                dict(fill, fill_id="a", broker_order_id=first["id"], executed_at="2026-11-10T15:04:00Z"),
                dict(fill, fill_id="b", broker_order_id=second["id"], executed_at="2026-11-10T15:03:00Z"),
            ],
            "cash_movements": [cash, dict(cash, amount="15.00")],
        }
        result = reconcile_portfolio(bundle)
        self.assertEqual(result["state"], "BALANCES_MATCH")
        self.assertEqual(result["positions"]["MSFT"]["expected"], "0.02")
        self.assertEqual(result["cash_usd"]["expected"], "104.98")
        self.assertEqual(result["cash_usd"]["fees"], "0.02")
        self.assertEqual(result["duplicate_cash_movement_count"], 1)
        self.assertEqual(reconcile_portfolio(dict(bundle, orders=list(reversed(bundle["orders"])))), result)
        discrepancies = reconcile_portfolio(dict(
            bundle, after=dict(bundle["after"], cash="105", positions={"MSFT": "0.02"}), fills=bundle["fills"][:1]
        ))
        self.assertCountEqual(discrepancies["discrepancies"], [
            "ORDER_EVIDENCE_MISMATCH", "POSITION_QUANTITY_MISMATCH", "CASH_BALANCE_MISMATCH",
        ])
        self.assertEqual(discrepancies["positions"]["AAPL"]["difference"], "-1")
        with self.assertRaisesRegex(ValueError, "fill ID reused"):
            reconcile_portfolio(dict(bundle, fills=[bundle["fills"][0], dict(bundle["fills"][1], fill_id="a")]))
        with self.assertRaisesRegex(ValueError, "conflicting cash movement"):
            reconcile_portfolio(dict(bundle, cash_movements=[cash, dict(cash, amount="14")]))
        with self.assertRaisesRegex(ValueError, "untraced order"):
            reconcile_portfolio(dict(bundle, orders=bundle["orders"][:1]))

        settle = dict(identity, settled_at="2026-11-10T15:04:30Z")
        paid = dict(settle, settlement_id="old-payment", obligation_id="opening", amount="-2")
        partial = dict(settle, settlement_id="partial-payment", obligation_id="a", amount="-3.01")
        evidence = {
            "before": dict(identity, observed_at=bundle["before"]["observed_at"],
                           settled_cash="102", obligations={"opening": "-2"}),
            "after": dict(identity, observed_at=bundle["after"]["observed_at"],
                          settled_cash="111.99", obligations={"a": "-2", "b": "-5.01"}),
            "events": [partial, paid, dict(paid, amount="-2.00")],
        }
        audit = reconcile_portfolio(dict(bundle, settlement=evidence))
        self.assertEqual(audit["state"], "BALANCES_MATCH")
        settlement = audit["settlement"]
        self.assertEqual(settlement["state"], "SETTLEMENT_MATCHES")
        self.assertEqual(settlement["settled_cash_usd"]["expected"], "111.99")
        self.assertEqual(settlement["expected_open_obligations"], {"a": "-2.00", "b": "-5.01"})
        self.assertEqual(settlement["duplicate_settlement_count"], 1)

        # A wrong cash and obligation pair can preserve the bridge and still fail replay.
        changed = dict(evidence, after=dict(evidence["after"], settled_cash="112.99",
                                           obligations={"a": "-3", "b": "-5.01"}))
        audit = reconcile_portfolio(dict(bundle, settlement=changed))
        self.assertEqual(audit["discrepancies"], ["SETTLEMENT_MISMATCH"])
        self.assertEqual(audit["settlement"]["discrepancies"], [
            "SETTLED_CASH_MISMATCH", "OPEN_OBLIGATION_MISMATCH",
        ])
        for extra, message in (
            (dict(partial, amount="-6"), "exceeds or reverses"),
            (dict(partial, settled_at="2026-11-10T15:03:30Z"), "valid interval"),
            (dict(partial, obligation_id="unknown"), "known paper obligation"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                reconcile_portfolio(dict(bundle, settlement=dict(evidence, events=[paid, extra])))
