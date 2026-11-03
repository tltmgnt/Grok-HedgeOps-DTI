# Phase 8 — Operational safeguards (prototype)

## CI baseline

A GitHub Actions Python tests run for the preceding Phase 7 commit was reported
successful. Phase 8 tests must pass separately before review or merge.

## Operator gate

Set `HEDGEOPS_OPERATOR_TOKEN` to a long, randomly generated secret (at least 24
characters). Do not put it in command arguments, commits, logs or screenshots.
The `operator_cli.py review` command checks the token before recording a
human review decision.

```bash
python operator_cli.py review CASE_ID approved_for_tracking \
  --reviewer analyst --rationale "Approved only for measurement tracking"
```

**Limitations:** This is a shared-secret gate, not identity authentication,
role-based access control or an auditable proof of who approved. The lower-level
`record_review` function remains callable without the gate; production users
must not expose it as an unprotected API.

## Interrupted analysis recovery

```bash
python operator_cli.py recover CASE_ID
```

Recovery runs the five-agent laboratory again only if the case has no completed
analysis. A failed previous attempt may already have incurred API charges.
This implementation is intended for a single operator, not concurrent workers:
there is no distributed lock or atomic check-and-append across processes.

## Remaining release blockers

- Verify new CI run and live xAI integration against a supported model.
- Add real identity authentication and authorization at every write boundary.
- Add database-level concurrency and idempotency controls.
- Add encryption, backup/restore testing, retention and secret rotation.
- Harden partial-failure handling, costs and operational observability.
- Obtain explicit human sign-off before merging or deployment.
