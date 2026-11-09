# Empirical reliability of news topology

Status: research instrumentation, not demonstrated predictive reliability. The
existing keyword, graph and H0 cohorts stay fixed and shadow-only. No result in
this document approves trading or establishes profitability.

## Observed starting point

PR #58 merged the shadow module. The inspected main-branch paper run
[42610781911](https://github.com/tltmgnt/Grok-HedgeOps-DTI/actions/runs/42610781911)
completed on November 9, 2026 at 11:39 UTC. Its `session.json` reports
`MARKET_CLOSED`, with no entry snapshot. That run verifies a closed-market skip,
not news prediction, matured returns, or a profitable trade. Its 90-day artifact
retention is not a durable research archive. Preserve genuine observations before
expiry; keep account data out of public study datasets.

## Freeze the experiment before looking at outcomes

Copy `news_reliability_protocol.example.json` into a private study archive. Its
`frozen_at: null` intentionally marks it as an **unregistered draft**. Choose and
record the actual freeze timestamp, cutoff, universe, sampling rule, execution
price convention, benchmark, costs, stopping rule and economic improvement margin
before held-out observation. Commit or timestamp the exact protocol and code hash
in an independently reviewable record; the evaluator cannot authenticate a typed
timestamp. Never backdate a freeze or reuse an already inspected holdout as unseen.

The supplied numeric defaults are safeguards/hypotheses, not calibrated guarantees:
five calendar days of embargo, at least 60 distinct entry dates, block lengths of
5/10/20 observed entry dates, round-trip costs of 10/25/50 basis points, 20,000
bootstrap replicates, and one declared research trial. Declare **all** variants and
repeated analyses; incrementing a counter does not repair a contaminated holdout.
More declared trials may require more bootstrap replicates for tail resolution.

Do not declare 60 dates sufficient to prove an edge. Use development-only estimates
to plan power for an economically material effect under dependence, then reserve
new dates and an independent replication. Treat unstable estimates or insufficient
power as inconclusive. Do not stop at the first encouraging interval.

## Build a complete prospective registry

Use the point-in-time snapshot and baseline fields described in
[NEWS_TOPOLOGY.md](NEWS_TOPOLOGY.md). Add these fields to each registered opportunity:

| Field | Required meaning |
|---|---|
| `label_policy` | `five_calendar_days_next_session_close` |
| `outcome_status` | `PENDING`, `MISSING` or `OBSERVED` |
| `outcome_known_at` | Actual availability of matched stock/benchmark exit prices, for observed labels |

Retain every registered eligible opportunity, including trades not executed,
failed runs, bad signals and missing outcomes. Keep pending records rather than
dropping them. Eight-day-old pending records are classified as missing; a missing
mature label blocks inference. The five-to-eight-calendar-day exit window allows
the stated five-day horizon and a normal weekend/session gap. Exceptional market
closures require a versioned protocol amendment; do not silently substitute an
optimized exit. The horizon is a fixed research label, **not** the strategy's
-3%/+6%/five-day realized exit rule.

Entry and exit prices must follow the frozen executable-price convention, include
split/dividend handling consistently, and match the benchmark's timestamps. Store
source IDs and the exact observations used in the archive. The current workflow's
selected-candidate snapshots alone do not provide these price labels or complete
all-candidate coverage. The evaluator does not fetch historical prices, reconstruct
first availability, discover omitted rows, or attest that a price was executable.

Keep snapshots, observation registry, protocol, failed records and price provenance
separate from account holdings. Never fabricate mature prices to exercise the tool;
synthetic fixtures belong only in tests and must remain labeled synthetic.

## Paired comparisons instead of cherry-picked cohort means

For every baseline-eligible opportunity, compute all three policy outcomes on the
same dates: keyword, graph and graph-plus-H0. Accepted entries receive stock return
less round-trip costs. A filtered entry receives cash return zero. Then compare:

1. Graph minus keyword — does the simpler graph filter help?
2. **H0 minus graph** — does topology add anything beyond the graph?
3. H0 minus keyword — does the complete filter help relative to the current baseline?

The benchmark component cancels in these paired differences when the same benchmark
is assigned to both policies. These opportunity averages are not investable portfolio
returns. Different cash exposure can explain improvement; independently test risk,
factor exposure, capital constraints, turnover, drawdown and cash yield before
interpreting it as alpha. Use a separate portfolio replay for actual execution rules.

The evaluator averages symbols within each Eastern entry date, then resamples
contiguous date clusters jointly for all policy comparisons using a seeded circular
block bootstrap. Same-date stocks therefore do not become independent evidence.
Block-size sensitivity addresses some serial dependence; it does not establish
stationarity or remove all market-regime dependence.

Intervals use percentile tails with a Bonferroni allocation over displayed policy
comparisons, block sizes, cost scenarios and declared trials. Coverage is approximate,
not a guaranteed finite-sample error rate. At least three longest blocks and ten
expected replicates in each adjusted tail are required for diagnostics. Too little
data, unresolved labels, draft protocols and low tail resolution produce explicit
blockers and **no statistical intervals**. Zero-width null intervals are not positive
evidence. Results always retain `edge_verdict: UNPROVEN` and `order_authority: false`.

```sh
python news_reliability.py --input archived-observations.json \
  --protocol frozen-protocol.json --asof 2027-03-01T00:00:00Z \
  --output reliability-report.json
```

`protocol_hash` and `registry_hash` make exact reruns comparable; they establish
neither authentic provenance nor complete disclosure. An empty registry produces a
blocked result rather than a zero-return success. Earlier/development rows and
baseline-false rows are counted separately, not quietly mixed into held-out results.

## Review decision

Keep shadow mode until an independent review verifies the archive, protocol timing,
all attempted variants, complete opportunity coverage, label conventions and costs.
Look for an economically useful H0-minus-graph effect that persists on untouched
data, across dependence/cost sensitivity and a fresh replication. If it disappears,
prefer the simpler graph or keyword system. Neither a positive sample mean nor a
`POSITIVE_INTERVAL` diagnostic is a release criterion by itself.

Sources for method choices:

- [Kevin Sheppard, arch time-series bootstrap documentation](https://bashtage.github.io/arch/doc/bootstrap/timeseries-bootstraps.html): fixed-length circular blocks and dependence-aware resampling.
- [Harvey and Liu, Backtesting (2015)](https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF): multiple testing and selection bias in financial backtests.

This implementation uses its own small standard-library bootstrap and does not
claim to implement arch's full inference framework or Harvey/Liu's Sharpe adjustment.
