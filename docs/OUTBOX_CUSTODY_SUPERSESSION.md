# Phase 81 — Custody supersession during final confirmation

After publication or verification of the execution checkpoint, the outbox workflow re-reads independent custody inside the local SQLite confirmation transaction. The read must match the exact checkpoint sequence and fingerprint. Missing custody, a newer custody sequence, or a different fingerprint at the same sequence must deny confirmation and leave pending entries unchanged.

`tests/test_outbox_custody_supersession.py` covers all three denials and an unchanged-custody success case. These are deterministic regression tests of the existing read-before-confirmation guarantee. No recovery mutation is retried; the remote custody write, if any, is not rolled back.
