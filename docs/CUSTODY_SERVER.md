# Phase 31 — SQLite-backed reference custody server

`hedgeops.custody_server` provides a **local-only reference server**
implementing the Phase 30 HTTP custody protocol. The server binds to
loopback, authenticates bearer requests, returns strong ETags and uses
SQLite `BEGIN IMMEDIATE` transactions for atomic conditional updates.

Example for local evaluation (do not embed credentials in source):

```python
from hedgeops.custody_server import serve
serve("/protected/custody.sqlite3", operator_supplied_bearer_token)
```

Connect through a properly configured TLS-terminating reverse proxy,
or use a separately authenticated TLS tunnel. The HTTPS client does not
connect to plain HTTP directly. Keep the database, WAL/journal files,
filesystem and backups under restricted operator control.

## Security and deployment limitations

This reference server **is not independently rollback-resistant**.
An administrator who restores an older SQLite database can roll back
the receipt state. A production custodian must use independent
monotonic/immutable retention, authenticated fresh reads, secure TLS
termination, rate limiting, availability monitoring, access controls,
key rotation and disaster recovery. SQLite transaction atomicity alone
does not establish immutable history or independent trust.

The server rejects missing or stale conditions, malformed records,
non-monotonic sequences and unauthorized requests. The regression
suite includes concurrent HTTP writers and database reopening.

Run `python release_check.py --verbose` and verify Python 3.10/3.12 CI.
