# Grok-HedgeOps-DTI Agent Team

An additive, offline-first multi-agent decision-support package for the existing
Grok-HedgeOps-DTI paper-trading project. It does **not** replace `paper_trader.py`,
connect to a broker, submit orders, or enable live trading.

## Team

| Role | Responsibility |
|---|---|
| Temporal Analyst | Multi-period trend, return volatility, and basic regime assessment |
| Strategic Analyst | Competing BUY / SELL / HOLD scenarios |
| Risk Analyst | Volatility, drawdown, exposure, and position-size constraints |
| Adversarial Analyst | Counterarguments, data-quality checks, and failure cases |
| Evidence Arbitrator | Evidence-weighted decision; risk and safety vetoes |
| Feedback Analyst | Compares prior forecasts with realized outcomes |

The initial agents are deterministic and work offline. `GrokStrategicAgent` is an
optional xAI API adapter; it is never called unless explicitly instantiated and
given an API key.

## Install / run

Copy the `hedgeops_team/` directory into the repository root. Then:

```bash
python -m pytest tests/test_hedgeops_team.py -q
python examples/run_team_demo.py
```

No third-party runtime packages are required. `pytest` is only needed to run tests.

## Minimal integration

```python
from hedgeops_team import HedgeOpsTeam

team = HedgeOpsTeam()
report = team.analyze(
    bars=[
        {"timestamp": "2026-01-01", "close": 100.0},
        {"timestamp": "2026-01-02", "close": 101.0},
        {"timestamp": "2026-01-03", "close": 102.0},
    ],
    portfolio={"equity": 200.0, "cash": 200.0, "exposure_pct": 0.0},
)
print(report.to_dict())
```

Feed the returned decision into your existing **paper-only** workflow for review.
Do not wire agent output directly to a broker or live execution endpoint.

## Optional Grok strategic agent

The xAI adapter uses the OpenAI-compatible Chat Completions interface. Configure
credentials outside source control:

```bash
export XAI_API_KEY="..."
export XAI_MODEL="grok-3-mini"
```

Then explicitly inject it:

```python
from hedgeops_team import HedgeOpsTeam
from hedgeops_team.grok import GrokStrategicAgent

team = HedgeOpsTeam(strategic_agent=GrokStrategicAgent.from_env())
```

The model name is configurable because available model identifiers can change.
The adapter requests JSON and validates the returned action. If the API is
unavailable or the response is invalid, it fails closed to HOLD. API integration
must be tested in your own environment; this package does not claim that a live
xAI connection has been verified.

## Input contract

`bars` is an ordered sequence of mappings containing `close`; `timestamp` is
optional. Prices must be finite positive numbers. At least two bars are required.
`portfolio` may contain `equity`, `cash`, `exposure_pct`, and `drawdown_pct`.

## Safety boundaries

- This is decision support, not investment advice.
- No broker, exchange, or order-placement code is included.
- The arbitrator can return `REJECT` or `HOLD`; it does not execute trades.
- Risk limits are configurable and should be independently reviewed.
- Historical or demo performance does not establish future profitability.
- Keep API keys in environment variables or a secrets manager; never commit them.
- Do not enable live trading based solely on passing unit tests.
