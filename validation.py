import math


def validate_bars(bars):
    if not isinstance(bars, (list, tuple)) or len(bars) < 2:
        raise ValueError("bars must contain at least two price records")
    closes = []
    for index, bar in enumerate(bars):
        if not isinstance(bar, dict) or "close" not in bar:
            raise ValueError(f"bar {index} must be a mapping with a close value")
        value = bar["close"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"bar {index} close must be numeric")
        value = float(value)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"bar {index} close must be finite and positive")
        closes.append(value)
    return closes


def finite_metric(value, default=0.0):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default
