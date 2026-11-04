from collections import Counter
from .models import TeamReport


class EvidenceArbitrator:
    def __init__(self, min_confidence=0.50):
        self.min_confidence = float(min_confidence)

    def decide(self, assessments):
        by_name = {a.agent: a for a in assessments}
        rationale = []
        risk = by_name.get("risk_analyst")
        adversary = by_name.get("adversarial_analyst")

        if risk and risk.metrics.get("risk_pass") is False:
            return TeamReport("REJECT", False,
                ["Risk analyst identified a hard-limit violation."] +
                list(risk.risks), assessments)
        if adversary and adversary.metrics.get("observations", 99) < 5:
            return TeamReport("HOLD", False,
                ["Insufficient observations for a directional decision."], assessments)

        directional = [a for a in assessments
                       if a.agent in {"temporal_analyst", "strategic_analyst"}
                       and a.action in {"BUY", "SELL"}
                       and a.confidence >= self.min_confidence]
        counts = Counter(a.action for a in directional)
        if not directional:
            rationale.append("No sufficiently confident directional recommendation.")
            decision = "HOLD"
        elif counts["BUY"] and counts["SELL"]:
            rationale.append("Strategic and temporal assessments disagree; defer.")
            decision = "HOLD"
        elif counts["BUY"] >= 1:
            decision = "BUY"
            rationale.append("Directional evidence supports BUY; risk gate passed.")
        else:
            decision = "SELL"
            rationale.append("Directional evidence supports SELL; risk gate passed.")

        if adversary and adversary.risks:
            rationale.append("Adversarial review raised issues requiring monitoring.")
        return TeamReport(decision, decision != "REJECT", rationale, assessments,
                          {"directional_assessments": len(directional),
                           "buy_votes": counts["BUY"], "sell_votes": counts["SELL"]})
