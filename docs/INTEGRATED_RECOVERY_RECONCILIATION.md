# Phase 63 — Integrated recovery and custody reconciliation

`execute_and_reconcile_recovery(...)` calls `execute_fenced_recovery(...)` once, then calls `reconcile_execution_custody(...)` to publish or confirm the current authenticated execution-audit head. On success it returns `(mutation_result, checkpoint)`.

When the local recovery succeeds but reconciliation raises, the workflow raises `CommittedRecoveryUnconfirmed` with `local_committed=True` and the original `cause`. **Do not retry the recovery mutation** after this exception. Inspect the custody state and retry only `reconcile_execution_custody(authority, key, custodian)`. Admission or mutation errors propagate without attempting publication.

The local commit and remote custody publication are separate operations. There is no distributed transaction; reconciliation can publish the latest head if another local execution has advanced it. An exception from a mutation callback that performs prohibited external side effects cannot be reliably classified. Tests: `tests/test_recovery_execution_workflow.py`.
