"""Recovery and operator authorization controls for persistent cases.

Shared-secret authorization is an operator gate, not user authentication.
"""
import hashlib
import hmac
import os
from hedgeops.lab import run_lab
from hedgeops.workflow import replay
from hedgeops.store import EventStore

def require_operator_token(supplied, configured=None):
    """Require a secret token for privileged review operations."""
    expected = configured if configured is not None else os.getenv("HEDGEOPS_OPERATOR_TOKEN")
    if not isinstance(expected, str) or len(expected) < 24:
        raise RuntimeError("Configure HEDGEOPS_OPERATOR_TOKEN (at least 24 characters)")
    if not isinstance(supplied, str) or not hmac.compare_digest(
        hashlib.sha256(supplied.encode()).digest(),
        hashlib.sha256(expected.encode()).digest()
    ):
        raise PermissionError("Invalid operator token")

def recover_analysis(store: EventStore, case_id: str, ask):
    """Retry analysis for a case with case_created but no analysis_completed.

    An interrupted model call may have incurred API charges. Re-running can
    incur additional charges. Sequential operator use only: no distributed lock.
    """
    state = replay(store, case_id)
    if state["analysis"] is not None:
        raise ValueError("Case already has an analysis")
    if state["review"] is not None or state["predictions"]:
        raise ValueError("Cannot recover a case with downstream events")
    result = run_lab(state["problem"], ask)
    store.append(case_id, "analysis_completed", {"result": result},
                 expected_stream_events=state["event_count"])
    return replay(store, case_id)

def authorized_review(store, case_id, decision, reviewer, rationale, token,
                      configured_token=None):
    """Gate an existing review operation with an operator-held shared secret."""
    require_operator_token(token, configured_token)
    from hedgeops.workflow import record_review
    # The domain boundary checks the configured secret again; a test-only
    # configured_token override is not an authorization bypass.
    return record_review(store, case_id, decision, reviewer, rationale,
                         operator_token=token)
