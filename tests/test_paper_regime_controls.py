"""Safety regression tests for opt-in PAPER entry regime control."""
import json
import hashlib
import hmac
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

from paper_regime_controls import entry_block_reason, _approval_message
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
            "PAPER_REGIME_APPROVED_SHA256": hashlib.sha256(self.path.read_bytes()).hexdigest(),
            "PAPER_REGIME_APPROVAL_EXPIRES_AT": (self.now + timedelta(hours=2)).isoformat(),
            "PAPER_REGIME_APPROVAL_HMAC_KEY": "a1" * 32,  # synthetic-only test key
        }
        self.sign(self.env)

    def sign(self, env):
        env["PAPER_REGIME_APPROVAL_HMAC_SHA256"] = hmac.new(
            bytes.fromhex(env["PAPER_REGIME_APPROVAL_HMAC_KEY"]),
            _approval_message(env["PAPER_REGIME_APPROVED_SHA256"],
                              env["PAPER_REGIME_APPROVAL_EXPIRES_AT"]),
            hashlib.sha256,
        ).hexdigest()

    def tearDown(self):
        self.tmp.cleanup()

    def test_disabled_preserves_preexisting_behavior(self):
        self.assertIsNone(entry_block_reason(now=self.now, environ={}))

    def test_verified_bull_only_continues_existing_gates(self):
        self.assertIsNone(entry_block_reason(now=self.now, environ=self.env))

    def test_modified_evidence_is_rejected_even_when_label_is_bull(self):
        self.path.write_text(json.dumps(sample(self.now), sort_keys=True))
        self.assertIn("digest", entry_block_reason(now=self.now, environ=self.env))

    def test_digest_and_expiry_are_both_required(self):
        for key in ("PAPER_REGIME_APPROVED_SHA256", "PAPER_REGIME_APPROVAL_EXPIRES_AT"):
            with self.subTest(key=key):
                env = dict(self.env)
                env.pop(key)
                self.assertIsNotNone(entry_block_reason(now=self.now, environ=env))
        expired = dict(self.env)
        expired["PAPER_REGIME_APPROVAL_EXPIRES_AT"] = (self.now - timedelta(minutes=1)).isoformat()
        self.sign(expired)
        self.assertIn("expired", entry_block_reason(now=self.now, environ=expired))
        too_far = dict(self.env)
        too_far["PAPER_REGIME_APPROVAL_EXPIRES_AT"] = (self.now + timedelta(days=2)).isoformat()
        self.sign(too_far)
        self.assertIn("window", entry_block_reason(now=self.now, environ=too_far))

    def test_stale_evidence_is_rejected_even_with_matching_digest(self):
        row = sample(self.now)
        row["observed_at"] = (self.now - timedelta(days=2)).isoformat()
        row["decision_at"] = (self.now - timedelta(days=2, minutes=-10)).isoformat()
        self.path.write_text(json.dumps(row))
        env = dict(self.env)
        env["PAPER_REGIME_APPROVED_SHA256"] = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.sign(env)
        self.assertIn("stale", entry_block_reason(now=self.now, environ=env))

    def test_changed_bear_evidence_with_matching_digest_is_still_blocked(self):
        row = sample(self.now)
        row.update({"trend_pct": -4, "breadth_fraction": 0.2})
        self.path.write_text(json.dumps(row))
        env = dict(self.env)
        env["PAPER_REGIME_APPROVED_SHA256"] = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.sign(env)
        self.assertIn("not verified BULL", entry_block_reason(now=self.now, environ=env))

    def test_authenticated_approval_is_required_even_with_correct_digest(self):
        for name in ("PAPER_REGIME_APPROVAL_HMAC_KEY", "PAPER_REGIME_APPROVAL_HMAC_SHA256"):
            with self.subTest(name=name):
                env = dict(self.env)
                env.pop(name)
                self.assertIn("authenticated approval",
                              entry_block_reason(now=self.now, environ=env))
        env = dict(self.env)
        env["PAPER_REGIME_APPROVAL_HMAC_SHA256"] = "0" * 64
        self.assertIn("authenticated approval",
                      entry_block_reason(now=self.now, environ=env))

    def test_approval_is_bound_to_digest_and_expiry(self):
        altered = dict(self.env)
        altered["PAPER_REGIME_APPROVED_SHA256"] = "0" * 64
        self.assertIn("authenticated approval",
                      entry_block_reason(now=self.now, environ=altered))
        altered = dict(self.env)
        altered["PAPER_REGIME_APPROVAL_EXPIRES_AT"] = (self.now + timedelta(hours=1)).isoformat()
        self.assertIn("authenticated approval",
                      entry_block_reason(now=self.now, environ=altered))

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
