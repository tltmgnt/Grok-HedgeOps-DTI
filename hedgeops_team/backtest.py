"""Offline expanding-window, out-of-sample evaluation. No order execution."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math

from .core import HedgeOpsTeam, _validate

ACTIONS = frozenset({"BUY", "SELL", "HOLD"})

@dataclass(frozen=True)
class Prediction:
    origin: int
    outcome: int
    action: str
    confidence: float
    realized_return: float
    direction_correct: bool | None
    paper_only: bool = True

    def to_dict(self):
        return asdict(self)

def validate_bars(bars):
    """Validate every bar before constructing folds or scoring outcomes."""
    if not isinstance(bars, (list, tuple)) or len(bars) < 2:
        raise ValueError("at least two bars required")
    # Reuse the same price and chronological constraints as live decision support.
    _validate(bars, {"equity": 1, "cash": 1, "exposure_pct": 0, "drawdown_pct": 0})
    return tuple(float(bar["close"]) for bar in bars)

def _integer(value, name, minimum):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")

def walk_forward_splits(n, train_size, test_size, gap=0):
    """Yield (train indices, test indices) with an expanding historical window."""
    for name, value, minimum in (("n", n, 2), ("train_size", train_size, 2), ("test_size", test_size, 1), ("gap", gap, 0)):
        _integer(value, name, minimum)
    if train_size + gap >= n:
        raise ValueError("insufficient bars for a test origin")
    start = train_size + gap
    while start < n:
        end = min(n, start + test_size)
        yield tuple(range(start - gap)), tuple(range(start, end))
        start = end

def _prediction(origin, outcome, action, confidence, prices):
    if action not in ACTIONS or not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("invalid prediction")
    realized = prices[outcome] / prices[origin] - 1
    correct = None if action == "HOLD" else (realized > 0 if action == "BUY" else realized < 0)
    return Prediction(origin, outcome, action, float(confidence), realized, correct)

def evaluate_walk_forward(team, bars, portfolio, *, train_size, test_size, gap=0, horizon=1):
    """At origin i, the strategy receives only bars[:i+1]; future is scoring-only."""
    if not isinstance(team, HedgeOpsTeam):
        raise TypeError("team must be HedgeOpsTeam")
    prices = validate_bars(bars)
    _integer(horizon, "horizon", 1)
    result = []
    for train, test in walk_forward_splits(len(bars), train_size, test_size, gap):
        for origin in test:
            outcome = origin + horizon
            if outcome >= len(bars):
                continue
            # No fitting API: expanding folds determine eligible origins only.
            # Defensive snapshots isolate the strategy from caller-owned data.
            from copy import deepcopy
            report = team.analyze(deepcopy(list(bars[:origin + 1])), deepcopy(portfolio))
            if report.paper_only is not True:
                raise ValueError("non-paper report")
            result.append(_prediction(origin, outcome, report.action, report.confidence, prices))
    return tuple(result)

def baseline_predictions(bars, origins, *, horizon=1, action="BUY"):
    prices = validate_bars(bars)
    _integer(horizon, "horizon", 1)
    if action not in ACTIONS:
        raise ValueError("invalid baseline action")
    if not isinstance(origins, (list, tuple)) or any(isinstance(i, bool) or not isinstance(i, int) for i in origins):
        raise ValueError("invalid origins")
    if len(set(origins)) != len(origins) or list(origins) != sorted(origins):
        raise ValueError("origins must be strictly increasing")
    if any(i < 0 or i + horizon >= len(prices) for i in origins):
        raise ValueError("origin outside scoring range")
    return tuple(_prediction(i, i + horizon, action, 1.0 if action != "HOLD" else 0.0, prices) for i in origins)

def summarize(predictions, *, bucket_count=5):
    _integer(bucket_count, "bucket_count", 1)
    if not isinstance(predictions, (list, tuple)):
        raise ValueError("predictions must be a sequence")
    if any(not isinstance(p, Prediction) or not p.paper_only or p.action not in ACTIONS or p.direction_correct not in (True, False, None) for p in predictions):
        raise ValueError("invalid prediction record")
    if any(p.action == "HOLD" and p.direction_correct is not None or p.action != "HOLD" and p.direction_correct is None for p in predictions):
        raise ValueError("invalid abstention record")
    if len({p.origin for p in predictions}) != len(predictions):
        raise ValueError("duplicate origins")
    decided = [p for p in predictions if p.direction_correct is not None]
    total = len(predictions)
    buckets = []
    for i in range(bucket_count):
        members = [p for p in decided if min(bucket_count - 1, int(p.confidence * bucket_count)) == i]
        buckets.append({"bucket": i, "count": len(members), "mean_confidence": sum(p.confidence for p in members) / len(members) if members else None, "accuracy": sum(p.direction_correct for p in members) / len(members) if members else None})
    return {
        "total": total,
        "decided": len(decided),
        "abstained": total - len(decided),
        "coverage": len(decided) / total if total else None,
        "directional_accuracy": sum(p.direction_correct for p in decided) / len(decided) if decided else None,
        "mean_realized_return": sum(p.realized_return for p in predictions) / total if total else None,
        "calibration_buckets": buckets,
    }
