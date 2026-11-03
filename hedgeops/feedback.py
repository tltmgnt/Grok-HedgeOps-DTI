"""Reality Feedback Ω: explicit predictions, measurements and audit events."""
from datetime import datetime, timezone
from math import isfinite
from uuid import uuid4


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class FeedbackEngine:
    """In-memory state machine. Persistence is delegated to the caller."""

    def __init__(self):
        self.predictions = {}
        self.events = []

    def _event(self, prediction_id, action, details):
        self.events.append({"prediction_id": prediction_id, "action": action,
                            "timestamp": timestamp(), "details": details})

    def propose(self, hypothesis, metric, target, tolerance, unit, source_required=True):
        if not all(isinstance(x, str) and x.strip()
                   for x in (hypothesis, metric, unit)):
            raise ValueError("Hypothesis, metric and unit are required")
        if any(type(x) not in (int, float) or not isfinite(x)
               for x in (target, tolerance)) or tolerance < 0:
            raise ValueError("Target and nonnegative tolerance must be finite numbers")
        identifier = str(uuid4())
        self.predictions[identifier] = {
            "id": identifier, "hypothesis": hypothesis, "metric": metric,
            "target": target, "tolerance": tolerance, "unit": unit,
            "source_required": source_required, "status": "pending",
            "measurement": None, "created_at": timestamp(),
        }
        self._event(identifier, "proposed", {"target": target, "tolerance": tolerance})
        return identifier

    def observe(self, prediction_id, value, source, reviewer):
        if prediction_id not in self.predictions:
            raise KeyError("Unknown prediction")
        prediction = self.predictions[prediction_id]
        if prediction["status"] != "pending":
            raise ValueError("Prediction already evaluated")
        if type(value) not in (int, float) or not isfinite(value):
            raise ValueError("Measurement must be finite")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("Measurement source is required")
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise ValueError("Reviewer identity is required")
        error = abs(value - prediction["target"])
        status = "within_tolerance" if error <= prediction["tolerance"] else "outside_tolerance"
        prediction["measurement"] = {
            "value": value, "source": source, "reviewer": reviewer,
            "observed_at": timestamp(), "absolute_error": error,
            "source_verified": False,
        }
        prediction["status"] = status
        self._event(prediction_id, "observed", {"status": status, "value": value,
                                                "source": source, "reviewer": reviewer})
        return status

    def snapshot(self):
        return {"predictions": list(self.predictions.values()), "events": list(self.events),
                "note": "Measurement provenance is supplied, not independently verified. "
                        "Tolerance checks do not prove or falsify causal hypotheses."}
