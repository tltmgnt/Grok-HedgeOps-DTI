"""Offline research acceptance tests, including explicit leakage probes."""
from dataclasses import replace
import pytest
from hedgeops_team import HedgeOpsTeam
from hedgeops_team.backtest import (
    Prediction, baseline_predictions, evaluate_walk_forward, summarize,
    validate_bars, walk_forward_splits,
)

def bars(n=22):
    return [{"timestamp": f"2026-01-{i+1:02d}", "close": 100 + i} for i in range(n)]

def portfolio():
    return {"equity": 200, "cash": 200, "exposure_pct": 0, "drawdown_pct": 0}

def test_splits_have_no_overlap_and_expand():
    folds = list(walk_forward_splits(22, 5, 4, gap=2))
    assert folds[0] == (tuple(range(5)), tuple(range(7, 11)))
    assert folds[1] == (tuple(range(9)), tuple(range(11, 15)))
    assert all(max(train) < min(test) for train, test in folds)

@pytest.mark.parametrize("bad", [0, -1, True, 1.5])
def test_invalid_horizon(bad):
    with pytest.raises(ValueError):
        evaluate_walk_forward(HedgeOpsTeam(), bars(), portfolio(), train_size=5, test_size=3, horizon=bad)

def test_paper_only_and_baseline_alignment():
    result = evaluate_walk_forward(HedgeOpsTeam(), bars(), portfolio(), train_size=5, test_size=3, gap=2)
    assert result and all(p.paper_only and p.outcome == p.origin + 1 for p in result)
    baseline = baseline_predictions(bars(), [p.origin for p in result], action="BUY")
    assert [p.origin for p in baseline] == [p.origin for p in result]
    assert summarize(baseline)["directional_accuracy"] == 1

def test_future_change_cannot_change_earlier_decision():
    original = bars()
    changed = bars()
    changed[-1]["close"] = 1
    a = evaluate_walk_forward(HedgeOpsTeam(), original, portfolio(), train_size=5, test_size=3)
    b = evaluate_walk_forward(HedgeOpsTeam(), changed, portfolio(), train_size=5, test_size=3)
    early_a = [(p.origin, p.action, p.confidence) for p in a if p.origin < len(original) - 1]
    early_b = [(p.origin, p.action, p.confidence) for p in b if p.origin < len(original) - 1]
    assert early_a == early_b

def test_strategy_never_sees_future_bars():
    class GuardedTeam(HedgeOpsTeam):
        def __init__(self):
            super().__init__()
            self.seen = []
        def analyze(self, bars, portfolio):
            self.seen.append(len(bars))
            return super().analyze(bars, portfolio)
    team = GuardedTeam()
    result = evaluate_walk_forward(team, bars(), portfolio(), train_size=5, test_size=3)
    assert team.seen == [p.origin + 1 for p in result]

def test_no_future_outcome_is_scored():
    result = evaluate_walk_forward(HedgeOpsTeam(), bars(), portfolio(), train_size=5, test_size=4, horizon=3)
    assert result and max(p.outcome for p in result) < len(bars())
    assert all(p.outcome - p.origin == 3 for p in result)

def test_abstentions_not_counted_as_correct():
    predictions = (
        Prediction(1, 2, "HOLD", 0, 0.01, None),
        Prediction(2, 3, "BUY", 0.6, -0.01, False),
        Prediction(3, 4, "SELL", 0.6, -0.01, True),
    )
    report = summarize(predictions)
    assert report["total"] == 3
    assert report["decided"] == 2
    assert report["coverage"] == pytest.approx(2/3)
    assert report["directional_accuracy"] == 0.5

def test_empty_summary_has_no_fabricated_accuracy():
    assert summarize(())["directional_accuracy"] is None

def test_invalid_bar_chronology_rejected():
    bs = bars()
    bs[5]["timestamp"] = bs[4]["timestamp"]
    with pytest.raises(ValueError):
        validate_bars(bs)

def test_duplicate_baseline_origins_rejected():
    with pytest.raises(ValueError):
        baseline_predictions(bars(), [5, 5])

def test_nonpaper_report_rejected():
    class Unsafe(HedgeOpsTeam):
        def analyze(self, bars, portfolio):
            return replace(super().analyze(bars, portfolio), paper_only=False)
    with pytest.raises(ValueError, match="non-paper"):
        evaluate_walk_forward(Unsafe(), bars(), portfolio(), train_size=5, test_size=3)

def test_deterministic_repeat():
    a = evaluate_walk_forward(HedgeOpsTeam(), bars(), portfolio(), train_size=5, test_size=3)
    b = evaluate_walk_forward(HedgeOpsTeam(), bars(), portfolio(), train_size=5, test_size=3)
    assert a == b
