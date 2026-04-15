from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .memory import MemoryManager, MemoryRecord


DEFAULT_EXCLUDED_CONTEXT_ROOTS = [
    ".state/runtime/learning",
    ".state/runtime/trajectories",
    ".state/events",
    ".state/runtime/events",
    ".state/runtime_manifests",
]


@dataclass(slots=True)
class ContextPackItem:
    item_id: str
    item_type: str
    title: str
    summary: str
    source_path: str = ""
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ContextPack:
    pack_id: str
    query: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    policy: dict[str, Any] = field(default_factory=dict)
    memory_items: list[ContextPackItem] = field(default_factory=list)
    literature_items: list[ContextPackItem] = field(default_factory=list)
    graph_items: list[ContextPackItem] = field(default_factory=list)
    failed_attempt_items: list[ContextPackItem] = field(default_factory=list)
    exclusions: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ["memory_items", "literature_items", "graph_items", "failed_attempt_items"]:
            data[key] = [item.to_dict() for item in getattr(self, key)]
        return data

    def render_prompt_context(self, *, max_chars: int = 12000) -> str:
        sections = [
            "# Scientific Context Pack",
            "",
            f"- Pack id: `{self.pack_id}`",
            f"- Query: {self.query}",
            "- Policy: compact summaries only; raw learning logs, trajectories, and event ledgers are excluded.",
        ]
        sections.extend(self._render_items("Relevant Memory", self.memory_items))
        sections.extend(self._render_items("Failed Attempts / Negative Results", self.failed_attempt_items))
        sections.extend(self._render_items("Literature Notes", self.literature_items))
        sections.extend(self._render_items("Graph Facts", self.graph_items))
        if self.exclusions:
            sections.extend(["", "## Excluded Cold Context"])
            for item in self.exclusions[:20]:
                sections.append(f"- {item.get('path', '')}: {item.get('reason', '')}")
        text = "\n".join(sections).strip()
        if len(text) > max_chars:
            return text[: max_chars - 80].rstrip() + "\n\n[context pack truncated by max_chars]"
        return text

    @staticmethod
    def _render_items(title: str, items: list[ContextPackItem]) -> list[str]:
        if not items:
            return []
        lines = ["", f"## {title}"]
        for item in items:
            lines.append(
                f"- {item.title}: {item.summary}"
                + (f" [`{item.source_path}`]" if item.source_path else "")
            )
        return lines


class ContextPackBuilder:
    def __init__(
        self,
        *,
        root: str | Path,
        memory_manager: MemoryManager,
        literature_root: str | Path | None = None,
        state_root: str | Path | None = None,
        excluded_roots: list[str] | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.memory_manager = memory_manager
        self.literature_root = Path(literature_root).resolve() if literature_root else self.root / "literature"
        self.state_root = Path(state_root).resolve() if state_root else self.root / ".state"
        self.excluded_roots = excluded_roots or DEFAULT_EXCLUDED_CONTEXT_ROOTS

    def build(
        self,
        query: str,
        *,
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        max_memory_items: int = 8,
        max_literature_items: int = 6,
        max_graph_items: int = 8,
        max_failed_attempt_items: int = 6,
    ) -> ContextPack:
        memory_records = self.memory_manager.find_relevant_memories(
            query,
            max_memories=max_memory_items + max_failed_attempt_items,
            user_id=user_id or None,
            project_id=project_id or None,
            group_id=group_id or None,
        )
        failed_records = [
            record
            for record in memory_records
            if record.kind == "warning" or "failed-attempt" in record.tags or "negative-result" in record.tags
        ][:max_failed_attempt_items]
        normal_records = [record for record in memory_records if record not in failed_records][:max_memory_items]
        return ContextPack(
            pack_id=f"context-pack::{_slugify(query)}::{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            query=query,
            policy=build_context_exclusion_policy_summary(root=self.root, state_root=self.state_root),
            memory_items=[self._memory_item(record, query) for record in normal_records],
            failed_attempt_items=[self._memory_item(record, query) for record in failed_records],
            literature_items=self._literature_items(query, max_items=max_literature_items),
            graph_items=self._graph_items(query, project_id=project_id, max_items=max_graph_items),
            exclusions=self._excluded_context_items(),
            metadata={
                "max_memory_items": max_memory_items,
                "max_literature_items": max_literature_items,
                "max_graph_items": max_graph_items,
                "max_failed_attempt_items": max_failed_attempt_items,
            },
        )

    def _memory_item(self, record: MemoryRecord, query: str) -> ContextPackItem:
        return ContextPackItem(
            item_id=record.path.name,
            item_type=f"memory/{record.kind}/{record.scope}",
            title=record.title,
            summary=_clip(record.summary or record.excerpt, 500),
            source_path=str(record.path),
            score=float(len(_terms(query).intersection(_terms(" ".join([record.title, record.summary, record.excerpt]))))),
            metadata={
                "scope": record.scope,
                "kind": record.kind,
                "tags": record.tags,
                "evidence_level": record.evidence_level,
                "confidence": record.confidence,
                "status": record.status,
                "visibility": record.visibility,
            },
        )

    def _literature_items(self, query: str, *, max_items: int) -> list[ContextPackItem]:
        if not self.literature_root.exists():
            return []
        query_terms = _terms(query)
        scored: list[tuple[float, Path, str]] = []
        for path in sorted((self.literature_root / "wiki").rglob("*.md")) if (self.literature_root / "wiki").exists() else []:
            if path.name.upper() == "TEMPLATE.MD":
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            score = len(query_terms.intersection(_terms(text)))
            if score <= 0:
                continue
            scored.append((float(score), path, text))
        items: list[ContextPackItem] = []
        for score, path, text in sorted(scored, key=lambda row: row[0], reverse=True)[:max_items]:
            items.append(
                ContextPackItem(
                    item_id=path.name,
                    item_type="literature/wiki",
                    title=_first_heading_or_title(text, fallback=path.stem),
                    summary=_clip(_first_bullet(text) or _first_paragraph(text), 500),
                    source_path=str(path),
                    score=score,
                    metadata={"relative_path": _safe_relative(path, self.literature_root)},
                )
            )
        return items

    def _graph_items(self, query: str, *, project_id: str, max_items: int) -> list[ContextPackItem]:
        if not project_id:
            return []
        try:
            context = self.memory_manager._load_graph_context(project_id=project_id)
        except Exception:
            return []
        query_terms = _terms(query)
        candidates: list[tuple[float, dict[str, Any]]] = []
        for node in context.get("nodes", []) if isinstance(context.get("nodes", []), list) else []:
            if not isinstance(node, dict):
                continue
            text = " ".join(
                [
                    str(node.get("node_id", "")),
                    str(node.get("node_type", "")),
                    str(node.get("label", "")),
                    json.dumps(node.get("metadata", {}), ensure_ascii=False, sort_keys=True, default=str),
                ]
            )
            score = len(query_terms.intersection(_terms(text)))
            if score > 0:
                candidates.append((float(score), node))
        items: list[ContextPackItem] = []
        for score, node in sorted(candidates, key=lambda row: row[0], reverse=True)[:max_items]:
            metadata = node.get("metadata", {}) if isinstance(node.get("metadata", {}), dict) else {}
            items.append(
                ContextPackItem(
                    item_id=str(node.get("node_id", "")),
                    item_type=f"graph/{node.get('node_type', 'node')}",
                    title=str(node.get("label", "") or node.get("node_id", "")),
                    summary=_clip(str(metadata.get("summary", "")) or json.dumps(metadata, ensure_ascii=False, default=str), 500),
                    score=score,
                    metadata={"project_id": project_id, "node_type": str(node.get("node_type", ""))},
                )
            )
        return items

    def _excluded_context_items(self) -> list[dict[str, Any]]:
        excluded: list[dict[str, Any]] = []
        policy = build_context_exclusion_policy_summary(root=self.root, state_root=self.state_root)
        for raw_path in policy.get("excluded_by_default", []):
            path = Path(str(raw_path))
            if not path.exists():
                continue
            excluded.append(
                {
                    "path": str(path),
                    "reason": "cold runtime data; retrieve through replay/evaluation tools, not prompt stuffing",
                }
            )
        for raw in self.excluded_roots:
            path = self.root / raw
            if not path.exists():
                continue
            item = (
                {
                    "path": str(path),
                    "reason": "cold runtime data; retrieve through replay/evaluation tools, not prompt stuffing",
                }
            )
            if item not in excluded:
                excluded.append(item)
        return excluded


def build_context_exclusion_policy_summary(*, root: str | Path, state_root: str | Path | None = None) -> dict[str, Any]:
    resolved = Path(root).resolve()
    state = Path(state_root).resolve() if state_root else resolved / ".state"
    return {
        "policy_id": "learning-logs-exclusion-policy-v1",
        "default_prompt_policy": "exclude_cold_runtime_logs",
        "excluded_by_default": [
            str(state / "runtime" / "learning"),
            str(state / "runtime" / "trajectories"),
            str(state / "runtime" / "events"),
            str(state / "events"),
            str(state / "runtime_manifests"),
        ],
        "allowed_access_modes": ["explicit_replay", "benchmark_eval", "audit_query", "training_export"],
        "prompt_inclusion_rule": "Only compact ContextPack summaries may enter prompts by default.",
        "business_logic_effect": "none",
    }


def _terms(text: str) -> set[str]:
    import re

    return {term for term in re.findall(r"[a-zA-Z0-9_]+", str(text).lower()) if len(term) >= 3}


def _clip(text: str, width: int) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= width:
        return compact
    return compact[: width - 3] + "..."


def _first_heading_or_title(text: str, *, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("title:"):
            return line.split(":", 1)[1].strip().strip('"')
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _first_bullet(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and len(stripped) > 2:
            return stripped[2:]
    return ""


def _first_paragraph(text: str) -> str:
    for block in text.split("\n\n"):
        stripped = " ".join(block.split())
        if stripped and not stripped.startswith("---") and not stripped.startswith("#"):
            return stripped
    return ""


def _safe_relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except Exception:
        return str(path)


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "context"


