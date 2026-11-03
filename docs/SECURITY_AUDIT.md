# Phase 13 — Security regression validation

This phase adds regression tests for the shared-secret review boundary:

- Invalid operator tokens must not append a review event.
- The operator token must not be serialized into the SQLite journal.
- Valid reviews must survive a database reopen and preserve the event hash chain.

These are **offline application tests**, not a penetration test, a verified
identity system, or an external audit. The SQLite journal still stores case
content in plaintext; operators must treat it as sensitive data.

## Reproduce

```bash
python release_check.py --verbose
```

## Release status

Phase 10 CI was verified successful on Python 3.10 and 3.12.
The final Phase 12 CI result could not be independently confirmed through
the available commit-workflow lookup. Phase 13 CI must be checked separately.

**Remaining blockers:** authenticated identities, authorization for all write
operations, live xAI integration tests, encrypted storage and backup testing.
