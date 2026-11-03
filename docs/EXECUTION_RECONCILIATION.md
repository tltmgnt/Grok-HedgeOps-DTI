# Phase 62 — Post-commit execution custody reconciliation

After a successful locally fenced recovery transaction, call `reconcile_execution_custody(authority, key, custodian)` to publish the current authenticated execution-audit head to independent custody. The operation confirms a matching existing record on retry and advances custody with conditional compare-and-swap when the local head is newer.

A conflicting same-sequence fingerprint, a custody sequence ahead of the local audit, an unavailable custody service or an ambiguous publication failure raises `ExecutionReconciliationError`. The local mutation has already committed and **must not be represented as rolled back**. Operators should retain the error, investigate custody, and retry reconciliation only when safe. The reconciliation helper does not automatically execute another recovery mutation.

The custody double-read reduces but cannot eliminate remote races. This reference implementation does not provide a distributed transaction, lease or rollback-resistant storage. Run `python release_check.py --verbose` to exercise the Phase 62 regression tests.
