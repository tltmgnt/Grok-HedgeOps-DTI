"""Evidence provenance and verification ledger (in-memory; not a fact checker)."""
from dataclasses import dataclass, asdict
from hashlib import sha256
from typing import Optional

@dataclass(frozen=True)
class Evidence:
    claim: str
    source: str
    source_type: str = "unverified"
    retrieved_at: Optional[str] = None
    verified: bool = False

    def __post_init__(self):
        if not self.claim.strip() or not self.source.strip():
            raise ValueError("Evidence requires nonempty claim and source")
        if self.source_type not in {"document", "web", "measurement", "user", "unverified"}:
            raise ValueError("Unsupported source type")
        if self.verified and self.source_type == "unverified":
            raise ValueError("Unverified evidence cannot be marked verified")

    @property
    def identifier(self):
        return sha256((self.claim + "\0" + self.source).encode()).hexdigest()[:16]

    def as_record(self):
        return {"id": self.identifier, **asdict(self)}


def provenance_for_reports(reports):
    """Legacy evidence strings have no source metadata; flag as unverified."""
    return [
        {"agent": agent, "claim": claim, "source": None,
         "verified": False, "status": "source_required"}
        for agent, report in reports.items()
        for claim in report["evidence"]
    ]


def verification_ledger(reports):
    """Create stable test IDs and pending states; never claim tests were run."""
    tests = {}
    for agent, report in reports.items():
        for test in report["falsification_tests"]:
            key = sha256(test.strip().casefold().encode()).hexdigest()[:16]
            if key not in tests:
                tests[key] = {"id": key, "test": test, "proposed_by": [],
                              "status": "pending", "observed_result": None}
            tests[key]["proposed_by"].append(agent)
    return sorted(tests.values(), key=lambda item: item["id"])
