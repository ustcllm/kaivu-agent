from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Literal

from .graph import ResearchGraphRegistry
from .messages import Message


ENTRYPOINT_NAME = "MEMORY.md"
MEMORY_LOG_NAME = "log.md"
MAX_ENTRYPOINT_LINES = 200
MAX_ENTRYPOINT_BYTES = 25_000

MemoryScope = Literal["instruction", "personal", "project", "group", "public", "agent", "session"]
MemoryKind = Literal["fact", "hypothesis", "method", "decision", "dataset_note", "warning", "preference", "reference"]
EvidenceLevel = Literal["low", "medium", "high"]
ConfidenceLevel = Literal["low", "medium", "high"]
MemoryStatus = Literal["active", "revised", "uncertain", "deprecated", "rejected"]
VisibilityLevel = Literal["private", "project", "group", "public"]
PromotionStatus = Literal["personal", "project", "group", "public"]

TYPE_WEIGHTS = {
    "warning": 2.8,
    "decision": 2.4,
    "fact": 2.2,
    "dataset_note": 2.0,
    "method": 1.9,
    "preference": 1.8,
    "hypothesis": 1.6,
    "reference": 1.2,
}
EVIDENCE_WEIGHTS = {"low": 0.8, "medium": 1.0, "high": 1.25}
CONFIDENCE_WEIGHTS = {"low": 0.85, "medium": 1.0, "high": 1.15}
STATUS_WEIGHTS = {"active": 1.2, "revised": 1.0, "uncertain": 0.9, "deprecated": 0.4, "rejected": 0.15}


@dataclass(slots=True)
class MemoryRecord:
    path: Path
    title: str
    summary: str
    scope: MemoryScope
    kind: MemoryKind
    tags: list[str]
    source_refs: list[str]
    evidence_level: EvidenceLevel
    confidence: ConfidenceLevel
    status: MemoryStatus
    owner_agent: str
    user_id: str
    project_id: str
    group_id: str
    visibility: VisibilityLevel
    promotion_status: PromotionStatus
    created_at: str
    last_verified_at: str
    needs_review: bool
    review_due_at: str
    supersedes: list[str]
    superseded_by: str | None
    derived_from: list[str]
    conflicts_with: list[str]
    validated_by: list[str]
    excerpt: str
    namespace: str | None = None


class MemoryManager:
    def __init__(self, root: str | Path, *, agent_namespace: str | None = None) -> None:
        self.root = Path(root).resolve()
        self.shared_memory_dir = self.root / "memory"
        self.graph_registry = ResearchGraphRegistry(self.root / ".state" / "graph")
        self._graph_context_cache: dict[str, dict[str, Any]] = {}
        self.agent_namespace = self._slugify_agent_namespace(agent_namespace) or "default"
        self.agent_memory_dir = self.shared_memory_dir / "agents" / self.agent_namespace
        self.entrypoint = self.shared_memory_dir / ENTRYPOINT_NAME
        self.log_file = self.shared_memory_dir / MEMORY_LOG_NAME
        self.session_dir = self.shared_memory_dir / "session" / "agents" / self.agent_namespace
        self.session_file = self.session_dir / "current_session.md"
        self.static_memory_files = self._discover_static_memory_files()
        self._ensure_layout()

    def _ensure_layout(self) -> None:
        self.shared_memory_dir.mkdir(parents=True, exist_ok=True)
        for path in [
            self.shared_memory_dir / "personal",
            self.shared_memory_dir / "projects",
            self.shared_memory_dir / "groups",
            self.shared_memory_dir / "public",
            self.shared_memory_dir / "agents",
            self.agent_memory_dir,
            self.session_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)
        if not self.entrypoint.exists():
            self.entrypoint.write_text("# MEMORY\n\n", encoding="utf-8")
        if not self.log_file.exists():
            self.log_file.write_text("# Memory Log\n\n", encoding="utf-8")
        if not self.session_file.exists():
            self.session_file.write_text("# Session Memory\n\nNo session summary yet.\n", encoding="utf-8")

    def _discover_static_memory_files(self) -> list[Path]:
        candidates = [self.root / "CLAUDE.md", self.root / ".agent" / "CLAUDE.md"]
        rules_dir = self.root / ".agent" / "rules"
        if rules_dir.exists():
            candidates.extend(sorted(rules_dir.glob("*.md")))
        return [path for path in candidates if path.exists()]

    def build_system_memory_prompt(self) -> str:
        sections = [
            "Collaborative memory system is available.",
            f"Shared memory lives in `{self.shared_memory_dir}`.",
            f"Agent-private memory lives in `{self.agent_memory_dir}`.",
            f"`{ENTRYPOINT_NAME}` is an index, not the memory body.",
            "Scientific memories should track type, scope, user_id, project_id, group_id, visibility, and promotion_status.",
        ]
        static_content = self._load_static_memory_text()
        if static_content:
            sections.extend(["", "Instruction memory:", static_content])
        session_text = self.get_session_memory()
        if session_text:
            sections.extend(["", "Current session memory:", session_text])
        return "\n".join(sections)

    def build_query_memory_context(
        self,
        query: str,
        max_memories: int = 5,
        *,
        user_id: str | None = None,
        project_id: str | None = None,
        group_id: str | None = None,
    ) -> str:
        relevant = self.find_relevant_memories(
            query,
            max_memories=max_memories,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
        )
        if not relevant:
            return ""
        parts = ["Relevant scientific memories:"]
        for item in relevant:
            try:
                content = item.path.read_text(encoding="utf-8").strip()
            except Exception:
                continue
            parts.extend(
                [
                    f"## {item.title} ({item.path.name})",
                    f"- type: {item.kind}",
                    f"- scope: {item.scope}",
                    f"- visibility: {item.visibility}",
                    f"- promotion_status: {item.promotion_status}",
                    f"- user_id: {item.user_id or 'none'}",
                    f"- project_id: {item.project_id or 'none'}",
                    f"- group_id: {item.group_id or 'none'}",
                    content,
                    "",
                ]
            )
        return "\n".join(parts).strip()

    def save_memory(
        self,
        *,
        title: str,
        summary: str,
        kind: MemoryKind,
        scope: MemoryScope,
        content: str,
        tags: list[str] | None = None,
        filename: str | None = None,
        source_refs: list[str] | None = None,
        evidence_level: EvidenceLevel = "medium",
        confidence: ConfidenceLevel = "medium",
        status: MemoryStatus = "active",
        owner_agent: str = "unknown",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        visibility: VisibilityLevel | None = None,
        promotion_status: PromotionStatus | None = None,
        last_verified_at: str | None = None,
        needs_review: bool = False,
        review_due_at: str | None = None,
        supersedes: list[str] | None = None,
        superseded_by: str | None = None,
        derived_from: list[str] | None = None,
        conflicts_with: list[str] | None = None,
        validated_by: list[str] | None = None,
    ) -> Path:
        safe_name = filename or self._slugify(title)
        target_dir = self._resolve_target_dir(scope, user_id=user_id, project_id=project_id, group_id=group_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / safe_name
        now = datetime.now(timezone.utc).isoformat()
        body = "\n".join(
            [
                "---",
                f"title: {title}",
                f"summary: {summary}",
                f"type: {kind}",
                f"scope: {scope}",
                f"tags: {', '.join(tags or [])}",
                f"source_refs: {', '.join(source_refs or [])}",
                f"evidence_level: {evidence_level}",
                f"confidence: {confidence}",
                f"status: {status}",
                f"owner_agent: {owner_agent}",
                f"user_id: {user_id}",
                f"project_id: {project_id}",
                f"group_id: {group_id}",
                f"visibility: {visibility or self._default_visibility_for_scope(scope)}",
                f"promotion_status: {promotion_status or self._default_promotion_for_scope(scope)}",
                f"created_at: {now}",
                f"last_verified_at: {last_verified_at or now}",
                f"needs_review: {str(needs_review).lower()}",
                f"review_due_at: {review_due_at or ''}",
                f"supersedes: {', '.join(supersedes or [])}",
                f"superseded_by: {superseded_by or ''}",
                f"derived_from: {', '.join(derived_from or [])}",
                f"conflicts_with: {', '.join(conflicts_with or [])}",
                f"validated_by: {', '.join(validated_by or [])}",
                "---",
                "",
                content.strip(),
                "",
            ]
        )
        target.write_text(body, encoding="utf-8")
        self._append_memory_log(
            "save",
            target,
            {
                "scope": scope,
                "kind": kind,
                "visibility": visibility or self._default_visibility_for_scope(scope),
                "project_id": project_id,
                "group_id": group_id,
                "user_id": user_id,
                "owner_agent": owner_agent,
            },
        )
        self._rebuild_entrypoint()
        return target

    def forget_memory(self, filename: str) -> bool:
        target = self._find_memory_file(filename)
        if target is None or target.name == ENTRYPOINT_NAME:
            return False
        self._append_memory_log("forget", target, {"filename": filename})
        target.unlink()
        self._rebuild_entrypoint()
        return True

    def get_memory_record(self, filename: str) -> MemoryRecord | None:
        target = self._find_memory_file(filename)
        if target is None:
            return None
        for record in self._scan_memory_records():
            if record.path == target:
                return record
        return None

    def review_memory(
        self,
        filename: str,
        *,
        status: MemoryStatus | None = None,
        needs_review: bool | None = None,
        review_due_at: str | None = None,
        superseded_by: str | None = None,
        conflicts_with: list[str] | None = None,
        validated_by: list[str] | None = None,
        last_verified_at: str | None = None,
        visibility: VisibilityLevel | None = None,
        promotion_status: PromotionStatus | None = None,
    ) -> bool:
        target = self._find_memory_file(filename)
        if target is None:
            return False
        text = target.read_text(encoding="utf-8")
        meta, body = self._parse_frontmatter(text)
        if not meta:
            return False
        if status is not None:
            meta["status"] = status
        if needs_review is not None:
            meta["needs_review"] = str(needs_review).lower()
        if review_due_at is not None:
            meta["review_due_at"] = review_due_at
        if superseded_by is not None:
            meta["superseded_by"] = superseded_by
        if conflicts_with is not None:
            meta["conflicts_with"] = ", ".join(conflicts_with)
        if validated_by is not None:
            meta["validated_by"] = ", ".join(validated_by)
        if visibility is not None:
            meta["visibility"] = visibility
        if promotion_status is not None:
            meta["promotion_status"] = promotion_status
        meta["last_verified_at"] = last_verified_at or datetime.now(timezone.utc).isoformat()
        target.write_text(self._compose_frontmatter(meta, body), encoding="utf-8")
        self._append_memory_log(
            "review",
            target,
            {
                "status": meta.get("status", ""),
                "needs_review": meta.get("needs_review", ""),
                "visibility": meta.get("visibility", ""),
                "promotion_status": meta.get("promotion_status", ""),
                "superseded_by": meta.get("superseded_by", ""),
            },
        )
        self._rebuild_entrypoint()
        return True

    def promote_memory(
        self,
        filename: str,
        *,
        target_scope: MemoryScope,
        target_visibility: VisibilityLevel | None = None,
        user_id: str | None = None,
        project_id: str | None = None,
        group_id: str | None = None,
        approved_by: str | None = None,
    ) -> Path | None:
        target = self._find_memory_file(filename)
        if target is None:
            return None
        text = target.read_text(encoding="utf-8")
        meta, body = self._parse_frontmatter(text)
        if not meta:
            return None
        current_scope = self._coerce_scope(meta.get("scope", self._infer_scope_from_path(target)))
        resolved_user_id = user_id if user_id is not None else meta.get("user_id", "")
        resolved_project_id = project_id if project_id is not None else meta.get("project_id", "")
        resolved_group_id = group_id if group_id is not None else meta.get("group_id", "")
        destination_dir = self._resolve_target_dir(
            target_scope,
            user_id=resolved_user_id,
            project_id=resolved_project_id,
            group_id=resolved_group_id,
        )
        destination_dir.mkdir(parents=True, exist_ok=True)
        meta["scope"] = target_scope
        meta["user_id"] = resolved_user_id
        meta["project_id"] = resolved_project_id
        meta["group_id"] = resolved_group_id
        meta["visibility"] = target_visibility or self._default_visibility_for_scope(target_scope)
        if current_scope != target_scope:
            meta["promotion_status"] = self._default_promotion_for_scope(target_scope)
        meta["last_verified_at"] = datetime.now(timezone.utc).isoformat()
        validated_by = self._parse_list(meta.get("validated_by", ""))
        if approved_by:
            validated_by.append(
                f"approved-by:{approved_by}:{target_scope}:{datetime.now(timezone.utc).isoformat()}"
            )
        meta["validated_by"] = ", ".join(validated_by)
        meta["needs_review"] = "false"
        destination = destination_dir / target.name
        destination.write_text(self._compose_frontmatter(meta, body), encoding="utf-8")
        self._append_memory_log(
            "promote",
            destination,
            {
                "source": str(target.relative_to(self.shared_memory_dir)) if target.is_relative_to(self.shared_memory_dir) else str(target),
                "target_scope": target_scope,
                "target_visibility": meta.get("visibility", ""),
                "approved_by": approved_by or "",
                "project_id": resolved_project_id,
                "group_id": resolved_group_id,
                "user_id": resolved_user_id,
            },
        )
        if destination != target and target.exists():
            target.unlink()
        self._rebuild_entrypoint()
        return destination

    def get_session_memory(self) -> str:
        try:
            return self.session_file.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def maybe_update_session_memory(self, messages: list[Message], session_meta: dict[str, Any]) -> bool:
        current_chars = sum(len(m.content) for m in messages)
        current_messages = len(messages)
        last_chars = int(session_meta.get("session_memory_chars", 0))
        last_messages = int(session_meta.get("session_memory_messages", 0))
        if current_messages < 6:
            return False
        if current_chars - last_chars < 1500 and current_messages - last_messages < 4:
            return False
        summary = self._summarize_recent_messages(messages)
        self.session_file.write_text(summary, encoding="utf-8")
        session_meta["session_memory_chars"] = current_chars
        session_meta["session_memory_messages"] = current_messages
        return True

    def maybe_extract_long_term_memories(
        self,
        messages: list[Message],
        session_meta: dict[str, Any],
        *,
        owner_agent: str = "coordinator",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
    ) -> list[Path]:
        last_processed = int(session_meta.get("long_memory_last_message_count", 0))
        if len(messages) <= last_processed:
            return []
        recent = messages[last_processed:]
        extracted = self._extract_memories_from_messages(
            recent,
            owner_agent=owner_agent,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
        )
        saved_paths: list[Path] = []
        existing_titles = {record.title.lower() for record in self._scan_memory_records()}
        for item in extracted:
            if item["title"].lower() in existing_titles:
                continue
            saved_paths.append(self.save_memory(**item))
            existing_titles.add(item["title"].lower())
        session_meta["long_memory_last_message_count"] = len(messages)
        return saved_paths

    def search_memories(
        self,
        query: str,
        *,
        max_results: int = 5,
        user_id: str | None = None,
        project_id: str | None = None,
        group_id: str | None = None,
        scopes: list[str] | None = None,
    ) -> list[MemoryRecord]:
        return self.find_relevant_memories(
            query,
            max_memories=max_results,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            scopes=scopes,
        )

    def list_memories(
        self,
        *,
        user_id: str | None = None,
        project_id: str | None = None,
        group_id: str | None = None,
        scopes: list[str] | None = None,
    ) -> list[MemoryRecord]:
        return [
            record
            for record in self._scan_memory_records()
            if self._record_is_accessible(
                record,
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                scopes=scopes,
            )
        ]

    def find_relevant_memories(
        self,
        query: str,
        max_memories: int = 5,
        *,
        user_id: str | None = None,
        project_id: str | None = None,
        group_id: str | None = None,
        scopes: list[str] | None = None,
    ) -> list[MemoryRecord]:
        query_terms = self._terms(query)
        graph_context = self._load_graph_context(project_id=project_id or "")
        scored: list[tuple[float, MemoryRecord]] = []
        for record in self._scan_memory_records():
            if not self._record_is_accessible(record, user_id=user_id, project_id=project_id, group_id=group_id, scopes=scopes):
                continue
            overlap = self._compute_overlap_score(query_terms, record)
            if overlap <= 0:
                continue
            score = overlap
            score *= TYPE_WEIGHTS.get(record.kind, 1.0)
            score *= EVIDENCE_WEIGHTS.get(record.evidence_level, 1.0)
            score *= CONFIDENCE_WEIGHTS.get(record.confidence, 1.0)
            score *= STATUS_WEIGHTS.get(record.status, 1.0)
            score *= self._recency_weight(record.last_verified_at or record.created_at)
            score *= self._hypothesis_lifecycle_weight(record, query_terms)
            score *= self._typed_graph_recall_weight(
                record,
                query_terms,
                project_id=project_id or "",
                graph_context=graph_context,
            )
            if record.needs_review:
                score *= 0.8
            if record.scope == "project" and project_id and record.project_id == project_id:
                score *= 1.2
            if record.scope == "personal" and user_id and record.user_id == user_id:
                score *= 1.15
            if record.scope == "group" and group_id and record.group_id == group_id:
                score *= 1.1
            scored.append((score, record))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        shortlist = [record for _, record in scored[:20]]
        return self._select_recall_memories(
            query_terms,
            shortlist,
            max_memories,
            project_id=project_id or "",
            graph_context=graph_context,
        )

    def _record_is_accessible(
        self,
        record: MemoryRecord,
        *,
        user_id: str | None,
        project_id: str | None,
        group_id: str | None,
        scopes: list[str] | None,
    ) -> bool:
        if scopes and record.scope not in scopes:
            return False
        if record.scope == "personal":
            return bool(user_id and record.user_id == user_id)
        if record.scope == "project":
            return bool(project_id and record.project_id == project_id)
        if record.scope == "group":
            return bool(group_id and record.group_id == group_id)
        if record.scope == "agent":
            return bool(self.agent_namespace and record.namespace == self.agent_namespace)
        return True

    def _compute_overlap_score(self, query_terms: set[str], record: MemoryRecord) -> float:
        haystack = " ".join(
            [
                record.title,
                record.summary,
                record.kind,
                record.scope,
                record.user_id,
                record.project_id,
                record.group_id,
                record.visibility,
                record.promotion_status,
                " ".join(record.tags),
                " ".join(record.source_refs),
                " ".join(record.validated_by),
                " ".join(record.conflicts_with),
                record.excerpt,
            ]
        )
        return float(len(query_terms.intersection(self._terms(haystack))))

    def _hypothesis_lifecycle_weight(self, record: MemoryRecord, query_terms: set[str]) -> float:
        if record.kind != "hypothesis":
            return 1.0
        weight = 1.0
        tags = {tag.lower() for tag in record.tags}
        validated = {item.lower() for item in record.validated_by}
        query_hints = {
            "hypothesis",
            "mechanism",
            "prediction",
            "failed",
            "failure",
            "negative",
            "result",
            "deprecated",
            "revised",
            "rejected",
        }
        if query_terms.intersection(query_hints):
            weight *= 1.25
        if "challenged" in tags or any(item.startswith("challenged-by:") for item in validated):
            weight *= 1.35
        if record.status in {"revised", "deprecated"}:
            weight *= 1.2
        if record.status == "rejected":
            weight *= 0.8
        return weight

    def _typed_graph_recall_weight(
        self,
        record: MemoryRecord,
        query_terms: set[str],
        *,
        project_id: str,
        graph_context: dict[str, Any],
    ) -> float:
        if not project_id or record.project_id != project_id:
            return 1.0
        if not graph_context:
            return 1.0
        summary = graph_context.get("summary", {})
        nodes = graph_context.get("nodes", [])
        edges = graph_context.get("edges", [])
        if not isinstance(summary, dict) or not isinstance(nodes, list) or not isinstance(edges, list):
            return 1.0

        weight = 1.0
        node_type_counts = summary.get("node_type_counts", {}) if isinstance(summary.get("node_type_counts", {}), dict) else {}
        edge_type_counts = summary.get("edge_type_counts", {}) if isinstance(summary.get("edge_type_counts", {}), dict) else {}
        challenged_hypotheses = int(summary.get("challenged_hypothesis_count", 0) or 0)
        negative_result_count = int(node_type_counts.get("negative_result", 0) or 0)
        challenge_edges = int(edge_type_counts.get("challenges", 0) or 0)
        test_edges = int(edge_type_counts.get("tests", 0) or 0)

        if summary.get("snapshot_count", 0):
            weight *= 1.03
        if record.kind == "hypothesis" and challenged_hypotheses:
            weight *= min(1.4, 1.0 + 0.08 * challenged_hypotheses)
        if record.kind in {"warning", "decision"} and (negative_result_count or challenge_edges):
            weight *= min(1.35, 1.0 + 0.05 * max(negative_result_count, challenge_edges))
        if record.kind in {"method", "dataset_note", "decision"} and test_edges and query_terms.intersection(
            {"experiment", "protocol", "run", "interpretation", "quality", "control", "analysis"}
        ):
            weight *= min(1.25, 1.0 + 0.04 * test_edges)

        matched_node_ids = self._find_matching_graph_node_ids(record, query_terms, nodes)
        if matched_node_ids:
            weight *= min(1.45, 1.0 + 0.08 * len(matched_node_ids))
            adjacent_edges = sum(
                1
                for edge in edges
                if isinstance(edge, dict)
                and (
                    str(edge.get("source_id", "")).strip() in matched_node_ids
                    or str(edge.get("target_id", "")).strip() in matched_node_ids
                )
            )
            if adjacent_edges:
                weight *= min(1.25, 1.0 + 0.03 * adjacent_edges)
        return weight

    def _find_matching_graph_node_ids(
        self,
        record: MemoryRecord,
        query_terms: set[str],
        nodes: list[dict[str, Any]],
    ) -> set[str]:
        if not query_terms:
            return set()
        record_terms = self._terms(
            " ".join(
                [
                    record.title,
                    record.summary,
                    record.kind,
                    " ".join(record.tags),
                    " ".join(record.source_refs),
                    " ".join(record.derived_from),
                    " ".join(record.conflicts_with),
                    " ".join(record.validated_by),
                    record.excerpt,
                ]
            )
        )
        matched: set[str] = set()
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_terms = self._terms(
                " ".join(
                    [
                        str(node.get("node_id", "")),
                        str(node.get("node_type", "")),
                        str(node.get("label", "")),
                        self._flatten_graph_metadata(node.get("metadata", {})),
                    ]
                )
            )
            if not node_terms:
                continue
            if query_terms.intersection(node_terms) and record_terms.intersection(node_terms):
                matched.add(str(node.get("node_id", "")).strip())
        return {item for item in matched if item}

    def _load_graph_context(self, *, project_id: str) -> dict[str, Any]:
        if not project_id:
            return {}
        if project_id in self._graph_context_cache:
            return self._graph_context_cache[project_id]
        summary = self.graph_registry.summarize(project_id=project_id)
        context = {
            "summary": summary,
            "nodes": self.graph_registry.load_nodes(project_id=project_id),
            "edges": self.graph_registry.load_edges(project_id=project_id),
        }
        self._graph_context_cache[project_id] = context
        return context

    @staticmethod
    def _flatten_graph_metadata(metadata: Any) -> str:
        if isinstance(metadata, dict):
            return " ".join(MemoryManager._flatten_graph_metadata(value) for value in metadata.values())
        if isinstance(metadata, list):
            return " ".join(MemoryManager._flatten_graph_metadata(item) for item in metadata)
        return str(metadata or "")

    def _select_recall_memories(
        self,
        query_terms: set[str],
        candidates: list[MemoryRecord],
        max_memories: int,
        *,
        project_id: str,
        graph_context: dict[str, Any],
    ) -> list[MemoryRecord]:
        ranked_candidates = sorted(
            candidates,
            key=lambda record: (
                self._graph_shortlist_priority(
                    record,
                    query_terms,
                    project_id=project_id,
                    graph_context=graph_context,
                ),
                self._compute_overlap_score(query_terms, record),
            ),
            reverse=True,
        )
        selected: list[MemoryRecord] = []
        seen_titles: set[str] = set()
        for record in ranked_candidates:
            if len(selected) >= max_memories:
                break
            overlap = self._compute_overlap_score(query_terms, record)
            if overlap <= 0 or record.status == "rejected":
                continue
            if record.kind == "reference" and overlap < 2:
                continue
            if record.kind not in {"warning", "decision"} and overlap < 2 and record.evidence_level == "low":
                continue
            normalized_title = record.title.strip().lower()
            if normalized_title in seen_titles:
                continue
            seen_titles.add(normalized_title)
            selected.append(record)
        return selected

    def _graph_shortlist_priority(
        self,
        record: MemoryRecord,
        query_terms: set[str],
        *,
        project_id: str,
        graph_context: dict[str, Any],
    ) -> float:
        if not project_id or record.project_id != project_id or not graph_context:
            return 0.0
        nodes = graph_context.get("nodes", [])
        edges = graph_context.get("edges", [])
        if not isinstance(nodes, list) or not isinstance(edges, list):
            return 0.0
        matched_node_ids = self._find_matching_graph_node_ids(record, query_terms, nodes)
        if not matched_node_ids:
            return 0.0
        priority = float(len(matched_node_ids))
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            source_id = str(edge.get("source_id", "")).strip()
            target_id = str(edge.get("target_id", "")).strip()
            relation = str(edge.get("relation", "")).strip()
            if source_id not in matched_node_ids and target_id not in matched_node_ids:
                continue
            if relation == "challenges":
                priority += 1.25
            elif relation == "supports":
                priority += 0.9
            elif relation == "tests":
                priority += 0.75
            else:
                priority += 0.35
        if record.kind == "hypothesis":
            priority += 0.8
        if record.kind in {"warning", "decision"}:
            priority += 0.5
        return priority

    def _recency_weight(self, timestamp: str) -> float:
        try:
            ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except Exception:
            return 1.0
        age_days = max((datetime.now(timezone.utc) - ts).days, 0)
        return max(0.7, 1.2 - min(age_days / 365.0, 0.5))

    def _summarize_recent_messages(self, messages: list[Message]) -> str:
        lines = ["# Session Memory", "", "## Recent conversation state", ""]
        for msg in messages[-10:]:
            if msg.role == "system":
                continue
            content = " ".join(msg.content.split())
            if len(content) > 220:
                content = content[:217] + "..."
            lines.append(f"- {msg.role}: {content}")
        lines.extend(["", "## Notes", "", "- Keep this summary focused on active research state."])
        return "\n".join(lines)

    def _extract_memories_from_messages(
        self,
        messages: list[Message],
        *,
        owner_agent: str,
        user_id: str,
        project_id: str,
        group_id: str,
    ) -> list[dict[str, Any]]:
        extracted: list[dict[str, Any]] = []
        for msg in messages:
            text = " ".join(msg.content.split())
            lower = text.lower()
            if msg.role == "user" and any(phrase in lower for phrase in ["prefer ", "please use ", "always ", "avoid "]):
                extracted.append(
                    {
                        "title": self._clip_title(f"user preference: {text}", 80),
                        "summary": "User preference captured from conversation",
                        "kind": "preference",
                        "scope": "personal",
                        "content": text,
                        "tags": ["user-preference"],
                        "source_refs": [],
                        "evidence_level": "high",
                        "confidence": "high",
                        "status": "active",
                        "owner_agent": owner_agent,
                        "user_id": user_id,
                        "project_id": project_id,
                        "group_id": group_id,
                        "visibility": "private",
                        "promotion_status": "personal",
                        "needs_review": False,
                        "validated_by": ["conversation"],
                    }
                )
            if any(
                phrase in lower
                for phrase in [
                    "failed attempt",
                    "failed experiment",
                    "did not support",
                    "didn't support",
                    "negative result",
                    "no effect",
                    "null result",
                    "did not replicate",
                    "was not reproducible",
                ]
            ):
                extracted.append(
                    {
                        "title": self._clip_title(f"failed attempt: {text}", 80),
                        "summary": "Negative result or failed attempt captured from conversation",
                        "kind": "warning",
                        "scope": "project",
                        "content": text,
                        "tags": ["negative-result", "failed-attempt", "conversation"],
                        "source_refs": [],
                        "evidence_level": "medium",
                        "confidence": "medium",
                        "status": "active",
                        "owner_agent": owner_agent,
                        "user_id": user_id,
                        "project_id": project_id,
                        "group_id": group_id,
                        "visibility": "project",
                        "promotion_status": "project",
                        "needs_review": True,
                        "validated_by": ["conversation"],
                    }
                )
        return extracted[:6]

    def _load_static_memory_text(self) -> str:
        chunks: list[str] = []
        for path in self.static_memory_files:
            try:
                text = path.read_text(encoding="utf-8").strip()
            except Exception:
                continue
            if text:
                chunks.extend([f"## {path.name}", text, ""])
        return "\n".join(chunks).strip()

    def _scan_memory_records(self) -> list[MemoryRecord]:
        records: list[MemoryRecord] = []
        for path in sorted(self.shared_memory_dir.rglob("*.md")):
            if path.name in {ENTRYPOINT_NAME, MEMORY_LOG_NAME} or path.name == self.session_file.name:
                continue
            if "session" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            meta, body = self._parse_frontmatter(text)
            records.append(
                MemoryRecord(
                    path=path,
                    title=meta.get("title", path.stem),
                    summary=meta.get("summary", ""),
                    scope=self._coerce_scope(meta.get("scope", self._infer_scope_from_path(path))),
                    kind=self._coerce_kind(meta.get("type", "reference")),
                    tags=self._parse_list(meta.get("tags", "")),
                    source_refs=self._parse_list(meta.get("source_refs", "")),
                    evidence_level=self._coerce_evidence(meta.get("evidence_level", "medium")),
                    confidence=self._coerce_confidence(meta.get("confidence", "medium")),
                    status=self._coerce_status(meta.get("status", "active")),
                    owner_agent=meta.get("owner_agent", "unknown"),
                    user_id=meta.get("user_id", ""),
                    project_id=meta.get("project_id", ""),
                    group_id=meta.get("group_id", ""),
                    visibility=self._coerce_visibility(meta.get("visibility", self._default_visibility_for_scope(self._coerce_scope(meta.get("scope", self._infer_scope_from_path(path)))))),
                    promotion_status=self._coerce_promotion(meta.get("promotion_status", self._default_promotion_for_scope(self._coerce_scope(meta.get("scope", self._infer_scope_from_path(path)))))),
                    created_at=meta.get("created_at", ""),
                    last_verified_at=meta.get("last_verified_at", ""),
                    needs_review=self._coerce_bool(meta.get("needs_review", "false")),
                    review_due_at=meta.get("review_due_at", ""),
                    supersedes=self._parse_list(meta.get("supersedes", "")),
                    superseded_by=meta.get("superseded_by", "") or None,
                    derived_from=self._parse_list(meta.get("derived_from", "")),
                    conflicts_with=self._parse_list(meta.get("conflicts_with", "")),
                    validated_by=self._parse_list(meta.get("validated_by", "")),
                    excerpt=body[:400],
                    namespace=self._infer_agent_namespace_from_path(path),
                )
            )
        return records

    def _rebuild_entrypoint(self) -> None:
        lines = ["# MEMORY", ""]
        for record in self._scan_memory_records():
            rel = record.path.relative_to(self.shared_memory_dir).as_posix()
            hook = f"{record.kind}/{record.scope} | {record.summary or record.status} | visibility={record.visibility}"
            lines.append(f"- [{record.title}]({rel}) - {hook}")
        lines.append("")
        self.entrypoint.write_text("\n".join(lines), encoding="utf-8")

    def _find_memory_file(self, filename: str) -> Path | None:
        for path in self.shared_memory_dir.rglob(filename):
            if path.is_file() and path.name not in {ENTRYPOINT_NAME, MEMORY_LOG_NAME}:
                scope = self._infer_scope_from_path(path)
                namespace = self._infer_agent_namespace_from_path(path)
                if scope == "agent" and namespace != self.agent_namespace:
                    continue
                return path
        return None

    def _append_memory_log(self, action: str, path: Path, metadata: dict[str, Any] | None = None) -> None:
        try:
            rel = path.relative_to(self.shared_memory_dir).as_posix()
        except Exception:
            rel = str(path)
        timestamp = datetime.now(timezone.utc).isoformat()
        metadata = metadata or {}
        details = "; ".join(
            f"{key}={value}"
            for key, value in metadata.items()
            if str(value).strip()
        )
        line = f"## [{timestamp}] {action} | {rel}"
        if details:
            line = f"{line} | {details}"
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with self.log_file.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    @staticmethod
    def _compose_frontmatter(meta: dict[str, str], body: str) -> str:
        lines = ["---"]
        for key, value in meta.items():
            lines.append(f"{key}: {value}")
        lines.extend(["---", "", body.strip(), ""])
        return "\n".join(lines)

    def _resolve_target_dir(self, scope: MemoryScope, *, user_id: str, project_id: str, group_id: str) -> Path:
        if scope == "personal":
            return self.shared_memory_dir / "personal" / self._slugify_identifier(user_id or "unknown-user")
        if scope == "project":
            return self.shared_memory_dir / "projects" / self._slugify_identifier(project_id or "default-project")
        if scope == "group":
            return self.shared_memory_dir / "groups" / self._slugify_identifier(group_id or "default-group")
        if scope == "public":
            return self.shared_memory_dir / "public"
        if scope == "agent":
            return self.agent_memory_dir
        return self.shared_memory_dir

    def _infer_scope_from_path(self, path: Path) -> str:
        if "personal" in path.parts:
            return "personal"
        if "projects" in path.parts:
            return "project"
        if "groups" in path.parts:
            return "group"
        if "public" in path.parts:
            return "public"
        if "agents" in path.parts:
            return "agent"
        return "project"

    def _infer_agent_namespace_from_path(self, path: Path) -> str | None:
        parts = list(path.parts)
        if "agents" not in parts:
            return None
        index = parts.index("agents")
        if index + 1 >= len(parts):
            return None
        return parts[index + 1]

    @staticmethod
    def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
        if not text.startswith("---\n"):
            return {}, text
        parts = text.split("\n---\n", 1)
        if len(parts) != 2:
            return {}, text
        raw_meta = parts[0].replace("---\n", "", 1)
        content = parts[1]
        meta: dict[str, str] = {}
        for line in raw_meta.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
        return meta, content

    @staticmethod
    def _parse_list(raw: str) -> list[str]:
        if not raw:
            return []
        return [item.strip() for item in raw.split(",") if item.strip()]

    @staticmethod
    def _clip_title(text: str, width: int) -> str:
        return text if len(text) <= width else text[: width - 3] + "..."

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
        return (slug or "memory") + ".md"

    @staticmethod
    def _slugify_identifier(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
        return slug or "default"

    @staticmethod
    def _slugify_agent_namespace(value: str | None) -> str | None:
        if not value:
            return None
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
        return slug or None

    @staticmethod
    def _terms(text: str) -> set[str]:
        return {term for term in re.findall(r"[a-zA-Z0-9_]+", text.lower()) if len(term) >= 3}

    @staticmethod
    def _coerce_scope(value: str) -> MemoryScope:
        allowed = {"instruction", "personal", "project", "group", "public", "agent", "session"}
        return value if value in allowed else "project"

    @staticmethod
    def _coerce_kind(value: str) -> MemoryKind:
        allowed = {"fact", "hypothesis", "method", "decision", "dataset_note", "warning", "preference", "reference"}
        return value if value in allowed else "reference"

    @staticmethod
    def _coerce_evidence(value: str) -> EvidenceLevel:
        return value if value in {"low", "medium", "high"} else "medium"

    @staticmethod
    def _coerce_confidence(value: str) -> ConfidenceLevel:
        return value if value in {"low", "medium", "high"} else "medium"

    @staticmethod
    def _coerce_status(value: str) -> MemoryStatus:
        return value if value in {"active", "revised", "uncertain", "deprecated", "rejected"} else "active"

    @staticmethod
    def _coerce_visibility(value: str) -> VisibilityLevel:
        return value if value in {"private", "project", "group", "public"} else "project"

    @staticmethod
    def _coerce_promotion(value: str) -> PromotionStatus:
        return value if value in {"personal", "project", "group", "public"} else "project"

    @staticmethod
    def _coerce_bool(value: str) -> bool:
        return str(value).strip().lower() in {"1", "true", "yes"}

    @staticmethod
    def _default_visibility_for_scope(scope: MemoryScope) -> VisibilityLevel:
        return {
            "personal": "private",
            "project": "project",
            "group": "group",
            "public": "public",
            "agent": "private",
            "instruction": "project",
            "session": "private",
        }.get(scope, "project")

    @staticmethod
    def _default_promotion_for_scope(scope: MemoryScope) -> PromotionStatus:
        return {
            "personal": "personal",
            "project": "project",
            "group": "group",
            "public": "public",
            "agent": "personal",
            "instruction": "project",
            "session": "personal",
        }.get(scope, "project")

