# Phase 73 — Stable operator CLI exit-code contract

The CLI emits one JSON diagnostic object and uses the following process exit codes:

- `0` — `READY` with `ready=true` and `custody_verified=true`.
- `2` — evidence-based denial: `PENDING_RECONCILIATION`, `LOCAL_INTEGRITY_FAILURE`, `CHECKPOINT_MISMATCH`, `CUSTODY_UNVERIFIED`, or `LOCAL_STATE_CHANGED`.
- `3` — operational inability or invalid status: `LOCAL_STATUS_UNAVAILABLE`, `READINESS_UNAVAILABLE`, malformed configuration, missing files, or an unrecognized/inconsistent diagnostic result.

Monitoring should inspect both exit code and the JSON `reason_code`. In particular, `CUSTODY_UNVERIFIED` means confirmation is absent, which can arise from an unavailable remote service as well as a mismatched custody record; this layer does not claim to distinguish those underlying causes. No failure should be treated as authorization to retry a committed recovery mutation. Exit codes do not imply a distributed lease.

Regression coverage: `tests/test_reconciliation_exit_contract.py` and `tests/test_reconciliation_cli.py`.
