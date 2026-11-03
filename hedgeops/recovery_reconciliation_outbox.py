"""Durable local outbox for recovery custody reconciliation.

Outbox rows are inserted in the same SQLite transaction as the mutation.
"""
from hedgeops.recovery_execution import execute_fenced_recovery
from hedgeops.recovery_outbox_integrity import require_reconciliation_outbox_integrity
from hedgeops.recovery_execution_audit import execution_audit_head
from hedgeops.recovery_execution_reconciliation import reconcile_execution_custody, ExecutionReconciliationError
from hedgeops.recovery_execution_custody import (
    execution_checkpoint_fingerprint, validate_execution_record)


def ensure_reconciliation_outbox(authority):
    with authority._connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS recovery_reconciliation_outbox (
            sequence INTEGER PRIMARY KEY,
            event_hash TEXT NOT NULL,
            confirmed INTEGER NOT NULL DEFAULT 0 CHECK(confirmed IN (0,1))
        )""")
        db.commit()


def pending_reconciliations(authority):
    """Read pending local commits without invoking any mutation."""
    with authority._connect() as db:
        return [{"sequence": seq, "event_hash": digest}
                for seq, digest in db.execute(
                    "SELECT sequence,event_hash FROM recovery_reconciliation_outbox "
                    "WHERE confirmed=0 ORDER BY sequence").fetchall()]


def execute_with_reconciliation_outbox(
        authority, fence_checkpoint, fence_key, fence_custodian,
        journal, alert_checkpoint, alert_key, alert_custodian,
        generation, operator_token, mutation, *, configured_token=None,
        execution_checkpoint=None, execution_key=None,
        execution_custodian=None):
    """Commit mutation, audit and pending outbox entry atomically."""
    ensure_reconciliation_outbox(authority)

    def wrapped(db):
        result = mutation(db)
        row = db.execute(
            "SELECT sequence,event_hash FROM recovery_execution_audit "
            "ORDER BY sequence DESC LIMIT 1").fetchone()
        next_sequence = row[0] + 1 if row else 1
        # The executor appends its audit event after this callback returns.
        # Predict its hash from the same generation and predecessor.
        from hedgeops.recovery_execution_audit import GENESIS, _digest
        predecessor = row[1] if row else GENESIS
        digest = _digest(next_sequence, generation, predecessor)
        db.execute(
            "INSERT INTO recovery_reconciliation_outbox(sequence,event_hash) "
            "VALUES(?,?)", (next_sequence, digest))
        return result

    return execute_fenced_recovery(
        authority, fence_checkpoint, fence_key, fence_custodian,
        journal, alert_checkpoint, alert_key, alert_custodian,
        generation, operator_token, wrapped, configured_token=configured_token,
        execution_checkpoint=execution_checkpoint, execution_key=execution_key,
        execution_custodian=execution_custodian)


def reconcile_pending_outbox(authority, key, custodian):
    """Publish current head and confirm all covered, matching outbox entries."""
    require_reconciliation_outbox_integrity(authority)
    checkpoint = reconcile_execution_custody(authority, key, custodian)
    with authority._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        # Confirm local linkage again after remote publication.
        # The SQLite write lock prevents concurrent local modifications.
        audit = db.execute(
            "SELECT sequence,generation,previous_hash,event_hash "
            "FROM recovery_execution_audit ORDER BY sequence").fetchall()
        from hedgeops.recovery_execution_audit import _verify_rows
        if not _verify_rows(audit):
            raise ValueError("Execution audit changed during publication")
        all_rows = db.execute(
            "SELECT sequence,event_hash,confirmed "
            "FROM recovery_reconciliation_outbox ORDER BY sequence").fetchall()
        pending_seen = False
        for expected_seq, (seq, digest, confirmed) in enumerate(all_rows, 1):
            if seq != expected_seq or seq > len(audit) or digest != audit[seq - 1][3]:
                raise ValueError("Outbox does not match execution audit")
            if confirmed == 0:
                pending_seen = True
            elif pending_seen:
                raise ValueError("Outbox confirmation order invalid")
        # Confirm remote custody still anchors this exact authenticated head.
        observed = custodian.read()
        expected = {"sequence": checkpoint["sequence"],
                    "checkpoint_sha256": execution_checkpoint_fingerprint(checkpoint)}
        if observed is None or validate_execution_record(observed) != expected:
            raise ExecutionReconciliationError("Custody changed before outbox confirmation")
        rows = db.execute(
            "SELECT sequence,event_hash FROM recovery_reconciliation_outbox "
            "WHERE confirmed=0 AND sequence<=? ORDER BY sequence",
            (checkpoint["sequence"],)).fetchall()
        for sequence, digest in rows:
            actual = db.execute(
                "SELECT event_hash FROM recovery_execution_audit "
                "WHERE sequence=?", (sequence,)).fetchone()
            if actual is None or actual[0] != digest:
                raise ValueError("Outbox does not match execution audit")
        db.execute(
            "UPDATE recovery_reconciliation_outbox SET confirmed=1 "
            "WHERE confirmed=0 AND sequence<=?", (checkpoint["sequence"],))
        db.commit()
    return checkpoint
