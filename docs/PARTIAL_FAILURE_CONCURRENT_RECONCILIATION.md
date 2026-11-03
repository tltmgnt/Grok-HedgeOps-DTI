# Phase 86 — Partial failure during concurrent reconciliation

Two reconciliation workers observe the same initial custody state. A deterministic fault makes the first custody CAS fail before committing; the competing worker publishes the authenticated checkpoint successfully. The failing worker must return a reconciliation error rather than retry the recovery mutation. Once the successful worker confirms the local outbox, a later explicit reconciliation must be idempotent.

`tests/test_partial_failure_concurrent_reconciliation.py` verifies exactly one successful custody write, one execution audit event, one confirmed outbox entry, and one recovery mutation. This is an in-process deterministic race regression, not a distributed chaos or load test.
