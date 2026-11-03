"""Cross-namespace recovery custody preflight; not a distributed lease."""
import hmac

from hedgeops.fence_audit_custody import audit_fingerprint
from hedgeops.fence_audit_checkpoint import verify_fence_audit_checkpoint
from hedgeops.custody_alert_anchor import checkpoint_fingerprint
from hedgeops.custody_alert_checkpoint import verify_alert_checkpoint


def verify_recovery_custody_gate(authority, fence_checkpoint, fence_key,
                                 fence_custodian, journal, alert_checkpoint,
                                 alert_key, alert_custodian, generation):
    """Require consistent independently held audit and alert checkpoints."""
    if type(generation) is not int or generation < 1:
        return False
    try:
        fence_before = fence_custodian.read()
        alert_before = alert_custodian.read()
        if fence_before is None or alert_before is None:
            return False
        if (fence_before["generation"] != generation or
                fence_checkpoint["generation"] != generation or
                alert_before["sequence"] != alert_checkpoint["sequence"]):
            return False
        if (not hmac.compare_digest(
                fence_before["audit_sha256"], audit_fingerprint(fence_checkpoint)) or
                not hmac.compare_digest(
                    alert_before["checkpoint_sha256"],
                    checkpoint_fingerprint(alert_checkpoint))):
            return False
        if (not verify_fence_audit_checkpoint(
                authority, fence_checkpoint, fence_key) or
                not verify_alert_checkpoint(
                    journal, alert_checkpoint, alert_key) or
                authority.current() != generation):
            return False
        fence_after = fence_custodian.read()
        alert_after = alert_custodian.read()
        return (fence_after == fence_before and
                alert_after == alert_before and
                authority.current() == generation)
    except (ValueError, TypeError, KeyError, OSError):
        return False
