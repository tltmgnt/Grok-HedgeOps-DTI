# Phase 80 — Audit-head freshness during confirmation

After custody reconciliation, the outbox confirmation transaction validates that the returned authenticated checkpoint still identifies the current execution-audit tip. Both sequence and event hash must match. A newer local execution causes `ExecutionReconciliationError` before the final custody read or any outbox confirmation.

The check runs after `BEGIN IMMEDIATE` and audit-chain verification, closing the gap between custody publication and local confirmation. It does not undo a committed recovery, rewind custody, or automatically retry a mutation. Regression coverage: `tests/test_outbox_audit_head_races.py`.
