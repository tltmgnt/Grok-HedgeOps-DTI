"""Opt-in three-namespace recovery admission with execution audit custody.

A first execution cannot have an existing execution checkpoint. Bootstrap
must use the existing two-namespace gate, then publish its execution head.
"""
from hedgeops.recovery_custody_gate import verify_recovery_custody_gate
from hedgeops.recovery_execution_custody import verify_custodied_execution


def verify_recovery_execution_custody_gate(
        authority, fence_checkpoint, fence_key, fence_custodian,
        journal, alert_checkpoint, alert_key, alert_custodian,
        generation, execution_checkpoint, execution_key, execution_custodian):
    """Require all three authenticated custody namespaces to be consistent."""
    if type(generation) is not int or generation < 1:
        return False
    try:
        before = execution_custodian.read()
        if before is None:
            return False
        if not verify_recovery_custody_gate(
                authority, fence_checkpoint, fence_key, fence_custodian,
                journal, alert_checkpoint, alert_key, alert_custodian,
                generation):
            return False
        if not verify_custodied_execution(
                authority, execution_checkpoint, execution_key,
                execution_custodian):
            return False
        after = execution_custodian.read()
        return (before == after and
                authority.current() == generation)
    except (ValueError, TypeError, KeyError, OSError):
        return False
