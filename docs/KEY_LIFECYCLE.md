# Phase 18 — Local reviewer key rotation and revocation

The existing `ReviewerRegistry({"alice": ("approver", secret_bytes)})`
format remains supported for legacy HMAC-SHA256 v1 attestations.

Versioned reviewer keys use this trusted configuration shape:

```python
ReviewerRegistry({"alice": {
    "role": "approver",
    "active": "2026-q4",
    "keys": {"2026-q4": key_bytes, "2026-q3": previous_key_bytes},
    "revoked": ["2026-q3"],
}})
```

Each key must contain at least 32 bytes of independently provisioned secret
material. Keep keys outside source control and event payloads.

New versioned signatures bind a `key_id` to the case, decision, reviewer,
rationale and v2 domain. Only the active key can sign a new review.
Historical v2 signatures remain verifiable after rotation **if the old key is
retained and not revoked**. Revocation causes verification to fail, including
for historical approvals; secure tracking then fails closed. This intentionally
prioritizes current trust over preservation of historical authorization.

A historical v1 signature remains compatible with a legacy registry. The
legacy key format has no versioned key lifecycle controls.

## Limitations

This is an in-memory trust configuration, not a durable key-management service,
automatic revocation distribution, certificate authority or SSO. Operators
must securely and consistently distribute updated registries to every process.
There is no independent timestamp authority or external journal anchoring.
A malicious database administrator can still alter case data and an
administrator holding a reviewer key can impersonate the reviewer.

Run `python release_check.py --verbose` and confirm both CI matrix jobs.
