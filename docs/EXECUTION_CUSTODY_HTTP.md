# Phase 54 — Execution checkpoint HTTP namespace

The reference custody server now supports authenticated `GET /v1/execution-checkpoint` and conditional `PUT /v1/execution-checkpoint`, isolated from receipt, alert and fencing audit records. The SQLite `execution_custody` table uses transactional compare-and-swap, strong ETags and strictly increasing sequence numbers; first publication requires sequence 1. The HTTPS client is `HTTPSExecutionCheckpointCustodian`.

Requests inherit the existing bearer authentication, framing validation, admission limits and 4096-byte maximum body. A 404 indicates no record, 204 an accepted write and 412 a conflicting conditional update.

**Operational boundary:** The reference server binds to loopback and does not provide TLS itself. Deploy only behind a properly configured TLS reverse proxy with independently protected rollback-resistant storage. A standalone SQLite database is not independent custody, and these requests are not a distributed transaction. Run `python release_check.py --verbose`.
