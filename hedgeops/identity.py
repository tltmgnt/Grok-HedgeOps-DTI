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
    """Trusted local configuration: reviewer ID -> (role, secret bytes).

    Callers must provision distinct random keys (32+ bytes) securely. Registry
    contents are never persisted in the event store.
    """
    def __init__(self, identities):
        self._identities = {}
        for reviewer, entry in identities.items():
            _required(reviewer, "reviewer")
            role, key = entry
            if role not in {APPROVAL_ROLE, REVIEW_ROLE}:
                raise ValueError("Unsupported reviewer role")
            if not isinstance(key, bytes) or len(key) < 32:
                raise ValueError("Reviewer key must be at least 32 bytes")
            self._identities[reviewer] = (role, key)

    def _authorize(self, reviewer, decision):
        if decision not in ALLOWED_DECISIONS:
            raise ValueError("Unsupported review decision")
        if reviewer not in self._identities:
            raise PermissionError("Unknown reviewer")
        role, key = self._identities[reviewer]
        if decision == "approved_for_tracking" and role != APPROVAL_ROLE:
            raise PermissionError("Approval requires approver role")
        return key

    def sign(self, case_id, decision, reviewer, rationale):
        key = self._authorize(reviewer, decision)
        return hmac.new(key, _message(case_id, decision, reviewer, rationale),
                        hashlib.sha256).hexdigest()

    def verify(self, case_id, decision, reviewer, rationale, signature):
        key = self._authorize(reviewer, decision)
        if not isinstance(signature, str) or len(signature) != 64:
            return False
        expected = hmac.new(key, _message(case_id, decision, reviewer, rationale),
                            hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


def record_attested_review(store, case_id, decision, reviewer, rationale,
                           *, signature, registry, operator_token):
    """Require both operator token and reviewer-specific signed authorization."""
    require_operator_token(operator_token)
    if not registry.verify(case_id, decision, reviewer, rationale, signature):
        raise PermissionError("Invalid reviewer attestation")
    state = replay(store, case_id)
    if state["analysis"] is None:
        raise ValueError("Analysis not completed")
    if state["review"] is not None:
        raise ValueError("Review already recorded")
    store.append(case_id, "review_recorded", {
        "decision": decision, "reviewer": reviewer, "rationale": rationale,
        "attestation": {"scheme": "hmac-sha256-v1", "signature": signature}},
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
        return (attestation["scheme"] == "hmac-sha256-v1" and
                registry.verify(case_id, p["decision"], p["reviewer"],
                                p["rationale"], attestation["signature"]))
    except (KeyError, TypeError, ValueError, PermissionError):
        return False
