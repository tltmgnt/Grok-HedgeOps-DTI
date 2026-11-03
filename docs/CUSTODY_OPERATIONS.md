# Phase 33 — Reference custody operational controls

The loopback reference server now offers authenticated `GET /v1/health`.
A 200 response means the SQLite database completed `PRAGMA quick_check`;
503 indicates a failed integrity check or SQLite error. This is a local
readiness signal, **not** evidence of external receipt freshness or
rollback-resistant storage. The endpoint does not disclose database paths,
SQL errors, or secrets.

Receipt reads and conditional writes return HTTP 503 on SQLite errors,
rather than propagating private exception details to HTTP clients. Accepted
connections have a five-second socket timeout to bound stalled request
handling. Existing request-framing checks and atomic SQLite CAS remain.

Operational requirements still outstanding: external TLS termination,
authenticated independent monotonic storage, admission controls, rate
limiting, monitoring, secure credential rotation, backup encryption and
disaster-recovery drills. The built-in Python HTTP server is a reference
implementation, not a production-ready internet-facing service.

Run `python release_check.py --verbose` and verify both Python CI jobs.
