"""Safety regression tests for opt-in PAPER entry regime control."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

from paper_regime_controls import entry_block_reason
from market_regime_validation import classify


def sample(now):
    return {
        "decision_at": (now - timedelta(minutes=10)).isoformat(),
        "observed_at": (now - timedelta(minutes=15)).isoformat(),
        "source_id": "SYNTHETIC-TEST",
        "evidence_verified": True,
        "trend_pct": 4.0,
        "breadth_fraction": 0.7,
        "realized_vol_pct": 12.0,
    }


class RegimeEntryControlTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "evidence.json"
        self.path.write_text(json.dumps(sample(self.now)))
        self.env = {
            "PAPER_REGIME_CONTROL_ENABLED": "true",
            "PAPER_REGIME_REVIEW_APPROVED": "true",
            "PAPER_REGIME_EVIDENCE_FILE": str(self.path),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_disabled_preserves_preexisting_behavior(self):
        self.assertIsNone(entry_block_reason(now=self.now, environ={}))

    def test_verified_bull_only_continues_existing_gates(self):
        self.assertIsNone(entry_block_reason(now=self.now, environ=self.env))

    def test_missing_approval_and_evidence_hold(self):
        for key in ("PAPER_REGIME_REVIEW_APPROVED", "PAPER_REGIME_EVIDENCE_FILE"):
            with self.subTest(key=key):
                env = dict(self.env)
                env.pop(key)
                self.assertIsNotNone(entry_block_reason(now=self.now, environ=env))

    def test_bear_neutral_unknown_and_stale_hold(self):
        cases = [
            {"trend_pct": -4, "breadth_fraction": 0.2},
            {"trend_pct": 0, "breadth_fraction": 0.5},
            {"trend_pct": 4, "breadth_fraction": 0.2},
            {"evidence_verified": False},
            {"observed_at": (self.now - timedelta(days=8)).isoformat()},
            {"decision_at": (self.now + timedelta(days=1)).isoformat()},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                row = sample(self.now)
                row.update(overrides)
                self.path.write_text(json.dumps(row))
                self.assertIsNotNone(entry_block_reason(now=self.now, environ=self.env))

    def test_automatic_buy_is_blocked_before_any_broker_call(self):
        from paper_opportunity_intelligence import execute
        with patch.dict(os.environ, self.env, clear=True):
            self.path.write_text(json.dumps(sample(
                self.now) | {"trend_pct": -5, "breadth_fraction": 0.2}))
            broker = lambda *a, **k: self.fail("broker should not be contacted")
            outcome = execute({"decision": "READY"}, key="k", secret="s", get=broker)
            self.assertEqual(outcome["decision"], "SKIP")

    def test_manual_submit_blocks_post_but_allows_order_lookup(self):
        from paper_purchase_decision import submit
        from decimal import Decimal
        calls = []
        def broker(host, path, key, secret, *, params=None, payload=None):
            calls.append((path, payload))
            if path == "/v2/orders:by_client_order_id":
                raise RuntimeError("Alpaca HTTP 404")
            if path == "/v2/account":
                return {"status": "ACTIVE", "trading_blocked": False,
                        "account_blocked": False, "cash": "100", "buying_power": "100"}
            if path == "/v2/assets/SPY":
                return {"status": "active", "tradable": True, "fractionable": True}
            self.fail("unexpected broker route")
        with patch.dict(os.environ, self.env, clear=True):
            self.path.write_text(json.dumps(sample(
                self.now) | {"trend_pct": -5, "breadth_fraction": 0.2}))
            with self.assertRaisesRegex(ValueError, "Regime gate"):
                submit("SPY", Decimal("25"), "sample-client-order-id",
                       key="k", secret="s", get=broker)
        self.assertTrue(calls)
        self.assertFalse(any(payload is not None for _, payload in calls))


if __name__ == "__main__":
    unittest.main()
