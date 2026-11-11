"""Offline point-in-time regime research tests (synthetic fixtures only)."""
import copy
import unittest

from market_regime_validation import classify, validate_holdout


def sample(**updates):
    row = {
        "decision_at": "2020-03-10T21:00:00Z",
        "observed_at": "2020-03-10T20:00:00Z",
        "outcome_end_at": "2020-03-11T21:00:00Z",
        "source_id": "SYNTHETIC/NOT_REAL",
        "evidence_verified": True,
        "trend_pct": 3.0,
        "breadth_fraction": 0.65,
        "realized_vol_pct": 15.0,
        "strategy_forward_return": 0.01,
        "benchmark_forward_return": 0.005,
    }
    row.update(updates)
    return row


class RegimeValidationTests(unittest.TestCase):
    def test_bull_bear_neutral_and_conflict(self):
        self.assertEqual(classify(sample()), "BULL")
        self.assertEqual(classify(sample(trend_pct=-5, breadth_fraction=0.3)), "BEAR")
        self.assertEqual(classify(sample(trend_pct=0, breadth_fraction=0.5)), "NEUTRAL")
        self.assertEqual(classify(sample(trend_pct=5, breadth_fraction=0.2)), "UNKNOWN")
        self.assertEqual(classify(sample(realized_vol_pct=60)), "UNKNOWN")

    def test_unverified_future_stale_and_invalid_fail_closed(self):
        changes = [
            {"evidence_verified": False},
            {"observed_at": "2020-03-11T00:00:00Z"},
            {"observed_at": "2020-02-01T00:00:00Z"},
            {"source_id": ""},
            {"trend_pct": float("nan")},
            {"breadth_fraction": 1.2},
            {"realized_vol_pct": -1},
            {"decision_at": "2020-03-10T21:00:00"},  # no offset
        ]
        for change in changes:
            with self.subTest(change=change):
                self.assertEqual(classify(sample(**change)), "UNKNOWN")

    def test_forward_outcomes_never_influence_classification(self):
        row = sample()
        variant = copy.deepcopy(row)
        variant["strategy_forward_return"] = -0.8
        variant["benchmark_forward_return"] = 0.8
        self.assertEqual(classify(row), classify(variant))

    def test_holdout_excludes_pre_split_and_future_outcomes(self):
        history = [
            sample(decision_at="2020-03-01T21:00:00Z",
                   observed_at="2020-03-01T20:00:00Z",
                   outcome_end_at="2020-03-11T21:00:00Z"),
            sample(),
            sample(decision_at="2020-03-12T21:00:00Z",
                   observed_at="2020-03-12T20:00:00Z",
                   outcome_end_at="2020-04-01T21:00:00Z"),
        ]
        result = validate_holdout(history, holdout_start="2020-03-10T00:00:00Z",
                                  evaluated_through="2020-03-20T00:00:00Z")
        self.assertEqual(result["included"], 1)
        self.assertEqual(result["excluded_outside_evaluation_window"], 2)
        self.assertEqual(result["by_regime"]["BULL"]["count"], 1)
        self.assertAlmostEqual(result["observations"][0]["prototype_net_return"], 0.009)
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["observations"][0]["execution_authorized"])

    def test_bear_abstains_even_with_positive_forward_returns(self):
        row = sample(trend_pct=-6, breadth_fraction=0.3,
                     strategy_forward_return=0.2)
        result = validate_holdout([row], holdout_start="2020-03-10T00:00:00Z",
                                  evaluated_through="2020-03-12T00:00:00Z")
        self.assertEqual(result["observations"][0]["prototype_net_return"], 0)
        self.assertEqual(result["observations"][0]["regime"], "BEAR")

    def test_duplicate_and_invalid_windows_rejected(self):
        row = sample()
        with self.assertRaises(ValueError):
            validate_holdout([row, row], holdout_start="2020-03-10T00:00:00Z",
                             evaluated_through="2020-03-20T00:00:00Z")
        with self.assertRaises(ValueError):
            validate_holdout([row], holdout_start="2020-03-20T00:00:00Z",
                             evaluated_through="2020-03-10T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
