"""Offline fail-closed tests for the additive Grok/HedgeOps decision topology."""
from dataclasses import replace
from itertools import repeat
from unittest.mock import patch

import pytest

from hedgeops_team import HedgeOpsTeam
from hedgeops_team.decision_topology import (
    DecisionEdge, DecisionFamily, EdgeKind, FAMILY_CAPABILITIES, NodeKind,
    TemporalCapacity, build_structured_report_topology, build_team_topology,
    simulate_regime_branches, simulate_temporal_branches, validate_topology,
)
from report_validation import ARRAY_FIELDS, REQUIRED_FIELDS


def bars(*, down=False, count=6):
    return [
        {"timestamp": "2026-01-%02d" % (i + 1),
         "close": (110 - i if down else 100 + i)}
        for i in range(count)
    ]


def portfolio(**kwargs):
    data = {"equity": 200.0, "cash": 200.0, "exposure_pct": 0.0, "drawdown_pct": 0.0}
    data.update(kwargs)
    return data


def structured_report():
    data = {key: [] if key in ARRAY_FIELDS else "UNKNOWN" for key in REQUIRED_FIELDS}
    data["evidence"] = ["Unverified model-supplied claim"]
    data["risks"] = ["False certainty"]
    data["verification"] = ["Independently validate source"]
    data["recommendation"] = "Hypothesis only"
    return data


def test_team_topology_additive_and_not_executable():
    team = HedgeOpsTeam()
    original = team.analyze(bars(), portfolio())
    report, graph = team.analyze_with_topology(bars(), portfolio())
    assert report == original
    assert report.action == "BUY"
    assert graph.source == "deterministic_team"
    assert graph.disposition == report.action
    assert graph.input_digest == report.input_digest
    assert graph.paper_only is True
    assert graph.human_review_required is True
    assert graph.execution_authorized is False
    assert graph.to_dict()["execution_authorized"] is False
    assert {n.attributes["agent_id"] for n in graph.nodes if n.kind == NodeKind.AGENT} == {
        "temporal", "strategic", "risk", "adversarial"
    }
    assert any(n.kind == NodeKind.EVIDENCE_REF and n.attributes["verified"] is False
               for n in graph.nodes)
    validate_topology(graph)


def test_risk_veto_stays_hold_in_graph():
    team = HedgeOpsTeam()
    report, graph = team.analyze_with_topology(bars(), portfolio(drawdown_pct=0.25))
    assert report.action == graph.disposition == "HOLD"
    assert report.suggested_position_pct == 0
    assert "drawdown veto" in [
        n.label for n in graph.nodes if n.kind == NodeKind.REVIEW_REASON
    ]
    assert graph.execution_authorized is False


def test_directional_sell_remains_paper_only():
    report, graph = HedgeOpsTeam().analyze_with_topology(bars(down=True), portfolio())
    assert report.action == graph.disposition == "SELL"
    assert next(n for n in graph.nodes if n.kind == NodeKind.DISPOSITION
                ).attributes["sell_semantics"] == "directional_signal_only"
    assert report.suggested_position_pct == 0


def test_broken_adapter_keeps_failure_provenance():
    class Broken:
        def analyze(self, **kwargs):
            raise RuntimeError("synthetic adapter failure")
    report, graph = HedgeOpsTeam(strategic_agent=Broken()).analyze_with_topology(
        bars(), portfolio()
    )
    assert report.action == "HOLD"
    assert report.strategic_source == "adapter_failure"
    assert "adapter" in {
        n.attributes["agent_id"] for n in graph.nodes if n.kind == NodeKind.AGENT
    }


def test_tampered_team_report_cannot_bypass_paper_only():
    report = HedgeOpsTeam().analyze(bars(), portfolio())
    for altered in (
        replace(report, paper_only=False),
        replace(report, input_digest="0" * 8),
        replace(report, confidence=float("nan")),
        replace(report, action="APPROVED"),
        replace(report, action="SELL", suggested_position_pct=0.01),
        replace(report, action="HOLD", suggested_position_pct=0.1),
    ):
        with pytest.raises(ValueError):
            build_team_topology(altered)


def test_missing_and_duplicate_roles_are_rejected():
    report = HedgeOpsTeam().analyze(bars(), portfolio())
    for rows in (
        report.evidence[:-1],
        report.evidence[:-1] + (report.evidence[0],),
    ):
        with pytest.raises(ValueError, match="role|evidence"):
            build_team_topology(replace(report, evidence=rows))


def test_injected_veto_cannot_keep_directional_action():
    report = HedgeOpsTeam().analyze(bars(), portfolio())
    with pytest.raises(ValueError, match="veto"):
        build_team_topology(replace(report, reasons=("drawdown veto",)))


def test_graph_rejects_execution_and_missing_paths():
    _, graph = HedgeOpsTeam().analyze_with_topology(bars(), portfolio())
    for changed in (
        replace(graph, paper_only=False),
        replace(graph, human_review_required=False),
        replace(graph, execution_authorized=True),
        replace(graph, disposition="APPROVED"),
        replace(graph, input_digest="0" * 64),
    ):
        with pytest.raises(ValueError):
            validate_topology(changed)
    removed = next(e for e in graph.edges if e.kind == EdgeKind.OBSERVES)
    with pytest.raises(ValueError, match="incomplete"):
        validate_topology(replace(
            graph, edges=tuple(e for e in graph.edges if e != removed)
        ))
    with pytest.raises(ValueError, match="duplicate"):
        validate_topology(replace(graph, edges=graph.edges + (graph.edges[0],)))
    with pytest.raises(ValueError, match="dangling"):
        validate_topology(replace(graph, edges=graph.edges + (
            DecisionEdge("missing", "advisory", EdgeKind.INFORMS),)))
    with pytest.raises(ValueError, match="typed"):
        validate_topology(replace(graph, edges=graph.edges + (
            DecisionEdge("advisory", "input", EdgeKind.INFORMS),)))


def test_grok_projection_is_structural_not_verified():
    report = structured_report()
    graph = build_structured_report_topology(report)
    assert graph.source == "grok_structured_report"
    assert graph.disposition == "ADVISORY_ONLY"
    assert graph.paper_only is True
    assert graph.human_review_required is True
    assert graph.execution_authorized is False
    field_nodes = [n for n in graph.nodes if n.kind == NodeKind.REPORT_FIELD]
    assert {n.attributes["field"] for n in field_nodes} == set(REQUIRED_FIELDS)
    assert all(n.attributes["verified"] is False for n in field_nodes)
    assert graph.to_dict()["disposition"] == "ADVISORY_ONLY"
    validate_topology(graph)


def test_grok_projection_rejects_missing_or_invalid_fields():
    report = structured_report()
    report.pop("evidence")
    with pytest.raises(ValueError, match="missing fields"):
        build_structured_report_topology(report)
    report = structured_report()
    report["evidence"] = "claim"
    with pytest.raises(ValueError, match="array"):
        build_structured_report_topology(report)
    report = structured_report()
    report["extra"] = float("nan")
    with pytest.raises(ValueError):
        build_structured_report_topology(report)


def test_grok_projection_preserves_extra_fields_and_detects_tampering():
    report = structured_report()
    report["extra"] = {"provenance": "not externally authenticated"}
    graph = build_structured_report_topology(report)
    assert len([n for n in graph.nodes if n.kind == NodeKind.REPORT_FIELD]) == len(report)
    nodes = tuple(
        replace(n, attributes={**n.attributes, "value_json": '"Altered"'})
        if n.kind == NodeKind.REPORT_FIELD and n.attributes["field"] == "recommendation"
        else n for n in graph.nodes
    )
    with pytest.raises(ValueError, match="digest"):
        validate_topology(replace(graph, nodes=nodes))


def test_grok_agent_helper_does_not_call_provider_in_test():
    from agent import analyze_with_topology
    synthetic = structured_report()
    with patch("agent.analyze", return_value=synthetic) as request:
        report, graph = analyze_with_topology("hypothetical study")
    request.assert_called_once_with("hypothetical study")
    assert report == synthetic
    assert graph.execution_authorized is False


def test_temporal_what_if_is_bounded_and_noncausal():
    state = TemporalCapacity(
        horizon_minutes=120, committed_minutes=70,
        fragmentation_index=0.25, autonomy_fraction=0.8,
        recovery_minutes=10,
    )
    assert state.effective_minutes() == pytest.approx(24)
    branches = simulate_temporal_branches(state, 30, [0, 0.25, 1])
    assert [b.effective_minutes for b in branches] == pytest.approx([32, 24, 0])
    assert [b.feasible for b in branches] == [True, False, False]
    assert all(b.execution_authorized is False for b in branches)
    assert state.fragmentation_index == 0.25


@pytest.mark.parametrize("required,values", [
    (True, [0.0]), (-1, [0.0]), (float("nan"), [0.0]),
    (1, []), (1, [True]), (1, [float("inf")]), (1, [1.1]),
    (1, repeat(0.5)), (1, [0] * 101),
])
def test_invalid_temporal_scenarios_rejected(required, values):
    state = TemporalCapacity(120, 70, 0.25, 0.8, 10)
    with pytest.raises(ValueError):
        simulate_temporal_branches(state, required, values)


def test_regime_branches_never_grant_execution():
    unknown = simulate_regime_branches()
    assert {r.assessed_regime for r in unknown} == {"UNKNOWN"}
    assert all(r.execution_authorized is False for r in unknown)
    reviewed = simulate_regime_branches(("BULL", "NEUTRAL", "BEAR"), evidence_verified=True)
    assert [r.assessed_regime for r in reviewed] == ["BULL", "NEUTRAL", "BEAR"]
    assert all(r.execution_authorized is False for r in reviewed)
    with pytest.raises(ValueError):
        simulate_regime_branches(evidence_verified=1)
    with pytest.raises(ValueError):
        simulate_regime_branches(repeat("BULL"), evidence_verified=True)


def test_10_family_registry_does_not_claim_unbuilt_models():
    assert len(DecisionFamily) == 10
    assert {f.family for f in FAMILY_CAPABILITIES} == set(DecisionFamily)
    bounded = {f.family for f in FAMILY_CAPABILITIES if f.maturity == "bounded"}
    assert bounded == {
        DecisionFamily.AXIOMATIC, DecisionFamily.COUNTERFACTUAL,
        DecisionFamily.REGIME_SWITCHING, DecisionFamily.TOPOLOGICAL,
    }


def test_drawdown_trace_and_single_input_replay():
    team = HedgeOpsTeam()
    inputs = portfolio(drawdown_pct=0.20)
    result = team.replay_portfolio_risk(bars(), inputs, field="drawdown_pct", value=0.19)
    baseline, scenario = result["baseline"], result["scenario"]
    assert (baseline.disposition, scenario.disposition) == ("HOLD", "BUY")
    assert result["disposition_changed"]
    assert result["cleared_reasons"] == ("drawdown veto",)
    assert inputs["drawdown_pct"] == 0.20
    veto = next(node for node in baseline.nodes if node.label == "drawdown veto")
    assert veto.attributes == {
        "evidence_id": "portfolio:drawdown_pct", "limit": "max_drawdown_pct",
        "observed": 0.20, "threshold": 0.20, "comparison": ">=",
    }
    source = next(node for node in baseline.nodes
                  if node.label == "portfolio:drawdown_pct")
    assert DecisionEdge(source.node_id, veto.node_id, EdgeKind.INFORMS) in baseline.edges
    assert DecisionEdge(veto.node_id, "advisory", EdgeKind.EXPLAINS) in baseline.edges
    assert source.attributes == {"verified": False, "source_group": "input_portfolio"}
    price_refs = [node for node in baseline.nodes if node.label.startswith("close:")]
    assert len(price_refs) > 1
    assert all(node.attributes["source_group"] == "input_bars" and
               node.attributes["last_observed_at"] == "2026-01-06" for node in price_refs)
    forged = replace(veto, attributes={**veto.attributes, "observed": 0.19})
    with pytest.raises(ValueError, match="invalid risk gate trace"):
        validate_topology(replace(baseline, nodes=tuple(
            forged if node == veto else node for node in baseline.nodes
        )))


def test_risk_replay_keeps_other_vetoes_and_disallows_adapters():
    team = HedgeOpsTeam()
    inputs = portfolio(drawdown_pct=0.20, exposure_pct=0.25)
    result = team.replay_portfolio_risk(bars(), inputs, field="drawdown_pct", value=0.19)
    assert not result["disposition_changed"]
    assert result["cleared_reasons"] == ("drawdown veto",)
    assert result["scenario"].disposition == "HOLD"
    with pytest.raises(ValueError, match="deterministic strategy"):
        HedgeOpsTeam(strategic_agent=object()).replay_portfolio_risk(
            bars(), inputs, field="drawdown_pct", value=0.19
        )
