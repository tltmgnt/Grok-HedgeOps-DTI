"""Explainable multidimensional risk diagnostics (advisory, never grants execution).

A missing observation is UNKNOWN, not PASS. Hard failures reject; soft
thresholds can defer or recommend smaller size, but cannot override a hard gate.
"""
from datetime import datetime, timezone
import math

CATEGORIES = (
    "market", "liquidity", "volatility", "execution", "portfolio",
    "drawdown", "data_integrity", "ai_model", "strategy",
    "broker_api", "operations", "event_gap",
)
HARD = {
    "market": ("market_open",),
    "data_integrity": ("asof", "price"),
    "broker_api": ("tradable",),
    "operations": ("kill_switch",),
}
SOFT = {
    "liquidity": ("spread_bps", "volume", "avg_volume"),
    "volatility": ("volatility_pct",),
    "execution": ("estimated_slippage_bps",),
    "portfolio": ("portfolio_exposure_pct",),
    "drawdown": ("daily_loss_pct",),
    "ai_model": ("grok_veto",),
    "strategy": ("sma20", "sma50"),
    "event_gap": ("event_within_24h",),
}
def _number(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)

def assess(signal, *, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(signal, dict):
        signal = {}
    categories = {}
    def record(category, severity, code, detail, factor=1.0):
        categories[category] = {"severity": severity, "code": code,
                                "detail": detail, "size_factor": factor}
    for category in CATEGORIES:
        fields = HARD.get(category, ()) + SOFT.get(category, ())
        if any(k not in signal for k in fields):
            record(category, "UNKNOWN", "MISSING_EVIDENCE",
                   "Missing: " + ", ".join(k for k in fields if k not in signal))
        else:
            record(category, "PASS", "PASS", "Evidence present")
    if signal.get("market_open") is False:
        record("market", "HARD", "MARKET_CLOSED", "Trading session closed")
    if signal.get("market_open") not in (True, False):
        record("market", "UNKNOWN", "UNVERIFIED_MARKET_CLOCK", "Boolean market clock required")
    if signal.get("tradable") is False:
        record("broker_api", "HARD", "NOT_TRADABLE", "Instrument not tradable")
    if signal.get("tradable") not in (True, False):
        record("broker_api", "UNKNOWN", "UNVERIFIED_TRADABILITY", "Broker tradability required")
    if signal.get("kill_switch") is True:
        record("operations", "HARD", "KILL_SWITCH", "Trading suspended")
    elif signal.get("kill_switch") is not False:
        record("operations", "UNKNOWN", "KILL_SWITCH_UNVERIFIED", "Explicit false required")
    if not _number(signal.get("price")) or signal["price"] <= 0:
        record("data_integrity", "HARD", "INVALID_PRICE", "Positive finite price required")
    try:
        observed = datetime.fromisoformat(signal["asof"].replace("Z", "+00:00"))
        if observed.tzinfo is None or not 0 <= (now - observed).total_seconds() <= 900:
            record("data_integrity", "HARD", "STALE_OR_FUTURE_DATA", "Market data outside 15-minute window")
    except (KeyError, TypeError, ValueError, AttributeError):
        record("data_integrity", "HARD", "INVALID_TIMESTAMP", "Timestamp must be timezone-aware ISO 8601")
    spread = signal.get("spread_bps")
    volume, average = signal.get("volume"), signal.get("avg_volume")
    if all(_number(x) for x in (spread, volume, average)):
        if spread < 0 or volume < 0 or average <= 0:
            record("liquidity", "HARD", "INVALID_LIQUIDITY", "Invalid volume or spread")
        elif spread > 20 or volume < average:
            record("liquidity", "SOFT", "LOW_LIQUIDITY", "Wide spread or weak volume", 0.5)
    for category, field, threshold, code in (
        ("volatility", "volatility_pct", 4, "HIGH_VOLATILITY"),
        ("execution", "estimated_slippage_bps", 15, "HIGH_SLIPPAGE"),
        ("portfolio", "portfolio_exposure_pct", 20, "HIGH_EXPOSURE"),
        ("drawdown", "daily_loss_pct", 1, "DAILY_LOSS_THRESHOLD"),
    ):
        value = signal.get(field)
        if _number(value):
            if value < 0:
                record(category, "HARD", "INVALID_METRIC", field + " must be nonnegative")
            elif value > threshold:
                record(category, "SOFT", code, "Threshold exceeded", 0.5)
    if signal.get("grok_veto") is True:
        record("ai_model", "HARD", "GROK_VETO", "AI advisory veto")
    elif signal.get("grok_veto") is not False:
        record("ai_model", "UNKNOWN", "AI_EVIDENCE_MISSING", "Explicit advisory result required")
    if all(_number(signal.get(k)) for k in ("price", "sma20", "sma50")):
        if not signal["price"] > signal["sma20"] > signal["sma50"] > 0:
            record("strategy", "SOFT", "TREND_NOT_CONFIRMED", "Trend rule not met", 0)
    if signal.get("event_within_24h") is True:
        record("event_gap", "SOFT", "EVENT_RISK", "Upcoming event", 0)
    elif signal.get("event_within_24h") is not False:
        record("event_gap", "UNKNOWN", "EVENT_CALENDAR_MISSING", "Event calendar required")
    severity = {v["severity"] for v in categories.values()}
    if "HARD" in severity:
        decision, factor = "REJECT", 0
    elif "UNKNOWN" in severity:
        decision, factor = "DEFER", 0
    else:
        factor = min(v["size_factor"] for v in categories.values())
        decision = "DEFER" if factor == 0 else "REDUCE_SIZE" if factor < 1 else "PASS"
    return {"symbol": signal.get("symbol", ""), "decision": decision,
            "suggested_size_factor": factor, "categories": categories}
