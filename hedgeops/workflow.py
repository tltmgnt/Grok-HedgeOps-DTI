"""Integrated case workflow: analysis, human review, prediction and observation."""
from uuid import uuid4
from math import isfinite
from hedgeops.lab import run_lab
from hedgeops.store import EventStore

def _required(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value.strip()

def replay(store: EventStore, case_id: str):
    """Materialize state by replaying events for a case in sequence."""
    events = store.history(case_id)
    if not events:
        raise KeyError(f"Unknown case: {case_id}")
    state = {"case_id": case_id, "problem": None, "analysis": None,
             "review": None, "predictions": {}, "event_count": len(events)}
    for event in events:
        kind, p = event["kind"], event["payload"]
        if kind == "case_created":
            state["problem"] = p["problem"]
        elif kind == "analysis_completed":
            state["analysis"] = p["result"]
        elif kind == "review_recorded":
            state["review"] = {"decision": p["decision"], "reviewer": p["reviewer"],
                               "rationale": p["rationale"]}
        elif kind == "prediction_proposed":
            state["predictions"][p["prediction_id"]] = {
                "metric": p["metric"], "target": p["target"],
                "tolerance": p["tolerance"], "unit": p["unit"],
                "status": "pending", "observation": None}
        elif kind == "measurement_recorded":
            prediction = state["predictions"][p["prediction_id"]]
            prediction["status"] = p["status"]
            prediction["observation"] = {
                "value": p["value"], "source": p["source"],
                "reviewer": p["reviewer"], "source_verified": False}
        else:
            raise ValueError(f"Unknown event type: {kind}")
    return state

def create_case(store: EventStore, problem: str, ask):
    _required(problem, "problem")
    case_id = str(uuid4())
    store.append(case_id, "case_created", {"problem": problem})
    result = run_lab(problem, ask)
    store.append(case_id, "analysis_completed", {"result": result})
    return case_id

def record_review(store: EventStore, case_id: str, decision: str,
                  reviewer: str, rationale: str, *, operator_token=None):
    from hedgeops.operations import require_operator_token
    require_operator_token(operator_token)
    if decision not in {"approved_for_tracking", "rejected", "needs_revision"}:
        raise ValueError("Unsupported review decision")
    _required(reviewer, "reviewer")
    _required(rationale, "rationale")
    state = replay(store, case_id)
    if state["analysis"] is None:
        raise ValueError("Analysis not completed")
    if state["review"] is not None:
        raise ValueError("Review already recorded")
    store.append(case_id, "review_recorded", {
        "decision": decision, "reviewer": reviewer, "rationale": rationale},
        expected_stream_events=state["event_count"])
    return replay(store, case_id)

def propose_prediction(store: EventStore, case_id: str, metric: str,
                       target: float, tolerance: float, unit: str, *,
                       review_registry=None, require_attestation=False):
    _required(metric, "metric")
    _required(unit, "unit")
    if any(type(x) not in (int, float) or not isfinite(x)
           for x in (target, tolerance)) or tolerance < 0:
        raise ValueError("Target and tolerance must be finite; tolerance >= 0")
    state = replay(store, case_id)
    if not state["review"] or state["review"]["decision"] != "approved_for_tracking":
        raise PermissionError("Explicit human approval for tracking is required")
    if require_attestation:
        if review_registry is None:
            raise PermissionError("Attested tracking requires a reviewer registry")
        from hedgeops.identity import verify_case_review
        if not verify_case_review(store, case_id, review_registry):
            raise PermissionError("Tracking requires a verified signed approval")
    prediction_id = str(uuid4())
    store.append(case_id, "prediction_proposed", {
        "prediction_id": prediction_id, "metric": metric, "target": target,
        "tolerance": tolerance, "unit": unit},
        expected_stream_events=state["event_count"])
    return prediction_id

def record_measurement(store: EventStore, case_id: str, prediction_id: str,
                       value: float, source: str, reviewer: str):
    _required(source, "source")
    _required(reviewer, "reviewer")
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError("Value must be finite")
    state = replay(store, case_id)
    if prediction_id not in state["predictions"]:
        raise KeyError("Unknown prediction")
    prediction = state["predictions"][prediction_id]
    if prediction["status"] != "pending":
        raise ValueError("Prediction already measured")
    status = ("within_tolerance"
              if abs(value - prediction["target"]) <= prediction["tolerance"]
              else "outside_tolerance")
    store.append(case_id, "measurement_recorded", {
        "prediction_id": prediction_id, "value": value, "source": source,
        "reviewer": reviewer, "status": status},
        expected_stream_events=state["event_count"])
    return replay(store, case_id)
