# Phase 7 — Operational Intelligence Ω

## Live analysis

```bash
cp .env.example .env
# Set XAI_API_KEY and XAI_MODEL
pip install --require-hashes --only-binary=:all: -r requirements.txt
python live_case.py "Evaluate deployment risks" --timeout 30
```

This makes **five sequential paid API calls**, one for each HEDGE 302 role.
The result and arbitration are persisted as a case in SQLite. The CLI does not
automatically approve, execute or trade anything.

## Offline CI

```bash
python -m unittest discover -s tests -v
```

GitHub Actions runs the offline tests on Python 3.10 and 3.12. No API key is
required for CI. The live adapter has mock-based unit tests; live provider
compatibility is not verified by these tests.

## Operations and limits

- Explicit per-request timeout and bounded retry count. Overall duration may
  be approximately five times the per-agent timeout plus retries.
- Transient API failures retry; nontransient 4xx failures surface as errors.
- Logging records only timing, attempt count and exception type, not prompts,
  responses or secrets. The persistent case record **does** contain user prompts
  and agent responses; protect the local SQLite file accordingly.
- Model JSON is parsed but remains subject to report validation in the lab.
- If a call fails mid-run, a case_created event can remain without analysis.
- No authenticated human approval, secret manager, monitoring service,
  distributed lock or production-grade recovery strategy is implemented.

Next: authenticated approval workflow, recovery/resume for partial cases,
metrics and redaction policy, cost budgets, and provider integration testing.
