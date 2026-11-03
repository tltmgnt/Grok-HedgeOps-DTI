# Phase 23 — HMAC-authenticated checkpoints

Provide a separate, randomly generated 32+ byte authentication key:

```python
save_checkpoint(store, case_id, reviewer_registry, checkpoint_path,
                authentication_key=checkpoint_key)
verify_saved_checkpoint(store, checkpoint_path, reviewer_registry,
                        authentication_key=checkpoint_key)
backup_with_checkpoint(store, case_id, reviewer_registry, backup_path,
                       checkpoint_path, authentication_key=checkpoint_key)
verify_restored_journal(backup_path, checkpoint_path, reviewer_registry,
                        authentication_key=checkpoint_key)
```

Authenticated checkpoint files contain a domain-separated HMAC-SHA256 tag
over the canonical checkpoint body. Verification fails closed when the
authentication key is absent, incorrect or the checkpoint is altered.

The new authentication option is explicit; unsigned legacy checkpoint
files remain supported by calls that omit `authentication_key`. For
production, supply the key on **both** creation and verification and keep it
separate from SQLite, backups and checkpoint files. Do not commit it to Git.

## Security limits

HMAC authenticates data only while the secret key remains protected. It does
not provide public-key non-repudiation, a trusted timestamp, immutable
retention, independent publication, replay prevention or automatic key
rotation. A privileged attacker with the authentication key can forge
checkpoints. A previously valid signed checkpoint can still be replayed
alongside an older matching database; use independent monotonic retention
or external anchoring to prevent rollback.

Run `python release_check.py --verbose` and verify the CI matrix.
