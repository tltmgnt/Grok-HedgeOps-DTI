# Phase 49 — Cross-namespace recovery custody gate

`verify_recovery_custody_gate` checks the independently retained
fencing issuance audit checkpoint and alert-journal checkpoint together.

The gate requires:
- A positive current recovery generation equal to the trusted fencing
  audit checkpoint and the independently held fencing custody record.
- Matching custody fingerprints and authenticated checkpoint histories.
- An alert custody record matching the authenticated journal checkpoint.
- Both custodians to return the same records before and after validation.

The gate fails closed on missing, substituted or changing custody records.
Eleven regression tests exercise stale generations, wrong keys, tampering
and changes during verification.

**This is a read-only preflight, not a distributed atomic transaction.**
Custody may advance after the final read; the gate does not authorize a
later remote mutation. Recovery writes must still enforce the generation
at their actual commit boundary (Phase 44). The reference SQLite
custodian is not rollback-resistant, and the checkpoint keys and trusted
records must be independently protected.

Run `python release_check.py --verbose` and inspect Python 3.10/3.12 CI.
