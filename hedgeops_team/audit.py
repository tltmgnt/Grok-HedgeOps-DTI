"""Deterministic, offline decision provenance; digests are not signatures."""
from dataclasses import dataclass, asdict
from datetime import timedelta
from hashlib import sha256
import json
import math

from .core import HedgeOpsTeam, RiskLimits, DecisionReport

SCHEMA_VERSION = "hedgeops-audit-v1"

def canonical_json(value):
    """Strict canonical JSON for the supported JSON data model."""
    def validate(item):
        if item is None or isinstance(item, (str, bool, int)):
            return
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("non-finite JSON value")
            return
        if isinstance(item, (list, tuple)):
            for child in item:
                validate(child)
            return
        if isinstance(item, dict):
            if any(not isinstance(k, str) for k in item):
                raise ValueError("JSON keys must be strings")
            for child in item.values():
                validate(child)
            return
        raise ValueError("unsupported JSON type")
    validate(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)

def digest_payload(value):
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()

@dataclass(frozen=True)
class DecisionAudit:
    schema_version: str
    implementation_id: str
    input_json: str
    input_digest: str
    policy_json: str
    policy_digest: str
    decision_json: str
    decision_digest: str
    audit_digest: str

def _policy(team):
    interval = team.expected_bar_interval
    return {
        "risk_limits": asdict(team.risk_limits),
        "expected_bar_interval_us": None if interval is None else (
            (interval.days * 86400 + interval.seconds) * 1000000 + interval.microseconds
        ),
        "require_independent_strategy": team.require_independent_strategy,
        "strategic_source": "external_adapter" if team.strategic_agent is not None else "unverified_mirror",
    }

def audit_decision(team, bars, portfolio, implementation_id="hedgeops-team-v1"):
    if not isinstance(team, HedgeOpsTeam):
        raise TypeError("team must be HedgeOpsTeam")
    if not isinstance(implementation_id, str) or not implementation_id.strip():
        raise ValueError("implementation_id is required")
    inputs = {"bars": bars, "portfolio": portfolio}
    input_json = canonical_json(inputs)
    policy_json = canonical_json(_policy(team))
    # Rehydrate to ensure adapters cannot mutate the archived snapshot.
    snapshot = json.loads(input_json)
    decision = team.analyze(snapshot["bars"], snapshot["portfolio"])
    if not decision.paper_only:
        raise ValueError("non-paper decision rejected")
    decision_json = canonical_json(decision.to_dict())
    fields = {
        "schema_version": SCHEMA_VERSION,
        "implementation_id": implementation_id,
        "input_json": input_json,
        "input_digest": digest_payload(inputs),
        "policy_json": policy_json,
        "policy_digest": digest_payload(json.loads(policy_json)),
        "decision_json": decision_json,
        "decision_digest": digest_payload(json.loads(decision_json)),
    }
    return DecisionAudit(**fields, audit_digest=digest_payload(fields))

def verify_audit(audit, team=None, replay=False):
    """Check consistency; optional replay requires a deterministic compatible team."""
    if not isinstance(audit, DecisionAudit) or audit.schema_version != SCHEMA_VERSION:
        return False
    try:
        fields = asdict(audit)
        expected = fields.pop("audit_digest")
        if digest_payload(fields) != expected:
            return False
        inputs = json.loads(audit.input_json)
        policy = json.loads(audit.policy_json)
        decision = json.loads(audit.decision_json)
        if canonical_json(inputs) != audit.input_json or canonical_json(policy) != audit.policy_json or canonical_json(decision) != audit.decision_json:
            return False
        if digest_payload(inputs) != audit.input_digest or digest_payload(policy) != audit.policy_digest or digest_payload(decision) != audit.decision_digest:
            return False
        if not isinstance(decision, dict) or decision.get("paper_only") is not True:
            return False
        if decision.get("action") not in {"BUY", "SELL", "HOLD"}:
            return False
        if decision.get("action") == "SELL" and (decision.get("sell_semantics") != "directional_signal_only" or decision.get("suggested_position_pct") != 0):
            return False
        if not isinstance(policy, dict) or "risk_limits" not in policy:
            return False
        if replay:
            if not isinstance(team, HedgeOpsTeam) or _policy(team) != policy:
                return False
            recomputed = team.analyze(inputs["bars"], inputs["portfolio"])
            if canonical_json(recomputed.to_dict()) != audit.decision_json:
                return False
        return True
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError):
        return False
