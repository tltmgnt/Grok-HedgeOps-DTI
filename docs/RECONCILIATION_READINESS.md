# Phase 68 — Local and external reconciliation readiness

Call `reconciliation_readiness(authority, checkpoint, key, custodian)` to obtain a read-only readiness assessment. `ready=True` requires healthy local outbox integrity, zero pending entries, a supplied authenticated execution checkpoint matching the current local audit head, and successful independent custody verification. The function checks local health and audit head again after the remote verification to detect local advancement.

Failure statuses include `pending`, `integrity_failure`, `unavailable`, `checkpoint_mismatch`, `custody_unverified`, and `local_changed`. The response also includes local health details and a separate `custody_verified` boolean. This API does not issue a recovery, publish custody, or mark outbox rows confirmed.

Readiness is a point-in-time assessment, not a distributed lease. Remote custody may change immediately after verification. Use the fenced admission and transaction checks for actual recovery execution. Tests: `tests/test_reconciliation_readiness.py`.
