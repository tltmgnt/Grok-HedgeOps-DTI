# Phase 30 — HTTPS custody adapter

`HTTPSReceiptCustodian(url, bearer_token)` implements the Phase 29
`read()` / `compare_and_swap(expected, new)` contract over HTTPS using
Python's standard library.

Example (operator supplies URL and secret through secure configuration):

```python
custodian = HTTPSReceiptCustodian(custody_url, custody_bearer_token)
publish_receipt_to_custodian(
    floor_directory, receipt_path, floor_key, receipt_key, custodian)
accepted = verify_custodied_recovery(
    backup_path, checkpoint_path, reviewer_registry,
    floor_directory, receipt_path, custodian,
    checkpoint_key=checkpoint_key, floor_key=floor_key,
    receipt_key=receipt_key)
```

## Required remote service contract

- `GET /receipt` returns `200`, a JSON custody record and a **strong**
  `ETag`; `404` means no record exists.
- Initial `PUT` sends `If-None-Match: *`; updates send `If-Match`
  with the last read's strong ETag.
- Successful conditional writes return `200`, `201` or `204`;
  `409`, `412` or `428` signal conflicts.
- The service must atomically enforce conditions, authenticate and authorize
  writers, reject non-monotonic sequences, durably retain the latest state,
  prohibit deletion/rollback, and return fresh reads.
- TLS certificate validation is enabled. Supply a trusted service endpoint;
  the adapter rejects redirected successful responses, but deployments
  should also disable cross-origin redirects in their network policy.

The adapter does **not** deploy the remote service or prove its security.
A server that ignores conditional headers, replays old responses or
allows administrative rollback does not satisfy the custody contract.
Bearer credentials must not be committed or logged. Requests are bounded
to 60 seconds and reads to 4 KiB.

Tests use mocked HTTPS responses; no external service is contacted.
Run `python release_check.py --verbose` and check both CI jobs.
