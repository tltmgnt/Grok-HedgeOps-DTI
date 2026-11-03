# Phase 55 — Execution custody HTTP integration

The integration suite `tests/test_execution_custody_http.py` runs the reference custody handler on an ephemeral loopback HTTP server and checks the `/v1/execution-checkpoint` protocol end to end. It covers authenticated GET and conditional PUT, monotonic updates, replay and stale ETag rejection, invalid payloads, missing preconditions, namespace separation and concurrent first writes. It also exercises `HTTPSExecutionCheckpointCustodian` through an HTTP transport test adapter without requiring a public TLS service.

Run `python release_check.py --verbose` and confirm Python 3.10 and 3.12 CI. These tests verify the local reference protocol, not production TLS configuration, independent durable custody or rollback resistance. The reference server remains loopback-only and requires an appropriately secured reverse proxy and independently protected storage for production use.
