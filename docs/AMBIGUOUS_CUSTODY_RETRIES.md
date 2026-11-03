# Phase 84 — Ambiguous custody publication and explicit retries

A custody CAS may commit remotely and then lose its response, fail before committing, or return a conflict. In all cases the initial reconciliation must fail closed and leave the local outbox pending. Operators may retry **reconciliation**, not the already committed recovery mutation.

On retry, the reconciliation reads custody: an already matching checkpoint is confirmed without another CAS; absent custody is published through CAS; conflicts remain denied unless a subsequent read verifies the exact checkpoint. After local confirmation, repeated reconciliation is idempotent. `tests/test_ambiguous_custody_retries.py` exercises these outcomes and asserts a single recovery mutation.
