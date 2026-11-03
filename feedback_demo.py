"""Offline demonstration of Reality Feedback Ω. No API calls."""
import json
from hedgeops.feedback import FeedbackEngine

engine = FeedbackEngine()
prediction_id = engine.propose(
    hypothesis="A proposed intervention reduces processing latency",
    metric="processing_latency", target=100, tolerance=10, unit="ms")
engine.observe(prediction_id, value=107, source="example-only synthetic measurement",
               reviewer="demo")
print(json.dumps(engine.snapshot(), indent=2))
