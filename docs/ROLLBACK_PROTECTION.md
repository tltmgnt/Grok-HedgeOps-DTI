# Phase 24 — Trusted recovery floor

A checkpoint authentication tag prevents undetected modification but does not
prevent replay of an older, still-valid database/checkpoint pair.

`create_recovery_floor(checkpoint, floor_key)` creates an authenticated record
of the minimum acceptable global event count and journal head hash. Retain this
floor **outside the backup/checkpoint trust boundary**, with a separately
controlled 32+ byte floor key.

During recovery:

```python
verify_restored_journal(
    backup_path, checkpoint_path, reviewer_registry,
    authentication_key=checkpoint_key,
    trusted_floor=trusted_floor,
    floor_key=floor_key,
)
```

Verification checks the SQLite journal and checkpoint, validates the floor
authentication tag, rejects a candidate older than the minimum event count,
and checks that the candidate journal contains the exact floor head hash at
the minimum position. This detects truncation and divergent history.

## Trust boundary and limitations

The floor is **supplied by the caller**. This module does not fetch it from
an independent service, ensure it is the latest floor, or enforce monotonic
updates. A malicious operator can replay an older valid floor unless a
separate trusted retention system prevents rollback of the floor itself.
Do not store the only floor alongside the database or backup. The floor key
must be independently protected. HMAC does not provide trusted timestamps
or public-key non-repudiation.

For production, require both authenticated checkpoints and a trusted floor
on every recovery verification call. Omission remains supported for
backward-compatible offline workflows.

Run `python release_check.py --verbose` and check both CI jobs.
