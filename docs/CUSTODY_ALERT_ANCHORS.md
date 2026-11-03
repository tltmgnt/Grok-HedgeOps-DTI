# Phase 40 — Independent custody for alert-journal checkpoints

`hedgeops.custody_alert_anchor` defines a **separate** monotonic custody
namespace for Phase 39 authenticated alert-journal checkpoints. It must
not share a resource with the receipt-fingerprint custody record.

```python
from hedgeops.custody_alert_anchor import (
    publish_alert_checkpoint, verify_custodied_alert_journal)

# The adapter must independently guarantee atomic CAS, authenticated fresh
# reads and durable monotonic sequence retention.
checkpoint = publish_alert_checkpoint(journal, alert_checkpoint_key, custodian)
# Retain checkpoint separately; supply it from trusted custody on recovery.
accepted = verify_custodied_alert_journal(
    recovered_journal, trusted_checkpoint, alert_checkpoint_key, custodian)
```

The custodian contract is `read() -> record | None` and
`compare_and_swap(expected, new) -> bool`. The record contains exactly
`sequence` and `checkpoint_sha256`. Publication verifies the complete
journal, creates a signed checkpoint, and only advances a strictly larger
sequence through atomic compare-and-swap. Verification requires the
independently retrieved record, matching checkpoint sequence/fingerprint,
valid HMAC and journal ancestry. Missing or inconsistent evidence fails
closed. Newer journal events after the anchored head are allowed.

**Limitations:** The tests use an in-memory fake, not independent custody.
The existing HTTPS receipt adapter and reference server accept a
`receipt_sha256` schema and are **not** automatically compatible with
`checkpoint_sha256`. A dedicated authenticated remote endpoint with
monotonic, rollback-resistant storage and separately retained checkpoint
contents is required before production use. The custody read must be fresh;
a malicious custodian can replay older valid state. No remote alert anchor
has been deployed.

Run `python release_check.py --verbose` and verify both CI matrix jobs.
