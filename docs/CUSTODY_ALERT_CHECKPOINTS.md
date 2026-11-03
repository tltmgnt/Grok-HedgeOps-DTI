# Phase 39 — Authenticated alert-journal checkpoints

`hedgeops.custody_alert_checkpoint` creates HMAC-SHA256 authenticated
checkpoints for a verified, nonempty Phase 38 alert journal.

```python
from hedgeops.custody_alert_checkpoint import (
    create_alert_checkpoint, verify_alert_checkpoint)

checkpoint = create_alert_checkpoint(journal, independent_checkpoint_key)
# Preserve checkpoint in independently protected, trusted custody.
accepted = verify_alert_checkpoint(
    recovered_journal, trusted_checkpoint, independent_checkpoint_key)
```

A checkpoint contains a versioned scheme, positive journal sequence,
SHA-256 event head and HMAC authentication tag. Creation verifies the
chain inside a consistent SQLite read transaction. Verification checks
the HMAC, entire journal chain and the exact event hash at the trusted
sequence. Newer valid events may follow that checkpoint; truncated or
divergent histories fail closed.

**Trust boundary:** The HMAC authenticates a checkpoint but does not prove
it is the *latest* checkpoint. Operators must independently retain and
retrieve the newest accepted checkpoint and protect its HMAC key. Replaying
both an old valid journal and an old valid checkpoint remains possible
without external monotonic custody. No remote publication, key management,
trusted timestamp or production deployment is provided.

Run `python release_check.py --verbose` and verify both CI matrix jobs.
