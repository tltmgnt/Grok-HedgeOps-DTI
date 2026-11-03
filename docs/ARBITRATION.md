# Phase 3 — Evidence-based Arbitration Ω (prototype)

The laboratory now produces three additional structures:

1. **Hypothesis comparison:** normalizes exact text and groups matching statements. Distinct statements are *potential disagreements*, not verified logical contradictions.
2. **Provenance audit:** legacy free-text evidence is flagged `source_required`. A typed `Evidence` record supports claim, source, source type, retrieval time and a verification flag. This does not independently validate the source.
3. **Verification ledger:** stable IDs, proposing agents, pending status, and blank observed results. This is a proposed-test ledger, not a record of completed experiments.

## Decision gate

The arbitrator returns `investigate` when evidence is absent, confidence is low/unknown, provenance is missing, or distinct hypotheses require review. Otherwise it returns `human_review`. Neither state authorizes autonomous action.

## Remaining work

Build source retrieval and corroboration, semantic entailment/contradiction evaluation, durable audit storage, test execution and measured outcomes, human sign-off, and API integration tests.
