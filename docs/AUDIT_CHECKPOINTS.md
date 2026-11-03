# Phase 19 — Audit checkpoints and external preservation

`export_checkpoint(store, case_id, trusted_registry)` creates a deterministic
JSON-serializable record of the journal head, global and case event counts,
case head hash, and current signed-review verification status. The record
includes a SHA-256 digest over its canonical fields, excluding the digest.

`verify_checkpoint(store, checkpoint, trusted_registry)` verifies the current
journal chain and requires an **exact** match with the trusted checkpoint.
Any subsequent append requires a new checkpoint. Changes to reviewer key
revocation state can also invalidate a prior checkpoint.

## External trust boundary

An exported checkpoint **must be preserved outside the database** in an
independently controlled, access-restricted, ideally immutable location.
A checksum saved beside the SQLite file is not a trusted anchor. An attacker
who can replace both the database and checkpoint can create matching values.
This feature does not sign checkpoints, provide trusted timestamps, authenticate
the exporter, or automatically upload records. It does not prove that a
reviewer's identity was verified by an external identity provider.

Do not include reviewer secrets in checkpoints. The export intentionally
excludes case narrative and agent content, but case IDs and event counts may
still be sensitive operational metadata.

Run `python release_check.py --verbose` and verify the latest CI jobs.
