# Phase 44 — Fenced alert custody HTTP writes

The reference custody server supports opt-in fencing for alert-checkpoint
writes:

```python
from hedgeops.custody_server import serve
from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.https_custody import HTTPSAlertCheckpointCustodian

authority = RecoveryFenceAuthority("/protected/custody.sqlite3")
generation = authority.acquire()
# In a separate server process, start:
# serve("/protected/custody.sqlite3", bearer_token,
#       require_alert_fence=True)

custodian = HTTPSAlertCheckpointCustodian(
    "https://trusted.example/v1/alert-checkpoint",
    bearer_token, recovery_fence=generation)
```

When `require_alert_fence=True`, every PUT to
`/v1/alert-checkpoint` requires exactly one positive decimal
`X-Recovery-Fence` header. Missing or malformed generations return
HTTP 428; stale generations return HTTP 412. The server checks the
generation and performs the alert-checkpoint CAS under the **same
SQLite BEGIN IMMEDIATE transaction**. Existing receipt custody is
unfenced and rejects a fence header. The default remains
`require_alert_fence=False` for backward compatibility.

The local generation authority must be created using **the same SQLite
file** as `CustodyDatabase`. Generations are acquired through a trusted
local control plane, not through a public HTTP endpoint. Do not expose
the authority or let arbitrary HTTP clients mint generations.

**Critical limitations:** This opt-in feature is not a distributed
rollback-resistant fencing service. An administrator can restore the
SQLite database, including its generation counter, and reuse old
tokens. An attacker with a valid bearer token and current generation
can still issue a write; the generation is not bound to a principal.
A production deployment requires independent monotonic state, strict
authorization for generation issuance, protected keys and TLS.
Existing deployments must explicitly enable fencing; the default
does not enforce it.

Run `python release_check.py --verbose` and inspect Python 3.10/3.12 CI.
