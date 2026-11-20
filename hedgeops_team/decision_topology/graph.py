"""Read-only projections of deterministic team and Grok structured reports.

A graph is NOT evidence authentication, a calibrated forecast, or execution
authority. These functions never call a provider, workflow or broker.
"""
from __future__ import annotations

import json
import math
from collections import deque
from hashlib import sha256

from hedgeops_team.audit import canonical_json, digest_payload
from hedgeops_team.core import ACTIONS, RISK_GATES, DecisionReport, risk_gate_triggered
from report_validation import REQUIRED_FIELDS, validate_report

from .schema import DecisionEdge, DecisionNode, DecisionTopology, EdgeKind, NodeKind

_REQUIRED_ROLES = frozenset({"temporal", "strategic", "risk", "adversarial"})
_ALLOWED_ROLES = _REQUIRED_ROLES | {"adapter"}
_ALLOWED_SOURCES = {"grok_structured_report", "deterministic_team"}
_VETOES = frozenset({
    "independent strategic evidence required", "drawdown veto", "exposure veto",
    "volatility veto", "insufficient regime history", "strategic disagreement",
    "insufficient directional consensus",
})


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _bounded_text(value: object, name: str, limit: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(name + " must be nonempty bounded text")
    return value


def _confidence(value: object) -> float:
    if (isinstance(value, bool) or not isinstance(value, (float, int))
            or not math.isfinite(value) or not 0 <= value <= 1):
        raise ValueError("invalid confidence")
    return float(value)


def validate_topology(topology: DecisionTopology) -> None:
    """Fail closed on unsafe, incomplete, unsupported or cyclic review graphs."""
    if not isinstance(topology, DecisionTopology):
        raise ValueError("expected DecisionTopology")
    if (topology.paper_only is not True or topology.human_review_required is not True
            or topology.execution_authorized is not False):
        raise ValueError("topology cannot authorize trading or bypass human review")
    if topology.source not in _ALLOWED_SOURCES:
        raise ValueError("unsupported topology source")
    if not _is_digest(topology.input_digest):
        raise ValueError("invalid input digest")
    expected_disposition = (
        {"BUY", "SELL", "HOLD"} if topology.source == "deterministic_team"
        else {"ADVISORY_ONLY"}
    )
    if topology.disposition not in expected_disposition:
        raise ValueError("invalid advisory disposition")
    if not 1 <= len(topology.nodes) <= 1024 or len(topology.edges) > 4096:
        raise ValueError("decision topology size limit exceeded")

    nodes = {}
    for node in topology.nodes:
        if not isinstance(node, DecisionNode) or not isinstance(node.kind, NodeKind):
            raise ValueError("invalid graph node")
        if not isinstance(node.node_id, str) or not node.node_id or node.node_id in nodes:
            raise ValueError("duplicate or invalid node ID")
        _bounded_text(node.label, "node label", 100000)
        if not isinstance(node.attributes, dict):
            raise ValueError("node attributes must be mapping")
        nodes[node.node_id] = node

    roots = [n for n in nodes.values() if n.kind == NodeKind.INPUT]
    leaves = [n for n in nodes.values() if n.kind == NodeKind.DISPOSITION]
    if len(roots) != 1 or len(leaves) != 1:
        raise ValueError("exactly one input and advisory disposition required")
    root, leaf = roots[0], leaves[0]
    if root.attributes.get("input_digest") != topology.input_digest:
        raise ValueError("input digest mismatches input node")
    if leaf.attributes.get("disposition") != topology.disposition:
        raise ValueError("disposition mismatches graph output")
    if leaf.attributes.get("execution_authorized") is not False:
        raise ValueError("advisory node cannot authorize execution")

    permitted = {
        (NodeKind.INPUT, NodeKind.AGENT, EdgeKind.OBSERVES),
        (NodeKind.AGENT, NodeKind.EVIDENCE_REF, EdgeKind.CITES),
        (NodeKind.AGENT, NodeKind.WARNING, EdgeKind.FLAGS),
        (NodeKind.INPUT, NodeKind.REVIEW_REASON, EdgeKind.DESCRIBES),
        (NodeKind.INPUT, NodeKind.REPORT_FIELD, EdgeKind.DESCRIBES),
        (NodeKind.AGENT, NodeKind.DISPOSITION, EdgeKind.INFORMS),
        (NodeKind.EVIDENCE_REF, NodeKind.REVIEW_REASON, EdgeKind.INFORMS),
        (NodeKind.EVIDENCE_REF, NodeKind.DISPOSITION, EdgeKind.INFORMS),
        (NodeKind.WARNING, NodeKind.DISPOSITION, EdgeKind.INFORMS),
        (NodeKind.REPORT_FIELD, NodeKind.DISPOSITION, EdgeKind.INFORMS),
        (NodeKind.REVIEW_REASON, NodeKind.DISPOSITION, EdgeKind.EXPLAINS),
    }
    indegree = {nid: 0 for nid in nodes}
    successors = {nid: [] for nid in nodes}
    seen = set()
    for edge in topology.edges:
        if not isinstance(edge, DecisionEdge) or not isinstance(edge.kind, EdgeKind):
            raise ValueError("invalid graph edge")
        if edge.source not in nodes or edge.target not in nodes:
            raise ValueError("dangling graph edge")
        if (nodes[edge.source].kind, nodes[edge.target].kind, edge.kind) not in permitted:
            raise ValueError("invalid typed dependency edge")
        key = (edge.source, edge.target, edge.kind)
        if key in seen:
            raise ValueError("duplicate graph edge")
        seen.add(key)
        successors[edge.source].append(edge.target)
        indegree[edge.target] += 1

    queue = deque(nid for nid, n in indegree.items() if n == 0)
    visited = 0
    while queue:
        nid = queue.popleft()
        visited += 1
        for to in successors[nid]:
            indegree[to] -= 1
            if indegree[to] == 0:
                queue.append(to)
    if visited != len(nodes):
        raise ValueError("directed cycle in decision topology")

    edge_set = seen
    if topology.source == "deterministic_team":
        invalid_kinds = {NodeKind.REPORT_FIELD}
        if any(n.kind in invalid_kinds for n in nodes.values()):
            raise ValueError("team topology cannot contain Grok report fields")
        roles = [n.attributes.get("agent_id") for n in nodes.values() if n.kind == NodeKind.AGENT]
        if (len(roles) != len(set(roles)) or not _REQUIRED_ROLES.issubset(roles)
                or not set(roles).issubset(_ALLOWED_ROLES)):
            raise ValueError("required distinct team agents missing or duplicated")
        for n in nodes.values():
            if n.kind == NodeKind.AGENT:
                _confidence(n.attributes.get("confidence"))
                if n.attributes.get("action") not in ACTIONS:
                    raise ValueError("invalid agent action")
                if ((root.node_id, n.node_id, EdgeKind.OBSERVES) not in edge_set
                        or (n.node_id, leaf.node_id, EdgeKind.INFORMS) not in edge_set):
                    raise ValueError("assessment pathway incomplete")
            elif n.kind in {NodeKind.EVIDENCE_REF, NodeKind.WARNING}:
                edge_kind = EdgeKind.CITES if n.kind == NodeKind.EVIDENCE_REF else EdgeKind.FLAGS
                parents = [e for e in topology.edges if e.target == n.node_id and e.kind == edge_kind]
                if (len(parents) != 1 or nodes[parents[0].source].kind != NodeKind.AGENT
                        or (n.node_id, leaf.node_id, EdgeKind.INFORMS) not in edge_set):
                    raise ValueError("evidence/warning pathway incomplete")
            elif n.kind == NodeKind.REVIEW_REASON:
                if ((root.node_id, n.node_id, EdgeKind.DESCRIBES) not in edge_set
                        or (n.node_id, leaf.node_id, EdgeKind.EXPLAINS) not in edge_set):
                    raise ValueError("review reason pathway incomplete")
        risk_agent = next(n.node_id for n in nodes.values()
                          if n.kind == NodeKind.AGENT and n.attributes.get("agent_id") == "risk")
        for reason, reference, limit, comparison in RISK_GATES:
            for node in nodes.values():
                if node.kind != NodeKind.REVIEW_REASON or node.label != reason or not node.attributes:
                    continue
                observed = node.attributes.get("observed")
                threshold = node.attributes.get("threshold")
                if (node.attributes.get("evidence_id") != reference
                        or node.attributes.get("limit") != limit
                        or node.attributes.get("comparison") != comparison
                        or any(isinstance(value, bool) or not isinstance(value, (int, float))
                               or not math.isfinite(value) or value < 0
                               for value in (observed, threshold))
                        or threshold > 1
                        or not risk_gate_triggered(observed, threshold, comparison)):
                    raise ValueError("invalid risk gate trace")
                if not any(source.kind == NodeKind.EVIDENCE_REF
                           and source.label == reference
                           and (source.node_id, node.node_id, EdgeKind.INFORMS) in edge_set
                           and (risk_agent, source.node_id, EdgeKind.CITES) in edge_set
                           for source in nodes.values()):
                    raise ValueError("risk gate evidence pathway incomplete")
        if (topology.disposition != "HOLD"
                and any(n.label in _VETOES for n in nodes.values()
                        if n.kind == NodeKind.REVIEW_REASON)):
            raise ValueError("vetoes cannot allow directional advisory")
        suggested = leaf.attributes.get("suggested_position_pct")
        if (isinstance(suggested, bool) or not isinstance(suggested, (int, float))
                or not math.isfinite(suggested) or not 0 <= suggested <= 1):
            raise ValueError("invalid position suggestion")
        if topology.disposition in {"SELL", "HOLD"} and suggested != 0:
            raise ValueError("SELL/HOLD cannot suggest a new position")
        if topology.disposition == "SELL" and leaf.attributes.get("sell_semantics") != "directional_signal_only":
            raise ValueError("SELL is directional only")
    else:
        if any(n.kind not in {NodeKind.INPUT, NodeKind.REPORT_FIELD, NodeKind.DISPOSITION}
               for n in nodes.values()):
            raise ValueError("structured report may only contain report-field nodes")
        fields = [n for n in nodes.values() if n.kind == NodeKind.REPORT_FIELD]
        if len(fields) != len({n.attributes.get("field") for n in fields}):
            raise ValueError("duplicate report field")
        reconstructed = {}
        for n in fields:
            field = n.attributes.get("field")
            payload = n.attributes.get("value_json")
            if not isinstance(field, str) or not field or field != n.label or not isinstance(payload, str):
                raise ValueError("invalid report field node")
            if ((root.node_id, n.node_id, EdgeKind.DESCRIBES) not in edge_set
                    or (n.node_id, leaf.node_id, EdgeKind.INFORMS) not in edge_set):
                raise ValueError("report field pathway incomplete")
            try:
                value = json.loads(payload)
                if canonical_json(value) != payload:
                    raise ValueError("noncanonical report field")
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid report field JSON") from exc
            reconstructed[field] = value
        validate_report(canonical_json(reconstructed))
        if digest_payload(reconstructed) != topology.input_digest:
            raise ValueError("structured report digest mismatch")


def build_team_topology(report: DecisionReport, *, trace=None) -> DecisionTopology:
    """Project the existing four-role deterministic team decision, without approval."""
    if not isinstance(report, DecisionReport) or report.paper_only is not True:
        raise ValueError("paper-only DecisionReport required")
    if report.action not in {"BUY", "SELL", "HOLD"}:
        raise ValueError("invalid action")
    _confidence(report.confidence)
    if not _is_digest(report.input_digest):
        raise ValueError("invalid input digest")
    if (isinstance(report.suggested_position_pct, bool)
            or not isinstance(report.suggested_position_pct, (int, float))
            or not math.isfinite(report.suggested_position_pct)
            or not 0 <= report.suggested_position_pct <= 1):
        raise ValueError("invalid position suggestion")
    if report.action in {"SELL", "HOLD"} and report.suggested_position_pct != 0:
        raise ValueError("SELL/HOLD cannot suggest a new position")
    if report.action == "SELL" and report.sell_semantics != "directional_signal_only":
        raise ValueError("SELL must be directional only")
    if report.strategic_source not in {"unverified_mirror", "external_adapter", "adapter_failure"}:
        raise ValueError("invalid strategic source")
    if not isinstance(report.reasons, tuple) or not 1 <= len(report.reasons) <= 64:
        raise ValueError("bounded review reasons required")
    if not isinstance(report.evidence, tuple) or not 4 <= len(report.evidence) <= 5:
        raise ValueError("four team roles plus optional adapter required")

    trace = {} if trace is None else trace
    risk_references = {}
    roles = []
    nodes = [
        DecisionNode("input", NodeKind.INPUT, "Input snapshot fingerprint",
                     {"input_digest": report.input_digest, "authenticated": False}),
        DecisionNode("advisory", NodeKind.DISPOSITION, "Paper-only advisory",
                     {"disposition": report.action,
                      "confidence": report.confidence,
                      "suggested_position_pct": report.suggested_position_pct,
                      "sell_semantics": report.sell_semantics,
                      "strategic_source": report.strategic_source,
                      "execution_authorized": False}),
    ]
    edges = []
    for index, row in enumerate(report.evidence):
        if not isinstance(row, dict):
            raise ValueError("invalid team evidence row")
        agent_id = _bounded_text(row.get("agent_id"), "agent_id", 64)
        if agent_id not in _ALLOWED_ROLES or agent_id in roles:
            raise ValueError("missing, unknown or duplicate agent role")
        roles.append(agent_id)
        action = row.get("action")
        if action not in ACTIONS:
            raise ValueError("invalid agent evidence action")
        confidence = _confidence(row.get("confidence"))
        rationale = _bounded_text(row.get("rationale"), "rationale")
        evidence_ids = row.get("evidence_ids")
        warnings = row.get("warnings", ())
        if (not isinstance(evidence_ids, (list, tuple)) or not 1 <= len(evidence_ids) <= 32
                or not isinstance(warnings, (list, tuple)) or len(warnings) > 32):
            raise ValueError("invalid evidence IDs or warnings")
        aid = "agent:" + agent_id
        nodes.append(DecisionNode(aid, NodeKind.AGENT, rationale,
                                  {"agent_id": agent_id, "action": action,
                                   "confidence": confidence}))
        edges.extend((DecisionEdge("input", aid, EdgeKind.OBSERVES),
                      DecisionEdge(aid, "advisory", EdgeKind.INFORMS)))
        for j, reference in enumerate(evidence_ids):
            refid = "reference:" + agent_id + ":" + str(j)
            reference = _bounded_text(reference, "evidence reference", 256)
            attributes = {"verified": False}
            if reference.startswith("close:"):
                attributes.update(source_group="input_bars",
                                  last_observed_at=trace.get("last_bar_timestamp"))
            elif reference.startswith("portfolio:"):
                attributes.update(source_group="input_portfolio")
            elif reference == "adapter:failure":
                attributes.update(source_group="strategic_adapter")
            if agent_id == "risk":
                risk_references[reference] = refid
            nodes.append(DecisionNode(refid, NodeKind.EVIDENCE_REF, reference, attributes))
            edges.extend((DecisionEdge(aid, refid, EdgeKind.CITES),
                          DecisionEdge(refid, "advisory", EdgeKind.INFORMS)))
        for j, warning in enumerate(warnings):
            wid = "warning:" + agent_id + ":" + str(j)
            nodes.append(DecisionNode(wid, NodeKind.WARNING,
                                      _bounded_text(warning, "warning")))
            edges.extend((DecisionEdge(aid, wid, EdgeKind.FLAGS),
                          DecisionEdge(wid, "advisory", EdgeKind.INFORMS)))
    if set(roles) != _REQUIRED_ROLES and set(roles) != _REQUIRED_ROLES | {"adapter"}:
        raise ValueError("missing required agent roles")
    if ("adapter" in roles) != (report.strategic_source == "adapter_failure"):
        raise ValueError("adapter failure provenance mismatch")
    for i, reason in enumerate(report.reasons):
        reason = _bounded_text(reason, "review reason")
        nid = "reason:" + str(i)
        gate = trace.get(reason, {})
        nodes.append(DecisionNode(nid, NodeKind.REVIEW_REASON, reason, gate))
        if gate:
            refid = risk_references.get(gate.get("evidence_id"))
            if refid is None:
                raise ValueError("risk gate evidence reference missing")
            edges.append(DecisionEdge(refid, nid, EdgeKind.INFORMS))
        edges.extend((DecisionEdge("input", nid, EdgeKind.DESCRIBES),
                      DecisionEdge(nid, "advisory", EdgeKind.EXPLAINS)))

    graph = DecisionTopology("deterministic_team", report.input_digest,
                             report.action, tuple(nodes), tuple(edges))
    validate_topology(graph)
    return graph


def build_structured_report_topology(report: dict) -> DecisionTopology:
    """Project Grok's existing 13-field report schema WITHOUT provider invocation.

    This is structural visualization only. Evidence strings are not authenticated;
    a schema-valid assertion can still be false.
    """
    if not isinstance(report, dict):
        raise ValueError("structured report must be a dictionary")
    try:
        snapshot = canonical_json(report)
    except (TypeError, ValueError) as exc:
        raise ValueError("report must be strict JSON") from exc
    if len(snapshot.encode("utf-8")) > 100000:
        raise ValueError("report too large to project safely")
    validated = validate_report(snapshot)
    if not REQUIRED_FIELDS.issubset(validated):
        raise ValueError("report fields incomplete")
    if len(validated) > 64:
        raise ValueError("too many report fields")
    digest = sha256(snapshot.encode("utf-8")).hexdigest()
    nodes = [
        DecisionNode("input", NodeKind.INPUT, "Grok report snapshot",
                     {"input_digest": digest, "authenticated": False}),
        DecisionNode("advisory", NodeKind.DISPOSITION, "Unverified Grok advisory",
                     {"disposition": "ADVISORY_ONLY", "execution_authorized": False}),
    ]
    edges = []
    for index, field in enumerate(sorted(validated)):
        node_id = "field:" + str(index)
        nodes.append(DecisionNode(
            node_id, NodeKind.REPORT_FIELD, field,
            {"field": field, "value_json": canonical_json(validated[field]), "verified": False}
        ))
        edges.extend((DecisionEdge("input", node_id, EdgeKind.DESCRIBES),
                      DecisionEdge(node_id, "advisory", EdgeKind.INFORMS)))
    graph = DecisionTopology("grok_structured_report", digest, "ADVISORY_ONLY",
                             tuple(nodes), tuple(edges))
    validate_topology(graph)
    return graph
