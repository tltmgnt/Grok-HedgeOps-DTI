# Phase 47 — Externally retainable fencing audit checkpoint

Use `create_fence_audit_checkpoint(authority, key)` to authenticate
the latest audited recovery-fence issuance. The HMAC-SHA256 key must
be at least 32 bytes and independently protected. The function checks
the complete local issuance hash chain, current generation and SQLite
integrity within one consistent read snapshot before signing the head.

Retain the returned checkpoint **outside the fencing SQLite database**
in independent protected custody. Later call
`verify_fence_audit_checkpoint(authority, trusted_checkpoint, key)`
to verify its HMAC, the anchored historical issuance and all subsequent
issuance events. A later valid issuance is permitted; deletion, audit
rewriting, divergence or generation rollback is rejected.

The checkpoint has fields `scheme`, `generation`, `event_hash`
and `authentication_tag`. No operator token or identifier is exported.

**Trust limitations:** HMAC authentication is not independent freshness.
If an attacker controls the key and the external checkpoint, or can
replace the checkpoint with an older valid one, rollback can remain
undetected. The checkpoint does not automatically publish itself to a
remote custodian, and does not protect unaudited legacy `acquire()`
generations from omission. Use strict mode, independent custody and
external retention. This is not a distributed recovery lease.

Run `python release_check.py --verbose` and confirm both CI jobs.
