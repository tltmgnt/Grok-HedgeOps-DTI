"""Offline robustness diagnostics. Descriptive uncertainty, not trading advice."""
from copy import deepcopy
from dataclasses import dataclass
import math
import random

from .backtest import Prediction, validate_bars

def _integer(value, name, minimum):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")

def _fraction(value, name, low=0, high=1):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low < value < high:
        raise ValueError(f"{name} must be strictly between {low} and {high}")
    return float(value)

def moving_block_sample(values, block_length, rng):
    """Resample contiguous blocks with replacement to preserve short-range dependence."""
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError("nonempty values required")
    _integer(block_length, "block_length", 1)
    if block_length > len(values):
        raise ValueError("block_length exceeds series")
    if not hasattr(rng, "randrange"):
        raise TypeError("rng must supply randrange")
    result = []
    while len(result) < len(values):
        start = rng.randrange(len(values) - block_length + 1)
        result.extend(values[start:start + block_length])
    return tuple(result[:len(values)])

def _finite_values(values):
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError("nonempty values required")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ValueError("finite numeric values required")
    return tuple(float(v) for v in values)

def _percentile(sorted_values, probability):
    position = (len(sorted_values) - 1) * probability
    lo = int(position)
    hi = min(lo + 1, len(sorted_values) - 1)
    weight = position - lo
    return sorted_values[lo] * (1 - weight) + sorted_values[hi] * weight

def block_bootstrap_mean(values, *, block_length, replicates=2000, confidence=0.95, seed=0):
    """Seeded moving-block bootstrap percentile interval for the arithmetic mean."""
    values = _finite_values(values)
    _integer(block_length, "block_length", 1)
    _integer(replicates, "replicates", 2)
    _fraction(confidence, "confidence")
    _integer(seed, "seed", 0)
    if block_length > len(values):
        raise ValueError("block_length exceeds series")
    rng = random.Random(seed)
    means = sorted(sum(moving_block_sample(values, block_length, rng)) / len(values) for _ in range(replicates))
    alpha = (1 - confidence) / 2
    return {"mean": sum(values) / len(values), "lower": _percentile(means, alpha), "upper": _percentile(means, 1 - alpha), "confidence": confidence, "replicates": replicates, "block_length": block_length}

def paired_accuracy_difference(candidate, baseline, *, block_length, replicates=2000, confidence=0.95, seed=0):
    """Compare correctness on identical chronological forecast origins; exclude paired abstentions."""
    if not isinstance(candidate, (list, tuple)) or not isinstance(baseline, (list, tuple)):
        raise ValueError("predictions must be sequences")
    if len(candidate) != len(baseline) or not candidate:
        raise ValueError("paired predictions required")
    if any(not isinstance(c, Prediction) or not isinstance(b, Prediction) for c, b in zip(candidate, baseline)):
        raise ValueError("prediction records required")
    if any((c.origin, c.outcome) != (b.origin, b.outcome) for c, b in zip(candidate, baseline)):
        raise ValueError("misaligned forecast origins or horizons")
    if any(candidate[i].origin >= candidate[i + 1].origin for i in range(len(candidate) - 1)):
        raise ValueError("origins must increase")
    for p in (*candidate, *baseline):
        if not p.paper_only or p.action not in {"BUY", "SELL", "HOLD"} or p.direction_correct not in (True, False, None):
            raise ValueError("invalid paper prediction")
        if (p.action == "HOLD") != (p.direction_correct is None):
            raise ValueError("inconsistent abstention")
    paired = [(float(c.direction_correct) - float(b.direction_correct)) for c, b in zip(candidate, baseline) if c.direction_correct is not None and b.direction_correct is not None]
    if not paired:
        return {"paired_count": 0, "excluded_count": len(candidate), "difference": None, "interval": None}
    return {"paired_count": len(paired), "excluded_count": len(candidate) - len(paired), "difference": sum(paired) / len(paired), "interval": block_bootstrap_mean(paired, block_length=block_length, replicates=replicates, confidence=confidence, seed=seed)}

def regime_at_origin(prices, origin, *, lookback=5, threshold=0.02):
    """Past-only classification; the origin price is the most recent observation."""
    values = _finite_values(prices)
    _integer(origin, "origin", 0)
    _integer(lookback, "lookback", 1)
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or threshold < 0:
        raise ValueError("threshold must be nonnegative finite")
    if any(v <= 0 for v in values):
        raise ValueError("prices must be positive")
    if origin >= len(values):
        raise ValueError("origin outside series")
    if origin < lookback:
        return "insufficient_history"
    change = values[origin] / values[origin - lookback] - 1
    return "up" if change > threshold else "down" if change < -threshold else "sideways"

def summarize_by_regime(bars, predictions, *, lookback=5, threshold=0.02):
    prices = validate_bars(bars)
    if not isinstance(predictions, (list, tuple)):
        raise ValueError("predictions must be a sequence")
    result = {}
    seen = set()
    for prediction in predictions:
        if not isinstance(prediction, Prediction) or not prediction.paper_only or prediction.origin in seen:
            raise ValueError("invalid or duplicate prediction")
        seen.add(prediction.origin)
        if prediction.origin < 0 or prediction.origin >= len(prices):
            raise ValueError("origin outside series")
        regime = regime_at_origin(prices, prediction.origin, lookback=lookback, threshold=threshold)
        group = result.setdefault(regime, {"total": 0, "decided": 0, "correct": 0})
        group["total"] += 1
        if prediction.direction_correct is not None:
            group["decided"] += 1
            group["correct"] += int(prediction.direction_correct)
    return {key: {"total": val["total"], "coverage": val["decided"] / val["total"], "directional_accuracy": val["correct"] / val["decided"] if val["decided"] else None} for key, val in sorted(result.items())}

def stress_missing_bar(bars, index, *, mode="drop"):
    validate_bars(bars)
    _integer(index, "index", 0)
    if index >= len(bars):
        raise ValueError("index outside bars")
    if mode != "drop":
        raise ValueError("only drop mode supported")
    if len(bars) <= 2:
        raise ValueError("cannot remove bar from minimum series")
    changed = deepcopy(list(bars))
    del changed[index]
    validate_bars(changed)
    return changed

def stress_price_shock(bars, index, *, shock_pct):
    validate_bars(bars)
    _integer(index, "index", 0)
    if index >= len(bars):
        raise ValueError("index outside bars")
    if isinstance(shock_pct, bool) or not isinstance(shock_pct, (int, float)) or not math.isfinite(shock_pct) or shock_pct <= -1:
        raise ValueError("shock_pct must be finite and greater than -1")
    changed = deepcopy(list(bars))
    changed[index]["close"] = float(changed[index]["close"]) * (1 + shock_pct)
    validate_bars(changed)
    return changed

def bonferroni_adjust(p_values):
    if not isinstance(p_values, (list, tuple)):
        raise ValueError("p-values must be a sequence")
    if any(isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1 for p in p_values):
        raise ValueError("p-values must be between 0 and 1")
    return tuple(min(1.0, float(p) * len(p_values)) for p in p_values)
