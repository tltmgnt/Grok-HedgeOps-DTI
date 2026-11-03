# Phase 72 — Fail-closed CLI custody failures

`tests/test_reconciliation_cli_failures.py` exercises the operator CLI with a real local execution audit and outbox, using an injected HTTPS custody transport that returns failures. The tests cover connection timeout, HTTP 401 authentication rejection, malformed JSON, a weak ETag and an oversized response.

Every scenario must produce a nonzero exit code and `ready: false`, never issue a custody PUT, and never print checkpoint key material, bearer tokens or the custody endpoint. Transport errors may be represented as denied readiness (`2`) or unavailable checks (`3`), depending on which layer handles the failure; neither is authorization to recover.

These tests validate fault handling through an injected adapter, not production TLS certificate behavior or actual network partitions. Run `python -m unittest discover -s tests -p 'test_reconciliation_cli_failures.py'`.
