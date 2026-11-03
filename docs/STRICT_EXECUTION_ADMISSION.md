# Phase 57 — Strict execution custody admission

Call `require_execution_custody(authority)` to persist the strict-admission setting in the authority SQLite database. The setting survives reopening the database and repeated enablement is idempotent.

Use `execute_strict_recovery(...)` for recovery calls that must present execution checkpoint, key and custodian. The wrapper refuses calls without the persisted setting or complete evidence and delegates to the three-namespace verification in `execute_fenced_recovery`.

**Important limitation:** The existing `execute_fenced_recovery` remains callable without execution custody. This phase introduces a strict entry point, **not** a universal non-bypassable policy. Integrations must exclusively expose the strict entry point and prohibit direct calls to the legacy API. Enforcing the persisted requirement inside the original executor remains outstanding. Neither SQLite nor the remote custody double-read provides independent rollback protection or a distributed lease. Run `python release_check.py --verbose`.
