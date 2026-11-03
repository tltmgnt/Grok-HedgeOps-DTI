# Phase 69 — Operator-facing reconciliation diagnostics

Call `readiness_diagnostics(authority, checkpoint, key, custodian)` to obtain a bounded, allowlisted status report. The report contains `ready`, `reason_code`, `message`, `pending`, `confirmed`, `audit_head`, and `custody_verified` only. It never returns supplied keys, checkpoint authentication tags, event hashes, raw exceptions, or custody endpoint URLs.

Denial reason codes: `PENDING_RECONCILIATION`, `LOCAL_INTEGRITY_FAILURE`, `LOCAL_STATUS_UNAVAILABLE`, `CHECKPOINT_MISMATCH`, `CUSTODY_UNVERIFIED`, `LOCAL_STATE_CHANGED`, and `READINESS_UNAVAILABLE` for unexpected statuses. `READY` indicates a successful point-in-time readiness assessment, not permission to bypass recovery admission or a durable remote lease.

Diagnostics delegates to the read-only readiness check and cannot publish custody, acknowledge outbox entries or rerun a recovery mutation. Tests: `tests/test_reconciliation_diagnostics.py`.
