# Phase 43 — Recovery fencing generations

`hedgeops.recovery_fence.RecoveryFenceAuthority` provides a **reference,
local SQLite** fencing-generation authority. Each `acquire()` atomically
increments a positive generation under `BEGIN IMMEDIATE`. Stale
generations fail closed.

```python
from hedgeops.recovery_fence import RecoveryFenceAuthority

authority = RecoveryFenceAuthority("/protected/fence.sqlite3")
generation = authority.acquire()

def local_mutation(db):
    db.execute("INSERT INTO guarded_state(value) VALUES (?)", ("accepted",))

authority.guarded_update(generation, local_mutation)
```

`guarded_update()` checks the generation and executes a local mutation in
the **same SQLite transaction** as the check, preventing competing
`acquire()` calls from invalidating the generation before that local
transaction commits. The callback must use the provided connection,
must not commit or roll back itself, and must not perform remote side
effects. All participants must share the same database and fence
authority. `require_current()` is only a read-only diagnostic check;
it is not a commit guard.

**Security and integration boundary:** This is a fencing primitive, not
yet an end-to-end recovery authorization gate. The alert checkpoint
custodian and remote recovery writers are **not automatically fenced**
by this local SQLite authority. For meaningful distributed fencing,
the independently trusted custody service and every protected write
destination must enforce the token atomically with the write.
Restoring/rolling back this SQLite database can reuse old generations.
No distributed lease, expiration, external monotonic authority or
production deployment is provided.

Run `python release_check.py --verbose` and inspect both CI matrix jobs.
