"""Read-only local recovery reconciliation status and integrity health."""
import sqlite3

from hedgeops.recovery_execution_audit import _verify_rows


def reconciliation_health(authority):
    """Return a consistent local snapshot without network calls or writes.

    Status is one of healthy, pending, integrity_failure, or unavailable.
    A missing schema is unavailable rather than silently treated as healthy.
    """
    try:
        with authority._connect() as db:
            db.execute("BEGIN")
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                return {"status": "integrity_failure", "pending": None,
                        "confirmed": None, "audit_head": None}
            audit = db.execute(
                "SELECT sequence,generation,previous_hash,event_hash "
                "FROM recovery_execution_audit ORDER BY sequence").fetchall()
            outbox = db.execute(
                "SELECT sequence,event_hash,confirmed "
                "FROM recovery_reconciliation_outbox ORDER BY sequence").fetchall()
            pending = sum(confirmed == 0 for _, _, confirmed in outbox)
            confirmed = sum(confirmed == 1 for _, _, confirmed in outbox)
            head = audit[-1][0] if audit else 0
            valid = _verify_rows(audit)
            # Every outbox row must occupy its matching audit position.
            # Legacy missing tail rows remain visible as untracked audit
            # to the readiness layer, while internal holes are corruption.
            pending_seen = False
            for expected, (sequence, digest, state) in enumerate(outbox, 1):
                if (type(sequence) is not int or sequence != expected or
                        sequence > len(audit) or type(state) is not int or
                        state not in (0, 1) or
                        digest != audit[sequence - 1][3]):
                    valid = False
                    break
                if state == 0:
                    pending_seen = True
                elif pending_seen:
                    valid = False
                    break
            return {"status": ("integrity_failure" if not valid else
                               "pending" if pending else "healthy"),
                    "pending": pending, "confirmed": confirmed,
                    "audit_head": head}
    except sqlite3.Error:
        return {"status": "unavailable", "pending": None,
                "confirmed": None, "audit_head": None}
