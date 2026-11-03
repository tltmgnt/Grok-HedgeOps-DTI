# Phase 65 — Reconciliation outbox race handling

The outbox reconciler rereads independent custody immediately before marking locally durable entries confirmed. The observed record must match the authenticated checkpoint sequence and fingerprint. If custody changes, confirmation fails and pending rows remain available for a later investigation or retry.

`tests/test_reconciliation_outbox_races.py` covers concurrent publishers converging on one checkpoint, a custody change immediately before local confirmation, and a local execution-audit head advancing while remote publication is in progress. The reconciler only confirms outbox entries covered by the checkpoint it published; newer local entries remain pending.

The final remote read and local SQLite update cannot be globally atomic. This reference design does not provide a distributed lock, external lease, or independently rollback-resistant custody. Run `python release_check.py --verbose` and verify CI.
