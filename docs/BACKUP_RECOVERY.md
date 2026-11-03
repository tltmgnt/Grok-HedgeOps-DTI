# Phase 21 — Consistent SQLite backup and offline recovery verification

`backup_journal(store, destination)` uses the SQLite backup API to snapshot
an open event database. It writes into a temporary file, runs SQLite's
`PRAGMA integrity_check`, syncs the file and publishes it without replacing
an existing destination. On supported POSIX local filesystems the published
backup is mode 0600.

`verify_restored_journal(backup_path, checkpoint_path, trusted_registry)`
checks SQLite integrity, restores into an isolated temporary database,
validates the journal hash chain and compares it with a **separately preserved
trusted checkpoint**. Verification does not intentionally modify the original
backup. An old snapshot remains valid against its corresponding old checkpoint
even after the live database advances.

## Operator procedure

1. Preserve a trusted checkpoint using Phase 20 before the backup.
2. Take the SQLite backup while the database is available.
3. Verify the backup against that checkpoint. If the live journal changed
   between checkpoint and backup, verification correctly fails: take a new
   checkpoint for the backup's exact snapshot instead.
4. Transfer backup and checkpoint to independently controlled storage with
   access restrictions, retention policies and tested recovery procedures.

## Limits

- The checkpoint and backup are not cryptographically authenticated by an
  independent external service; a privileged operator could replace both.
- Backup and checkpoint are separate operations, not an atomic cross-file
  transaction. Concurrent writes can cause a mismatch that requires retry.
- The snapshot includes plaintext case content. Encryption at rest, secure
  offsite transfer, retention, and recovery-point objectives are not provided.
- This is POSIX-oriented local-file backup verification, not a managed
  disaster-recovery service or automated restore into production.

Run `python release_check.py --verbose` and verify both CI matrix jobs.
