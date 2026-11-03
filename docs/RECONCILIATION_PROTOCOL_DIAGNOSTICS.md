# Phase 75 — Custody protocol diagnostics

The read-only operator CLI reports `CUSTODY_PROTOCOL_INVALID` with exit code `3` when a custody read returns an invalid record or fails response validation. Transport failures remain `CUSTODY_TRANSPORT_UNAVAILABLE` (exit `3`). Readable but mismatched authenticated evidence remains `CUSTODY_UNVERIFIED` (exit `2`).

The custody observer validates the returned record and never performs CAS or PUT. Diagnostic output contains allowlisted messages only, not raw exceptions or secrets. Regression tests assert the new classification for malformed JSON, weak ETags and oversized responses.
