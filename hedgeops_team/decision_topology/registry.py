"""Ten overlapping decision-method families; maturity is explicitly bounded."""
from dataclasses import dataclass
from enum import Enum


class DecisionFamily(str, Enum):
    AXIOMATIC = "axiomatic"
    PROBABILISTIC = "probabilistic"
    GAME_THEORETIC = "game_theoretic"
    REINFORCEMENT_LEARNING = "reinforcement_learning"
    COUNTERFACTUAL = "counterfactual"
    REGIME_SWITCHING = "regime_switching"
    BEHAVIORAL = "behavioral"
    INFORMATION_THEORETIC = "information_theoretic"
    TOPOLOGICAL = "topological"
    META = "meta"


@dataclass(frozen=True)
class FamilyCapability:
    family: DecisionFamily
    maturity: str
    scope: str


FAMILY_CAPABILITIES = (
    FamilyCapability(DecisionFamily.AXIOMATIC, "bounded", "Existing deterministic team risk vetoes and validation"),
    FamilyCapability(DecisionFamily.PROBABILISTIC, "research_only", "No trained/calibrated probability model"),
    FamilyCapability(DecisionFamily.GAME_THEORETIC, "research_only", "No formal players, payoffs or solution concept"),
    FamilyCapability(DecisionFamily.REINFORCEMENT_LEARNING, "research_only", "No offline RL policy evaluation"),
    FamilyCapability(DecisionFamily.COUNTERFACTUAL, "bounded", "Temporal what-if sensitivity; not a causal estimator"),
    FamilyCapability(DecisionFamily.REGIME_SWITCHING, "bounded", "Existing static advisory regime table; not latent regime inference"),
    FamilyCapability(DecisionFamily.BEHAVIORAL, "research_only", "No validated behavioral-state model"),
    FamilyCapability(DecisionFamily.INFORMATION_THEORETIC, "research_only", "No acquisition-cost/information-gain optimizer"),
    FamilyCapability(DecisionFamily.TOPOLOGICAL, "bounded", "Typed evidence/dependency DAG; not inferred systemic contagion"),
    FamilyCapability(DecisionFamily.META, "research_only", "No self-rewriting model or policy mutation"),
)
