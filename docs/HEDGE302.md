# HEDGE 302 — Multi-Agent Laboratory

## Scope

Five independent role-specific calls share one user-provided problem. Each returns
a typed report with hypothesis, evidence, assumptions, risks, falsification tests,
and qualitative confidence.

The deterministic arbitrator currently checks completeness, presence of evidence,
and confidence. It does **not** resolve semantic conflicts, validate evidence
authenticity, measure agent independence, or authorize execution. All outputs
require human review.

## Run

```bash
python lab.py "Should we launch a product this quarter?"
python -m unittest discover -s tests -v
```

Five API requests are made per laboratory run; usage is separately billed by xAI.
Use a model that supports JSON object output.

## Next milestones

- JSON Schema / Pydantic contracts and retries for malformed responses
- Provenance and evidence source validation
- Conflict graph and explicit hypothesis comparison
- Audit log, budgets and token limits
- Human review interface and prediction-outcome tracking
