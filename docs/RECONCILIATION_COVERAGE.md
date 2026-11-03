# Phase 76 — Complete execution audit coverage

A healthy local SQLite integrity result alone does not establish readiness: older or bypassed recovery paths may append execution-audit events without outbox records. Readiness now requires a positive execution-audit head and an equal count of confirmed outbox rows. If the audit is empty, the operator receives `NO_EXECUTIONS`; if the audit is nonempty but not fully covered, it receives `UNTRACKED_AUDIT`. Both are denied (`exit 2`) before remote custody reads.

The local state is checked again after remote verification. These checks are diagnostic only and do not create or confirm missing outbox entries. Tests: `tests/test_reconciliation_coverage.py`.
