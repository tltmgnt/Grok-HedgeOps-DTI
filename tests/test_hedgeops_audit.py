"""Increment 2: audit provenance, independent-evidence labels and tamper resistance."""
from dataclasses import replace
from datetime import timedelta
import json
import pytest

from hedgeops_team import HedgeOpsTeam, RiskLimits
from hedgeops_team.audit import audit_decision, canonical_json, digest_payload, verify_audit

def bars():
    return [{"timestamp": f"2026-01-{i:02d}", "close": 100 + i} for i in range(1, 7)]

def portfolio():
    return {"equity": 200, "cash": 200, "exposure_pct": 0, "drawdown_pct": 0}

def test_audit_deterministic_and_replayable():
    team = HedgeOpsTeam()
    first = audit_decision(team, bars(), portfolio(), implementation_id="test-build")
    assert first == audit_decision(team, bars(), portfolio(), implementation_id="test-build")
    assert verify_audit(first)
    assert verify_audit(first, team=team, replay=True)

def test_policy_changes_audit_identity():
    a = audit_decision(HedgeOpsTeam(), bars(), portfolio())
    b = audit_decision(HedgeOpsTeam(risk_limits=RiskLimits(max_exposure_pct=0.15)), bars(), portfolio())
    assert a.input_digest == b.input_digest
    assert a.policy_digest != b.policy_digest
    assert a.audit_digest != b.audit_digest

def test_implementation_identity_changes_audit():
    a = audit_decision(HedgeOpsTeam(), bars(), portfolio(), "build-1")
    b = audit_decision(HedgeOpsTeam(), bars(), portfolio(), "build-2")
    assert a.audit_digest != b.audit_digest

@pytest.mark.parametrize("field", ["input_json", "input_digest", "policy_json", "policy_digest", "decision_json", "decision_digest", "audit_digest"])
def test_tampering_detected(field):
    a = audit_decision(HedgeOpsTeam(), bars(), portfolio())
    assert not verify_audit(replace(a, **{field: getattr(a, field) + "x"}))

def test_noncanonical_json_rejected_even_if_outer_digest_recomputed():
    a = audit_decision(HedgeOpsTeam(), bars(), portfolio())
    fields = a.__dict__.copy()
    fields["input_json"] = json.dumps(json.loads(a.input_json), indent=2)
    fields["audit_digest"] = digest_payload({k: v for k, v in fields.items() if k != "audit_digest"})
    assert not verify_audit(type(a)(**fields))

def test_mirror_not_independent():
    team = HedgeOpsTeam()
    result = team.analyze(bars(), portfolio())
    assert result.strategic_source == "unverified_mirror"
    assert result.action == "BUY"
    guarded = HedgeOpsTeam(require_independent_strategy=True).analyze(bars(), portfolio())
    assert guarded.action == "HOLD"
    assert "independent strategic evidence required" in guarded.reasons

def test_external_strategy_labeled_not_cryptographically_verified():
    class Strategy:
        def analyze(self, **kwargs):
            return {"action": "BUY"}
    report = HedgeOpsTeam(strategic_agent=Strategy(), require_independent_strategy=True).analyze(bars(), portfolio())
    assert report.action == "BUY"
    assert report.strategic_source == "external_adapter"

def test_adapter_cannot_mutate_input_or_decision_snapshot():
    class Mutator:
        def analyze(self, bars, portfolio):
            bars[0]["close"] = 0
            portfolio["drawdown_pct"] = 1
            return {"action": "BUY"}
    bs, p = bars(), portfolio()
    report = HedgeOpsTeam(strategic_agent=Mutator()).analyze(bs, p)
    assert bs[0]["close"] == 101
    assert p["drawdown_pct"] == 0
    assert report.action == "BUY"
    audit = audit_decision(HedgeOpsTeam(strategic_agent=Mutator()), bs, p)
    assert verify_audit(audit)

def test_replay_requires_matching_policy():
    audit = audit_decision(HedgeOpsTeam(), bars(), portfolio())
    assert not verify_audit(audit, team=HedgeOpsTeam(risk_limits=RiskLimits(max_position_pct=0.05)), replay=True)

def test_nonfinite_and_unsupported_json_rejected():
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})
    with pytest.raises(ValueError):
        canonical_json({"x": {1, 2}})

def test_paper_only_sell_audit():
    bs = bars()
    for i, bar in enumerate(bs):
        bar["close"] = 120 - i
    audit = audit_decision(HedgeOpsTeam(expected_bar_interval=timedelta(days=1)), bs, portfolio())
    assert verify_audit(audit)
    decision = json.loads(audit.decision_json)
    assert decision["action"] == "SELL"
    assert decision["paper_only"] is True
    assert decision["suggested_position_pct"] == 0
