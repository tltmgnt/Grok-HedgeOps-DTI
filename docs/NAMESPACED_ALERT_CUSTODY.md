# Phase 41 — Namespaced HTTPS alert custody

The reference custody server now supports two **independent** authenticated
resources backed by separate SQLite tables:

- `GET/PUT /v1/receipt`: `sequence` and `receipt_sha256` (unchanged).
- `GET/PUT /v1/alert-checkpoint`: `sequence` and `checkpoint_sha256`.

Both enforce atomic SQLite `BEGIN IMMEDIATE` compare-and-swap, strong
ETags, conditional writes, monotonic sequence advancement, HTTP request
framing restrictions, authentication and admission limits. The two record
schemas are mutually exclusive; a write to one cannot overwrite the other.

```python
from hedgeops.https_custody import HTTPSAlertCheckpointCustodian
from hedgeops.custody_alert_anchor import (
    publish_alert_checkpoint, verify_custodied_alert_journal)

custodian = HTTPSAlertCheckpointCustodian(
    "https://independent-custodian.example/v1/alert-checkpoint",
    alert_custody_bearer_token)
checkpoint = publish_alert_checkpoint(journal, checkpoint_key, custodian)
# Independently retain checkpoint; retrieve it from trusted storage on recovery.
assert verify_custodied_alert_journal(
    journal, trusted_checkpoint, checkpoint_key, custodian)
```

**Production limitations:** The reference HTTP server is loopback-only and
does not provide TLS itself. A TLS-terminating reverse proxy, independent
authorization, secure storage, protected keys, external checkpoint
retention, monitoring and rollback-resistant custody are required.
SQLite CAS ensures local concurrency, **not** protection from database
restoration or administrative rollback. Do not deploy the reference
server as an independently trusted monotonic authority.

Run `python release_check.py --verbose` and confirm both CI matrix jobs.
