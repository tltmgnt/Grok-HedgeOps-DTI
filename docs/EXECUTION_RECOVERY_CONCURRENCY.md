# Phase 61 — Competing recovery transactions

Two recovery operations can pass three-namespace preflight using the same execution-audit checkpoint. The local SQLite write transaction serializes their mutations and checks the checkpoint against the current audit head. Once the first transaction appends an audit event, the second transaction must reject its stale checkpoint before running the mutation callback.

`tests/test_competing_execution_recoveries.py` covers two simultaneous preflight successes followed by one successful commit and one stale-head rejection, plus a sequential replay rejection. The tests use a barrier to align preflight and a database marker to count committed mutations.

Phase 60 documentation: the three-namespace admission gate also checks that the checkpoint matches the latest local audit head, while the mutation boundary repeats that check under the SQLite write lock. This does not make remote custody reads and SQLite commits atomic; external custody can still change after admission. Run `python release_check.py --verbose` and check the CI matrix.
