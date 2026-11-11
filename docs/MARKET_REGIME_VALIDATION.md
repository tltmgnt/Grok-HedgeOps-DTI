# Point-in-time market-regime research and historical holdout

**Status:** Experimental research-only prototype stacked on the
[bull/neutral/bear decision table](MARKET_REGIME_DECISION_TABLE.md).
This work does **not** change the broker pipeline, enable trading or
establish profitable alpha in any market.

## Data contract

Supply JSONL records with a timezone-aware `decision_at` and `observed_at`,
a nonblank `source_id`, and `evidence_verified` boolean. Observations must be
available **before or at** decision time and no older than seven calendar days.
Required observations:

- `trend_pct`: signed benchmark-trend measure in percent, computed using
  only history known by `observed_at`;
- `breadth_fraction`: fraction of a documented, survivorship-bias-controlled
  universe meeting a preregistered positive trend criterion, 0–1;
- `realized_vol_pct`: trailing annualized volatility as a percent;
- `outcome_end_at`: later date when a forward outcome can be evaluated;
- `strategy_forward_return` and `benchmark_forward_return`: externally
  supplied **decimal** simple returns (0.01 = +1%), used **only for scoring**.

A source ID and `evidence_verified=True` are *assertions by the dataset
preparer*, **not** independently verified by software. Research reports using
unverified historical data are not acceptance evidence.

### Illustrative classifier (thresholds NOT optimized)

| Condition at decision time | Prototype label | Follow-up |
| --- | --- | --- |
| Trend at least +2%, breadth at least 55%, vol at most 25% | BULL | Research continuation, never automatically buy |
| Trend at most −2%, breadth at most 45% | BEAR | Cash benchmark, no new long entries under proposed policy |
| Trend between −2% and +2%, breadth between 45% and 55% | NEUTRAL | No new entries under proposed policy |
| Unverified, stale, missing, contradictory, extreme or invalid | UNKNOWN | HOLD and investigate evidence |

These values are deliberately *illustrative placeholders*, not calibrated
market thresholds or a fitted model. A future research proposal must state
exact benchmark, lookback, price adjustments, universe membership and volatility
estimator and independently validate them before a regime label may guide
operations.

## Offline holdout scoring

`market_regime_validation.py` accepts historical JSONL snapshots, a fixed
holdout start and evaluation cutoff. It excludes decisions before the holdout
start and decisions whose future outcomes are not yet complete. The classifier
does not read forward returns. A BULL-only **hypothetical research baseline**
uses the supplied strategy return minus an assumed 0.1% round-trip cost;
NEUTRAL/BEAR/UNKNOWN are modeled as 0% cash returns. An unfiltered-strategy
and external benchmark comparator are also reported. Sums of per-row returns
are **not portfolio compounded returns** and can overcount overlapping
positions—do not use them as account P/L.

Run with independently reviewed local data (not included here):

```sh
python -m market_regime_validation --input private-snapshots.jsonl \\
  --holdout-start 2023-01-01T00:00:00Z \\
  --evaluated-through 2026-01-01T00:00:00Z \\
  --output regime-report.json
python -m unittest discover -s tests -p 'test_market_regime_validation.py' -v
```

Do not commit private market/provider data, account identifiers or broker
credentials. Treat artifacts as research output, not executable instructions.

## Validation gates not yet completed

1. Build reproducible, licensed point-in-time trend, breadth, volatility and
   asset-universe histories; record adjustments, timestamps and provenance.
2. Preregister classifier features/thresholds on a training period and
   freeze them before the untouched holdout. Account for regime transitions.
3. Use disjoint chronological blocks and purge overlapping outcome horizons.
   The implementation excludes boundary-crossing training rows but does not
   model overlapping holdings or correlated positions.
4. Analyze realistic slippage, transaction costs, unavailable prices,
   execution latency, overnight gaps, missed stops and drawdown.
5. Compare risk, turnover and outcomes by regime with uncertainty intervals,
   walk-forward sensitivity checks and a cash baseline, including failures.
6. Require independent review and all existing ledger/order/risk gates before
   any separate operational integration; this code must remain offline.

**No external data has been downloaded or historical performance established.**
