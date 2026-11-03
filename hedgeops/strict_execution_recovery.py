"""Strict recovery entry point requiring independently held execution custody."""
from hedgeops.execution_admission_policy import execution_custody_required
from hedgeops.recovery_execution import RecoveryAdmissionError, execute_fenced_recovery


def execute_strict_recovery(
        authority, fence_checkpoint, fence_key, fence_custodian,
        journal, alert_checkpoint, alert_key, alert_custodian,
        generation, operator_token, mutation, *,
        execution_checkpoint, execution_key, execution_custodian,
        configured_token=None):
    with authority._connect() as db:
        if not execution_custody_required(db):
            raise RecoveryAdmissionError("Strict execution custody policy not enabled")
    if (execution_checkpoint is None or execution_key is None or
            execution_custodian is None):
        raise RecoveryAdmissionError("Execution custody evidence is required")
    return execute_fenced_recovery(
        authority, fence_checkpoint, fence_key, fence_custodian,
        journal, alert_checkpoint, alert_key, alert_custodian,
        generation, operator_token, mutation,
        configured_token=configured_token,
        execution_checkpoint=execution_checkpoint,
        execution_key=execution_key,
        execution_custodian=execution_custodian)
