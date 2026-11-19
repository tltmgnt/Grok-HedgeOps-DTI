"""Typed, non-executable dependency graph for offline HedgeOps research."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeKind(str, Enum):
    INPUT = "input"
    AGENT = "agent"
    EVIDENCE_REF = "evidence_reference"
    WARNING = "warning"
    REVIEW_REASON = "review_reason"
    REPORT_FIELD = "report_field"
    DISPOSITION = "disposition"


class EdgeKind(str, Enum):
    OBSERVES = "observes"
    CITES = "cites"
    FLAGS = "flags"
    DESCRIBES = "describes"
    INFORMS = "informs"
    EXPLAINS = "explains"


@dataclass(frozen=True)
class DecisionNode:
    node_id: str
    kind: NodeKind
    label: str
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.node_id, "kind": self.kind.value,
            "label": self.label, "attributes": dict(self.attributes),
        }


@dataclass(frozen=True)
class DecisionEdge:
    source: str
    target: str
    kind: EdgeKind

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "target": self.target, "kind": self.kind.value}


@dataclass(frozen=True)
class DecisionTopology:
    """Review-only projection, with no trading/approval capability or broker APIs."""
    source: str
    input_digest: str
    disposition: str
    nodes: tuple[DecisionNode, ...]
    edges: tuple[DecisionEdge, ...]
    paper_only: bool = True
    human_review_required: bool = True
    execution_authorized: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "grok-hedgeops-decision-topology-v1",
            "source": self.source,
            "input_digest": self.input_digest,
            "disposition": self.disposition,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "paper_only": self.paper_only,
            "human_review_required": self.human_review_required,
            "execution_authorized": self.execution_authorized,
        }
