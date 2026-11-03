"""Fail-closed release gate based on explicit human attestations.

This evaluates supplied evidence, not cryptographic identity or external CI APIs.
"""
from dataclasses import dataclass

REQUIRED = (
    "offline_ci_passed",
    "live_provider_tested",
    "authorization_reviewed",
    "data_protection_reviewed",
    "concurrency_reviewed",
    "maintainer_approved",
)

@dataclass(frozen=True)
class ReleaseAssessment:
    eligible: bool
    missing: tuple

def assess_release(evidence):
    if not isinstance(evidence, dict):
        raise TypeError("Release evidence must be a JSON object")
    missing = tuple(name for name in REQUIRED if evidence.get(name) is not True)
    return ReleaseAssessment(eligible=not missing, missing=missing)
