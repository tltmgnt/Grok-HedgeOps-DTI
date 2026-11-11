"""Deterministic offline tests for the non-executing regime decision table."""
import unittest

from market_regime_policy import decide_regime, decision_table


class MarketRegimePolicyTests(unittest.TestCase):
    def test_unverified_labels_always_hold(self):
        for label in ("BULL", "NEUTRAL", "BEAR", "", "nonsense", None):
            with self.subTest(label=label):
                decision = decide_regime(label)
                self.assertEqual(decision.regime, "UNKNOWN")
                self.assertIn("HOLD_NEW_ENTRIES", decision.new_long_entries)
                self.assertFalse(decision.execution_authorized)

    def test_reviewed_regimes_map_to_explicit_playbooks(self):
        expected = {
            "BULL": "BULL_CONTINUATION_RESEARCH",
            "NEUTRAL": "RANGE_OR_UNCERTAIN_RESEARCH",
            "BEAR": "CAPITAL_PRESERVATION_RESEARCH",
        }
        for label, mode in expected.items():
            with self.subTest(label=label):
                decision = decide_regime(label, evidence_verified=True)
                self.assertEqual(decision.mode, mode)
                self.assertFalse(decision.execution_authorized)
        self.assertIn("HOLD_NEW_ENTRIES",
                      decide_regime("BEAR", evidence_verified=True).new_long_entries)

    def test_invalid_or_missing_reviewed_input_fails_closed(self):
        for label in (None, "mixed", "BULL/BEAR", "UNKNOWN", ""):
            self.assertEqual(decide_regime(label, evidence_verified=True).regime,
                             "UNKNOWN")

    def test_policy_never_grants_broker_authority(self):
        for item in decision_table().values():
            self.assertFalse(item.execution_authorized)
        self.assertEqual(set(decision_table()),
                         {"BULL", "NEUTRAL", "BEAR", "UNKNOWN"})


if __name__ == "__main__":
    unittest.main()
