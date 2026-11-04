# Increment 4 — Statistical robustness and stress tests

This is a paper-only, offline research extension to Increment 3. It does not execute trades.

## Included
- Seeded moving-block bootstrap percentile intervals for means, with an explicit block length.
- Paired directional-accuracy differences against baseline predictions on identical origins and horizons.
- Past-only market regime labeling (up/down/sideways/insufficient history).
- Non-mutating missing-bar and price-shock stress transformations.
- Bonferroni correction for exploratory multiple comparisons.

## Example
```python
from hedgeops_team import HedgeOpsTeam
from hedgeops_team.backtest import evaluate_walk_forward, baseline_predictions
from hedgeops_team.robustness import paired_accuracy_difference

bars = [{"timestamp": f"2026-01-{i+1:02d}", "close": 100 + i} for i in range(22)]
portfolio = {"equity": 200, "cash": 200, "exposure_pct": 0, "drawdown_pct": 0}
candidate = evaluate_walk_forward(HedgeOpsTeam(), bars, portfolio, train_size=5, test_size=3)
baseline = baseline_predictions(bars, [p.origin for p in candidate], action="BUY")
print(paired_accuracy_difference(candidate, baseline, block_length=2, replicates=500, seed=42))
```

## Interpretation limits
Bootstrap intervals describe resampling uncertainty under a chosen dependence/block model. They are not proof of future performance, causality, independence, or statistically valid selection after extensive tuning. No transaction costs, slippage, or portfolio-return simulation is included.

Paired accuracy comparisons exclude any origin at which either strategy abstains; the excluded count is reported to avoid hiding the denominator. Regimes use only historical prices at each origin. Stress transformations alter data copies and must be followed by re-evaluation to assess strategy sensitivity.

Run `python -m pytest tests/ -q` and `python release_check.py --verbose` before merge.
