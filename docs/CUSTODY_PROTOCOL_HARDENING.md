# Phase 32 — Custody HTTP protocol hardening

The loopback-only reference server now rejects ambiguous request framing:
duplicate Authorization headers, duplicate conditional headers, transfer
encoding, missing PUT Content-Length, unexpected GET bodies, and malformed
If-Match validators. Oversized PUT requests close their connection to avoid
reinterpreting unread bytes as another request.

`tests/test_custody_protocol.py` exercises a real local HTTP server with
the existing HTTPS custody client request logic through a test-only transport
adapter. This tests the request/response protocol without claiming TLS
integration or contacting an external service.

**Security boundaries:** The reference server still does not provide TLS,
independent monotonic storage, or administrative rollback resistance. The
test transport is never used for production. Deploy behind authenticated
TLS infrastructure with independent trusted custody and review operational
logging, rate limits, and availability controls before production use.

Run `python release_check.py --verbose` and confirm both CI matrix jobs.
