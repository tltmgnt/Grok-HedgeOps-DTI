# Phase 46 — Persistent strict recovery fence policy

`RecoveryFenceAuthority(path, strict=True)` enables a persistent
strict issuance policy in the authority's SQLite database.

Once enabled, `acquire()` rejects unauthenticated generation issuance
with `PermissionError`, even from another authority instance opened
without `strict=True`. The policy is checked under the same SQLite
write transaction used for legacy issuance, so policy activation and
legacy generation increments serialize.

Authorized issuance remains available through
`acquire_authorized(operator_id, token)`, which authenticates the
operator secret and records the issuance audit in the same transaction.

Existing databases can be upgraded by opening the authority with
`strict=True`. The Python API does not provide a downgrade operation.
Legacy mode remains the default for compatibility. Ten tests cover
persistent policy, upgrades, concurrent bypass attempts and token checks.

**Security limitations:** Strict mode is enforced by application code
and SQLite, not by database permissions. A process with filesystem or
SQL write access can modify or remove the policy, edit generations or
restore an older database. Operators must protect the DB, prevent
untrusted code from running in the authority process, and anchor
monotonic state externally. The HTTP custody service still does not
expose generation issuance. Strict mode does not provide per-user
identity or distributed rollback resistance.

Run `python release_check.py --verbose` and inspect both CI jobs.
