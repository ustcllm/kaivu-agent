from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import ProvenanceEvent, ProvenanceFact, ResearchGraphEdge, ResearchGraphNode, ResearchGraphSnapshot


class ResearchGraphRegistry:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save_node(self, node: ResearchGraphNode) -> Path:
        return self._save("nodes", node.node_id, asdict(node))

    def save_edge(self, edge: ResearchGraphEdge) -> Path:
        return self._save("edges", edge.edge_id, asdict(edge))

    def save_snapshot(self, snapshot: ResearchGraphSnapshot) -> Path:
        return self._save("snapshots", snapshot.snapshot_id, asdict(snapshot))

    def save_fact(self, fact: ProvenanceFact) -> Path:
        return self._save("facts", fact.fact_id, asdict(fact))

    def save_event(self, event: ProvenanceEvent) -> Path:
        return self._save("events", event.event_id, asdict(event))

    def load_nodes(self, *, project_id: str = "", topic: str = "") -> list[dict[str, Any]]:
        return self._load_filtered("nodes", project_id=project_id, topic=topic)

    def load_edges(self, *, project_id: str = "", topic: str = "") -> list[dict[str, Any]]:
        return self._load_filtered("edges", project_id=project_id, topic=topic)

    def load_snapshots(self, *, project_id: str = "", topic: str = "") -> list[dict[str, Any]]:
        return self._load_filtered("snapshots", project_id=project_id, topic=topic)

    def load_facts(self, *, project_id: str = "", topic: str = "") -> list[dict[str, Any]]:
        return self._load_filtered("facts", project_id=project_id, topic=topic)

    def load_events(self, *, project_id: str = "", topic: str = "") -> list[dict[str, Any]]:
        return self._load_filtered("events", project_id=project_id, topic=topic)

    def query(
        self,
        *,
        project_id: str = "",
        topic: str = "",
        node_type: str = "",
        relation: str = "",
        search: str = "",
        limit: int = 100,
        source_node_id: str = "",
        target_node_id: str = "",
        specialist_name: str = "",
        include_consulted_only: bool = False,
    ) -> dict[str, Any]:
        summary = self.summarize(project_id=project_id, topic=topic)
        nodes = self.load_nodes(project_id=project_id, topic=topic)
        edges = self.load_edges(project_id=project_id, topic=topic)
        snapshots = self.load_snapshots(project_id=project_id, topic=topic)
        facts = self.load_facts(project_id=project_id, topic=topic)
        events = self.load_events(project_id=project_id, topic=topic)
        search_terms = {term.strip().lower() for term in search.split() if term.strip()}

        if node_type:
            node_types = {item.strip() for item in node_type.split(",") if item.strip()}
            nodes = [item for item in nodes if str(item.get("node_type", "")).strip() in node_types]
        if relation:
            relations = {item.strip() for item in relation.split(",") if item.strip()}
            edges = [item for item in edges if str(item.get("relation", "")).strip() in relations]
        if source_node_id:
            edges = [item for item in edges if str(item.get("source_id", "")).strip() == source_node_id]
        if target_node_id:
            edges = [item for item in edges if str(item.get("target_id", "")).strip() == target_node_id]
        if specialist_name:
            nodes = [
                item
                for item in nodes
                if str(item.get("metadata", {}).get("profile_name", "")).strip() == specialist_name
            ]
        if include_consulted_only:
            consulted_sources = {
                str(item.get("source_id", "")).strip()
                for item in edges
                if str(item.get("relation", "")).strip() == "consulted"
            }
            consulted_targets = {
                str(item.get("target_id", "")).strip()
                for item in edges
                if str(item.get("relation", "")).strip() == "consulted"
            }
            consulted_ids = consulted_sources.union(consulted_targets)
            nodes = [item for item in nodes if str(item.get("node_id", "")).strip() in consulted_ids]
            edges = [item for item in edges if str(item.get("relation", "")).strip() == "consulted"]
        if search_terms:
            nodes = [item for item in nodes if self._matches_search(item, search_terms)]
            edges = [item for item in edges if self._matches_search(item, search_terms)]
            snapshots = [item for item in snapshots if self._matches_search(item, search_terms)]
            facts = [item for item in facts if self._matches_search(item, search_terms)]
            events = [item for item in events if self._matches_search(item, search_terms)]
        return {
            "project_id": project_id,
            "topic": topic,
            "summary": summary,
            "nodes": nodes[:limit],
            "edges": edges[:limit],
            "snapshots": snapshots[: min(limit, 20)],
            "facts": facts[:limit],
            "events": events[: min(limit, 50)],
        }

    def summarize(self, *, project_id: str = "", topic: str = "") -> dict[str, Any]:
        nodes = self.load_nodes(project_id=project_id, topic=topic)
        edges = self.load_edges(project_id=project_id, topic=topic)
        snapshots = self.load_snapshots(project_id=project_id, topic=topic)
        facts = self.load_facts(project_id=project_id, topic=topic)
        events = self.load_events(project_id=project_id, topic=topic)
        node_type_counts: dict[str, int] = {}
        edge_type_counts: dict[str, int] = {}
        fact_type_counts: dict[str, int] = {}
        fact_status_counts: dict[str, int] = {}
        governed_nodes = 0
        challenged_hypotheses = 0
        specialist_reference_nodes = 0
        artifact_nodes = 0
        consulted_profiles: dict[str, int] = {}
        for item in nodes:
            node_type = str(item.get("node_type", "")).strip() or "unknown"
            node_type_counts[node_type] = node_type_counts.get(node_type, 0) + 1
            metadata = item.get("metadata", {}) if isinstance(item.get("metadata", {}), dict) else {}
            if str(metadata.get("governance_status", "")).strip():
                governed_nodes += 1
            if node_type == "hypothesis" and int(metadata.get("challenge_count", 0) or 0) > 0:
                challenged_hypotheses += 1
            if node_type == "specialist_reference":
                specialist_reference_nodes += 1
                profile_name = str(metadata.get("profile_name", "")).strip() or "unknown"
                consulted_profiles[profile_name] = consulted_profiles.get(profile_name, 0) + 1
            if node_type in {"artifact", "dataset", "checkpoint", "spectrum", "notebook", "figure", "proof_note"}:
                artifact_nodes += 1
        for item in edges:
            relation = str(item.get("relation", "")).strip() or "related_to"
            edge_type_counts[relation] = edge_type_counts.get(relation, 0) + 1
        for item in facts:
            fact_type = str(item.get("fact_type", "")).strip() or "unknown"
            status = str(item.get("status", "")).strip() or "unknown"
            fact_type_counts[fact_type] = fact_type_counts.get(fact_type, 0) + 1
            fact_status_counts[status] = fact_status_counts.get(status, 0) + 1
        latest_snapshot = snapshots[-1] if snapshots else {}
        return {
            "project_id": project_id,
            "topic": topic,
            "snapshot_count": len(snapshots),
            "fact_count": len(facts),
            "event_count": len(events),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "node_type_counts": node_type_counts,
            "edge_type_counts": edge_type_counts,
            "fact_type_counts": fact_type_counts,
            "fact_status_counts": fact_status_counts,
            "graph_is_fact_backed": bool(facts),
            "governed_node_count": governed_nodes,
            "challenged_hypothesis_count": challenged_hypotheses,
            "specialist_reference_count": specialist_reference_nodes,
            "artifact_node_count": artifact_nodes,
            "consulted_profiles": consulted_profiles,
            "consulted_edge_count": int(edge_type_counts.get("consulted", 0) or 0),
            "latest_snapshot_id": str(latest_snapshot.get("snapshot_id", "")).strip(),
        }

    def replay_facts(self, *, project_id: str = "", topic: str = "") -> dict[str, Any]:
        facts = [
            item
            for item in self.load_facts(project_id=project_id, topic=topic)
            if str(item.get("status", "active")).strip() != "retracted"
        ]
        claims: dict[str, dict[str, Any]] = {}
        hypotheses: dict[str, dict[str, Any]] = {}
        evidence: dict[str, dict[str, Any]] = {}
        experiments: dict[str, dict[str, Any]] = {}
        memory: dict[str, dict[str, Any]] = {}
        artifacts: dict[str, dict[str, Any]] = {}
        relations: list[dict[str, Any]] = []
        buckets = {
            "claim": claims,
            "hypothesis": hypotheses,
            "evidence": evidence,
            "experiment": experiments,
            "memory": memory,
            "artifact": artifacts,
        }
        for fact in facts:
            fact_type = str(fact.get("fact_type", "")).strip()
            subject_id = str(fact.get("subject_id", "")).strip()
            predicate = str(fact.get("predicate", "")).strip()
            object_id = str(fact.get("object_id", "")).strip()
            if not subject_id:
                continue
            bucket_key = fact_type.split("_", 1)[0]
            bucket = buckets.get(bucket_key)
            if bucket is not None:
                item = bucket.setdefault(
                    subject_id,
                    {
                        "id": subject_id,
                        "fact_ids": [],
                        "source_refs": [],
                        "fields": {},
                    },
                )
                item["fact_ids"].append(str(fact.get("fact_id", "")).strip())
                item["source_refs"] = sorted(
                    set(item.get("source_refs", []) + self._strings(fact.get("source_refs", [])))
                )
                if predicate:
                    item["fields"][predicate] = fact.get("value") if fact.get("value") is not None else object_id
            if object_id:
                relations.append(
                    {
                        "source_id": subject_id,
                        "target_id": object_id,
                        "relation": predicate or "related_to",
                        "fact_id": str(fact.get("fact_id", "")).strip(),
                    }
                )
        return {
            "project_id": project_id,
            "topic": topic,
            "fact_count": len(facts),
            "claim_count": len(claims),
            "hypothesis_count": len(hypotheses),
            "evidence_count": len(evidence),
            "experiment_count": len(experiments),
            "memory_count": len(memory),
            "artifact_count": len(artifacts),
            "claims": list(claims.values()),
            "hypotheses": list(hypotheses.values()),
            "evidence": list(evidence.values()),
            "experiments": list(experiments.values()),
            "memory": list(memory.values()),
            "artifacts": list(artifacts.values()),
            "relations": relations,
        }

    def _load_filtered(self, collection: str, *, project_id: str = "", topic: str = "") -> list[dict[str, Any]]:
        directory = self.root / collection
        if not directory.exists():
            return []
        items: list[dict[str, Any]] = []
        for path in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            if project_id and str(payload.get("project_id", "")).strip() != project_id:
                continue
            if topic and str(payload.get("topic", "")).strip() != topic:
                continue
            items.append(payload)
        return items

    def _save(self, collection: str, identifier: str, payload: dict[str, Any]) -> Path:
        directory = self.root / collection
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{self._slugify(identifier)}.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    @staticmethod
    def _matches_search(item: dict[str, Any], search_terms: set[str]) -> bool:
        if not search_terms:
            return True
        haystack = json.dumps(item, ensure_ascii=False).lower()
        return all(term in haystack for term in search_terms)

    @staticmethod
    def _strings(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _slugify(value: str) -> str:
        safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
        while "--" in safe:
            safe = safe.replace("--", "-")
        slug = safe.strip("-") or "graph-record"
        if len(slug) <= 140:
            return slug
        digest = hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:12]
        return f"{slug[:127].rstrip('-')}-{digest}"


