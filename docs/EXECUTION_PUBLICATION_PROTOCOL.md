# Phase 83 — Custody publication protocol failure handling

The execution reconciliation workflow normalizes invalid custody read responses and malformed compare-and-swap errors into `ExecutionReconciliationError`. This includes `ValueError`, `TypeError`, `KeyError`, `UnicodeError`, and existing transport failures. A CAS failure remains uncertain; operators must explicitly retry reconciliation rather than rerun the already committed recovery mutation.

Twelve deterministic failure scenarios in `tests/test_execution_publication_protocol.py` cover initial reads, CAS publication, and confirmation reads, with pending outbox rows preserved. Unexpected application exceptions outside these protocol/transport categories are not suppressed.
