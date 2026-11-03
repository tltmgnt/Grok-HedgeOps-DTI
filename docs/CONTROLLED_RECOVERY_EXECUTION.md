# Phase 50 — Controlled local recovery execution

The new `execute_fenced_recovery(...)` entry point combines operator
authentication, Phase 49 cross-namespace custody verification, strict
issuance policy and a transactional local fencing check.

It requires a valid configured operator token and a positive generation.
The authority database must have strict issuance mode enabled. It
checks both independently retained custody checkpoints and verifies
their local histories before starting a mutation. At the mutation
boundary, `RecoveryFenceAuthority.guarded_update` obtains SQLite
`BEGIN IMMEDIATE`, checks the generation again and runs the supplied
callback on that same connection. Callback exceptions roll back the
local transaction. Strict mode is checked again inside the transaction.

The callback must use only the supplied SQLite connection, must not
commit or roll back, and must not perform network calls, filesystem
mutations or other external side effects. This function does not
automatically invoke `recover_analysis`, the Grok model, remote
custody writes or a deployment.

**Limits:** Cross-namespace custody verification happens before the
local transaction. It cannot atomically lock an independent remote
custodian. Custody can change after preflight; fencing protects only
local mutations using this authority database. SQLite administrators
can still bypass the policy or restore a database. Operator tokens are
shared secrets, not per-person identity. This is not a distributed
recovery lease or an authorization to make remote side effects.

Ten regression tests cover operator denial, gate failure, stale
generations, preflight-to-commit races, strict-mode requirements and
transaction rollback. Run `python release_check.py --verbose` and
confirm Python 3.10 and 3.12 CI.
