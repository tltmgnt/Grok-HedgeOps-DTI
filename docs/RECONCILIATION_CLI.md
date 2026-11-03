# Phase 70 — Read-only reconciliation readiness CLI

Run:

```sh
export HEDGEOPS_EXECUTION_CHECKPOINT_KEY_HEX='<64+ hex characters>'
export HEDGEOPS_CUSTODY_BEARER_TOKEN='<custody bearer token>'
python -m hedgeops.reconciliation_cli --database /path/to/fence.db --checkpoint /path/to/execution-checkpoint.json --custody-url https://custody.example/v1/execution-checkpoint
```

The CLI prints one JSON object with the allowlisted readiness diagnostic fields. Exit codes: `0` ready, `2` denied (including pending, mismatch or unverified custody), `3` invalid configuration or failed check. Never place secrets in CLI arguments, commit them to source control, or paste them into issue logs. Use an HTTPS endpoint with independent durable custody; the bearer token does not itself establish trust in the server.

The SQLite connection is opened with `mode=ro`; the CLI never creates tables, issues a recovery, publishes custody or acknowledges the outbox. This is a point-in-time diagnostic, not an admission grant. Tests: `tests/test_reconciliation_cli.py`.
