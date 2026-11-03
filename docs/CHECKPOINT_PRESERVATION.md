# Phase 20 — Local checkpoint preservation

`save_checkpoint(store, case_id, registry, destination)` creates a
JSON checkpoint using a temporary file, file sync and atomic hard-link
publication. It refuses to overwrite an existing destination. The parent
directory must already exist; choose an operator-controlled directory
**outside the SQLite database directory**.

`load_checkpoint(path)` reads bounded JSON (16 KiB maximum).
`verify_saved_checkpoint(store, path, registry)` fails closed for missing,
corrupt, stale or otherwise mismatched checkpoint files.

## Durability and security limits

- This implementation targets POSIX local filesystems with hard-link support.
  It does not support Windows or arbitrary network/object-store semantics.
- Checkpoints are mode 0600 when created. Directory permissions, access
  control, backups and secure transfer are the operator's responsibility.
- Atomic publication and local fsync reduce partial-write risk but are not
  a full backup/restore or crash-recovery guarantee on every filesystem.
- No overwrite is not the same as immutable storage. A privileged operator
  can delete or replace a checkpoint. A database attacker with access to
  the checkpoint directory can forge matching files.
- This does not automatically upload, sign, timestamp, or anchor checkpoint
  data in an independent trusted service.

Run `python release_check.py --verbose` and verify both CI matrix jobs.
