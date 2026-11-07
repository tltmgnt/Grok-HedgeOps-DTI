"""EFO: experience, facts, observation and falsification. Offline and paper-only.

SHA-256 content digests detect accidental changes, not malicious rewriting.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math

from .audit import canonical_json, digest_payload

VERSION = "efo-v1"
KINDS = frozenset({"experience", "observation", "fact", "hypothesis"})
VERDICTS = frozenset({"supported", "falsified", "inconclusive"})

def _time(value):
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be ISO 8601")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return parsed.astimezone(timezone.utc)

def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text")
    return value

def _digest(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("invalid SHA-256 digest")
    return value

@dataclass(frozen=True)
class Observation:
    kind: str
    observed_at: str
    recorded_at: str
    source_id: str
    claim: str
    measurements: dict
    evidence_digests: tuple = ()
    schema_version: str = VERSION
    paper_only: bool = True

    def __post_init__(self):
        if self.schema_version != VERSION or self.paper_only is not True or self.kind not in KINDS:
            raise ValueError("invalid observation contract")
        observed, recorded = _time(self.observed_at), _time(self.recorded_at)
        if observed > recorded:
            raise ValueError("observation cannot postdate recording")
        _text(self.source_id, "source_id")
        _text(self.claim, "claim")
        if not isinstance(self.measurements, dict):
            raise ValueError("measurements must be a mapping")
        canonical_json(self.measurements)
        if not isinstance(self.evidence_digests, tuple):
            raise ValueError("evidence_digests must be a tuple")
        for digest in self.evidence_digests:
            _digest(digest)
        if len(set(self.evidence_digests)) != len(self.evidence_digests):
            raise ValueError("duplicate evidence links")
        if self.kind == "fact" and not self.evidence_digests:
            raise ValueError("fact requires linked evidence")
        if self.kind == "hypothesis" and not self.evidence_digests:
            raise ValueError("hypothesis requires linked evidence")

    def to_dict(self):
        return asdict(self)

    @property
    def digest(self):
        return digest_payload(self.to_dict())

@dataclass(frozen=True)
class FalsificationTest:
    hypothesis_digest: str
    criterion: str
    operator: str
    threshold: float
    horizon_end: str
    registered_at: str
    schema_version: str = VERSION
    paper_only: bool = True

    def __post_init__(self):
        if self.schema_version != VERSION or self.paper_only is not True:
            raise ValueError("invalid test contract")
        _digest(self.hypothesis_digest)
        _text(self.criterion, "criterion")
        if self.operator not in {"gt", "ge", "lt", "le"}:
            raise ValueError("unsupported comparison")
        if isinstance(self.threshold, bool) or not isinstance(self.threshold, (int, float)) or not math.isfinite(self.threshold):
            raise ValueError("threshold must be finite")
        if _time(self.registered_at) >= _time(self.horizon_end):
            raise ValueError("test must be registered before outcome horizon")

    @property
    def digest(self):
        return digest_payload(asdict(self))

@dataclass(frozen=True)
class Outcome:
    test_digest: str
    outcome_at: str
    recorded_at: str
    source_id: str
    observed_value: float
    verdict: str
    schema_version: str = VERSION
    paper_only: bool = True

    def __post_init__(self):
        if self.schema_version != VERSION or self.paper_only is not True:
            raise ValueError("invalid outcome contract")
        _digest(self.test_digest)
        if _time(self.outcome_at) > _time(self.recorded_at):
            raise ValueError("outcome cannot postdate recording")
        _text(self.source_id, "source_id")
        if isinstance(self.observed_value, bool) or not isinstance(self.observed_value, (int, float)) or not math.isfinite(self.observed_value):
            raise ValueError("observed_value must be finite")
        if self.verdict not in VERDICTS:
            raise ValueError("invalid verdict")

    @property
    def digest(self):
        return digest_payload(asdict(self))

def register_test(hypothesis, *, criterion, operator, threshold, horizon_end, registered_at):
    if not isinstance(hypothesis, Observation) or hypothesis.kind != "hypothesis":
        raise ValueError("test must reference a hypothesis")
    if _time(hypothesis.recorded_at) > _time(registered_at):
        raise ValueError("hypothesis must predate test registration")
    return FalsificationTest(hypothesis.digest, criterion, operator, threshold, horizon_end, registered_at)

def evaluate_test(test, *, outcome_at, recorded_at, source_id, observed_value):
    if not isinstance(test, FalsificationTest):
        raise ValueError("test must be FalsificationTest")
    if _time(outcome_at) < _time(test.horizon_end):
        raise ValueError("outcome must be observed after horizon")
    if isinstance(observed_value, bool) or not isinstance(observed_value, (int, float)) or not math.isfinite(observed_value):
        raise ValueError("observed_value must be finite")
    meets = {"gt": lambda x, y: x > y, "ge": lambda x, y: x >= y, "lt": lambda x, y: x < y, "le": lambda x, y: x <= y}[test.operator](observed_value, test.threshold)
    return Outcome(test.digest, outcome_at, recorded_at, source_id, observed_value, "supported" if meets else "falsified")

def verify_chain(records, tests=(), outcomes=()):
    """Validate exact references and chronology; no signature or source authenticity."""
    try:
        if not isinstance(records, (tuple, list)) or not isinstance(tests, (tuple, list)) or not isinstance(outcomes, (tuple, list)):
            return False
        if any(not isinstance(r, Observation) for r in records) or any(not isinstance(t, FalsificationTest) for t in tests) or any(not isinstance(o, Outcome) for o in outcomes):
            return False
        record_map = {r.digest: r for r in records}
        test_map = {t.digest: t for t in tests}
        if len(record_map) != len(records) or len(test_map) != len(tests) or len({o.digest for o in outcomes}) != len(outcomes):
            return False
        for record in records:
            for parent in record.evidence_digests:
                linked = record_map.get(parent)
                if linked is None or _time(linked.recorded_at) > _time(record.recorded_at):
                    return False
                if record.kind == "fact" and linked.kind not in {"experience", "observation"}:
                    return False
        for test in tests:
            hypothesis = record_map.get(test.hypothesis_digest)
            if hypothesis is None or hypothesis.kind != "hypothesis" or _time(hypothesis.recorded_at) > _time(test.registered_at):
                return False
        for outcome in outcomes:
            test = test_map.get(outcome.test_digest)
            if test is None or _time(outcome.outcome_at) < _time(test.horizon_end):
                return False
            expected = evaluate_test(test, outcome_at=outcome.outcome_at, recorded_at=outcome.recorded_at, source_id=outcome.source_id, observed_value=outcome.observed_value)
            if outcome.verdict != expected.verdict:
                return False
        return True
    except (ValueError, TypeError, AttributeError, OverflowError):
        return False

def export_chain(records, tests=(), outcomes=()):
    if not verify_chain(records, tests, outcomes):
        raise ValueError("invalid evidence chain")
    payload = {"schema_version": VERSION, "paper_only": True, "observations": [r.to_dict() for r in records], "tests": [asdict(t) for t in tests], "outcomes": [asdict(o) for o in outcomes]}
    return {"payload": payload, "digest": digest_payload(payload)}

def verify_export(document):
    try:
        if not isinstance(document, dict) or set(document) != {"payload", "digest"}:
            return False
        payload = document["payload"]
        if not isinstance(payload, dict) or set(payload) != {"schema_version", "paper_only", "observations", "tests", "outcomes"} or payload["schema_version"] != VERSION or payload["paper_only"] is not True:
            return False
        if digest_payload(payload) != document["digest"]:
            return False
        records = [Observation(**{**r, "evidence_digests": tuple(r["evidence_digests"])}) for r in payload["observations"]]
        tests = [FalsificationTest(**t) for t in payload["tests"]]
        outcomes = [Outcome(**o) for o in payload["outcomes"]]
        return verify_chain(records, tests, outcomes)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return False
