"""Immutable forecast/outcome evaluation; no automatic strategy mutation."""
from dataclasses import dataclass
from datetime import datetime, timezone
import math

def _positive_finite_price(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError("price must be finite and positive")
    return float(value)

def _parse_time(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be ISO string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else parsed

@dataclass(frozen=True)
class Forecast:
    as_of: str
    horizon_end: str
    action: str
    reference_price: float

    def __post_init__(self):
        if self.action not in {"BUY", "SELL", "HOLD"}:
            raise ValueError("invalid forecast action")
        _positive_finite_price(self.reference_price)
        start, end = _parse_time(self.as_of), _parse_time(self.horizon_end)
        if (start.tzinfo is None) != (end.tzinfo is None):
            raise ValueError("mixed timezone timestamps")
        if start >= end:
            raise ValueError("forecast horizon must follow forecast")

def evaluate(forecast, outcome_timestamp, realized_price):
    if not isinstance(forecast, Forecast):
        raise ValueError("forecast must be Forecast")
    start = _parse_time(forecast.as_of)
    end = _parse_time(forecast.horizon_end)
    outcome = _parse_time(outcome_timestamp)
    if (start.tzinfo is None) != (end.tzinfo is None) or (end.tzinfo is None) != (outcome.tzinfo is None):
        raise ValueError("mixed timezone timestamps")
    if not start < end <= outcome:
        raise ValueError("outcome must follow the forecast horizon")
    reference = _positive_finite_price(forecast.reference_price)
    realized = _positive_finite_price(realized_price)
    change = realized / reference - 1
    correct = (forecast.action == "BUY" and change > 0) or (forecast.action == "SELL" and change < 0) or (forecast.action == "HOLD" and change == 0)
    return {"realized_return": change, "direction_correct": correct}
