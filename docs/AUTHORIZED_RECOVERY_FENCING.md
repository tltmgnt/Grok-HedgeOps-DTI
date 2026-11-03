# Phase 45 — Operator-authorized recovery fencing

The local reference authority now supports authenticated generation issuance:

```python
from hedgeops.recovery_fence import RecoveryFenceAuthority

authority = RecoveryFenceAuthority("/protected/custody.sqlite3")
generation = authority.acquire_authorized("operator-1", operator_token)
assert authority.verify_issuance_audit()
```

`acquire_authorized` checks the existing `HEDGEOPS_OPERATOR_TOKEN`
operator secret using the shared authorization helper. A test-only
`configured_token` override supports isolated tests. Operator identifiers
are restricted to short printable identifiers; the SQLite audit stores a
SHA-256 digest, not the identifier or bearer token.

Each authorized issuance increments the recovery generation and appends
a locally hash-chained issuance event **inside the same SQLite
transaction**. `verify_issuance_audit()` checks event continuity and
the current generation. Tests cover invalid tokens, invalid operator
identifiers, concurrent issuance, persistence and audit tampering.

**Important security limitations:**

- This is an **opt-in issuance method**. The legacy `acquire()` method
  remains callable for compatibility, so code or processes with direct
  authority/database access can bypass operator authentication and
  audit. Only expose the authenticated method through a separately
  access-controlled control plane.
- The audit chain is local and not externally anchored. Database
  administrators can rewrite or restore both the generations and audit.
- Hashing operator identifiers does not guarantee anonymity, especially
  for easily guessed identifiers.
- A shared operator token does not provide per-user identity, independent
  authorization, revocation or multi-party approval.
- Phase 44 fenced HTTP writes still require the separately issued
  generation; this change does not expose issuance over HTTP or
  automatically switch existing callers to authenticated issuance.

Run `python release_check.py --verbose` and confirm Python 3.10/3.12 CI.
