# Phase 66 — Recovery reconciliation outbox integrity

`verify_reconciliation_outbox(authority)` checks SQLite integrity, the execution-audit hash chain, every recorded outbox sequence and digest against the corresponding audit entry, and confirmation ordering. A confirmed entry cannot follow an unconfirmed outbox entry. This permits legacy executions without outbox rows, while requiring every present row to have a matching audit event.

`reconcile_pending_outbox` now refuses publication when local integrity checks fail and rechecks audit/outbox linkage under the SQLite write lock before local confirmation. Integrity failures leave the outbox unconfirmed for investigation; do not retry the recovery mutation.

These are local tamper-evidence checks, not proof against a database administrator who rewrites the entire SQLite database and its hashes. External custody checkpoints remain necessary for rollback detection. Tests: `tests/test_recovery_outbox_integrity.py`.
