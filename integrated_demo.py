"""Offline integrated demonstration; simulated agent responses and measurements."""
import json
import os
from hedgeops.store import EventStore
from hedgeops.workflow import (
    create_case, record_review, propose_prediction, record_measurement, replay)

def simulated_agent(system, problem):
    return {"hypothesis": "Test a reversible pilot before deployment",
            "evidence": [], "assumptions": ["Pilot environment is representative"],
            "risks": ["Measurement bias"], "falsification_tests": ["Measure pilot latency"],
            "confidence": "unknown"}

path = os.environ.get("HEDGEOPS_DB_PATH", "data/hedgeops.sqlite3")
with EventStore(path) as store:
    case_id = create_case(store, "Should we pilot a new deployment?", simulated_agent)
    record_review(store, case_id, "approved_for_tracking", "demo-human",
                  "Synthetic example: permission to record a test, not deploy",
                  operator_token=os.environ.get("HEDGEOPS_OPERATOR_TOKEN"))
    prediction_id = propose_prediction(store, case_id, "latency", 100, 10, "ms",
                                       require_attestation=False)
    record_measurement(store, case_id, prediction_id, 108,
                       "synthetic demo measurement", "demo-human")
    print(json.dumps(replay(store, case_id), indent=2))
    print("Chain valid:", store.verify_chain())
