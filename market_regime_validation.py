"""Offline, point-in-time regime research and holdout scoring. NO order authority.

The classifier uses only independently-reviewed market observations available
at decision time. Future returns are used only after classification for
illustrative holdout evaluation, never as classifier inputs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import math
from pathlib import Path

from market_regime_policy import decide_regime

VERSION = "regime-prototype-v1"
MAX_AGE = timedelta(days=7)
# Illustrative, predeclared thresholds; NOT trained or empirically validated.
TREND_PCT = 2.0
BULL_BREADTH = 0.55
BEAR_BREADTH = 0.45
MAX_BULL_VOL_PCT = 25.0


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("ISO 8601 timestamp with offset required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    return parsed


def finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError("Finite numeric observation required")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("NaN and infinity are invalid")
    return number


def classify(row):
    """Return regime; invalid, unreviewed, future or stale evidence -> UNKNOWN."""
    try:
        asof, measured = timestamp(row["decision_at"]), timestamp(row["observed_at"])
        age = asof - measured
        if age < timedelta(0) or age > MAX_AGE or row.get("evidence_verified") is not True:
            return "UNKNOWN"
        if not isinstance(row.get("source_id"), str) or not row["source_id"].strip():
            return "UNKNOWN"
        trend = finite_number(row["trend_pct"])
        breadth = finite_number(row["breadth_fraction"])
        volatility = finite_number(row["realized_vol_pct"])
        if not (0 <= breadth <= 1 and 0 <= volatility <= 200):
            return "UNKNOWN"
    except (KeyError, TypeError, ValueError, OverflowError):
        return "UNKNOWN"
    if trend >= TREND_PCT and breadth >= BULL_BREADTH and volatility <= MAX_BULL_VOL_PCT:
        return "BULL"
    if trend <= -TREND_PCT and breadth <= BEAR_BREADTH:
        return "BEAR"
    if -TREND_PCT < trend < TREND_PCT and BEAR_BREADTH < breadth < BULL_BREADTH:
        return "NEUTRAL"
    return "UNKNOWN"  # Conflicting indicators: abstain.


def validate_holdout(rows, *, holdout_start, evaluated_through, round_trip_cost=0.001):
    """Evaluate supplied forward outcomes on holdout only; never learn thresholds.

    Each row has one distinct decision timestamp and outcome_end_at after it.
    Rows with outcomes extending beyond evaluated_through are excluded.
    Returns are assumed supplied in decimal units, not percents. No external
    orders, price series, fills, data access or empirically trained signals.
    """
    split, cutoff = timestamp(holdout_start), timestamp(evaluated_through)
    cost = finite_number(round_trip_cost)
    if cost < 0 or cost >= 1 or split >= cutoff:
        raise ValueError("Invalid evaluation window or cost")
    if not isinstance(rows, list):
        raise ValueError("Expected list of snapshots")
    seen, included, skipped = set(), [], 0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each snapshot must be an object")
        decision, outcome_end = timestamp(row["decision_at"]), timestamp(row["outcome_end_at"])
        if decision in seen:
            raise ValueError("Duplicate decision timestamp: may double count returns")
        seen.add(decision)
        if outcome_end <= decision:
            raise ValueError("Outcome must end after decision")
        if decision < split or outcome_end > cutoff:
            skipped += 1
            continue
        strategy = finite_number(row["strategy_forward_return"])
        benchmark = finite_number(row["benchmark_forward_return"])
        if strategy <= -1 or benchmark <= -1:
            raise ValueError("Return smaller than -100% is invalid")
        label = classify(row)
        gate = decide_regime(label, evidence_verified=(label != "UNKNOWN"))
        exposed = label == "BULL"
        included.append({
            "decision_at": row["decision_at"],
            "regime": gate.regime,
            "research_exposure": "BULL_ONLY" if exposed else "CASH",
            "prototype_net_return": strategy - cost if exposed else 0.0,
            "unfiltered_baseline_return": strategy - cost,
            "cash_return": 0.0,
            "benchmark_return": benchmark,
            "execution_authorized": gate.execution_authorized,
        })
    by_regime = {}
    for label in ("BULL", "NEUTRAL", "BEAR", "UNKNOWN"):
        subset = [x for x in included if x["regime"] == label]
        by_regime[label] = {
            "count": len(subset),
            "prototype_sum": round(sum(x["prototype_net_return"] for x in subset), 8),
            "unfiltered_sum": round(sum(x["unfiltered_baseline_return"] for x in subset), 8),
            "benchmark_sum": round(sum(x["benchmark_return"] for x in subset), 8),
        }
    return {
        "version": VERSION,
        "status": "RESEARCH_ONLY_NOT_VALIDATED",
        "holdout_start": holdout_start,
        "evaluated_through": evaluated_through,
        "round_trip_cost_assumption": cost,
        "included": len(included),
        "excluded_outside_evaluation_window": skipped,
        "by_regime": by_regime,
        "observations": included,
        "execution_authorized": False,
        "limitations": [
            "Returns are supplied inputs, not verified fills or market data",
            "No overlapping-trade portfolio accounting or capital sizing",
            "Thresholds illustrative; no claim of alpha or causal effect",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline regime research ONLY")
    parser.add_argument("--input", required=True, type=Path, help="JSONL snapshots (review for provenance)")
    parser.add_argument("--holdout-start", required=True, help="ISO 8601 timestamp with offset")
    parser.add_argument("--evaluated-through", required=True, help="ISO 8601 timestamp with offset")
    parser.add_argument("--output", type=Path, default=Path("regime-holdout-report.json"))
    args = parser.parse_args(argv)
    rows = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    result = validate_holdout(rows, holdout_start=args.holdout_start,
                              evaluated_through=args.evaluated_through)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
