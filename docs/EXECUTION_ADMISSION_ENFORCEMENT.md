# Phase 58 — Enforced execution custody admission

When `require_execution_custody(authority)` has persisted the strict policy, both `execute_fenced_recovery(...)` and `execute_strict_recovery(...)` require all three execution custody arguments: `execution_checkpoint`, `execution_key`, and `execution_custodian`. The original executor reads the policy before admission and rechecks it inside the locally fenced SQLite transaction, before calling the mutation callback. This prevents a legacy caller from omitting execution custody after the policy is enabled.

The policy is opt-in and sticky across database reopenings. Enable it **after** bootstrap has produced and published the first execution audit checkpoint. Calls before policy activation retain the previous two-namespace behavior. A remote custodian changing after admission is not prevented by the local transaction; no distributed lease or independent rollback resistance is implied.

Regression coverage: `tests/test_execution_admission_enforcement.py`. Run `python release_check.py --verbose` and verify CI on Python 3.10 and 3.12.
