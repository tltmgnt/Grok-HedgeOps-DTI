# Grok–HedgeOps–DTI Ω — Decision Topology v1

**Implementation scope: offline, additive, advisory-only.** This repository has
multiple agents and broker workflows, including a separately gated **live** order
path. This addition does **not** connect to or alter any broker, scheduler,
paper-order, live-order, risk limit, approval gate, kill switch or trading
workflow. No new environment variables, credentials, permissions or API calls.

## Architecture adapted to the actual repository

The two supported evidence graph sources are intentionally separate:

1. The offline deterministic `hedgeops_team.core.HedgeOpsTeam` has **four
   mandatory assessments**: `temporal`, `strategic`, `risk`, `adversarial`.
   A fifth `adapter` assessment appears only if the external strategic adapter
   fails. This is *not* the six-role system in the sibling HedgeOps repository.
2. The xAI/Grok `agent.py` returns 13 required *structured-output fields*
   via `report_validation.validate_report`. The graph projects all fields,
   including any additional schema-valid fields, with no claim that the model's
   statements are true, independent or authenticated.

Both are typed, bounded, directed acyclic **review graphs**. Input digests are
plain SHA-256 content fingerprints; they are **not signatures**, authenticated
source proofs or assurance promotions. All projections set `paper_only=True`,
`human_review_required=True`, `execution_authorized=False`.

## Entry points

From the repository root (no broker or provider call):

```python
from hedgeops_team import HedgeOpsTeam
bars = [{"timestamp": f"2026-01-{i+1:02d}", "close": 100 + i}
        for i in range(6)]
portfolio = {"equity": 200, "cash": 200,
             "exposure_pct": 0, "drawdown_pct": 0}

report, graph = HedgeOpsTeam().analyze_with_topology(bars, portfolio)
assert report.paper_only is True
assert graph.to_dict()["execution_authorized"] is False
```

For *already obtained* Grok report dictionaries, without requesting a new model
response:

```python
from hedgeops_team.decision_topology import build_structured_report_topology
# report = previously validated agent.analyze(problem) response
graph = build_structured_report_topology(report)
```

`agent.analyze_with_topology(problem)` is an optional convenience wrapper
around `agent.analyze(problem)`, returning `(report, graph)`. This **does**
call the existing xAI API and requires separately configured model credentials;
it never sends an order and does not change the ordinary CLI behavior.

## Graph contract and fail-closed tests

A team graph records four unique mandatory agents, each rationale/action/
confidence, unverified evidence *identifiers*, warnings, review reasons and the
original BUY/SELL/HOLD **paper advisory**. Extra adapter evidence appears only
for a recorded adapter failure. SELL remains directional-only; HOLD and SELL
cannot suggest a new position. Known veto reasons cannot produce BUY/SELL.

A Grok graph preserves every structured-response field, retaining its JSON
content in a node, but labels all content **unverified**. A structurally valid
recommendation is not factually validated.

The validator rejects unsupported states, missing mandatory roles or fields,
duplicate node IDs/edges, invalid typed links, dangling references, incomplete
dependency pathways, inconsistent report digest, executable outcomes and graph
cycles. The validator is a structural guard, not an independent market-risk
assessment. All inputs and graph sizes are bounded.

## What-if branches

```python
from hedgeops_team.decision_topology import (
    TemporalCapacity, simulate_temporal_branches, simulate_regime_branches,
)

state = TemporalCapacity(
    horizon_minutes=120, committed_minutes=70, recovery_minutes=10,
    fragmentation_index=0.25, autonomy_fraction=0.8,
)
branches = simulate_temporal_branches(state, required_minutes=30)
regimes = simulate_regime_branches(("BULL", "BEAR"))  # UNKNOWN without evidence
```

The temporal formula is a **provisional illustrative proxy**:

```text
effective_minutes =
    max(0, horizon_minutes - committed_minutes - recovery_minutes)
    * (1 - fragmentation_index) * autonomy_fraction
```

Changing a fragmentation number is not evidence that a real-world intervention
can change it. The bounded regime branch simulator **reuses the existing
`market_regime_policy.decide_regime()` static research table**, not a latent
regime predictor. Its caller-supplied `evidence_verified` flag is not an
independent verification service. By default, all labels map to UNKNOWN/HOLD.
Neither temporal feasibility nor a BULL scenario creates an actionable order.

## Decision family maturity

The ten families are overlapping categories, **not** an exhaustive or disjoint
mathematical partition of every possible decision tree.

| Family | v1 capability |
| --- | --- |
| Axiomatic | Bounded: existing deterministic risk vetoes / graph invariants |
| Probabilistic | Research only; requires calibration and real baselines |
| Game-theoretic | Research only; no specified game/equilibrium |
| Reinforcement learning | Research only; no policy training or evaluation |
| Counterfactual | Bounded: time sensitivity only, no causal identification |
| Regime-switching | Bounded: static advisory table only, no learned transitions |
| Behavioral | Research only; no validated behavioral model |
| Information-theoretic | Research only; no measured information acquisition |
| Topological | Bounded: dependency DAG, not systemic contagion inference |
| Meta-decision | Research only; no autonomous policy rewriting |

## Verification and deployment boundaries

```sh
python -m pytest tests/test_decision_topology.py -q
python -m pytest tests/ -q
python release_check.py --verbose
```

The existing CI runs against Python 3.10, 3.12 and 3.13 with the repository's
pinned dependencies. This work does not assert new economic alpha, causal
validity, independent data provenance or production certification.

Future adoption should compare any topology benefit against the simpler
existing `DecisionReport` and `validate_report()` representations on
prespecified audit tasks before adding calibrated probabilistic or adaptive
methods. Maintain the current execution boundary and independent risk review.

## Risk veto audit and replay

Graphs from `HedgeOpsTeam.analyze_with_topology()` link each triggered
drawdown, exposure, or volatility veto to the risk assessment's input
reference and the resulting HOLD. The veto records the observed value,
configured limit, threshold, and comparison used by the policy.
Price references share the `input_bars` source group and carry the last
supplied bar timestamp when available. Portfolio references share
`input_portfolio`. These groups identify shared inputs within one decision.
Source authentication and freshness remain unverified.

`team.replay_portfolio_risk(bars, portfolio, field="drawdown_pct", value=0.19)`
returns before and after topologies, added and cleared review reasons,
and a disposition-change flag. It supports drawdown and exposure with the
deterministic strategy. A cleared gate can leave the recommendation at HOLD
when another veto applies.

To measure review value, use the same labeled single-veto and simultaneous-veto
fixtures with `DecisionReport` and the topology. Ask reviewers to identify
the decisive gates, give their observed values and thresholds, and explain
whether changing one input clears HOLD. Counterbalance which format each
reviewer sees first and record answer accuracy and time to completion.

Strategy disagreement and insufficient directional consensus show both
assessments' actions and sources. The independent-strategy blocker shows
the observed strategy source and the required one. The history blocker
shows the observed and minimum bar counts. Each blocker has its own edge
to HOLD, so reviewers can identify simultaneous blockers.
