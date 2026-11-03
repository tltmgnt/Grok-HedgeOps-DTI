"""Validate local recovery outbox against its execution audit."""
import sqlite3
from hedgeops.recovery_execution_audit import _verify_rows


class OutboxIntegrityError(ValueError):
    pass


def verify_reconciliation_outbox(authority):
    try:
        with authority._connect() as db:
            db.execute("BEGIN")
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                return False
            audit = db.execute("SELECT sequence,generation,previous_hash,event_hash FROM recovery_execution_audit ORDER BY sequence").fetchall()
            if not _verify_rows(audit):
                return False
            outbox = db.execute("SELECT sequence,event_hash,confirmed FROM recovery_reconciliation_outbox ORDER BY sequence").fetchall()
            pending_seen = False
            for sequence, digest, confirmed in outbox:
                if (type(sequence) is not int or sequence < 1 or sequence > len(audit)
                        or type(confirmed) is not int or confirmed not in (0, 1)
                        or digest != audit[sequence - 1][3]):
                    return False
                if confirmed == 0:
                    pending_seen = True
                elif pending_seen:
                    return False
            return True
    except (sqlite3.Error, ValueError, TypeError, IndexError):
        return False


def require_reconciliation_outbox_integrity(authority):
    if not verify_reconciliation_outbox(authority):
        raise OutboxIntegrityError("Recovery reconciliation outbox integrity failed")
