# Phase 29 — Controlled receipt custody contract

`hedgeops.receipt_custody` provides a narrow interface for publishing and
retrieving receipt fingerprints from an **independently trusted custodian**.

A custodian adapter must implement:

```python
read() -> {"sequence": positive_integer, "receipt_sha256": lowercase_sha256} | None
compare_and_swap(expected_record, new_record) -> bool
```

The compare-and-swap operation **must be atomic** and must durably enforce
monotonic sequence advancement under concurrent and adversarial writers.
The adapter must authenticate callers and prevent deletion, stale reads,
unauthorized rewriting and rollback of its own stored record. A normal
local file or in-memory dictionary does not meet these production guarantees.

```python
publish_receipt_to_custodian(
    floor_directory, trusted_receipt_path, floor_key, receipt_key, custodian)
accepted = verify_custodied_recovery(
    backup_path, checkpoint_path, reviewer_registry,
    floor_directory, trusted_receipt_path, custodian,
    checkpoint_key=checkpoint_key, floor_key=floor_key,
    receipt_key=receipt_key)
```

Publication checks the authenticated registry and receipt before invoking
the custodian's CAS. Recovery reads the custodian's fingerprint and sequence
and requires the supplied receipt to match before running pinned strict
recovery. Missing custody evidence, stale receipts, malformed records and
conflicts fail closed.

**Not yet implemented:** a real external custodian adapter, remote
authentication, secure network transport, independently verified
read freshness, service availability, immutable retention or automatic
credential rotation. Tests use an in-memory fake solely to exercise the
contract; do not use it for production security. The caller is responsible
for ensuring the custodian really provides trusted monotonic state.

Run `python release_check.py --verbose` and confirm both CI jobs.
