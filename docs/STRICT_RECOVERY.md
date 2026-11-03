# Phase 27 — Receipt-gated strict recovery

`verify_receipt_gated_recovery` is a fail-closed recovery entry point:

```python
accepted = verify_receipt_gated_recovery(
    backup_path, checkpoint_path, reviewer_registry,
    floor_directory, independently_retained_receipt_path,
    checkpoint_key=checkpoint_key,
    floor_key=floor_key,
    receipt_key=receipt_key,
)
```

It requires three distinct 32+ byte secrets. Verification rejects missing
or malformed receipts, a corrupt or rolled-back local registry relative to
the supplied receipt, invalid authenticated checkpoints, damaged SQLite
backups, journal-chain corruption, and backups older than the registry's
latest recovery floor.

The original `verify_restored_journal` API remains available for offline
compatibility. Use the strict API for production recovery policy; do not
silently fall back to legacy verification when it returns `False`.

**Trust limitation:** the receipt is passed in by the operator and is not
automatically fetched from an independent trusted service. If the operator
supplies an older valid receipt alongside a rolled-back registry, the
system cannot discover that a newer receipt exists. Custody, freshness,
independent retention, key rotation, encrypted backups and operational
restoration are separate requirements.

Run `python release_check.py --verbose` and check both CI matrix jobs.
