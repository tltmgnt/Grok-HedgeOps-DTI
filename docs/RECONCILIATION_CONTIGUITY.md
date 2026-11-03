# Phase 77 — Contiguous reconciliation outbox integrity

Local reconciliation health now requires each ordered outbox sequence to match its one-based position in the execution audit. A missing first or middle row is an integrity failure even if remaining event hashes are valid. Hash mismatches and confirmation ordering violations remain integrity failures.

A missing tail leaves a valid prefix and is reported by Phase 76 readiness as `UNTRACKED_AUDIT` when no pending rows remain. The integrity health check itself does not create missing rows or publish custody.

Regression coverage: `tests/test_reconciliation_contiguity.py`.
