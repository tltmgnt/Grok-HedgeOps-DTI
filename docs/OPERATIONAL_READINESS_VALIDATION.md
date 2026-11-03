# Phase 88 — Operational readiness validation

Readiness must be denied while an execution outbox entry is pending, become ready only after authenticated custody publication and local confirmation, and return to pending when a new local execution advances the audit head. A subsequent reconciliation must restore readiness for the new checkpoint. The readiness assessment itself is read-only: it must not publish custody, mutate recovery state or confirm outbox entries.

`tests/test_operational_readiness_lifecycle.py` exercises this lifecycle with real local SQLite state and a deterministic in-process custodian, plus a tampered-custody negative case. These checks are operational regression evidence, not a production deployment rehearsal. Before release, verify actual HTTPS custody, credential and key management, backup/restore drills, incident procedures, and monitoring in the target environment.
