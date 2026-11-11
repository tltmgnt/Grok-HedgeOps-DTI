# Bull / neutral / bear market regime decision table (research-only)

**Status:** Proposed research policy, not validated alpha, an executable trade
signal, or trading authorization. This policy intentionally has **no broker,
credential, network, scheduling or order-submission integration**. The current
paper-trading risk limits, exits, human approvals and kill switches are unchanged.

## Decisions

| Independently verified market regime | New long entries | Research playbook | Required evidence and evaluation |
| --- | --- | --- | --- |
| **Bull**: sustained positive trend, confirming breadth, acceptable volatility | **Research candidate only**; never automatically authorize a buy | Bull continuation: rank relative strength and catalyst quality; benchmark existing -3%/+6%/5-day exits against *simulated* trailing/volatility-aware alternatives | Timestamped benchmark trend, breadth, volatility, costs, liquidity, sector context; report bull-cohort out-of-sample net outcomes and drawdown |
| **Neutral / range**: weak or conflicting direction with adequate reliable data | **HOLD new entries** under this unvalidated regime policy | Research false-breakout filters, range behavior and a cash baseline; test whether any strategy beats not trading | Separate range cohorts, turnover, whipsaw rate, spreads/slippage and net returns |
| **Bear**: sustained negative trend or widespread risk-off conditions | **HOLD new long entries** under this unvalidated regime policy | Capital-preservation first; compare cash-only to restricted long exposure; explore inverse/hedges only as separate research requiring independent risk approval | Drawdown, downside gaps, liquidity stress, tail loss, correlated exposures, regime-transition performance |
| **Unknown / stale / conflicting** | **HOLD new entries** | Abstain; gather and validate evidence before classifying | Record missing sources, timestamps, conflicting indicators, abstention rate and reason |

**Critical distinction:** BULL is a research-candidate label, **not** a bypass of
the existing broker, market-hours, risk, ledger, approval or no-duplicate-order
gates. No regime label authorizes a trade. Bear and neutral directions are
not invitations to short, buy inverse products or change position limits.

## Regime evidence contract (future research integration)

A label should be asserted only after independent review of point-in-time,
time-zone-aware observations from at least trend, breadth and realized-volatility
dimensions. Indicators and thresholds must be preregistered and tested across
unseen market periods: this document does **not** claim empirically validated
cutoffs or that a regime can be known in real time. Missing/stale or contradictory
evidence maps to UNKNOWN, not to optimistic BULL. Retain indicator values,
sources, timestamps, missingness and classifier version for every label.
Avoid look-ahead bias and restated data in backtests.

## Safe implementation and boundary

`market_regime_policy.py` provides a deterministic, **advisory** map from a
reviewed label to a research playbook. Call
`decide_regime("BEAR", evidence_verified=True)` for an example. If
`evidence_verified` is false or the label is invalid, it returns UNKNOWN/HOLD.
All decisions expose `execution_authorized=False`.

`python -m unittest discover -s tests -p 'test_market_regime_policy.py' -v`
runs isolated tests. This file is intentionally not imported by the broker
execution pipeline. That separation prevents an unvalidated regime heuristic
from silently enabling/disabling orders or overriding established controls.

## Evaluation design before any operational adoption

1. **Define regimes ex ante:** preregister metrics and thresholds; log the
   exact information available at the decision time and avoid look-ahead.
2. **Use three baselines:** the current fixed-exit paper strategy, all-cash/no
   trade, and a simple low-cost diversified reference where suitable.
3. **Compare unseen cohorts:** bull, neutral, bear, crisis-transition and
   ambiguous observations, with walk-forward splits and sensitivity analyses.
4. **Use net execution assumptions:** estimate spread, slippage, gap-through,
   financing/borrow (if applicable), and portfolio-level drawdown; no guaranteed
   stop price. Scheduled observations are not continuous protection.
5. **Require independent review:** no adaptive sizing, new exits, options,
   hedges, shorts or live deployment until code review, integration tests,
   trading-risk approval and explicit opt-in.

**Success is not guaranteed in any regime.** A good abstention policy may be
more valuable than marginal simulated profits. A meaningful claim requires
replication outside the development sample, including losing and skipped runs.
