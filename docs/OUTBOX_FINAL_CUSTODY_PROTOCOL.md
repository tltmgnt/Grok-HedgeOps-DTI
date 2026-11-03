# Phase 82 — Final custody protocol failure handling

The final read-before-confirmation step now normalizes malformed custody records and read failures to `ExecutionReconciliationError`. This includes invalid record types, missing fields, incorrect digest formats, decoding/validation failures and transport errors. The SQLite confirmation transaction rolls back without marking pending outbox entries confirmed.

Regression coverage in `tests/test_outbox_final_custody_protocol.py` tests nine failure variants. No recovery mutation is retried; the remote publication may already have occurred. A later explicit reconciliation can verify custody and confirm pending entries.
