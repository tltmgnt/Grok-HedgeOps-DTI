# Phase 16 — Enforced attested tracking mode

Tracking can now be configured to require independently revalidated reviewer
attestations before writing a prediction event:

```python
propose_prediction(store, case_id, "latency", 100, 10, "ms",
                   review_registry=trusted_registry, require_attestation=True)
```

In this mode the workflow rejects missing registries, unsigned legacy reviews,
incorrect reviewer keys, invalid roles, broken event hash chains and missing
approvals. A denied write does not append an event.

## Migration and deployment limits

`require_attestation=False` remains the default to preserve existing callers
and demos. This is **opt-in enforcement**; it does not yet guarantee that all
applications, CLIs and external callers use the secure mode. Production code
should explicitly supply `require_attestation=True` and a trusted registry.
Historical unsigned approvals cannot be promoted to signed approvals merely by
replaying the old record. A new case or separately designed re-attestation
workflow is required.

Reviewer HMAC keys require secure provisioning and lifecycle management.
Direct SQLite access can bypass this check. Neither the journal nor its hash
chain is externally anchored or encrypted.

Run `python release_check.py --verbose` and inspect the latest GitHub Actions
run before treating this feature as verified.
