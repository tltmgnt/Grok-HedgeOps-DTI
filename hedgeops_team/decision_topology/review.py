"""Offline review tools for advisory decision topologies."""
from collections import Counter
from itertools import combinations

from .graph import validate_topology
from .schema import NodeKind


def _snapshot(graph):
    validate_topology(graph)
    if graph.source != "deterministic_team":
        raise ValueError("review requires a deterministic team topology")
    root = next(node for node in graph.nodes if node.kind == NodeKind.INPUT)
    leaf = next(node for node in graph.nodes if node.kind == NodeKind.DISPOSITION)
    return {
        "strategy_source": leaf.attributes.get("strategic_source"),
        "disposition": graph.disposition,
        "input_digest": graph.input_digest,
        "policy": root.attributes.get("policy"),
        "risk_gates": root.attributes.get("risk_gates", {}),
        "blockers": {
            node.label: node.attributes for node in graph.nodes
            if node.kind == NodeKind.REVIEW_REASON and graph.disposition == "HOLD"
        },
        "assessments": {
            node.attributes["agent_id"]: node.attributes["action"]
            for node in graph.nodes if node.kind == NodeKind.AGENT
        },
    }


def compare_decisions(baseline, scenario):
    """Compare two advisory decisions, including any changes in policy."""
    before, after = _snapshot(baseline), _snapshot(scenario)
    old, new = before["blockers"], after["blockers"]
    return {
        "disposition_changed": before["disposition"] != after["disposition"],
        "cleared_blockers": tuple(sorted(old.keys() - new.keys())),
        "added_blockers": tuple(sorted(new.keys() - old.keys())),
        "remaining_blockers": tuple(sorted(old.keys() & new.keys())),
        "before": before,
        "after": after,
    }


def review_markdown(graph, *, replay=None):
    """Render a compact human review summary, optionally with replay results."""
    snapshot = _snapshot(graph)

    def inline(value):
        return str(value).replace("\n", " ").replace("\r", " ").replace("<", "&lt;").replace("`", "´")

    lines = ["# Advisory review", "", f"Disposition **{snapshot['disposition']}**", "", "## Active blockers", ""]
    for reason, detail in snapshot["blockers"].items():
        fields = ", ".join(f"{key}={inline(value)}" for key, value in detail.items())
        lines.append(f"- {inline(reason)}" + (f" · {fields}" if fields else ""))
    if not snapshot["blockers"]:
        lines.append("- None")
    references = sorted({node.label for node in graph.nodes if node.kind == NodeKind.EVIDENCE_REF})
    lines.extend(["", "## Evidence references", ""])
    lines.extend(f"- `{inline(value)}`" for value in references)
    if replay is not None:
        if replay["baseline"] != graph:
            raise ValueError("replay baseline must match the review topology")
        lines.extend(["", "## Replay", ""])
        for name, result in (*replay["individual"].items(), ("combined", replay["combined"])):
            comparison = compare_decisions(graph, result["topology"])
            cleared = ", ".join(comparison["cleared_blockers"]) or "none"
            added = ", ".join(comparison["added_blockers"]) or "none"
            remaining = ", ".join(comparison["remaining_blockers"]) or "none"
            lines.append(f"- {inline(name)} · {comparison['after']['disposition']} · "
                         f"cleared {inline(cleared)} · added {inline(added)} · remaining {inline(remaining)}")
    return "\n".join(lines) + "\n"


def summarize_blockers(graphs):
    """Count blockers, blocker pairs, and missing timestamps per supplied run."""
    counts, pairs, missing = Counter(), Counter(), Counter()
    sample_size = 0
    for graph in graphs:
        snapshot = _snapshot(graph)
        sample_size += 1
        blockers = sorted(snapshot["blockers"])
        counts.update(blockers)
        pairs.update(combinations(blockers, 2))
        missing.update({
            node.attributes.get("source_group", "unknown")
            for node in graph.nodes if node.kind == NodeKind.EVIDENCE_REF
            and node.attributes.get("last_observed_at") is None
        })
    return {
        "sample_size": sample_size,
        "blocker_counts": dict(counts),
        "co_occurrences": [{"blockers": pair, "count": count} for pair, count in sorted(pairs.items())],
        "missing_observation_counts": dict(missing),
    }
