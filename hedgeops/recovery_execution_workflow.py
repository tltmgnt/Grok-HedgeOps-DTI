"""Recovery execution followed by explicit, non-atomic custody reconciliation."""
from hedgeops.recovery_execution import execute_fenced_recovery
from hedgeops.recovery_execution_reconciliation import (
    ExecutionReconciliationError, reconcile_execution_custody)


class CommittedRecoveryUnconfirmed(ExecutionReconciliationError):
    """The local recovery committed, but its custody publication is unconfirmed."""

    def __init__(self, cause):
        super().__init__(
            "Local recovery committed; custody unconfirmed. "
            "Retry reconciliation, never the mutation.")
        self.cause = cause
        self.local_committed = True


def execute_and_reconcile_recovery(
        authority, fence_checkpoint, fence_key, fence_custodian,
        journal, alert_checkpoint, alert_key, alert_custodian,
        generation, operator_token, mutation, *,
        custody_key, custody_custodian, configured_token=None,
        execution_checkpoint=None, execution_key=None,
        execution_custodian=None):
    """Run the mutation exactly once, then publish the resulting audit head.

    Returns (mutation_result, published_checkpoint) only on confirmed custody.
    If publication fails after commit, raises CommittedRecoveryUnconfirmed.
    Call reconcile_execution_custody separately to retry publication.
    """
    result = execute_fenced_recovery(
        authority, fence_checkpoint, fence_key, fence_custodian,
        journal, alert_checkpoint, alert_key, alert_custodian,
        generation, operator_token, mutation,
        configured_token=configured_token,
        execution_checkpoint=execution_checkpoint,
        execution_key=execution_key,
        execution_custodian=execution_custodian)
    try:
        checkpoint = reconcile_execution_custody(
            authority, custody_key, custody_custodian)
    except Exception as exc:
        raise CommittedRecoveryUnconfirmed(exc) from exc
    return result, checkpoint
