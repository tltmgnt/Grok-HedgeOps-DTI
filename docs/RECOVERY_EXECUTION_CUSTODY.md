# Phase 53 — Execution audit custody

`publish_execution_checkpoint(authority, key, custodian)` signs the current verified execution audit head and publishes its SHA-256 fingerprint to a separate monotonic custodian. `verify_custodied_execution(authority, checkpoint, key, custodian)` checks HMAC, historical ancestry and the custody record before and after verification.

Custodians must implement `read()` and atomic `compare_and_swap(expected, new)` with independently protected durable monotonic state. The custody record has exactly `sequence` and `checkpoint_sha256`. New publications must strictly advance sequence. A fake in-memory custodian is only for tests.

**Limitations:** This phase provides the domain-level contract, not a deployed HTTPS endpoint or production custody service. A local SQLite copy is rollbackable. The double-read is not a distributed lease or linearizable read across the audit database and custody service. The signing key and trusted checkpoint must remain independently protected. Run `python release_check.py --verbose`.
