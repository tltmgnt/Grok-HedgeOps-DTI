"""Operator-gated, locally fenced recovery mutation execution.

Only local SQLite callbacks on the authority database are supported.
This is not a distributed transaction or a remote recovery executor.
"""
from hedgeops.operations import require_operator_token
from hedgeops.recovery_execution_audit import append_execution_event, ensure_execution_audit
from hedgeops.recovery_custody_gate import verify_recovery_custody_gate
from hedgeops.recovery_fence import StaleRecoveryFence


class RecoveryAdmissionError(PermissionError):
    """Recovery custody evidence or strict issuance policy is insufficient."""


def execute_fenced_recovery(
        authority, fence_checkpoint, fence_key, fence_custodian,
        journal, alert_checkpoint, alert_key, alert_custodian,
        generation, operator_token, mutation, *, configured_token=None):
    """Authorize, verify custody, and execute one local fenced transaction.

    mutation(db) must only modify the authority's own SQLite database
    using the supplied connection. No remote calls, commits, rollbacks,
    or other side effects are permitted inside mutation.
    """
    require_operator_token(operator_token, configured_token)
    if not callable(mutation):
        raise TypeError("Recovery mutation must be callable")
    if type(generation) is not int or generation < 1:
        raise RecoveryAdmissionError("Invalid recovery generation")
    with authority._connect() as db:
        policy = db.execute(
            "SELECT 1 FROM recovery_fence_policy WHERE id=1").fetchone()
    if policy is None:
        raise RecoveryAdmissionError("Strict fencing policy is required")
    ensure_execution_audit(authority)
    if not verify_recovery_custody_gate(
            authority, fence_checkpoint, fence_key, fence_custodian,
            journal, alert_checkpoint, alert_key, alert_custodian,
            generation):
        raise RecoveryAdmissionError("Recovery custody gate rejected request")

    def guarded(db):
        # Recheck strict policy inside the same transaction as the mutation.
        if db.execute(
                "SELECT 1 FROM recovery_fence_policy WHERE id=1").fetchone() is None:
            raise RecoveryAdmissionError("Strict fencing policy was removed")
        result = mutation(db)
        append_execution_event(db, generation)
        return result

    # The fence is rechecked under BEGIN IMMEDIATE at the mutation boundary.
    return authority.guarded_update(generation, guarded)
