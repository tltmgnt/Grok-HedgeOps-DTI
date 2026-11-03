# Phase 56 — Three-namespace recovery admission

`verify_recovery_execution_custody_gate(...)` requires independently authenticated and stable fencing, alert and execution-audit custody evidence. `execute_fenced_recovery(...)` accepts optional keyword arguments `execution_checkpoint`, `execution_key` and `execution_custodian`; all three must be supplied together, or none. When supplied, a rejected three-namespace gate prevents the local mutation.

**Bootstrap:** The first recovery execution cannot have an execution-audit checkpoint. Use the existing two-namespace gate for bootstrap, then publish the resulting execution-audit head. The three-namespace mode is currently opt-in for compatibility; it is not a mandatory production policy. Deployments requiring it must enforce that choice at their application boundary.

**Limitations:** The custody checks and subsequent local SQLite transaction are not globally atomic. A remote custodian may change between admission and mutation. The generation and strict policy are rechecked in the local transaction. This phase does not create a distributed lease. Run `python release_check.py --verbose`.
