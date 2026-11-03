"""Independent monotonic custody contract for alert-journal checkpoints.

The custodian must atomically enforce CAS and independently resist rollback.
Never share a receipt-custody resource with alert-checkpoint custody.
"""
import hashlib
import hmac
import re

from hedgeops.custody_alert_checkpoint import (
    _key, _validate, create_alert_checkpoint, verify_alert_checkpoint)
from hedgeops.store import canonical

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class AlertCustodyError(ValueError):
    pass


def checkpoint_fingerprint(checkpoint):
    if _validate(checkpoint) is None:
        raise AlertCustodyError("Invalid alert checkpoint")
    return hashlib.sha256(canonical(checkpoint).encode("utf-8")).hexdigest()


def _record(record):
    if (not isinstance(record, dict) or
            set(record) != {"sequence", "checkpoint_sha256"} or
            type(record["sequence"]) is not int or record["sequence"] < 1 or
            not isinstance(record["checkpoint_sha256"], str) or
            _DIGEST.fullmatch(record["checkpoint_sha256"]) is None):
        raise AlertCustodyError("Invalid alert custody record")
    return record


def publish_alert_checkpoint(journal, checkpoint_key, custodian):
    """Publish a verified journal head using atomic monotonic CAS.

    Custodian API: read() -> record|None;
    compare_and_swap(expected_record, new_record) -> bool.
    """
    checkpoint = create_alert_checkpoint(journal, checkpoint_key)
    new = _record({"sequence": checkpoint["sequence"],
                   "checkpoint_sha256": checkpoint_fingerprint(checkpoint)})
    old = custodian.read()
    if old is not None:
        _record(old)
        if new["sequence"] <= old["sequence"]:
            raise AlertCustodyError("Alert checkpoint sequence must advance")
    if not custodian.compare_and_swap(old, new):
        raise AlertCustodyError("Alert custody CAS conflict")
    confirmed = custodian.read()
    if confirmed is None or _record(confirmed) != new:
        raise AlertCustodyError("Alert custody changed after publication")
    return checkpoint


def verify_custodied_alert_journal(journal, trusted_checkpoint,
                                  checkpoint_key, custodian):
    """Verify ancestry between two custody reads; reject observed advances.

    A writer can still advance after the final read. Callers needing a
    linearizable decision must coordinate through an external custody lease.
    """
    try:
        _key(checkpoint_key)
        record = custodian.read()
        if record is None:
            return False
        _record(record)
        if (_validate(trusted_checkpoint) is None or
                trusted_checkpoint["sequence"] != record["sequence"] or
                not hmac.compare_digest(
                    checkpoint_fingerprint(trusted_checkpoint),
                    record["checkpoint_sha256"])):
            return False
        if not verify_alert_checkpoint(journal, trusted_checkpoint,
                                       checkpoint_key):
            return False
        # Catch concurrent advances during potentially expensive journal checks.
        # This is a second observation, not a lease or atomic read transaction.
        confirmed = custodian.read()
        return confirmed is not None and _record(confirmed) == record
    except (AlertCustodyError, ValueError, TypeError, KeyError, OSError):
        return False
