from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class AgentAssessment:
    agent: str
    action: str
    confidence: float
    summary: str
    evidence: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.action = str(self.action).upper()
        if self.action not in {"BUY", "SELL", "HOLD"}:
            self.action = "HOLD"
        self.confidence = min(1.0, max(0.0, float(self.confidence)))

    def to_dict(self):
        return asdict(self)


@dataclass
class TeamReport:
    decision: str
    approved: bool
    rationale: list[str]
    assessments: list[AgentAssessment]
    metrics: dict[str, Any] = field(default_factory=dict)
    safety_mode: str = "PAPER_ONLY_DECISION_SUPPORT"

    def to_dict(self):
        return {
            "decision": self.decision,
            "approved": self.approved,
            "rationale": list(self.rationale),
            "assessments": [a.to_dict() for a in self.assessments],
            "metrics": dict(self.metrics),
            "safety_mode": self.safety_mode,
        }
