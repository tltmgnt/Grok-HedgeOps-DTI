# Phase 35 — Connection-level custody admission

The reference custody server now uses `BoundedCustodyHTTPServer` in its
`serve()` entry point. A nonblocking semaphore limits the number of
accepted connections that can spawn handler threads (default 32). Excess
connections are closed immediately, before a handler thread is created.
Slots are released when the handler thread exits, including on errors.

`active_connections` and `rejected_connections` expose counters for
local operational inspection. The existing per-peer request limits and
concurrent database-handler admission remain separate controls.

```python
serve(database_path, bearer_token, max_connections=32)
```

This bounds handler threads, **not** operating-system listen backlog,
connection acceptance rates, reverse-proxy connection pools, process
resources or distributed attacks. A keep-alive client occupies a slot
until disconnect or the configured five-second socket timeout. Rejected
connections receive a close rather than an HTTP response; proxy operators
must handle connection errors and implement their own admission policies.

The server remains loopback-only and is not a production deployment or
independently rollback-resistant custody authority. Run
`python release_check.py --verbose` and confirm both CI jobs.
