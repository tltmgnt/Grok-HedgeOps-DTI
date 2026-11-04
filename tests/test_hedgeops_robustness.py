"""Increment 4: reproducible robustness, leakage and paired-baseline tests."""
from dataclasses import replace
import random
import pytest
from hedgeops_team import HedgeOpsTeam
from hedgeops_team.backtest import Prediction, evaluate_walk_forward, baseline_predictions
from hedgeops_team.robustness import (
    moving_block_sample, block_bootstrap_mean, paired_accuracy_difference,
    regime_at_origin, summarize_by_regime, stress_missing_bar,
    stress_price_shock, bonferroni_adjust,
)

def bars(n=22):
    return [{"timestamp": f"2026-01-{i+1:02d}", "close": 100 + i} for i in range(n)]

def portfolio():
    return {"equity": 200, "cash": 200, "exposure_pct": 0, "drawdown_pct": 0}

def test_seeded_block_sample_preserves_length_and_local_blocks():
    result = moving_block_sample([1, 2, 3, 4, 5, 6], 2, random.Random(42))
    assert len(result) == 6
    assert result == moving_block_sample([1, 2, 3, 4, 5, 6], 2, random.Random(42))

def test_constant_series_bootstrap_is_exact():
    result = block_bootstrap_mean([0.5] * 10, block_length=3, replicates=100, seed=11)
    assert result["mean"] == result["lower"] == result["upper"] == 0.5

def test_bootstrap_reproducible():
    args = dict(block_length=2, replicates=100, seed=7)
    assert block_bootstrap_mean([0, 1, 0, 1, 1, 0], **args) == block_bootstrap_mean([0, 1, 0, 1, 1, 0], **args)

@pytest.mark.parametrize("bad", [0, -1, True, 1.5])
def test_bad_block_length_rejected(bad):
    with pytest.raises(ValueError):
        block_bootstrap_mean([0, 1], block_length=bad, replicates=10)

def test_paired_comparison_aligned_baseline():
    bs = bars()
    candidate = evaluate_walk_forward(HedgeOpsTeam(), bs, portfolio(), train_size=5, test_size=3)
    baseline = baseline_predictions(bs, [p.origin for p in candidate], action="BUY")
    result = paired_accuracy_difference(candidate, baseline, block_length=2, replicates=100, seed=4)
    assert result["paired_count"] == len(candidate)
    assert result["difference"] == 0
    assert result["interval"]["lower"] == result["interval"]["upper"] == 0

def test_misaligned_pairs_rejected():
    candidate = (Prediction(2, 3, "BUY", .6, .1, True),)
    baseline = (Prediction(2, 4, "BUY", 1, .1, True),)
    with pytest.raises(ValueError, match="misaligned"):
        paired_accuracy_difference(candidate, baseline, block_length=1, replicates=10)

def test_abstentions_excluded_without_inflation():
    candidate = (Prediction(2, 3, "HOLD", 0, .1, None), Prediction(3, 4, "BUY", .6, -.1, False))
    baseline = (Prediction(2, 3, "BUY", 1, .1, True), Prediction(3, 4, "BUY", 1, -.1, False))
    result = paired_accuracy_difference(candidate, baseline, block_length=1, replicates=20)
    assert result["paired_count"] == 1
    assert result["excluded_count"] == 1
    assert result["difference"] == 0

def test_all_abstentions_return_no_interval():
    candidate = (Prediction(2, 3, "HOLD", 0, .1, None),)
    baseline = (Prediction(2, 3, "BUY", 1, .1, True),)
    result = paired_accuracy_difference(candidate, baseline, block_length=1)
    assert result["difference"] is None and result["interval"] is None

def test_regime_uses_past_only():
    prices = [100, 101, 102, 103, 104, 105, 1000]
    assert regime_at_origin(prices, 5, lookback=3, threshold=.02) == regime_at_origin(prices[:-1], 5, lookback=3, threshold=.02)
    assert regime_at_origin(prices, 2, lookback=3) == "insufficient_history"

def test_regime_summary_coverage():
    bs = bars()
    predictions = evaluate_walk_forward(HedgeOpsTeam(), bs, portfolio(), train_size=5, test_size=3)
    result = summarize_by_regime(bs, predictions, lookback=3)
    assert sum(v["total"] for v in result.values()) == len(predictions)

def test_stress_copies_do_not_mutate_original():
    bs = bars()
    before = [dict(b) for b in bs]
    dropped = stress_missing_bar(bs, 8)
    shocked = stress_price_shock(bs, 8, shock_pct=-0.2)
    assert bs == before
    assert len(dropped) == len(bs) - 1
    assert shocked[8]["close"] == pytest.approx(bs[8]["close"] * .8)

@pytest.mark.parametrize("shock", [-1, -1.5, float("nan"), float("inf"), True])
def test_invalid_shock_rejected(shock):
    with pytest.raises(ValueError):
        stress_price_shock(bars(), 3, shock_pct=shock)

def test_bonferroni():
    assert bonferroni_adjust([0.01, 0.2, 0.9]) == pytest.approx((0.03, 0.6, 1.0))
    assert bonferroni_adjust([]) == ()

def test_nonpaper_predictions_rejected():
    candidate = (replace(Prediction(2, 3, "BUY", .6, .1, True), paper_only=False),)
    baseline = (Prediction(2, 3, "BUY", 1, .1, True),)
    with pytest.raises(ValueError, match="invalid paper"):
        paired_accuracy_difference(candidate, baseline, block_length=1, replicates=10)
