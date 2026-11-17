# ResearchOS TECT market-model integration
Companion repository: https://github.com/tltmgnt/-ResearchOS-TECT-Market-Mechanism-Resilience-Repair

## Offline integration
The companion app exports a bundle containing study and report. This repository vendors the same dependency-free deterministic evaluator as market_resilience_model.py. Its source must remain byte-identical to the companion market_model.py for this version; no runtime network download is performed.
```sh
python market_resilience_review.py market-review-bundle.json --output market-research-review.json
python -m unittest discover -s tests -p 'test_market_resilience*.py' -v
```
The CLI recomputes the report, rejects mismatches and writes a human-review-required research record. Input and bundle digests establish internal consistency, not evidence authenticity, independent reproduction or TECT assurance. Nothing is promoted in evidence_tect/register.json.

## Optional research critique
Call review_bundle(bundle, ask=your_explicit_callback) from a controlled research process. The callback receives only the supplied synthetic bundle and a research-review prompt. No existing Grok provider or credentials are automatically invoked. Prose is bounded, marked unverified and cannot modify candidate rules or authorize execution. Prompt instructions are not a security guarantee; inspect generated text independently.

## Model and boundaries
This is a finite resource-admission experiment with repeated IDs, optional idempotency, participant caps and participant-priority/pro-rata allocation. It is not exchange matching, live trading, automated weakness exploitation, or a formal proof. Capacity checks apply to evaluated inputs only. Participant labels are assumed, not authenticated; identity splitting and strategic economic behavior are not solved.
Trading, broker adapters, workflow permissions, schedules and approval gates are unchanged. No investment recommendation or IMR/DARPA affiliation is claimed. Source/review notes are owner declarations. The public module contains only synthetic fixtures and publishable logic.

## Updating both copies
Update both evaluators together, run each suite and the companion cross-repository contract test, and record the exact counterpart commit used for verification. Existing source remains Apache-2.0; no private algorithms or evidence are copied.
