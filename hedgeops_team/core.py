"""Deterministic multi-agent decision support; no broker integration."""
from dataclasses import dataclass, asdict
from datetime import datetime
from hashlib import sha256
import json
import math

ACTIONS = frozenset({"BUY", "SELL", "HOLD", "REJECT"})

@dataclass(frozen=True)
class RiskLimits:
    max_exposure_pct: float = 0.25
    max_drawdown_pct: float = 0.20
    max_daily_volatility: float = 0.08
    max_position_pct: float = 0.10

    def __post_init__(self):
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("invalid risk limit: " + name)

@dataclass(frozen=True)
class Evidence:
    agent_id: str
    action: str
    confidence: float
    evidence_ids: tuple
    rationale: str
    warnings: tuple = ()

    def __post_init__(self):
        if self.action not in ACTIONS or not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("invalid evidence")
        if not self.agent_id or not self.evidence_ids:
            raise ValueError("evidence requires provenance")

@dataclass(frozen=True)
class DecisionReport:
    action: str
    confidence: float
    reasons: tuple
    evidence: tuple
    input_digest: str
    suggested_position_pct: float = 0.0
    paper_only: bool = True

    def to_dict(self):
        return asdict(self)

def _number(value, name, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name + " must be finite numeric")
    value = float(value)
    if minimum is not None and value < minimum:
        raise ValueError(name + " below minimum")
    return value

def _validate(bars, portfolio):
    if not isinstance(bars, (list, tuple)) or len(bars) < 2:
        raise ValueError("at least two ordered bars required")
    prices, timestamps = [], []
    for bar in bars:
        if not isinstance(bar, dict):
            raise ValueError("bars must be mappings")
        prices.append(_number(bar.get("close"), "close", 0.000000001))
        if "timestamp" in bar:
            stamp = bar["timestamp"]
            if not isinstance(stamp, str):
                raise ValueError("timestamp must be ISO string")
            try:
                parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("invalid timestamp") from exc
            timestamps.append(parsed)
    if timestamps and len(timestamps) != len(bars):
        raise ValueError("timestamps must be supplied for all bars or none")
    if timestamps:
        try:
            ordered = all(a < b for a, b in zip(timestamps, timestamps[1:]))
        except TypeError as exc:
            raise ValueError("mixed timezone timestamps") from exc
        if not ordered:
            raise ValueError("timestamps must be strictly increasing")
    if not isinstance(portfolio, dict):
        raise ValueError("portfolio must be mapping")
    p = {}
    for name in ("equity", "cash", "exposure_pct", "drawdown_pct"):
        p[name] = _number(portfolio.get(name, 0), name, 0)
    if p["exposure_pct"] > 1 or p["drawdown_pct"] > 1 or p["cash"] > p["equity"]:
        raise ValueError("inconsistent portfolio")
    return prices, p

class HedgeOpsTeam:
    def __init__(self, strategic_agent=None, risk_limits=None):
        self.strategic_agent = strategic_agent
        self.risk_limits = risk_limits or RiskLimits()

    def analyze(self, bars, portfolio):
        prices, p = _validate(bars, portfolio)
        digest = sha256(json.dumps({"bars": bars, "portfolio": portfolio}, sort_keys=True, default=str).encode()).hexdigest()
        returns = [b / a - 1 for a, b in zip(prices, prices[1:])]
        mean = sum(returns) / len(returns)
        vol = (sum((r - mean) ** 2 for r in returns) / len(returns)) ** 0.5
        trend = prices[-1] / prices[0] - 1
        temporal_action = "BUY" if trend > 0.01 else "SELL" if trend < -0.01 else "HOLD"
        evidence = [
            Evidence("temporal", temporal_action, min(0.8, abs(trend) * 10), ("close:all",), "Observed price trend"),
            Evidence("risk", "HOLD", 1.0, ("portfolio:exposure_pct", "portfolio:drawdown_pct", "close:returns"), "Hard risk policy"),
        ]
        strategic_action = temporal_action
        if self.strategic_agent is not None:
            try:
                result = self.strategic_agent.analyze(bars=bars, portfolio=portfolio)
                strategic_action = result["action"] if isinstance(result, dict) else result.action
                if strategic_action not in ("BUY", "SELL", "HOLD"):
                    raise ValueError("invalid strategic action")
            except Exception:
                strategic_action = "HOLD"
                evidence.append(Evidence("adapter", "HOLD", 1.0, ("adapter:failure",), "Strategic adapter failed closed"))
        evidence.append(Evidence("strategic", strategic_action, 0.6 if strategic_action != "HOLD" else 1.0, ("close:all",), "Strategic scenario"))
        evidence.append(Evidence("adversarial", "HOLD", 0.5, ("close:returns",), "Historical prices cannot establish future outcomes", ("Forecast uncertainty",)))
        reasons = []
        if p["drawdown_pct"] >= self.risk_limits.max_drawdown_pct:
            reasons.append("drawdown veto")
        if p["exposure_pct"] >= self.risk_limits.max_exposure_pct:
            reasons.append("exposure veto")
        if vol > self.risk_limits.max_daily_volatility:
            reasons.append("volatility veto")
        if len(prices) < 5:
            reasons.append("insufficient regime history")
        if strategic_action != temporal_action:
            reasons.append("strategic disagreement")
        if strategic_action == "HOLD" or temporal_action == "HOLD":
            reasons.append("insufficient directional consensus")
        action = "HOLD" if reasons else temporal_action
        size = min(self.risk_limits.max_position_pct, max(0.0, self.risk_limits.max_exposure_pct - p["exposure_pct"])) if action == "BUY" else 0.0
        return DecisionReport(action, 0.0 if action == "HOLD" else 0.6, tuple(reasons or ("directional consensus; within risk limits",)), tuple(asdict(e) for e in evidence), digest, size)
