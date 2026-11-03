# Phase 36 — Custody security metrics

The loopback custody HTTP server now records thread-safe outcome counters
through `CustodyMetrics`. Each response increments a bounded tuple of
HTTP method (GET/PUT), route category (receipt/health/other) and status
code. Only fixed, allowlisted dimensions are accepted.

```python
metrics = CustodyMetrics()
handler = make_handler(database, bearer_token, metrics=metrics)
snapshot = metrics.snapshot()
```

Snapshots contain counts and categories only: **no bearer tokens,
request bodies, receipt hashes, source addresses or arbitrary URLs**.
Metrics are process-local and reset on restart. No unauthenticated metrics
HTTP endpoint is exposed. Operators may pass a shared metrics instance to
their own trusted monitoring integration.

These counters are observability aids, not immutable security logs.
Connection-level rejections happen before a handler exists and are
tracked separately by `BoundedCustodyHTTPServer.rejected_connections`.
Monitoring, external alert delivery and independent receipt custody
remain deployment responsibilities.

Run `python release_check.py --verbose` and check both CI matrix jobs.
