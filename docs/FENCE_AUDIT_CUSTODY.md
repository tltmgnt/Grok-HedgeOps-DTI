# Phase 48 — Independent custody for fencing audit heads

`hedgeops.fence_audit_custody` provides a distinct monotonic
custody contract for HMAC-authenticated fencing audit checkpoints.
A custody record contains exactly `generation` and `audit_sha256`.
It must not share the receipt or alert-checkpoint custody namespace.

```python
from hedgeops.fence_audit_custody import (
    publish_fence_audit_checkpoint, verify_custodied_fence_audit)
from hedgeops.https_custody import HTTPSFenceAuditCustodian

custodian = HTTPSFenceAuditCustodian(
    "https://trusted.example/v1/fence-audit", bearer_token)
checkpoint = publish_fence_audit_checkpoint(authority, checkpoint_key, custodian)
assert verify_custodied_fence_audit(
    authority, checkpoint, checkpoint_key, custodian)
```

The reference SQLite server supports GET and conditional PUT at
`/v1/fence-audit`, independently of `/v1/receipt` and
`/v1/alert-checkpoint`. The initial generation can be greater than
one, since a legacy issuance may predate the first audit checkpoint.
Subsequent generations must strictly increase. The client uses HTTPS,
bearer authorization and conditional ETags. Verification checks the
trusted checkpoint, historical audit ancestry and custody consistency
across two reads.

**Limitations:** Reference SQLite custody is rollbackable. HMAC does
not prove freshness; trusted checkpoints and signing keys require
independent retention. Two custody reads are not a linearizable lease,
and a writer can advance after the last read. Production custody must
be independently protected, monotonic and TLS-authenticated. The new
endpoint does not issue generations and is not a replacement for
strict operator authorization.

Run `python release_check.py --verbose` and inspect both CI jobs.
