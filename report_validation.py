"""Pure advisory report schema validation; no provider imports or execution."""
import json


REQUIRED_FIELDS = frozenset({
    "observation", "evidence", "assumptions", "current_state",
    "desired_state", "gaps", "dependencies", "bottlenecks", "options",
    "risks", "uncertainty", "recommendation", "verification",
})

ARRAY_FIELDS = frozenset({
    "evidence", "assumptions", "gaps", "dependencies",
    "bottlenecks", "options", "risks", "verification",
})

def validate_report(content: str) -> dict:
    """Reject malformed or structurally incomplete model responses."""
    try:
        report = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("Model response is not valid JSON") from exc
    if not isinstance(report, dict):
        raise ValueError("Model response must be a JSON object")
    missing = REQUIRED_FIELDS - report.keys()
    if missing:
        raise ValueError(f"Model response missing fields: {', '.join(sorted(missing))}")
    for field in ARRAY_FIELDS:
        if not isinstance(report[field], list):
            raise ValueError(f"Model response field {field!r} must be an array")
    return report
