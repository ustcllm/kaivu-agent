from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ResearchGraphNode:
    node_id: str
    node_type: str
    label: str
    project_id: str = ""
    topic: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ResearchGraphEdge:
    edge_id: str
    source_id: str
    target_id: str
    relation: str
    project_id: str = ""
    topic: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ResearchGraphSnapshot:
    snapshot_id: str
    project_id: str
    topic: str
    node_ids: list[str] = field(default_factory=list)
    edge_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ProvenanceFact:
    fact_id: str
    fact_type: str
    subject_id: str
    predicate: str
    object_id: str = ""
    value: Any = None
    project_id: str = ""
    topic: str = ""
    confidence: float = 1.0
    source_refs: list[str] = field(default_factory=list)
    produced_by: str = ""
    status: str = "active"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ProvenanceEvent:
    event_id: str
    event_type: str
    fact_ids: list[str] = field(default_factory=list)
    project_id: str = ""
    topic: str = ""
    actor: str = ""
    action: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


