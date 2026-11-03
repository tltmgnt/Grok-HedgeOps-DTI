"""Operator-gated, locally fenced recovery mutation execution.

Only local SQLite callbacks on the authority database are supported.
This is not a distributed transaction or a remote recovery executor.
"""
from hedgeops.execution_admission_policy import execution_custody_required
from hedgeops.operations import require_operator_token
from hedgeops.recovery_execution_audit import append_execution_event, ensure_execution_audit
from hedgeops.recovery_custody_gate import verify_recovery_custody_gate
from hedgeops.recovery_fence import StaleRecoveryFence
from hedgeops.recovery_execution_custody_gate import verify_recovery_execution_custody_gate


class RecoveryAdmissionError(PermissionError):
    """Recovery custody evidence or strict issuance policy is insufficient."""


def execute_fenced_recovery(
        authority, fence_checkpoint, fence_key, fence_custodian,
        journal, alert_checkpoint, alert_key, alert_custodian,
        generation, operator_token, mutation, *, configured_token=None,
        execution_checkpoint=None, execution_key=None,
        execution_custodian=None):
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
    with authority._connect() as db:
        required = execution_custody_required(db)
    execution_args = (execution_checkpoint, execution_key, execution_custodian)
    if any(value is not None for value in execution_args) and not all(
            value is not None for value in execution_args):
        raise RecoveryAdmissionError("Execution custody evidence is incomplete")
    if required and not all(value is not None for value in execution_args):
        raise RecoveryAdmissionError("Execution custody required by policy")
    ensure_execution_audit(authority)
    if all(value is not None for value in execution_args):
        permitted = verify_recovery_execution_custody_gate(
            authority, fence_checkpoint, fence_key, fence_custodian,
            journal, alert_checkpoint, alert_key, alert_custodian,
            generation, execution_checkpoint, execution_key,
            execution_custodian)
    else:
        permitted = verify_recovery_custody_gate(
            authority, fence_checkpoint, fence_key, fence_custodian,
            journal, alert_checkpoint, alert_key, alert_custodian,
            generation)
    if not permitted:
        raise RecoveryAdmissionError("Recovery custody gate rejected request")

    def guarded(db):
        # Recheck strict policy inside the same transaction as the mutation.
        if db.execute(
                "SELECT 1 FROM recovery_fence_policy WHERE id=1").fetchone() is None:
            raise RecoveryAdmissionError("Strict fencing policy was removed")
        if execution_custody_required(db) and not all(
                value is not None for value in execution_args):
            raise RecoveryAdmissionError("Execution custody required by policy")
        if all(value is not None for value in execution_args):
            row = db.execute(
                "SELECT sequence,event_hash FROM recovery_execution_audit "
                "ORDER BY sequence DESC LIMIT 1").fetchone()
            if (row is None or
                    type(execution_checkpoint) is not dict or
                    row[0] != execution_checkpoint.get("sequence") or
                    row[1] != execution_checkpoint.get("event_hash")):
                raise RecoveryAdmissionError("Execution audit head advanced")
        result = mutation(db)
        append_execution_event(db, generation)
        return result

    # The fence is rechecked under BEGIN IMMEDIATE at the mutation boundary.
    return authority.guarded_update(generation, guarded)
