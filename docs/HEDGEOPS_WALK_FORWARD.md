# Increment 3 — Evidence-first walk-forward research

This additive, offline-only module evaluates HedgeOpsTeam decisions at historical forecast origins without broker APIs.

## Example
```python
from hedgeops_team import HedgeOpsTeam
from hedgeops_team.backtest import evaluate_walk_forward, baseline_predictions, summarize

bars = [{"timestamp": f"2026-01-{i+1:02d}", "close": 100 + i} for i in range(20)]
portfolio = {"equity": 200, "cash": 200, "exposure_pct": 0, "drawdown_pct": 0}
predictions = evaluate_walk_forward(HedgeOpsTeam(), bars, portfolio, train_size=5, test_size=3, gap=1)
baseline = baseline_predictions(bars, [p.origin for p in predictions], action="BUY")
print(summarize(predictions))
print(summarize(baseline))
```

## Design boundaries
- Expanding training-window indices and optional embargo gap determine forecast origins. **No model is fitted**: the current HedgeOpsTeam is deterministic and uses historical prefixes only.
- Each forecast sees bars through its origin; the future outcome price is accessed only when scoring.
- Baselines use identical origins and horizons.
- HOLD is an abstention, not a correct directional prediction.
- Confidence buckets are descriptive diagnostics; current confidence is **not calibrated probability**.
- No trading costs, slippage, portfolio P&L, survivorship-bias correction, or profitability claim.
- Risk vetoes and paper-only enforcement remain in place.

Run `python -m pytest tests/ -q` and `python release_check.py --verbose`.

## Future increments
Paired robustness analysis, historical data provenance, and adversarial strategy disagreement should follow only after this evaluation foundation is green.
