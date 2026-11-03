"""Local reviewer-key registry and HMAC-attested review events.

This is symmetric message authentication, not public-key non-repudiation.
Reviewer keys must be supplied out of band and must never be journaled.
"""
import hashlib
import hmac

from hedgeops.store import canonical
from hedgeops.workflow import _required, replay
from hedgeops.operations import require_operator_token

ALLOWED_DECISIONS = frozenset({"approved_for_tracking", "rejected", "needs_revision"})
APPROVAL_ROLE = "approver"
REVIEW_ROLE = "reviewer"
DOMAIN = "hedgeops.review.v1"


def _message(case_id, decision, reviewer, rationale):
    return canonical({"domain": DOMAIN, "case_id": _required(case_id, "case_id"),
                      "decision": decision, "reviewer": _required(reviewer, "reviewer"),
                      "rationale": _required(rationale, "rationale")}).encode("utf-8")


class ReviewerRegistry:
    """Local trust store for reviewer keys and explicit key revocation.

    Legacy entries: reviewer -> (role, secret_bytes).
    Versioned entries: reviewer -> {"role": role, "active": key_id,
                                    "keys": {key_id: secret_bytes},
                                    "revoked": [key_id, ...]}.
    Rotation retains old keys for historical verification. Revocation rejects
    signatures made with the revoked key, including historical approvals.
    """
    def __init__(self, identities):
        self._identities = {}
        for reviewer, entry in identities.items():
            _required(reviewer, "reviewer")
            if isinstance(entry, dict):
                role = entry["role"]
                active = entry["active"]
                keys = dict(entry["keys"])
                revoked = frozenset(entry.get("revoked", ()))
                if (not isinstance(active, str) or not active or
                        not isinstance(keys, dict) or active not in keys):
                    raise ValueError("Invalid active key ID")
                if not all(isinstance(k, str) and k and isinstance(v, bytes)
                           and len(v) >= 32 for k, v in keys.items()):
                    raise ValueError("Reviewer keys must be 32+ bytes with valid IDs")
                if not revoked.issubset(keys):
                    raise ValueError("Unknown revoked key")
                if active in revoked:
                    raise ValueError("Active reviewer key cannot be revoked")
                legacy = False
            else:
                role, key = entry
                if not isinstance(key, bytes) or len(key) < 32:
                    raise ValueError("Reviewer key must be at least 32 bytes")
                active, keys, revoked, legacy = "legacy", {"legacy": key}, frozenset(), True
            if role not in {APPROVAL_ROLE, REVIEW_ROLE}:
                raise ValueError("Unsupported reviewer role")
            self._identities[reviewer] = (role, active, keys, revoked, legacy)

    def _authorize(self, reviewer, decision, key_id=None):
        if decision not in ALLOWED_DECISIONS:
            raise ValueError("Unsupported review decision")
        if reviewer not in self._identities:
            raise PermissionError("Unknown reviewer")
        role, active, keys, revoked, legacy = self._identities[reviewer]
        if decision == "approved_for_tracking" and role != APPROVAL_ROLE:
            raise PermissionError("Approval requires approver role")
        selected = active if key_id is None else key_id
        if selected not in keys or selected in revoked:
            raise PermissionError("Unknown or revoked reviewer key")
        return keys[selected], selected, legacy

    def active_key_id(self, reviewer):
        if reviewer not in self._identities:
            raise PermissionError("Unknown reviewer")
        return self._identities[reviewer][1]

    def sign(self, case_id, decision, reviewer, rationale, *, key_id=None):
        key, selected, legacy = self._authorize(reviewer, decision, key_id)
        if not legacy and selected != self.active_key_id(reviewer):
            raise PermissionError("Only active reviewer keys may sign new reviews")
        message = _message(case_id, decision, reviewer, rationale)
        if not legacy:
            message = canonical({"domain": "hedgeops.review.v2", "key_id": selected,
                                 "message": message.decode("utf-8")}).encode("utf-8")
        return hmac.new(key, message, hashlib.sha256).hexdigest()

    def verify(self, case_id, decision, reviewer, rationale, signature, *, key_id=None):
        key, selected, legacy = self._authorize(reviewer, decision, key_id)
        if not isinstance(signature, str) or len(signature) != 64:
            return False
        message = _message(case_id, decision, reviewer, rationale)
        if not legacy:
            if key_id is None:
                return False
            message = canonical({"domain": "hedgeops.review.v2", "key_id": selected,
                                 "message": message.decode("utf-8")}).encode("utf-8")
        expected = hmac.new(key, message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


def record_attested_review(store, case_id, decision, reviewer, rationale,
                           *, signature, registry, operator_token):
    """Require both operator token and reviewer-specific signed authorization."""
    require_operator_token(operator_token)
    key_id = registry.active_key_id(reviewer)
    if not registry.verify(case_id, decision, reviewer, rationale, signature,
                           key_id=None if key_id == "legacy" else key_id):
        raise PermissionError("Invalid reviewer attestation")
    state = replay(store, case_id)
    if state["analysis"] is None:
        raise ValueError("Analysis not completed")
    if state["review"] is not None:
        raise ValueError("Review already recorded")
    store.append(case_id, "review_recorded", {
        "decision": decision, "reviewer": reviewer, "rationale": rationale,
        "attestation": {"scheme": "hmac-sha256-v1" if key_id == "legacy"
                        else "hmac-sha256-v2", "signature": signature,
                        **({} if key_id == "legacy" else {"key_id": key_id})}},
        expected_stream_events=state["event_count"])
    return replay(store, case_id)


def verify_case_review(store, case_id, registry):
    """Check the entire journal chain and the single case review attestation.

    Returns False for unsigned legacy reviews or malformed/mismatched records.
    """
    if not store.verify_chain():
        return False
    events = [e for e in store.history(case_id) if e["kind"] == "review_recorded"]
    if len(events) != 1:
        return False
    p = events[0]["payload"]
    try:
        attestation = p["attestation"]
        scheme = attestation["scheme"]
        if scheme not in {"hmac-sha256-v1", "hmac-sha256-v2"}:
            return False
        key_id = None if scheme == "hmac-sha256-v1" else attestation["key_id"]
        return registry.verify(case_id, p["decision"], p["reviewer"],
                               p["rationale"], attestation["signature"],
                               key_id=key_id)
    except (KeyError, TypeError, ValueError, PermissionError):
        return False
