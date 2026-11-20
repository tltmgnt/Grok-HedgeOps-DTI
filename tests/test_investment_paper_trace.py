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
