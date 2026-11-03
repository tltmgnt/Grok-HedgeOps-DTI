# Phase 64 — Durable local reconciliation outbox

`execute_with_reconciliation_outbox(...)` wraps the existing fenced recovery executor. It creates a pending outbox entry for the next execution-audit head inside the same local SQLite transaction as the recovery mutation and audit append. If that transaction rolls back, no outbox entry is committed.

After a crash or custody outage, call `pending_reconciliations(authority)` to discover committed but unconfirmed execution heads. Call `reconcile_pending_outbox(authority, key, custodian)` to publish or confirm the latest authenticated head and mark covered outbox entries confirmed only after checking their hashes against the local audit. **Do not rerun the recovery mutation** to retry publication.

This is an opt-in wrapper: direct calls to `execute_fenced_recovery` and the Phase 63 workflow do not create outbox entries. External custody is not transactionally coupled to SQLite; a crash after publication but before local confirmation leaves a pending entry that can be reconciled idempotently. A reference SQLite database is not independent rollback-resistant custody. Run `python release_check.py --verbose` and verify CI.
