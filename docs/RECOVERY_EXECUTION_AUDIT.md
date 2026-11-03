# Phase 51 — Transactional recovery execution journal

Each successful controlled recovery callback appends a SHA-256-linked execution record inside the same SQLite transaction as the local mutation. Records contain a sequence, recovery generation, predecessor hash and event hash. `verify_execution_audit(authority)` validates local chain continuity; `execution_audit_head(authority)` returns the latest local head.

Callback errors and audit errors roll back the transaction. Ten tests cover commits, failures, corruption and truncation.

**Limitations:** A deleted suffix or database rollback can produce a shorter, locally valid chain. Independently authenticate and retain audit heads to detect rollback. This journal is not external custody, does not verify the semantics of arbitrary SQL callbacks, and does not create a distributed lease. Run `python release_check.py --verbose` to check CI.
