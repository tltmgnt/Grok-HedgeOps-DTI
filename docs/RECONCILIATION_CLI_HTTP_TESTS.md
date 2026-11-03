# Phase 71 — Readiness CLI and custody HTTP integration

`tests/test_reconciliation_cli_http.py` runs the real `ThreadingHTTPServer` reference custody handler on an ephemeral loopback port and routes the HTTPS-shaped custody client through an in-process HTTP test adapter. It exercises the actual CLI JSON and exit-code path against the real custody database and server protocol.

Coverage includes: pending local reconciliation returns exit code 2 without network requests; a reconciled authenticated checkpoint returns exit code 0 with GET-only custody reads; a conflicting custody fingerprint returns exit code 2 without attempting PUT or changing remote state. The test adapter deliberately bypasses TLS and is only for loopback protocol integration; production HTTPS certificate verification is not covered by these tests.

The CLI is diagnostic only and does not perform remote CAS, local outbox confirmation or recovery mutations. Run `python -m unittest tests/test_reconciliation_cli_http.py` if your test layout supports module import, or `python -m unittest discover -s tests -p 'test_reconciliation_cli_http.py'`.
