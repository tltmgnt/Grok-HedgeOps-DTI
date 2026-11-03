# Phase 28 — Externally pinned receipt recovery

The strict receipt-gated recovery path verifies the local floor registry
against a supplied receipt. To prevent substitution of an older *valid*
receipt, use an expected SHA-256 fingerprint obtained from a separate
trusted custody channel.

```python
from hedgeops.pinned_recovery import receipt_fingerprint, verify_pinned_recovery

# Publish this digest to independently controlled retention after receipt
# publication. Never derive the expected value from the untrusted receipt
# during recovery.
expected_digest = receipt_fingerprint(trusted_receipt)
accepted = verify_pinned_recovery(
    backup_path, checkpoint_path, reviewer_registry,
    floor_directory, trusted_receipt_path,
    expected_receipt_sha256=expected_digest,
    checkpoint_key=checkpoint_key,
    floor_key=floor_key,
    receipt_key=receipt_key,
)
```

The expected fingerprint must be exactly 64 lowercase hexadecimal
characters. It binds the canonical receipt contents, and recovery still
requires all three distinct HMAC keys and the complete strict verification
chain. Missing, malformed, or mismatched fingerprints fail closed.

**Critical trust boundary:** a hash is not proof of freshness by itself.
If the operator derives the expected hash from the same untrusted local
receipt during recovery, pinning adds no rollback protection. The
independent custodian must supply the latest accepted fingerprint and
prevent its own rollback. No remote custody service, automatic retrieval,
trusted timestamp or immutable publication is implemented.

Run `python release_check.py --verbose` and confirm both CI jobs.
