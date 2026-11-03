# Phase 34 — Reference custody admission limits

`AdmissionController` provides a thread-safe, in-process per-peer
fixed-window limit (default 60 requests per 60 seconds) and a nonblocking
concurrent request limit (default eight active handler operations).
The loopback reference server applies these before SQLite access.

Excess per-peer requests return HTTP 429; a saturated concurrent-request
limit returns HTTP 503. Rejected connections close to avoid interpreting
unread request bodies as subsequent requests. The peer identity comes
from the TCP connection, **not** untrusted forwarded-IP headers.

These are bounded application-level safeguards, not a full denial-of-service
defense: the standard library threading HTTP server can still create
threads before application admission; each process has independent counters;
reverse proxies may collapse all callers into one loopback peer. Production
requires edge admission, connection limits, distributed quotas where
appropriate, monitoring, TLS and independent monotonic receipt custody.

Run `python release_check.py --verbose` and confirm both CI jobs.
