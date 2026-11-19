"""Read-only scenario projection of the existing market regime research policy."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
from typing import Iterable

from market_regime_policy import decide_regime


@dataclass(frozen=True)
class RegimeBranch:
    requested_regime: str | None
    assessed_regime: str
    mode: str
    new_long_entries: str
    execution_authorized: bool = False

    def to_dict(self):
        return {
            "requested_regime": self.requested_regime,
            "assessed_regime": self.assessed_regime,
            "mode": self.mode,
            "new_long_entries": self.new_long_entries,
            "execution_authorized": False,
        }


def simulate_regime_branches(
    regimes: Iterable[str | None] = ("BULL", "NEUTRAL", "BEAR", "UNKNOWN"),
    *, evidence_verified: bool = False,
) -> tuple[RegimeBranch, ...]:
    """Compare advisory policies, not live latent states or trade eligibility.

    evidence_verified is a caller-supplied assertion, not authentication.
    Without it every label maps to UNKNOWN/HOLD.
    """
    if type(evidence_verified) is not bool:
        raise ValueError("evidence_verified must be bool")
    try:
        labels = tuple(islice(regimes, 17))
    except TypeError as exc:
        raise ValueError("regimes must be iterable") from exc
    if not 1 <= len(labels) <= 16:
        raise ValueError("1 to 16 regime scenarios required")
    branches = []
    for label in labels:
        if label is not None and not isinstance(label, str):
            raise ValueError("regime label must be string or None")
        if isinstance(label, str) and len(label) > 64:
            raise ValueError("regime label too long")
        row = decide_regime(label, evidence_verified=evidence_verified)
        if row.execution_authorized is not False:
            raise ValueError("regime policy must not authorize execution")
        branches.append(RegimeBranch(label, row.regime, row.mode, row.new_long_entries))
    return tuple(branches)
