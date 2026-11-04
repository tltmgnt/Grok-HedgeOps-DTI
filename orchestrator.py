from .agents import (TemporalAnalyst, StrategicAnalyst, RiskAnalyst,
                    AdversarialAnalyst)
from .arbitration import EvidenceArbitrator
from .validation import validate_bars


class HedgeOpsTeam:
    def __init__(self, strategic_agent=None, risk_agent=None, arbitrator=None):
        self.temporal = TemporalAnalyst()
        self.strategic = strategic_agent or StrategicAnalyst()
        self.risk = risk_agent or RiskAnalyst()
        self.adversarial = AdversarialAnalyst()
        self.arbitrator = arbitrator or EvidenceArbitrator()

    def analyze(self, bars, portfolio=None):
        validate_bars(bars)
        portfolio = dict(portfolio or {})
        assessments = [
            self.temporal.analyze(bars, portfolio),
            self.strategic.analyze(bars, portfolio),
            self.risk.analyze(bars, portfolio),
            self.adversarial.analyze(bars, portfolio),
        ]
        return self.arbitrator.decide(assessments)
