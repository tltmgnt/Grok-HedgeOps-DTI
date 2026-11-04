"""Immutable forecast/outcome evaluation; no automatic strategy mutation."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Forecast:
    as_of: str
    horizon_end: str
    action: str
    reference_price: float

def evaluate(forecast, outcome_timestamp, realized_price):
    if not forecast.as_of < forecast.horizon_end <= outcome_timestamp:
        raise ValueError("outcome must follow the forecast horizon")
    if forecast.reference_price <= 0 or realized_price <= 0:
        raise ValueError("prices must be positive")
    change = realized_price / forecast.reference_price - 1
    correct = (forecast.action == "BUY" and change > 0) or (forecast.action == "SELL" and change < 0) or (forecast.action == "HOLD" and change == 0)
    return {"realized_return": change, "direction_correct": correct}
