# Phase 67 — Read-only reconciliation health

Call `reconciliation_health(authority)` to inspect local outbox health. The response has `status` (`healthy`, `pending`, `integrity_failure`, or `unavailable`), `pending` and `confirmed` counts, and `audit_head` (local execution-audit sequence). A missing audit or outbox schema is `unavailable`; corrupted audit ancestry, outbox hash linkage or confirmation ordering is `integrity_failure`.

The function uses one SQLite read transaction and performs no schema creation, mutation, remote custody request or checkpoint publication. `healthy` means local records pass integrity checks and no outbox entries are pending; it does **not** prove remote custody is reachable, current or rollback-resistant. `pending` indicates a separate reconciliation action may be required. Inspect integrity failures before retrying publication.

Tests: `tests/test_reconciliation_health.py`.
