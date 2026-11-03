# DTI Ω × HedgeOps Ω

Experimental temporal intelligence and strategic hedge-operations decision-support framework.

## Status

**v0.1 prototype:** one Grok-powered analysis agent. Multi-agent orchestration, arbitration, verification feedback, and autonomous execution are **not implemented yet**.

## Quick start

Requires Python 3.10+ and an xAI API account with API credits (separate from SuperGrok).

```bash
git clone https://github.com/tltmgnt/Grok-HedgeOps-DTI.git
cd Grok-HedgeOps-DTI
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

On Windows, activate with `.venv\\Scripts\\activate` and copy with `copy .env.example .env`.

Edit `.env` with your own `XAI_API_KEY` and an `XAI_MODEL` ID available to your xAI team. **Never commit your .env or share an API key.**

```bash
python agent.py "Evaluate the risks and timing of launching a new product."
```

The agent requests a JSON report with observations, evidence, assumptions, gaps, options, risks, recommendations and verification conditions. JSON parsing is implemented, but model output is not yet schema-validated; malformed responses may fail. Outputs are hypotheses, not verified facts.

## Planned architecture

Orchestrator Ω → Temporal / Capacity / Strategy / Risk / Hedge / Contrarian / Red-Team agents → Evidence-based Arbitrator Ω → Human-approved decision → Observation and feedback.

Proposed state: `S_t = (T, C, O, U, R, G, V)`, representing time, capacity, options, uncertainty, risk, gaps and verification.

## Roadmap

1. Validate single-agent structured output with JSON Schema and tests.
2. Add sourced retrieval and evidence provenance.
3. Implement five-agent HEDGE 302 laboratory.
4. Add conflict arbitration and human approval gates.
5. Track predictions, falsification tests, and observed outcomes.

## License

Apache-2.0. See [LICENSE](LICENSE).
