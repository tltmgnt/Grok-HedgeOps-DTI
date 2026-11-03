# Phase 22 — Snapshot-aligned backup and checkpoint

Use `backup_with_checkpoint(store, case_id, registry, backup_path, checkpoint_path)`
to create a SQLite backup and then derive its checkpoint from an isolated copy
of that exact backup. The function verifies the pair before returning.

This closes the timing mismatch in the Phase 21 manual workflow: new writes
to the live journal after the backup do not invalidate its checkpoint.

Both destinations must be unused and different. The backup is published
first. If checkpoint creation or verification fails, an **unpaired backup**
may remain; never accept it as verified or restore it without independent
checks. There is no cross-file atomic commit or automatic cleanup.

The checkpoint must still be exported to independently controlled, preferably
immutable storage. A backup and checkpoint stored together can both be
replaced by a privileged attacker. No encryption, external signature, trusted
timestamp, offsite transfer or automated production restore is provided.

Run `python release_check.py --verbose` and confirm the CI matrix.
