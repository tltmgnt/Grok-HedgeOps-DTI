# Phase 26 — Authenticated registry-head receipts

A registry-head receipt binds the latest local recovery floor's sequence,
record hash, minimum event count and journal head hash under a separately
managed HMAC-SHA256 receipt key.

```python
receipt = export_registry_receipt(registry_directory, floor_key, receipt_key)
save_registry_receipt(receipt, independent_receipt_path)
trusted = load_registry_receipt(independent_receipt_path)
assert verify_registry_receipt(
    registry_directory, floor_key, trusted, receipt_key)
```

Retain the receipt **outside the local registry's trust boundary**. The
verification requires the *entire* local registry to validate and its latest
record to match the independently supplied receipt. Removing the most recent
floor record is detectable when the corresponding trusted receipt survives.

The receipt file is owner-only, created without overwrite and synchronized
on POSIX local filesystems. It is not automatically uploaded or published to
an external service. It is not a trusted timestamp, asymmetric signature,
append-only remote log or freshness oracle.

**Freshness limitation:** An attacker who can replace both registry and
receipt with an older valid pair can still roll back history. An independent
custodian must retain the latest accepted receipt, or use an immutable
monotonic external service. Keep the receipt HMAC key distinct from the
floor HMAC key, and never commit either key.

Run `python release_check.py --verbose` and confirm both CI jobs.
