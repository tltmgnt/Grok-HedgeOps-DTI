"""Provisional DTI temporal sensitivity; hypothetical changes are NOT causal effects."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
from math import isfinite
from typing import Iterable


def _finite(value: float, name: str, *, low: float = 0, high: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value):
        raise ValueError(name + " must be a finite numeric value")
    value = float(value)
    if value < low or (high is not None and value > high):
        raise ValueError(name + " out of range")
    return value


@dataclass(frozen=True)
class TemporalCapacity:
    horizon_minutes: float
    committed_minutes: float
    fragmentation_index: float
    autonomy_fraction: float
    recovery_minutes: float = 0.0

    def __post_init__(self):
        horizon = _finite(self.horizon_minutes, "horizon_minutes")
        if horizon <= 0:
            raise ValueError("horizon_minutes must be positive")
        _finite(self.committed_minutes, "committed_minutes", high=horizon)
        _finite(self.fragmentation_index, "fragmentation_index", high=1)
        _finite(self.autonomy_fraction, "autonomy_fraction", high=1)
        _finite(self.recovery_minutes, "recovery_minutes")

    @property
    def free_minutes(self) -> float:
        return self.horizon_minutes - self.committed_minutes

    def effective_minutes(self, *, fragmentation: float | None = None) -> float:
        index = self.fragmentation_index if fragmentation is None else _finite(
            fragmentation, "fragmentation", high=1
        )
        result = max(0.0, self.free_minutes - self.recovery_minutes) * (1 - index) * self.autonomy_fraction
        if not isfinite(result):
            raise ValueError("effective_minutes exceeds numeric range")
        return result


@dataclass(frozen=True)
class TemporalBranch:
    fragmentation_index: float
    required_minutes: float
    effective_minutes: float
    feasible: bool
    execution_authorized: bool = False

    def to_dict(self):
        return {
            "fragmentation_index": self.fragmentation_index,
            "required_minutes": self.required_minutes,
            "effective_minutes": self.effective_minutes,
            "feasible": self.feasible,
            "execution_authorized": False,
        }


def simulate_temporal_branches(
    state: TemporalCapacity,
    required_minutes: float,
    fragmentation_values: Iterable[float] = (0.0, 0.25, 0.5, 0.75, 1.0),
) -> tuple[TemporalBranch, ...]:
    """Bounded hypothetical branch evaluation, without side effects or orders."""
    if not isinstance(state, TemporalCapacity):
        raise ValueError("state must be TemporalCapacity")
    required = _finite(required_minutes, "required_minutes")
    try:
        values = tuple(islice(fragmentation_values, 101))
    except TypeError as exc:
        raise ValueError("fragmentation_values must be iterable") from exc
    if not 1 <= len(values) <= 100:
        raise ValueError("1 to 100 fragmentation scenarios required")
    branches = []
    for value in values:
        index = _finite(value, "fragmentation", high=1)
        capacity = state.effective_minutes(fragmentation=index)
        branches.append(TemporalBranch(
            fragmentation_index=index,
            required_minutes=required,
            effective_minutes=capacity,
            feasible=required <= capacity,
        ))
    return tuple(branches)
