"""Research-only market regime decision policy.

This module does not fetch data, authenticate to brokers, size orders, or
authorize execution. Regime labels must be supplied from independently
reviewed, timestamped research evidence. Unknown/invalid inputs fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Regime = Literal["BULL", "NEUTRAL", "BEAR", "UNKNOWN"]

@dataclass(frozen=True)
class RegimeDecision:
    regime: Regime
    mode: str
    new_long_entries: str
    research_focus: str
    evaluation: str
    execution_authorized: bool = False

_TABLE: dict[str, tuple[str, str, str, str]] = {
    "BULL": (
        "BULL_CONTINUATION_RESEARCH",
        "RESEARCH_ONLY: require validated trend, breadth, liquidity and catalyst evidence",
        "Compare continuation against fixed-exit baseline; model gap/slippage risk",
        "Bull cohorts: net return, drawdown, adverse excursion and costs",
    ),
    "NEUTRAL": (
        "RANGE_OR_UNCERTAIN_RESEARCH",
        "HOLD_NEW_ENTRIES: do not assume momentum follow-through",
        "Test false breakouts, mean reversion and cash baseline offline",
        "Neutral cohorts: false signal rate, turnover, cost-adjusted returns",
    ),
    "BEAR": (
        "CAPITAL_PRESERVATION_RESEARCH",
        "HOLD_NEW_ENTRIES: long-only strategy not validated for bear conditions",
        "Assess downside gaps, liquidity stress and a cash-only baseline; hedges require separate review",
        "Bear cohorts: drawdown, tail loss, gaps and exposure versus cash",
    ),
    "UNKNOWN": (
        "NO_TRADE_RESEARCH",
        "HOLD_NEW_ENTRIES: regime evidence missing, stale or conflicting",
        "Collect independently sourced trend, volatility and breadth evidence",
        "Missing/uncertain cohorts: data coverage and abstention rate",
    ),
}


def decide_regime(regime: str | None, *, evidence_verified: bool = False) -> RegimeDecision:
    """Choose an advisory playbook, never execution permission.

    An asserted label is not proof. If independent evidence verification is
    absent, conservatively classify as UNKNOWN irrespective of the label.
    """
    normalized = regime.strip().upper() if isinstance(regime, str) else "UNKNOWN"
    if not evidence_verified or normalized not in ("BULL", "NEUTRAL", "BEAR"):
        normalized = "UNKNOWN"
    mode, entries, focus, evaluation = _TABLE[normalized]
    return RegimeDecision(normalized, mode, entries, focus, evaluation)


def decision_table() -> dict[str, RegimeDecision]:
    """Return all documented rows, with no authorization to trade."""
    return {
        regime: RegimeDecision(regime, *values)
        for regime, values in _TABLE.items()
    }
