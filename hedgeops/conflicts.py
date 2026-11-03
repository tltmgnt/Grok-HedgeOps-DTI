"""Transparent disagreement screening; semantic conflict detection is future work."""
import re

def normalized(text):
    return re.sub(r"\s+", " ", text.strip().casefold())


def compare_hypotheses(reports):
    """Detect distinct statements, not logical contradictions."""
    groups = {}
    for agent, report in reports.items():
        groups.setdefault(normalized(report["hypothesis"]), []).append(agent)
    return {
        "distinct_hypothesis_count": len(groups),
        "agreement_groups": list(groups.values()),
        "potential_disagreement": len(groups) > 1,
        "semantic_conflicts_verified": False,
        "method": "normalized exact-text grouping; not semantic entailment",
    }
