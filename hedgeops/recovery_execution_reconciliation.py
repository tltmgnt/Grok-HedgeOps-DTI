"""Post-commit reconciliation of a local recovery audit head with custody.

A publication failure cannot undo an already committed SQLite mutation.
"""
import hmac

from hedgeops.recovery_execution_checkpoint import create_execution_checkpoint
from hedgeops.recovery_execution_custody import (
    ExecutionCustodyError, execution_checkpoint_fingerprint,
    validate_execution_record)


class ExecutionReconciliationError(RuntimeError):
    """The local commit exists, but custody is not confirmed."""


def reconcile_execution_custody(authority, key, custodian):
    """Publish or confirm the latest local head; never roll back local commits.

    Returns the authenticated checkpoint only when custody confirms it.
    A same-sequence, different-digest record or a newer custody head fails
    closed. An ambiguous CAS failure is resolved with a fresh read.
    """
    checkpoint = create_execution_checkpoint(authority, key)
    record = validate_execution_record({
        "sequence": checkpoint["sequence"],
        "checkpoint_sha256": execution_checkpoint_fingerprint(checkpoint)})
    try:
        before = custodian.read()
        if before is not None:
            validate_execution_record(before)
            if before["sequence"] >= record["sequence"]:
                if (before["sequence"] == record["sequence"] and
                        hmac.compare_digest(before["checkpoint_sha256"],
                                            record["checkpoint_sha256"])):
                    confirmed = custodian.read()
                    if confirmed is None or validate_execution_record(confirmed) != record:
                        raise ExecutionReconciliationError("Custody changed during confirmation")
                    return checkpoint
                raise ExecutionReconciliationError("Custody head conflicts with local audit")
        try:
            published = custodian.compare_and_swap(before, record)
        except (OSError, TimeoutError, ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise ExecutionReconciliationError(
                "Custody publication uncertain; retry reconciliation") from exc
        after = custodian.read()
        if after is not None:
            validate_execution_record(after)
        if after == record:
            return checkpoint
        if not published:
            raise ExecutionReconciliationError("Custody CAS conflict; retry reconciliation")
        raise ExecutionReconciliationError("Custody changed after publication")
    except (ExecutionCustodyError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise ExecutionReconciliationError("Invalid custody response") from exc
    except (OSError, TimeoutError) as exc:
        raise ExecutionReconciliationError("Custody unavailable; retry reconciliation") from exc
