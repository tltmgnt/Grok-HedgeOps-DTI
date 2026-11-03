# Phase 14 — Concurrency and recovery validation

Four offline regression tests exercise two independent SQLite connections to
the same database file:

- Stale stream preconditions reject writes without modifying the event chain.
- Unrelated streams can advance independently.
- Recovery rejects an analysis result if another writer commits first.
- Two connections observe and extend a single ordered event stream.

Run with `python release_check.py --verbose`.

These tests simulate competing connections sequentially and inject an
intervening write during model analysis. They do **not** constitute a
multi-process stress test or prove correctness under network partitions.
Model calls may still be billed before a conflicting commit is rejected.

## Release blockers

- Latest CI result must be checked after the workflow completes.
- Production authorization and individual identity remain unimplemented.
- Live provider integration and cost controls require real-world validation.
- Storage encryption, recovery procedures and external audit anchoring remain
  outside the current prototype.
