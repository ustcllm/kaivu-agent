from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from kaivu.literature_policy import decide_literature_ingest_policy, render_literature_ingest_digest
from kaivu import (
    ArxivSearchTool,
    BasicStatsTool,
    ContextPackBuilder,
    ExperimentRegistry,
    apply_backpropagation_to_claim_graph,
    build_backpropagation_events,
    build_backpropagation_memory_items,
    ResearchEventLedger,
    ResearchProgramRegistry,
    ResearchEvent,
    ResearchGraphRegistry,
    CrossrefSearchTool,
    ForgetMemoryTool,
    MemoryManager,
    plan_memory_migrations,
    migration_audit_tag,
    ModelRegistry,
    NotebookTool,
    PermissionPolicy,
    PlotCsvTool,
    PubMedSearchTool,
    PythonExecTool,
    ReadFileTool,
    ReadTableTool,
    ResearchWorkspaceLayout,
    ResolveCitationTool,
    ReviewMemoryTool,
    SaveMemoryTool,
    ResearchDirector,
    ScientificRuntimeHarness,
    RuntimeManifestStore,
    ScientificLearningEpisodeStore,
    SearchMemoryTool,
    SkillRuntime,
    ToolRegistry,
    WriteFileTool,
    load_experiment_backpropagation_summary,
    load_skills,
    normalize_run_handoff_payload,
    persist_run_handoff_bundle,
)


@dataclass(slots=True)
class RunRecord:
    run_id: str
    topic: str
    status: str
    discipline: str = ""
    user_id: str = ""
    project_id: str = ""
    group_id: str = ""
    group_role: str = ""
    result: Any | None = None
    error: str | None = None
    report_markdown: str | None = None
    usage_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ThreadMessageRecord:
    role: str
    content: str
    created_at: str


@dataclass(slots=True)
class ThreadRecord:
    thread_id: str
    title: str
    run_id: str | None = None
    user_id: str = ""
    project_id: str = ""
    group_id: str = ""
    group_role: str = ""
    chat: list[ThreadMessageRecord] = field(default_factory=list)
    snapshot: dict[str, Any] = field(default_factory=dict)
    archived: bool = False
    created_at: str = ""
    updated_at: str = ""


class WorkflowRuntime:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self._runs: dict[str, RunRecord] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._threads_path = self.root / ".state" / "service" / "threads.json"
        self._group_roles_path = self.root / ".state" / "service" / "group_roles.json"
        self._memberships_path = self.root / ".state" / "service" / "memberships.json"
        self._experiments_root = self.root / ".state" / "service" / "experiments"
        self._threads_path.parent.mkdir(parents=True, exist_ok=True)
        self._threads: dict[str, ThreadRecord] = self._load_threads()
        self._group_roles = self._load_group_roles()
        self._memberships = self._load_memberships()
        self._experiment_registry = ExperimentRegistry(self._experiments_root)
        self._research_graph_registry = ResearchGraphRegistry(self.root / ".state" / "graph")
        self._research_program_registry = ResearchProgramRegistry(self.root / ".state" / "programs")
        self._runtime_manifest_store = RuntimeManifestStore(self.root / ".state" / "runtime_manifests")
        self._event_ledger = ResearchEventLedger(self.root / ".state" / "events")

    def _layout_for_scope(
        self,
        *,
        discipline: str = "",
        project_id: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> ResearchWorkspaceLayout:
        layout = ResearchWorkspaceLayout.for_context(
            self.root,
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        layout.ensure()
        return layout

    def _memory_manager_for_scope(
        self,
        *,
        discipline: str = "",
        project_id: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> MemoryManager:
        layout = self._layout_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        return MemoryManager(
            self.root,
            memory_root=layout.memory_root,
            state_root=layout.state_root,
        )

    def build_context_pack(self, payload: dict[str, Any]) -> dict[str, Any]:
        discipline = str(payload.get("discipline", ""))
        project_id = str(payload.get("project_id", ""))
        group_id = str(payload.get("group_id", ""))
        user_id = str(payload.get("user_id", ""))
        layout = self._layout_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        manager = self._memory_manager_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        builder = ContextPackBuilder(
            root=self.root,
            memory_manager=manager,
            literature_root=layout.literature_root,
            state_root=layout.state_root,
        )
        pack = builder.build(
            str(payload.get("query", "")),
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            max_memory_items=int(payload.get("max_memory_items", 8) or 8),
            max_literature_items=int(payload.get("max_literature_items", 6) or 6),
            max_graph_items=int(payload.get("max_graph_items", 8) or 8),
            max_failed_attempt_items=int(payload.get("max_failed_attempt_items", 6) or 6),
        )
        return {
            "pack": pack.to_dict(),
            "rendered_prompt_context": pack.render_prompt_context(
                max_chars=int(payload.get("max_prompt_chars", 12000) or 12000)
            )
            if bool(payload.get("render_prompt", False))
            else "",
        }

    def _event_ledger_for_scope(
        self,
        *,
        discipline: str = "",
        project_id: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> ResearchEventLedger:
        layout = self._layout_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        return ResearchEventLedger(layout.state_root / "events")

    def _experiment_registry_for_scope(
        self,
        *,
        discipline: str = "",
        project_id: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> ExperimentRegistry:
        layout = self._layout_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        return ExperimentRegistry(layout.state_root / "service" / "experiments")

    def list_research_programs(
        self,
        *,
        discipline: str = "",
        project_id: str = "",
        topic: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> list[dict[str, Any]]:
        layout = self._layout_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        return ResearchProgramRegistry(layout.state_root / "programs").load_programs(project_id=project_id, topic=topic)

    def latest_research_program(
        self,
        *,
        discipline: str = "",
        project_id: str = "",
        topic: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> dict[str, Any] | None:
        layout = self._layout_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        return ResearchProgramRegistry(layout.state_root / "programs").latest_program(project_id=project_id, topic=topic)

    def list_runtime_manifests(
        self,
        *,
        limit: int = 50,
        discipline: str = "",
        project_id: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> list[dict[str, Any]]:
        layout = self._layout_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        return RuntimeManifestStore(layout.state_root / "runtime_manifests").list(limit=limit)

    def latest_runtime_manifest(
        self,
        *,
        discipline: str = "",
        project_id: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> dict[str, Any] | None:
        layout = self._layout_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        return RuntimeManifestStore(layout.state_root / "runtime_manifests").latest()

    def list_learning_episodes(
        self,
        *,
        limit: int = 50,
        discipline: str = "",
        project_id: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> list[dict[str, Any]]:
        layout = self._layout_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        path = layout.state_root / "runtime" / "learning" / "scientific_learning_episodes.jsonl"
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                rows.append(item)
        return rows[-max(1, min(limit, 500)) :]

    def _learning_store_for_scope(
        self,
        *,
        discipline: str = "",
        project_id: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> ScientificLearningEpisodeStore:
        layout = self._layout_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        return ScientificLearningEpisodeStore(layout.state_root / "runtime" / "learning")

    def validate_learning_episodes(
        self,
        *,
        limit: int = 1000,
        discipline: str = "",
        project_id: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> dict[str, Any]:
        return self._learning_store_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        ).validate_episodes(limit=limit)

    def summarize_learning_feedback(
        self,
        *,
        limit: int = 1000,
        discipline: str = "",
        project_id: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> dict[str, Any]:
        return self._learning_store_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        ).aggregate_feedback(limit=limit)

    def export_learning_training_dataset(self, payload: dict[str, Any]) -> dict[str, Any]:
        store = self._learning_store_for_scope(
            discipline=str(payload.get("discipline", "")),
            project_id=str(payload.get("project_id", "")),
            group_id=str(payload.get("group_id", "")),
            user_id=str(payload.get("user_id", "")),
        )
        path = store.export_training_dataset(
            target=str(payload.get("target", "policy")),
            limit=int(payload.get("limit", 1000) or 1000),
            filename=payload.get("filename"),
        )
        return {"ok": True, "path": str(path), "kind": "training_dataset", "message": "Training dataset exported."}

    def build_learning_benchmark_dataset(
        self,
        *,
        limit: int = 1000,
        discipline: str = "",
        project_id: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> dict[str, Any]:
        path = self._learning_store_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        ).build_benchmark_dataset(limit=limit)
        return {"ok": True, "path": str(path), "kind": "benchmark_dataset", "message": "Benchmark dataset built."}

    def build_learning_replay_index(
        self,
        *,
        limit: int = 1000,
        discipline: str = "",
        project_id: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> dict[str, Any]:
        path = self._learning_store_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        ).build_replay_index(limit=limit)
        return {"ok": True, "path": str(path), "kind": "replay_index", "message": "Replay index built."}

    def run_learning_replay_checks(
        self,
        *,
        limit: int = 1000,
        discipline: str = "",
        project_id: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> dict[str, Any]:
        path = self._learning_store_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        ).run_replay_checks(limit=limit)
        return {"ok": True, "path": str(path), "kind": "replay_report", "message": "Replay checks completed."}

    def run_learning_benchmark_checks(
        self,
        *,
        limit: int = 1000,
        discipline: str = "",
        project_id: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> dict[str, Any]:
        path = self._learning_store_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        ).run_benchmark_checks(limit=limit)
        return {"ok": True, "path": str(path), "kind": "benchmark_report", "message": "Benchmark checks completed."}

    def append_learning_feedback(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        layout = self._layout_for_scope(
            discipline=str(payload.get("discipline", "")),
            project_id=str(payload.get("project_id", "")),
            group_id=str(payload.get("group_id", "")),
            user_id=str(payload.get("user_id", "")),
        )
        feedback = {
            "episode_id": str(payload.get("episode_id", "")).strip(),
            "feedback_type": str(payload.get("feedback_type", "human_preference")).strip(),
            "rating": payload.get("rating"),
            "preferred_step_id": str(payload.get("preferred_step_id", "")).strip(),
            "rejected_step_id": str(payload.get("rejected_step_id", "")).strip(),
            "comment": str(payload.get("comment", "")).strip(),
            "reviewer_id": str(payload.get("reviewer_id", "")).strip(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "governance": {
                "observation_only": True,
                "does_not_modify_business_decisions": True,
            },
        }
        if not feedback["episode_id"]:
            return {"ok": False, "path": "", "message": "episode_id is required"}
        path = layout.state_root / "runtime" / "learning" / "human_feedback.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(feedback, ensure_ascii=False, sort_keys=True) + "\n")
        return {"ok": True, "path": str(path), "message": "Feedback appended to learning layer only."}

    @staticmethod
    def _allowed_run_status_transitions() -> dict[str, set[str]]:
        return {
            "planned": {"planned", "approved", "archived"},
            "approved": {"approved", "running", "archived"},
            "running": {"running", "completed", "quality_control_failed", "archived"},
            "completed": {"completed", "analyzed", "quality_control_failed", "archived"},
            "quality_control_failed": {"quality_control_failed", "archived"},
            "analyzed": {"analyzed", "archived"},
            "archived": {"archived"},
        }

    def _protocol_has_newer_amendment(
        self,
        protocol_id: str,
        *,
        registry: ExperimentRegistry | None = None,
    ) -> bool:
        protocols = (registry or self._experiment_registry).load_collection("experimental_protocols")
        for item in protocols:
            if not isinstance(item, dict):
                continue
            if str(item.get("lineage_parent_protocol_id", "")).strip() == protocol_id:
                return True
        return False

    def _validate_experiment_specification_payload(
        self,
        payload: dict[str, Any],
        existing: dict[str, Any] | None,
    ) -> None:
        if existing is not None and bool(existing.get("is_frozen", False)):
            raise ValueError("Frozen experiment specification cannot be modified until it is unfrozen")
        status = str(payload.get("status", existing.get("status", "planned") if existing else "planned")).strip()
        if status and status not in {"planned", "active", "paused", "retired", "archived"}:
            raise ValueError(f"Invalid experiment specification status: {status}")
        parent_id = str(payload.get("lineage_parent_experiment_id", "")).strip()
        if parent_id and existing and str(existing.get("experiment_id", "")).strip() == parent_id:
            raise ValueError("Experiment specification cannot point to itself as lineage parent")

    def _validate_experimental_protocol_payload(
        self,
        payload: dict[str, Any],
        existing: dict[str, Any] | None,
    ) -> None:
        if existing is not None and bool(existing.get("is_frozen", False)):
            raise ValueError("Frozen protocol cannot be modified; create an amendment instead")
        protocol_id = str(payload.get("protocol_id", "")).strip()
        parent_id = str(payload.get("lineage_parent_protocol_id", "")).strip()
        if parent_id and protocol_id and parent_id == protocol_id:
            raise ValueError("Protocol cannot point to itself as lineage parent")
        amendment_reason = str(payload.get("amendment_reason", "")).strip()
        if parent_id and not amendment_reason:
            raise ValueError("Protocol amendment requires an amendment_reason")
        version = str(payload.get("version", "")).strip()
        if not version:
            raise ValueError("Protocol version is required")

    def _validate_experiment_run_payload(
        self,
        payload: dict[str, Any],
        existing: dict[str, Any] | None,
        *,
        registry: ExperimentRegistry | None = None,
    ) -> None:
        run_id = str(payload.get("run_id", "")).strip()
        protocol_id = str(payload.get("protocol_id", "")).strip()
        status = str(payload.get("status", existing.get("status", "planned") if existing else "planned")).strip() or "planned"
        approval_status = str(payload.get("approval_status", existing.get("approval_status", "pending") if existing else "pending")).strip() or "pending"
        if status not in self._allowed_run_status_transitions():
            raise ValueError(f"Invalid experiment run status: {status}")
        if existing is not None:
            previous = str(existing.get("status", "planned")).strip() or "planned"
            allowed = self._allowed_run_status_transitions().get(previous, {previous})
            if status not in allowed:
                raise ValueError(f"Invalid run status transition: {previous} -> {status}")
        if self._protocol_has_newer_amendment(protocol_id, registry=registry) and existing is None:
            raise ValueError("Cannot create a new run from a superseded protocol; amend or use the latest protocol version")
        if status in {"running", "completed", "quality_control_failed", "analyzed"} and approval_status != "approved":
            raise ValueError("Run must be approved before it can move beyond planned status")
        if approval_status == "approved" and not str(payload.get("approved_by", existing.get("approved_by", "") if existing else "")).strip():
            raise ValueError("Approved runs must record approved_by")
        supersedes_run_id = str(payload.get("supersedes_run_id", "")).strip()
        if supersedes_run_id and supersedes_run_id == run_id:
            raise ValueError("Run cannot supersede itself")

    def _load_threads(self) -> dict[str, ThreadRecord]:
        if not self._threads_path.exists():
            return {}
        try:
            raw = json.loads(self._threads_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(raw, list):
            return {}
        threads: dict[str, ThreadRecord] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            messages = [
                ThreadMessageRecord(
                    role=str(message.get("role", "system")),
                    content=str(message.get("content", "")),
                    created_at=str(message.get("created_at", "")),
                )
                for message in item.get("chat", [])
                if isinstance(message, dict)
            ]
            record = ThreadRecord(
                thread_id=str(item.get("thread_id") or item.get("id") or uuid4().hex),
                title=str(item.get("title", "Untitled Research Thread")),
                run_id=item.get("run_id"),
                user_id=str(item.get("user_id", "")),
                project_id=str(item.get("project_id", "")),
                group_id=str(item.get("group_id", "")),
                group_role=str(item.get("group_role", "")),
                chat=messages,
                snapshot=item.get("snapshot", {}) if isinstance(item.get("snapshot"), dict) else {},
                archived=bool(item.get("archived", False)),
                created_at=str(item.get("created_at", "")),
                updated_at=str(item.get("updated_at", "")),
            )
            threads[record.thread_id] = record
        return threads

    def _save_threads(self) -> None:
        payload = [
            {
                "thread_id": record.thread_id,
                "title": record.title,
                "run_id": record.run_id,
                "user_id": record.user_id,
                "project_id": record.project_id,
                "group_id": record.group_id,
                "group_role": record.group_role,
                "chat": [
                    {
                        "role": message.role,
                        "content": message.content,
                        "created_at": message.created_at,
                    }
                    for message in record.chat
                ],
                "snapshot": record.snapshot,
                "archived": record.archived,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            }
            for record in self.list_threads()
        ]
        self._threads_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def _load_group_roles(self) -> dict[str, dict[str, str]]:
        if not self._group_roles_path.exists():
            return {}
        try:
            raw = json.loads(self._group_roles_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(raw, dict):
            return {}
        roles: dict[str, dict[str, str]] = {}
        for group_id, members in raw.items():
            if not isinstance(members, dict):
                continue
            roles[str(group_id)] = {str(user_id): str(role) for user_id, role in members.items()}
        return roles

    def _save_group_roles(self) -> None:
        self._group_roles_path.write_text(json.dumps(self._group_roles, ensure_ascii=True, indent=2), encoding="utf-8")

    def _load_memberships(self) -> dict[str, dict[str, dict[str, dict[str, str]]]]:
        if not self._memberships_path.exists():
            return {"groups": {}, "projects": {}}
        try:
            raw = json.loads(self._memberships_path.read_text(encoding="utf-8"))
        except Exception:
            return {"groups": {}, "projects": {}}
        if not isinstance(raw, dict):
            return {"groups": {}, "projects": {}}
        groups = raw.get("groups", {}) if isinstance(raw.get("groups", {}), dict) else {}
        projects = raw.get("projects", {}) if isinstance(raw.get("projects", {}), dict) else {}
        return {"groups": groups, "projects": projects}

    def _save_memberships(self) -> None:
        self._memberships_path.write_text(json.dumps(self._memberships, ensure_ascii=True, indent=2), encoding="utf-8")

    def list_runs(self) -> list[RunRecord]:
        return list(self._runs.values())

    def list_threads(self, *, include_archived: bool = True) -> list[ThreadRecord]:
        items = self._threads.values()
        if not include_archived:
            items = [item for item in items if not item.archived]
        return sorted(items, key=lambda item: item.updated_at or item.created_at, reverse=True)

    def get_thread(self, thread_id: str) -> ThreadRecord | None:
        return self._threads.get(thread_id)

    def create_thread(
        self,
        *,
        title: str,
        created_at: str,
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
        initial_message: dict[str, Any] | None = None,
    ) -> ThreadRecord:
        thread_id = f"thread-{uuid4().hex}"
        chat: list[ThreadMessageRecord] = []
        if initial_message is not None:
            chat.append(
                ThreadMessageRecord(
                    role=str(initial_message.get("role", "system")),
                    content=str(initial_message.get("content", "")),
                    created_at=str(initial_message.get("created_at", created_at)),
                )
            )
        record = ThreadRecord(
            thread_id=thread_id,
            title=title,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
            chat=chat,
            snapshot={},
            archived=False,
            created_at=created_at,
            updated_at=created_at,
        )
        self._threads[thread_id] = record
        self._save_threads()
        return record

    def update_thread(
        self,
        thread_id: str,
        *,
        title: str | None = None,
        run_id: str | None = None,
        snapshot: dict[str, Any] | None = None,
        archived: bool | None = None,
        user_id: str | None = None,
        project_id: str | None = None,
        group_id: str | None = None,
        group_role: str | None = None,
        updated_at: str,
    ) -> ThreadRecord | None:
        record = self._threads.get(thread_id)
        if record is None:
            return None
        if title is not None:
            record.title = title
        if run_id is not None:
            record.run_id = run_id
        if user_id is not None:
            record.user_id = user_id
        if project_id is not None:
            record.project_id = project_id
        if group_id is not None:
            record.group_id = group_id
        if group_role is not None:
            record.group_role = group_role
        if snapshot is not None:
            record.snapshot = snapshot
        if archived is not None:
            record.archived = archived
        record.updated_at = updated_at
        self._save_threads()
        return record

    def delete_thread(self, thread_id: str) -> bool:
        if thread_id not in self._threads:
            return False
        self._threads.pop(thread_id, None)
        self._save_threads()
        return True

    def append_thread_message(self, thread_id: str, *, role: str, content: str, created_at: str) -> ThreadRecord | None:
        record = self._threads.get(thread_id)
        if record is None:
            return None
        record.chat.append(ThreadMessageRecord(role=role, content=content, created_at=created_at))
        record.updated_at = created_at
        self._save_threads()
        return record

    def get_run(self, run_id: str) -> RunRecord | None:
        return self._runs.get(run_id)

    @staticmethod
    def _graph_item_matches_search(item: dict[str, Any], search_terms: set[str]) -> bool:
        if not search_terms:
            return True
        haystack = json.dumps(item, ensure_ascii=False).lower()
        return all(term in haystack for term in search_terms)

    def query_typed_research_graph(
        self,
        *,
        discipline: str = "",
        project_id: str,
        topic: str = "",
        group_id: str = "",
        user_id: str = "",
        node_type: str = "",
        relation: str = "",
        search: str = "",
        limit: int = 100,
        source_node_id: str = "",
        target_node_id: str = "",
        specialist_name: str = "",
        include_consulted_only: bool = False,
    ) -> dict[str, Any]:
        layout = self._layout_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        return ResearchGraphRegistry(layout.state_root / "graph").query(
            project_id=project_id,
            topic=topic,
            node_type=node_type,
            relation=relation,
            search=search,
            limit=limit,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            specialist_name=specialist_name,
            include_consulted_only=include_consulted_only,
        )

    def list_research_events(
        self,
        *,
        discipline: str = "",
        project_id: str = "",
        group_id: str = "",
        user_id: str = "",
        topic: str = "",
        event_type: str = "",
        limit: int = 100,
    ) -> dict[str, Any]:
        ledger = self._event_ledger_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        return {
            "results": ledger.load(
                project_id=project_id,
                topic=topic,
                event_type=event_type,
                limit=limit,
            )
        }

    def summarize_research_events(
        self,
        *,
        discipline: str = "",
        project_id: str = "",
        group_id: str = "",
        user_id: str = "",
        topic: str = "",
    ) -> dict[str, Any]:
        ledger = self._event_ledger_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        return ledger.summarize(project_id=project_id, topic=topic)

    def ingest_literature_source(
        self,
        *,
        source_type: str,
        title: str,
        content: str,
        filename: str | None = None,
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        target_scope: str = "project",
        user_mode: str = "auto",
        impact_level: str = "medium",
        conflict_level: str = "low",
        confidence: str = "medium",
        group_role: str = "",
    ) -> dict[str, Any]:
        bucket = {
            "paper": "papers",
            "papers": "papers",
            "report": "reports",
            "reports": "reports",
            "web": "web",
            "article": "web",
        }.get(source_type.strip().lower(), "web")
        literature_root = self._layout_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        ).literature_root
        safe_name = filename or f"{self._slugify(title)}.md"
        policy = decide_literature_ingest_policy(
            source_type=source_type,
            title=title,
            target_scope=target_scope,
            user_mode=user_mode,
            impact_level=impact_level,
            conflict_level=conflict_level,
            confidence=confidence,
            group_role=group_role,
        )
        if policy.mode == "autonomous":
            target_dir = literature_root / "raw_sources" / bucket
            target = target_dir / safe_name
            relative_target = f"raw_sources/{bucket}/{safe_name}"
            artifact_text = content
        elif policy.mode == "guided":
            target_dir = literature_root / "ingest_drafts"
            target = target_dir / safe_name
            relative_target = f"ingest_drafts/{safe_name}"
            artifact_text = render_literature_ingest_digest(
                title=title,
                source_type=source_type,
                content=content,
                policy=policy,
            )
        else:
            target_dir = literature_root / "ingest_proposals"
            target = target_dir / safe_name
            relative_target = f"ingest_proposals/{safe_name}"
            artifact_text = render_literature_ingest_digest(
                title=title,
                source_type=source_type,
                content=content,
                policy=policy,
            )
        target_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(artifact_text, encoding="utf-8")
        log_path = literature_root / "wiki" / "log.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entry = "\n".join(
            [
                "",
                f"## [{timestamp}] ingest-api | {title}",
                "",
                f"- Mode: `{policy.mode}`.",
                f"- Target: `{relative_target}`.",
                f"- Requires confirmation: `{str(policy.requires_confirmation).lower()}`.",
                f"- Needs review: `{str(policy.needs_review).lower()}`.",
            ]
        )
        existing = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Literature Log\n"
        log_path.write_text(existing.rstrip() + entry + "\n", encoding="utf-8")
        return {
            "saved": True,
            "path": str(target),
            "bucket": bucket,
            "mode": policy.mode,
            "requires_confirmation": policy.requires_confirmation,
            "needs_review": policy.needs_review,
            "policy": policy.to_dict(),
        }

    def query_literature_wiki(
        self,
        *,
        query: str,
        limit: int = 10,
        sections: list[str] | None = None,
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
    ) -> dict[str, Any]:
        wiki_root = self._layout_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        ).literature_root / "wiki"
        wanted_sections = sections or [
            "papers",
            "concepts",
            "mechanisms",
            "controversies",
            "methods",
            "datasets",
            "reviews",
        ]
        query_text = query.strip().lower()
        results: list[dict[str, Any]] = []
        for section in wanted_sections:
            directory = wiki_root / section
            if not directory.exists():
                continue
            for path in sorted(directory.glob("*.md")):
                if path.name.upper() == "TEMPLATE.MD":
                    continue
                text = path.read_text(encoding="utf-8")
                lowered = text.lower()
                if query_text not in lowered:
                    continue
                results.append(
                    {
                        "path": str(path),
                        "section": section,
                        "score": lowered.count(query_text),
                        "title": self._first_heading_or_title(text, fallback=path.stem),
                        "summary": self._first_bullet(text),
                    }
                )
        results.sort(key=lambda item: (-int(item.get("score", 0)), str(item.get("title", ""))))
        return {"results": results[: max(1, min(limit, 50))]}

    def lint_literature_workspace(
        self,
        *,
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
    ) -> dict[str, Any]:
        literature_root = self._layout_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        ).literature_root
        wiki_root = literature_root / "wiki"
        findings: list[str] = []
        index_path = wiki_root / "index.md"
        index_text = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
        for section in ["papers", "concepts", "mechanisms", "controversies", "methods", "datasets", "reviews"]:
            directory = wiki_root / section
            pages = [p for p in directory.glob("*.md") if p.name.upper() != "TEMPLATE.MD"] if directory.exists() else []
            if not pages:
                findings.append(f"No pages found in {section}/")
                continue
            for page in pages:
                relative = page.relative_to(wiki_root).as_posix()
                if relative not in index_text:
                    findings.append(f"Index missing page link: {relative}")
        lint_path = wiki_root / "lint.md"
        lint_path.parent.mkdir(parents=True, exist_ok=True)
        lint_path.write_text(
            "\n".join(
                [
                    "# Literature Lint",
                    "",
                    *([f"- {item}" for item in findings] if findings else ["- No major issues detected."]),
                ]
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        return {"findings": findings, "lint_path": str(lint_path)}

    @staticmethod
    def _first_heading_or_title(text: str, *, fallback: str) -> str:
        for line in text.splitlines():
            if line.startswith("title:"):
                return line.split(":", 1)[1].strip().strip('"')
            if line.startswith("# "):
                return line[2:].strip()
        return fallback

    @staticmethod
    def _first_bullet(text: str) -> str:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("- ") and len(stripped) > 2:
                return stripped[2:180]
        return ""

    @staticmethod
    def _slugify(value: str) -> str:
        safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
        while "--" in safe:
            safe = safe.replace("--", "-")
        return safe.strip("-") or "literature-item"

    def _experiment_record_accessible(
        self,
        record: dict[str, Any],
        *,
        requester_user_id: str = "",
        requester_project_id: str = "",
        requester_group_id: str = "",
        requester_group_role: str = "",
    ) -> bool:
        return self.can_access_scoped_resource(
            owner_user_id=str(record.get("user_id", "")),
            project_id=str(record.get("project_id", "")),
            group_id=str(record.get("group_id", "")),
            requester_user_id=requester_user_id,
            requester_project_id=requester_project_id,
            requester_group_id=requester_group_id,
            requester_group_role=requester_group_role,
        )

    def _list_experiment_collection(
        self,
        collection: str,
        *,
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
        experiment_id: str = "",
    ) -> list[dict[str, Any]]:
        registry = self._experiment_registry_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        items = registry.load_collection(collection)
        results: list[dict[str, Any]] = []
        for item in items:
            if experiment_id and str(item.get("experiment_id", "")) != experiment_id:
                continue
            if not self._experiment_record_accessible(
                item,
                requester_user_id=user_id,
                requester_project_id=project_id,
                requester_group_id=group_id,
                requester_group_role=group_role,
            ):
                continue
            results.append(item)
        return results

    def _get_experiment_record(
        self,
        collection: str,
        identifier: str,
        *,
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
    ) -> dict[str, Any] | None:
        registry = self._experiment_registry_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        item = registry.get_record(collection, identifier)
        if item is None:
            return None
        if not self._experiment_record_accessible(
            item,
            requester_user_id=user_id,
            requester_project_id=project_id,
            requester_group_id=group_id,
            requester_group_role=group_role,
        ):
            return None
        return item

    def _save_experiment_record(
        self,
        collection: str,
        identifier: str,
        payload: dict[str, Any],
        *,
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
    ) -> dict[str, Any]:
        scoped = {
            **payload,
            "user_id": user_id,
            "discipline": discipline or str(payload.get("discipline", "")),
            "project_id": project_id or str(payload.get("project_id", "")),
            "group_id": group_id,
            "group_role": group_role,
        }
        if not self.can_modify_scoped_resource(
            owner_user_id=user_id,
            project_id=str(scoped.get("project_id", "")),
            group_id=group_id,
            requester_user_id=user_id,
            requester_project_id=project_id,
            requester_group_id=group_id,
            requester_group_role=group_role,
        ):
            raise PermissionError("Experiment record write denied")
        registry = self._experiment_registry_for_scope(
            discipline=str(scoped.get("discipline", "")),
            project_id=str(scoped.get("project_id", "")),
            group_id=group_id,
            user_id=user_id,
        )
        existing = registry.get_record(collection, identifier)
        if collection == "experiment_specifications":
            self._validate_experiment_specification_payload(scoped, existing)
        elif collection == "experimental_protocols":
            self._validate_experimental_protocol_payload(scoped, existing)
        elif collection == "experiment_runs":
            self._validate_experiment_run_payload(scoped, existing, registry=registry)
        registry.save_record(collection, identifier, scoped)
        saved = registry.get_record(collection, identifier)
        return saved or scoped

    def list_experiment_specifications(
        self,
        *,
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
    ) -> list[dict[str, Any]]:
        return self._list_experiment_collection(
            "experiment_specifications",
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
        )

    def get_experiment_specification(self, experiment_id: str, **identity: str) -> dict[str, Any] | None:
        return self._get_experiment_record("experiment_specifications", experiment_id, **identity)

    def save_experiment_specification(self, payload: dict[str, Any], **identity: str) -> dict[str, Any]:
        return self._save_experiment_record(
            "experiment_specifications",
            str(payload["experiment_id"]),
            payload,
            **identity,
        )

    def list_experimental_protocols(
        self,
        *,
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
        experiment_id: str = "",
    ) -> list[dict[str, Any]]:
        return self._list_experiment_collection(
            "experimental_protocols",
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
            experiment_id=experiment_id,
        )

    def get_experimental_protocol(self, protocol_id: str, **identity: str) -> dict[str, Any] | None:
        return self._get_experiment_record("experimental_protocols", protocol_id, **identity)

    def save_experimental_protocol(self, payload: dict[str, Any], **identity: str) -> dict[str, Any]:
        return self._save_experiment_record(
            "experimental_protocols",
            str(payload["protocol_id"]),
            payload,
            **identity,
        )

    def amend_experimental_protocol(
        self,
        *,
        source_protocol_id: str,
        payload: dict[str, Any],
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
    ) -> dict[str, Any]:
        source = self.get_experimental_protocol(
            source_protocol_id,
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
        )
        if source is None:
            raise FileNotFoundError("Source protocol not found")
        amended = {
            **source,
            **payload,
            "lineage_parent_protocol_id": source_protocol_id,
            "experiment_id": str(payload.get("experiment_id", source.get("experiment_id", ""))),
            "version": str(payload.get("version", source.get("version", ""))),
            "amendment_reason": str(payload.get("amendment_reason", "")).strip(),
        }
        saved = self.save_experimental_protocol(
            amended,
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
        )
        frozen_source = {
            **source,
            "is_frozen": True,
            "freeze_reason": f"superseded by protocol {saved.get('protocol_id', '')}",
            "frozen_at": datetime.now(timezone.utc).isoformat(),
        }
        self._experiment_registry_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        ).save_record(
            "experimental_protocols",
            str(source_protocol_id),
            frozen_source,
        )
        return saved

    def freeze_experiment_specification(
        self,
        *,
        experiment_id: str,
        reason: str = "",
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
    ) -> dict[str, Any]:
        if self._role_rank(group_role) < self._role_rank("curator"):
            raise PermissionError("Only curator/admin can freeze experiment specifications")
        record = self.get_experiment_specification(
            experiment_id,
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
        )
        if record is None:
            raise FileNotFoundError("Experiment specification not found")
        updated = {
            **record,
            "is_frozen": True,
            "freeze_reason": str(reason).strip() or "manual freeze",
            "frozen_at": datetime.now(timezone.utc).isoformat(),
        }
        self._experiment_registry_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        ).save_record("experiment_specifications", experiment_id, updated)
        return self.get_experiment_specification(
            experiment_id,
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
        ) or updated

    def unfreeze_experiment_specification(
        self,
        *,
        experiment_id: str,
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
    ) -> dict[str, Any]:
        if self._role_rank(group_role) < self._role_rank("curator"):
            raise PermissionError("Only curator/admin can unfreeze experiment specifications")
        record = self.get_experiment_specification(
            experiment_id,
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
        )
        if record is None:
            raise FileNotFoundError("Experiment specification not found")
        updated = {
            **record,
            "is_frozen": False,
            "freeze_reason": "",
            "frozen_at": "",
        }
        self._experiment_registry_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        ).save_record("experiment_specifications", experiment_id, updated)
        return self.get_experiment_specification(
            experiment_id,
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
        ) or updated

    def retire_experiment_specification(
        self,
        *,
        experiment_id: str,
        reason: str = "",
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
    ) -> dict[str, Any]:
        if self._role_rank(group_role) < self._role_rank("curator"):
            raise PermissionError("Only curator/admin can retire experiment specifications")
        record = self.get_experiment_specification(
            experiment_id,
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
        )
        if record is None:
            raise FileNotFoundError("Experiment specification not found")
        thawed = {**record, "is_frozen": False}
        updated = {
            **thawed,
            "status": "retired",
            "retire_reason": str(reason).strip() or "manual retirement",
            "retired_at": datetime.now(timezone.utc).isoformat(),
        }
        return self.save_experiment_specification(
            updated,
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
        )

    def freeze_experimental_protocol(
        self,
        *,
        protocol_id: str,
        reason: str = "",
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
    ) -> dict[str, Any]:
        if self._role_rank(group_role) < self._role_rank("curator"):
            raise PermissionError("Only curator/admin can freeze experimental protocols")
        record = self.get_experimental_protocol(
            protocol_id,
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
        )
        if record is None:
            raise FileNotFoundError("Experimental protocol not found")
        updated = {
            **record,
            "is_frozen": True,
            "freeze_reason": str(reason).strip() or "manual freeze",
            "frozen_at": datetime.now(timezone.utc).isoformat(),
        }
        self._experiment_registry_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        ).save_record("experimental_protocols", protocol_id, updated)
        return self.get_experimental_protocol(
            protocol_id,
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
        ) or updated

    def unfreeze_experimental_protocol(
        self,
        *,
        protocol_id: str,
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
    ) -> dict[str, Any]:
        if self._role_rank(group_role) < self._role_rank("curator"):
            raise PermissionError("Only curator/admin can unfreeze experimental protocols")
        record = self.get_experimental_protocol(
            protocol_id,
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
        )
        if record is None:
            raise FileNotFoundError("Experimental protocol not found")
        updated = {
            **record,
            "is_frozen": False,
            "freeze_reason": "",
            "frozen_at": "",
        }
        self._experiment_registry_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        ).save_record("experimental_protocols", protocol_id, updated)
        return self.get_experimental_protocol(
            protocol_id,
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
        ) or updated

    def list_experiment_runs(
        self,
        *,
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
        experiment_id: str = "",
    ) -> list[dict[str, Any]]:
        return self._list_experiment_collection(
            "experiment_runs",
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
            experiment_id=experiment_id,
        )

    def get_experiment_run_record(self, run_id: str, **identity: str) -> dict[str, Any] | None:
        return self._get_experiment_record("experiment_runs", run_id, **identity)

    def save_experiment_run_record(self, payload: dict[str, Any], **identity: str) -> dict[str, Any]:
        return self._save_experiment_record(
            "experiment_runs",
            str(payload["run_id"]),
            payload,
            **identity,
        )

    def submit_run_handoff(
        self,
        *,
        topic: str,
        contract: dict[str, Any],
        payload: dict[str, Any],
        claim_graph: dict[str, Any] | None = None,
        write_memory: bool = True,
        write_events: bool = True,
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
    ) -> dict[str, Any]:
        experiment_id = str(contract.get("experiment_id", "")).strip()
        if not self.can_modify_scoped_resource(
            owner_user_id="",
            project_id=project_id,
            group_id=group_id,
            requester_user_id=user_id,
            requester_project_id=project_id,
            requester_group_id=group_id,
            requester_group_role=group_role,
        ):
            raise PermissionError("Run handoff submission denied")
        layout = self._layout_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        experiment_registry = ExperimentRegistry(layout.state_root / "service" / "experiments")
        bundle = normalize_run_handoff_payload(contract=contract, payload=payload)
        backpropagation = persist_run_handoff_bundle(
            registry=experiment_registry,
            bundle=bundle,
        )
        updated_claim_graph = (
            apply_backpropagation_to_claim_graph(
                claim_graph=claim_graph or {},
                backpropagation_record=backpropagation,
            )
            if claim_graph is not None
            else {}
        )
        memory_results: list[dict[str, Any]] = []
        if write_memory:
            for item in build_backpropagation_memory_items(
                backpropagation_record=backpropagation,
                topic=topic,
                project_id=project_id,
                user_id=user_id,
                group_id=group_id,
            ):
                payload_for_memory = dict(item)
                payload_for_memory["memory_type"] = payload_for_memory.pop(
                    "kind",
                    payload_for_memory.get("memory_type", "reference"),
                )
                payload_for_memory["discipline"] = discipline
                payload_for_memory["group_role"] = group_role
                memory_results.append(self.save_memory(payload_for_memory))
        events_written = 0
        if write_events:
            events = build_backpropagation_events(
                topic=topic,
                project_id=project_id,
                user_id=user_id,
                group_id=group_id,
                backpropagation_record=backpropagation,
            )
            ResearchEventLedger(layout.state_root / "events").append_many(events)
            events_written = len(events)
        registry_summary = load_experiment_backpropagation_summary(
            registry_root=layout.state_root / "service" / "experiments"
        )
        registry_summary["experiment_id"] = experiment_id
        return {
            "ok": bundle.get("validation_state") == "valid",
            "bundle": bundle,
            "backpropagation": backpropagation,
            "updated_claim_graph": updated_claim_graph,
            "memory_results": memory_results,
            "events_written": events_written,
            "registry_summary": registry_summary,
        }

    def approve_experiment_run(
        self,
        *,
        run_id: str,
        approved_by: str,
        approval_note: str = "",
        approval_status: str = "approved",
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
    ) -> dict[str, Any]:
        if self._role_rank(group_role) < self._role_rank("curator"):
            raise PermissionError("Only curator/admin can approve experiment runs")
        record = self.get_experiment_run_record(
            run_id,
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
        )
        if record is None:
            raise FileNotFoundError("Experiment run not found")
        protocol_id = str(record.get("protocol_id", "")).strip()
        if protocol_id and self._protocol_has_newer_amendment(
            protocol_id,
            registry=self._experiment_registry_for_scope(
                discipline=discipline,
                project_id=project_id,
                group_id=group_id,
                user_id=user_id,
            ),
        ):
            raise ValueError("Cannot approve a run built on a superseded protocol")
        current_status = str(record.get("status", "planned")).strip() or "planned"
        if current_status in {"quality_control_failed", "archived", "analyzed"}:
            raise ValueError(f"Run in status `{current_status}` cannot be approved")
        updated = {
            **record,
            "approval_status": approval_status,
            "approved_by": approved_by,
            "approval_note": approval_note,
            "governance_stage": "approved_for_execution" if approval_status == "approved" else "approval_blocked",
            "paused_reason": "" if approval_status == "approved" else str(approval_note or record.get("paused_reason", "")),
        }
        if approval_status == "approved" and str(updated.get("status", "")).strip() == "planned":
            updated["status"] = "approved"
        return self.save_experiment_run_record(
            updated,
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
        )

    def retire_experiment_run(
        self,
        *,
        run_id: str,
        reason: str = "",
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
    ) -> dict[str, Any]:
        if self._role_rank(group_role) < self._role_rank("curator"):
            raise PermissionError("Only curator/admin can retire experiment runs")
        record = self.get_experiment_run_record(
            run_id,
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
        )
        if record is None:
            raise FileNotFoundError("Experiment run not found")
        updated = {
            **record,
            "status": "archived",
            "governance_stage": "retired",
            "paused_reason": str(reason).strip() or "manual retirement",
            "retired_at": datetime.now(timezone.utc).isoformat(),
        }
        return self.save_experiment_run_record(
            updated,
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
        )

    def get_experiment_lineage(
        self,
        *,
        experiment_id: str,
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
    ) -> dict[str, Any]:
        specifications = [
            item
            for item in self.list_experiment_specifications(
                discipline=discipline,
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                group_role=group_role,
            )
            if str(item.get("experiment_id", "")).strip() == experiment_id
        ]
        protocols = self.list_experimental_protocols(
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
            experiment_id=experiment_id,
        )
        runs = self.list_experiment_runs(
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
            experiment_id=experiment_id,
        )
        return {
            "experiment_id": experiment_id,
            "specifications": specifications,
            "protocols": protocols,
            "runs": runs,
            "protocol_lineage": [
                {
                    "protocol_id": str(item.get("protocol_id", "")),
                    "parent_protocol_id": str(item.get("lineage_parent_protocol_id", "")),
                    "version": str(item.get("version", "")),
                    "amendment_reason": str(item.get("amendment_reason", "")),
                }
                for item in protocols
            ],
            "run_lineage": [
                {
                    "run_id": str(item.get("run_id", "")),
                    "supersedes_run_id": str(item.get("supersedes_run_id", "")),
                    "approval_status": str(item.get("approval_status", "")),
                    "governance_stage": str(item.get("governance_stage", "")),
                }
                for item in runs
            ],
        }

    def save_evaluation_record(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        discipline = str(payload.get("discipline", "")).strip()
        project_id = str(payload.get("project_id", "")).strip()
        group_id = str(payload.get("group_id", "")).strip()
        user_id = str(payload.get("user_id", "")).strip()
        topic = str(payload.get("topic", "")).strip()
        registry = self._experiment_registry_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        previous_candidates = self.list_evaluation_records(
            discipline=discipline,
            project_id=project_id,
            topic=topic,
            group_id=group_id,
            user_id=user_id,
        )
        previous = previous_candidates[-1] if previous_candidates else None
        enriched = {
            **payload,
            "created_at": payload.get("created_at") or datetime.now(timezone.utc).isoformat(),
            "comparison_to_previous": self._compare_evaluation_records(
                payload,
                previous if isinstance(previous, dict) else None,
            ),
        }
        registry.save_record("evaluation_records", run_id, enriched)
        saved = registry.get_record("evaluation_records", run_id)
        return saved or enriched

    def get_evaluation_record(
        self,
        run_id: str,
        *,
        discipline: str = "",
        project_id: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> dict[str, Any] | None:
        return self._experiment_registry_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        ).get_record("evaluation_records", run_id)

    def list_evaluation_records(
        self,
        *,
        discipline: str = "",
        project_id: str = "",
        group_id: str = "",
        user_id: str = "",
        topic: str = "",
    ) -> list[dict[str, Any]]:
        items = self._experiment_registry_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        ).load_collection("evaluation_records")
        filtered: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if project_id and str(item.get("project_id", "")).strip() != project_id:
                continue
            if topic and str(item.get("topic", "")).strip() != topic:
                continue
            filtered.append(item)
        filtered.sort(key=lambda item: str(item.get("created_at", "")))
        return filtered

    def build_evaluation_history_signal(
        self,
        *,
        discipline: str = "",
        project_id: str,
        group_id: str = "",
        user_id: str = "",
        topic: str,
    ) -> dict[str, Any]:
        if not project_id or not topic:
            return {}
        history = self.list_evaluation_records(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
            topic=topic,
        )
        if not history:
            return {}
        latest = history[-1]
        latest_comparison = (
            latest.get("comparison_to_previous", {})
            if isinstance(latest.get("comparison_to_previous", {}), dict)
            else {}
        )
        regressing_streak = 0
        for item in reversed(history):
            comparison = (
                item.get("comparison_to_previous", {})
                if isinstance(item.get("comparison_to_previous", {}), dict)
                else {}
            )
            if str(comparison.get("trend", "")).strip() == "regressing":
                regressing_streak += 1
            else:
                break
        evaluation_summary = (
            latest.get("evaluation_summary", {})
            if isinstance(latest.get("evaluation_summary", {}), dict)
            else {}
        )
        return {
            "history_count": len(history),
            "latest_run_id": str(latest.get("run_id", "")).strip(),
            "latest_trend": str(latest_comparison.get("trend", "baseline")).strip() or "baseline",
            "latest_benchmark_readiness": str(
                latest_comparison.get(
                    "current_benchmark_readiness",
                    evaluation_summary.get("benchmark_readiness", ""),
                )
            ).strip(),
            "blocker_delta": int(latest_comparison.get("blocker_delta", 0) or 0),
            "regressing_streak": regressing_streak,
        }

    @staticmethod
    def _compare_evaluation_records(
        current: dict[str, Any],
        previous: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if previous is None:
            return {"has_previous": False, "trend": "baseline"}
        current_summary = (
            current.get("evaluation_summary", {})
            if isinstance(current.get("evaluation_summary", {}), dict)
            else {}
        )
        previous_summary = (
            previous.get("evaluation_summary", {})
            if isinstance(previous.get("evaluation_summary", {}), dict)
            else {}
        )
        current_termination = (
            current.get("termination_strategy_summary", {})
            if isinstance(current.get("termination_strategy_summary", {}), dict)
            else {}
        )
        previous_termination = (
            previous.get("termination_strategy_summary", {})
            if isinstance(previous.get("termination_strategy_summary", {}), dict)
            else {}
        )
        readiness_order = {"low": 0, "medium": 1, "high": 2}
        current_readiness = str(current_summary.get("benchmark_readiness", "low")).strip()
        previous_readiness = str(previous_summary.get("benchmark_readiness", "low")).strip()
        current_blockers = len(current_termination.get("human_confirmation_reasons", []))
        previous_blockers = len(previous_termination.get("human_confirmation_reasons", []))
        trend = "stable"
        if readiness_order.get(current_readiness, 0) > readiness_order.get(previous_readiness, 0):
            trend = "improving"
        elif readiness_order.get(current_readiness, 0) < readiness_order.get(previous_readiness, 0):
            trend = "regressing"
        elif current_blockers > previous_blockers:
            trend = "regressing"
        return {
            "has_previous": True,
            "trend": trend,
            "previous_run_id": str(previous.get("run_id", "")),
            "previous_benchmark_readiness": previous_readiness,
            "current_benchmark_readiness": current_readiness,
            "blocker_delta": current_blockers - previous_blockers,
        }

    def list_quality_control_reviews(
        self,
        *,
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
        experiment_id: str = "",
    ) -> list[dict[str, Any]]:
        return self._list_experiment_collection(
            "quality_control_reviews",
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
            experiment_id=experiment_id,
        )

    def get_quality_control_review_record(self, review_id: str, **identity: str) -> dict[str, Any] | None:
        return self._get_experiment_record("quality_control_reviews", review_id, **identity)

    def save_quality_control_review_record(self, payload: dict[str, Any], **identity: str) -> dict[str, Any]:
        return self._save_experiment_record(
            "quality_control_reviews",
            str(payload["review_id"]),
            payload,
            **identity,
        )

    def list_interpretation_records(
        self,
        *,
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
        experiment_id: str = "",
    ) -> list[dict[str, Any]]:
        return self._list_experiment_collection(
            "interpretation_records",
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
            experiment_id=experiment_id,
        )

    def get_interpretation_record(self, interpretation_id: str, **identity: str) -> dict[str, Any] | None:
        return self._get_experiment_record("interpretation_records", interpretation_id, **identity)

    def save_interpretation_record(self, payload: dict[str, Any], **identity: str) -> dict[str, Any]:
        return self._save_experiment_record(
            "interpretation_records",
            str(payload["interpretation_id"]),
            payload,
            **identity,
        )

    def get_claim_graph(self, run_id: str) -> dict[str, Any]:
        record = self._runs.get(run_id)
        if record is None or record.result is None:
            return {}
        return record.result.claim_graph

    def get_group_role(self, *, group_id: str, user_id: str, claimed_role: str = "") -> str:
        if not group_id or not user_id:
            return claimed_role or ""
        stored = self._group_roles.get(group_id, {}).get(user_id, "")
        return stored or claimed_role or ""

    def set_group_role(self, *, group_id: str, user_id: str, role: str) -> dict[str, str]:
        self._group_roles.setdefault(group_id, {})[user_id] = role
        self._save_group_roles()
        return {"group_id": group_id, "user_id": user_id, "role": role}

    def upsert_group_member(self, *, group_id: str, user_id: str, role: str, display_name: str = "") -> dict[str, str]:
        self._memberships.setdefault("groups", {}).setdefault(group_id, {})[user_id] = {
            "role": role,
            "display_name": display_name,
        }
        self._group_roles.setdefault(group_id, {})[user_id] = role
        self._save_memberships()
        self._save_group_roles()
        return {"user_id": user_id, "role": role, "display_name": display_name}

    def list_group_members(self, *, group_id: str) -> list[dict[str, str]]:
        members = self._memberships.get("groups", {}).get(group_id, {})
        return [
            {
                "user_id": user_id,
                "role": str(info.get("role", "")),
                "display_name": str(info.get("display_name", "")),
            }
            for user_id, info in members.items()
            if isinstance(info, dict)
        ]

    def upsert_project_member(self, *, project_id: str, user_id: str, role: str, display_name: str = "") -> dict[str, str]:
        self._memberships.setdefault("projects", {}).setdefault(project_id, {})[user_id] = {
            "role": role,
            "display_name": display_name,
        }
        self._save_memberships()
        return {"user_id": user_id, "role": role, "display_name": display_name}

    def list_project_members(self, *, project_id: str) -> list[dict[str, str]]:
        members = self._memberships.get("projects", {}).get(project_id, {})
        return [
            {
                "user_id": user_id,
                "role": str(info.get("role", "")),
                "display_name": str(info.get("display_name", "")),
            }
            for user_id, info in members.items()
            if isinstance(info, dict)
        ]

    @staticmethod
    def _role_rank(role: str) -> int:
        return {"viewer": 0, "contributor": 1, "curator": 2, "admin": 3}.get(role, -1)

    def get_project_role(self, *, project_id: str, user_id: str) -> str:
        if not project_id or not user_id:
            return ""
        project = self._memberships.get("projects", {}).get(project_id, {})
        info = project.get(user_id, {}) if isinstance(project, dict) else {}
        if not isinstance(info, dict):
            return ""
        return str(info.get("role", ""))

    def _is_group_member(self, *, group_id: str, user_id: str, claimed_role: str = "") -> bool:
        return bool(self.get_group_role(group_id=group_id, user_id=user_id, claimed_role=claimed_role))

    def _is_project_member(self, *, project_id: str, user_id: str) -> bool:
        return bool(self.get_project_role(project_id=project_id, user_id=user_id))

    def can_access_scoped_resource(
        self,
        *,
        owner_user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        requester_user_id: str = "",
        requester_project_id: str = "",
        requester_group_id: str = "",
        requester_group_role: str = "",
    ) -> bool:
        if not owner_user_id and not project_id and not group_id:
            return True
        if requester_user_id and owner_user_id and requester_user_id == owner_user_id:
            return True
        if project_id:
            if requester_project_id and requester_project_id == project_id:
                return True
            if requester_user_id and self._is_project_member(project_id=project_id, user_id=requester_user_id):
                return True
        if group_id:
            if requester_group_id and requester_group_id == group_id:
                return True
            if requester_user_id and self._is_group_member(
                group_id=group_id,
                user_id=requester_user_id,
                claimed_role=requester_group_role,
            ):
                return True
        return False

    def can_modify_scoped_resource(
        self,
        *,
        owner_user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        requester_user_id: str = "",
        requester_project_id: str = "",
        requester_group_id: str = "",
        requester_group_role: str = "",
    ) -> bool:
        if requester_user_id and owner_user_id and requester_user_id == owner_user_id:
            return True
        project_role = self.get_project_role(project_id=project_id, user_id=requester_user_id) if requester_user_id else ""
        group_role = self.get_group_role(
            group_id=group_id,
            user_id=requester_user_id,
            claimed_role=requester_group_role,
        ) if requester_user_id else ""
        if project_id and self._role_rank(project_role) >= self._role_rank("contributor"):
            return True
        if group_id and self._role_rank(group_role) >= self._role_rank("contributor"):
            return True
        return not project_id and not group_id

    def _can_write_scope(self, scope: str, *, role: str) -> bool:
        if scope in {"personal", "project", "agent", "session"}:
            return True
        if scope == "group":
            return self._role_rank(role) >= self._role_rank("curator")
        if scope == "public":
            return self._role_rank(role) >= self._role_rank("admin")
        return False

    def _can_review_record(self, record: Any, *, role: str) -> bool:
        if record.scope in {"group", "public"}:
            return self._role_rank(role) >= self._role_rank("curator")
        return True

    @staticmethod
    def _extract_proposal_target(validated_by: list[str]) -> tuple[str, str]:
        for item in validated_by:
            if item.startswith("promotion-proposal:"):
                parts = item.split(":", 2)
                if len(parts) == 3:
                    return parts[1], parts[2]
        return "", ""

    def search_memory(
        self,
        query: str,
        max_results: int = 5,
        *,
        discipline: str = "",
        user_id: str | None = None,
        project_id: str | None = None,
        group_id: str | None = None,
        scopes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        manager = self._memory_manager_for_scope(
            discipline=discipline,
            project_id=project_id or "",
            group_id=group_id or "",
            user_id=user_id or "",
        )
        matches = manager.find_relevant_memories(
            query,
            max_memories=max_results,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            scopes=scopes,
        )
        return [
            {
                "path": str(item.path),
                "title": item.title,
                "summary": item.summary,
                "memory_type": item.kind,
                "scope": item.scope,
                "tags": item.tags,
                "source_refs": item.source_refs,
                "evidence_level": item.evidence_level,
                "confidence": item.confidence,
                "status": item.status,
                "user_id": item.user_id,
                "project_id": item.project_id,
                "group_id": item.group_id,
                "visibility": item.visibility,
                "promotion_status": item.promotion_status,
                "last_verified_at": item.last_verified_at,
                "needs_review": item.needs_review,
                "review_due_at": item.review_due_at,
                "derived_from": item.derived_from,
                "conflicts_with": item.conflicts_with,
                "validated_by": item.validated_by,
            }
            for item in matches
        ]

    def list_memory_proposals(
        self,
        *,
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
    ) -> list[dict[str, Any]]:
        role = self.get_group_role(group_id=group_id, user_id=user_id, claimed_role=group_role)
        if self._role_rank(role) < self._role_rank("curator"):
            return []
        manager = self._memory_manager_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        results: list[dict[str, Any]] = []
        for record in manager.list_memories(user_id=user_id, project_id=project_id, group_id=group_id):
            if not record.needs_review:
                continue
            target_scope, proposed_by = self._extract_proposal_target(record.validated_by)
            if not target_scope:
                continue
            results.append(
                {
                    "path": str(record.path),
                    "filename": record.path.name,
                    "title": record.title,
                    "summary": record.summary,
                    "source_scope": record.scope,
                    "target_scope": target_scope,
                    "user_id": record.user_id,
                    "project_id": record.project_id,
                    "group_id": record.group_id,
                    "visibility": record.visibility,
                    "proposed_by": proposed_by,
                    "validated_by": record.validated_by,
                    "needs_review": record.needs_review,
                }
            )
        return results

    def get_memory_audit(
        self,
        *,
        filename: str,
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
    ) -> dict[str, Any]:
        manager = self._memory_manager_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        record = manager.get_memory_record(filename)
        if record is None:
            return {"filename": filename, "events": []}
        role = self.get_group_role(group_id=group_id or record.group_id, user_id=user_id, claimed_role=group_role)
        if record.scope in {"group", "public"} and self._role_rank(role) < self._role_rank("contributor"):
            return {"filename": filename, "events": []}
        events: list[dict[str, Any]] = [
            {
                "kind": "created",
                "actor": record.user_id,
                "detail": f"Created in {record.scope} scope",
                "timestamp": record.created_at,
            }
        ]
        for item in record.validated_by:
            if item.startswith("promotion-proposal:"):
                parts = item.split(":", 2)
                if len(parts) == 3:
                    events.append(
                        {
                            "kind": "proposal",
                            "actor": parts[2],
                            "detail": f"Proposed promotion to {parts[1]}",
                            "timestamp": "",
                        }
                    )
            elif item.startswith("approved-by:"):
                parts = item.split(":", 3)
                if len(parts) == 4:
                    events.append(
                        {
                            "kind": "approved",
                            "actor": parts[1],
                            "detail": f"Approved into {parts[2]}",
                            "timestamp": parts[3],
                        }
                    )
            elif item.startswith("rejected-by:"):
                parts = item.split(":", 3)
                if len(parts) == 4:
                    events.append(
                        {
                            "kind": "rejected",
                            "actor": parts[1],
                            "detail": parts[2],
                            "timestamp": parts[3],
                        }
                    )
        return {
            "filename": filename,
            "title": record.title,
            "status": record.status,
            "scope": record.scope,
            "promotion_status": record.promotion_status,
            "needs_review": record.needs_review,
            "events": events,
        }

    def save_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        manager = self._memory_manager_for_scope(
            discipline=str(payload.get("discipline", "")),
            project_id=str(payload.get("project_id", "")),
            group_id=str(payload.get("group_id", "")),
            user_id=str(payload.get("user_id", "")),
        )
        role = self.get_group_role(
            group_id=payload.get("group_id", ""),
            user_id=payload.get("user_id", ""),
            claimed_role=payload.get("group_role", ""),
        )
        target_scope = payload.get("scope", "project")
        save_payload = dict(payload)
        mode = "saved"
        message = "Memory saved."
        if not self._can_write_scope(target_scope, role=role):
            fallback_scope = "project" if payload.get("project_id") else "personal"
            save_payload["scope"] = fallback_scope
            save_payload["visibility"] = "project" if fallback_scope == "project" else "private"
            save_payload["needs_review"] = True
            validated_by = list(save_payload.get("validated_by", []))
            validated_by.append(f"promotion-proposal:{target_scope}:{payload.get('user_id', 'unknown')}")
            save_payload["validated_by"] = validated_by
            mode = "proposed"
            message = f"Role `{role or 'unknown'}` cannot write {target_scope} memory directly. Saved as a proposal in {fallback_scope} scope."
        path = manager.save_memory(
            title=save_payload["title"],
            summary=save_payload["summary"],
            kind=save_payload["memory_type"],
            scope=save_payload["scope"],
            content=save_payload["content"],
            tags=save_payload.get("tags", []),
            filename=save_payload.get("filename"),
            source_refs=save_payload.get("source_refs", []),
            evidence_level=save_payload.get("evidence_level", "medium"),
            confidence=save_payload.get("confidence", "medium"),
            status=save_payload.get("status", "active"),
            owner_agent=save_payload.get("owner_agent", "service"),
            user_id=save_payload.get("user_id", ""),
            project_id=save_payload.get("project_id", ""),
            group_id=save_payload.get("group_id", ""),
            visibility=save_payload.get("visibility"),
            promotion_status=save_payload.get("promotion_status"),
            needs_review=save_payload.get("needs_review", False),
            review_due_at=save_payload.get("review_due_at"),
            supersedes=save_payload.get("supersedes", []),
            superseded_by=save_payload.get("superseded_by"),
            derived_from=save_payload.get("derived_from", []),
            conflicts_with=save_payload.get("conflicts_with", []),
            validated_by=save_payload.get("validated_by", []),
        )
        return {"path": str(path), "mode": mode, "message": message}

    def review_memory(self, payload: dict[str, Any]) -> bool:
        manager = self._memory_manager_for_scope(
            discipline=str(payload.get("discipline", "")),
            project_id=str(payload.get("project_id", "")),
            group_id=str(payload.get("group_id", "")),
            user_id=str(payload.get("user_id", "")),
        )
        record = manager.get_memory_record(payload["filename"])
        if record is None:
            return False
        role = self.get_group_role(
            group_id=payload.get("group_id", "") or record.group_id,
            user_id=payload.get("user_id", ""),
            claimed_role=payload.get("group_role", ""),
        )
        if not self._can_review_record(record, role=role):
            return False
        return manager.review_memory(
            payload["filename"],
            status=payload.get("status"),
            needs_review=payload.get("needs_review"),
            review_due_at=payload.get("review_due_at"),
            superseded_by=payload.get("superseded_by"),
            conflicts_with=payload.get("conflicts_with"),
            validated_by=payload.get("validated_by"),
            last_verified_at=payload.get("last_verified_at"),
            visibility=payload.get("visibility"),
            promotion_status=payload.get("promotion_status"),
        )

    def promote_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        manager = self._memory_manager_for_scope(
            discipline=str(payload.get("discipline", "")),
            project_id=str(payload.get("project_id", "")),
            group_id=str(payload.get("group_id", "")),
            user_id=str(payload.get("user_id", "")),
        )
        record = manager.get_memory_record(payload["filename"])
        if record is None:
            return {"ok": False, "mode": "missing", "message": "Memory file not found."}
        target_scope = str(payload.get("target_scope", "")).strip() or record.scope
        user_id = payload.get("user_id", "") or record.user_id
        project_id = payload.get("project_id", "") or record.project_id
        group_id = payload.get("group_id", "") or record.group_id
        role = self.get_group_role(
            group_id=group_id,
            user_id=user_id,
            claimed_role=payload.get("group_role", ""),
        )
        if not self._can_write_scope(target_scope, role=role):
            manager.review_memory(
                payload["filename"],
                needs_review=True,
                validated_by=[*record.validated_by, f"promotion-proposal:{target_scope}:{user_id or 'unknown'}"],
            )
            return {
                "ok": True,
                "mode": "proposed",
                "filename": payload["filename"],
                "message": f"Role `{role or 'unknown'}` cannot promote to {target_scope}. Saved as a promotion proposal for curator review.",
            }
        new_path = manager.promote_memory(
            payload["filename"],
            target_scope=target_scope,
            target_visibility=payload.get("target_visibility"),
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            approved_by=user_id,
        )
        if new_path is None:
            return {"ok": False, "mode": "failed", "message": "Promotion failed."}
        return {
            "ok": True,
            "mode": "promoted",
            "path": str(new_path),
            "filename": new_path.name,
            "message": f"Memory promoted to {target_scope}.",
        }

    def auto_govern_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        user_id = str(payload.get("user_id", "")).strip()
        project_id = str(payload.get("project_id", "")).strip()
        group_id = str(payload.get("group_id", "")).strip()
        discipline = str(payload.get("discipline", "")).strip()
        manager = self._memory_manager_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        target_scope = str(payload.get("target_scope", "project")).strip() or "project"
        automation_mode = str(payload.get("automation_mode", "safe")).strip() or "safe"
        max_items = int(payload.get("max_items", 25) or 25)
        role = self.get_group_role(
            group_id=group_id,
            user_id=user_id,
            claimed_role=payload.get("group_role", ""),
        )
        records = manager.list_memories(
            user_id=user_id or None,
            project_id=project_id or None,
            group_id=group_id or None,
        )
        plan = plan_memory_migrations(
            records=records,
            target_scope=target_scope,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            automation_mode=automation_mode,
            max_items=max_items,
        )
        results: list[dict[str, Any]] = []
        dry_run = automation_mode == "dry_run" or bool(payload.get("dry_run", False))
        for decision in plan:
            filename = str(decision.get("filename", "")).strip()
            action = str(decision.get("action", "")).strip()
            if not filename:
                continue
            record = manager.get_memory_record(filename)
            if record is None:
                results.append({**decision, "ok": False, "mode": "missing"})
                continue
            if action == "block":
                if not dry_run:
                    manager.review_memory(
                        filename,
                        needs_review=True,
                        validated_by=[
                            *record.validated_by,
                            migration_audit_tag(action="block", target_scope=target_scope, actor=user_id),
                        ],
                    )
                results.append({**decision, "ok": True, "mode": "blocked"})
                continue
            if action == "propose":
                if not dry_run:
                    manager.review_memory(
                        filename,
                        needs_review=True,
                        validated_by=[
                            *record.validated_by,
                            f"promotion-proposal:{target_scope}:{user_id or 'automation'}",
                            migration_audit_tag(action="propose", target_scope=target_scope, actor=user_id),
                        ],
                    )
                results.append({**decision, "ok": True, "mode": "proposed"})
                continue
            if action == "auto_promote":
                if not self._can_write_scope(target_scope, role=role):
                    if not dry_run:
                        manager.review_memory(
                            filename,
                            needs_review=True,
                            validated_by=[
                                *record.validated_by,
                                f"promotion-proposal:{target_scope}:{user_id or 'automation'}",
                                migration_audit_tag(action="propose", target_scope=target_scope, actor=user_id),
                            ],
                        )
                    results.append({**decision, "ok": True, "mode": "proposed_permission"})
                    continue
                if dry_run:
                    results.append({**decision, "ok": True, "mode": "would_promote"})
                    continue
                new_path = manager.promote_memory(
                    filename,
                    target_scope=target_scope,
                    target_visibility=decision.get("target_visibility") or None,
                    user_id=user_id or record.user_id,
                    project_id=project_id or record.project_id,
                    group_id=group_id or record.group_id,
                    approved_by=f"auto:{user_id or 'automation'}",
                )
                if new_path is not None:
                    promoted = manager.get_memory_record(new_path.name)
                    if promoted is not None:
                        manager.review_memory(
                            new_path.name,
                            validated_by=[
                                *promoted.validated_by,
                                migration_audit_tag(action="auto_promote", target_scope=target_scope, actor=user_id),
                            ],
                        )
                results.append(
                    {
                        **decision,
                        "ok": new_path is not None,
                        "mode": "promoted" if new_path is not None else "failed",
                        "path": str(new_path) if new_path is not None else "",
                    }
                )
        events = self._memory_migration_events(
            results=results,
            target_scope=target_scope,
            automation_mode=automation_mode,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            dry_run=dry_run,
        )
        if events and not dry_run:
            self._event_ledger_for_scope(
                discipline=discipline,
                project_id=project_id,
                group_id=group_id,
                user_id=user_id,
            ).append_many(events)
        return {
            "ok": True,
            "automation_mode": automation_mode,
            "target_scope": target_scope,
            "planned_count": len(plan),
            "applied_count": len([item for item in results if item.get("mode") in {"promoted", "proposed", "blocked", "proposed_permission"}]),
            "events_written": 0 if dry_run else len(events),
            "results": results,
        }

    def compact_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        user_id = str(payload.get("user_id", "")).strip()
        project_id = str(payload.get("project_id", "")).strip()
        group_id = str(payload.get("group_id", "")).strip()
        discipline = str(payload.get("discipline", "")).strip()
        manager = self._memory_manager_for_scope(
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
        return manager.compact_memories(
            user_id=user_id or None,
            project_id=project_id or None,
            group_id=group_id or None,
            scopes=payload.get("scopes") or None,
            max_groups=int(payload.get("max_groups", 20) or 20),
            dry_run=bool(payload.get("dry_run", False)),
            semantic_guard=bool(payload.get("semantic_guard", True)),
        )

    def _memory_migration_events(
        self,
        *,
        results: list[dict[str, Any]],
        target_scope: str,
        automation_mode: str,
        user_id: str,
        project_id: str,
        group_id: str,
        dry_run: bool,
    ) -> list[ResearchEvent]:
        timestamp = datetime.now(timezone.utc).isoformat()
        events: list[ResearchEvent] = []
        for item in results:
            filename = str(item.get("filename", "")).strip()
            mode = str(item.get("mode", "")).strip()
            action = str(item.get("action", "")).strip()
            if not filename:
                continue
            event_type = {
                "promoted": "memory_migration_promoted",
                "would_promote": "memory_migration_would_promote",
                "proposed": "memory_migration_proposed",
                "proposed_permission": "memory_migration_proposed",
                "blocked": "memory_migration_blocked",
                "failed": "memory_migration_failed",
                "missing": "memory_migration_failed",
            }.get(mode, "memory_migration_decision")
            events.append(
                ResearchEvent(
                    event_id=f"{event_type}::{filename}::{timestamp}",
                    event_type=event_type,
                    topic="memory_governance",
                    project_id=project_id,
                    user_id=user_id,
                    group_id=group_id,
                    actor="memory_governance",
                    timestamp=timestamp,
                    asset_type="memory_record",
                    asset_id=filename,
                    action=action or mode,
                    summary=(
                        f"{filename}: {mode} from {item.get('source_scope', '')} "
                        f"to {target_scope}; risk={item.get('risk_level', '')}"
                    ),
                    source_refs=[filename],
                    metadata={
                        "target_scope": target_scope,
                        "automation_mode": automation_mode,
                        "dry_run": dry_run,
                        "decision": item,
                    },
                )
            )
        return events

    def reject_memory_proposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        manager = self._memory_manager_for_scope(
            discipline=str(payload.get("discipline", "")),
            project_id=str(payload.get("project_id", "")),
            group_id=str(payload.get("group_id", "")),
            user_id=str(payload.get("user_id", "")),
        )
        record = manager.get_memory_record(payload["filename"])
        if record is None:
            return {"ok": False, "mode": "missing", "message": "Memory file not found."}
        user_id = payload.get("user_id", "")
        role = self.get_group_role(
            group_id=payload.get("group_id", "") or record.group_id,
            user_id=user_id,
            claimed_role=payload.get("group_role", ""),
        )
        if self._role_rank(role) < self._role_rank("curator"):
            return {"ok": False, "mode": "forbidden", "message": "Only curator/admin can reject proposals."}
        timestamp = datetime.now(timezone.utc).isoformat()
        validated_by = [*record.validated_by, f"rejected-by:{user_id}:{record.scope}:{timestamp}"]
        ok = manager.review_memory(
            payload["filename"],
            status="rejected",
            needs_review=False,
            validated_by=validated_by,
            last_verified_at=timestamp,
        )
        return {
            "ok": ok,
            "mode": "rejected" if ok else "failed",
            "filename": payload["filename"],
            "message": "Proposal rejected." if ok else "Failed to reject proposal.",
        }

    def _sync_experiment_records_from_workflow_result(
        self,
        *,
        result: Any,
        discipline: str,
        user_id: str,
        project_id: str,
        group_id: str,
        group_role: str,
    ) -> None:
        steps = getattr(result, "steps", [])
        if not isinstance(steps, list):
            return
        identity = {
            "discipline": discipline,
            "user_id": user_id,
            "project_id": project_id,
            "group_id": group_id,
            "group_role": group_role,
        }
        run_to_experiment_id: dict[str, str] = {}
        experiment_economics: dict[str, Any] = next(
            (
                parsed.get("experiment_economics", {})
                for step in steps
                for parsed in [getattr(step, "parsed_output", {})]
                if isinstance(parsed, dict)
                and isinstance(parsed.get("experiment_economics", {}), dict)
                and parsed.get("experiment_economics", {})
            ),
            {},
        )
        lab_meeting_consensus: dict[str, Any] = next(
            (
                parsed.get("lab_meeting_consensus", {})
                for step in steps
                for parsed in [getattr(step, "parsed_output", {})]
                if isinstance(parsed, dict)
                and isinstance(parsed.get("lab_meeting_consensus", {}), dict)
                and parsed.get("lab_meeting_consensus", {})
            ),
            {},
        )

        for step in steps:
            parsed = getattr(step, "parsed_output", {})
            if not isinstance(parsed, dict):
                continue

            experiment_specification = parsed.get("experiment_specification", {})
            if isinstance(experiment_specification, dict) and experiment_specification.get("experiment_id"):
                payload = {
                    **experiment_specification,
                    "project_id": project_id or str(experiment_specification.get("project_id", "")),
                    "economics_summary": {
                        "cost_pressure": str(experiment_economics.get("cost_pressure", "")).strip(),
                        "time_pressure": str(experiment_economics.get("time_pressure", "")).strip(),
                        "cheapest_discriminative_actions": (
                            experiment_economics.get("cheapest_discriminative_actions", [])
                            if isinstance(
                                experiment_economics.get("cheapest_discriminative_actions", []), list
                            )
                            else []
                        ),
                    },
                    "adjudication_context": {
                        "agenda_items": (
                            lab_meeting_consensus.get("agenda_items", [])
                            if isinstance(lab_meeting_consensus.get("agenda_items", []), list)
                            else []
                        ),
                        "evidence_needed_to_close": (
                            lab_meeting_consensus.get("evidence_needed_to_close", [])
                            if isinstance(
                                lab_meeting_consensus.get("evidence_needed_to_close", []), list
                            )
                            else []
                        ),
                        "chair_recommendation": str(
                            lab_meeting_consensus.get("chair_recommendation", "")
                        ).strip(),
                    },
                }
                self.save_experiment_specification(payload, **identity)

            experimental_protocol = parsed.get("experimental_protocol", {})
            if isinstance(experimental_protocol, dict) and experimental_protocol.get("protocol_id"):
                payload = {
                    **experimental_protocol,
                    "governance_checks": list(
                        dict.fromkeys(
                            (
                                experimental_protocol.get("quality_control_checks", [])
                                if isinstance(
                                    experimental_protocol.get("quality_control_checks", []), list
                                )
                                else []
                            )
                            + (
                                ["review lab meeting agenda before freeze"]
                                if lab_meeting_consensus.get("agenda_items")
                                else []
                            )
                        )
                    )[:8],
                    "approval_requirements": list(
                        dict.fromkeys(
                            (
                                ["human approval before route retirement"]
                                if str(lab_meeting_consensus.get("chair_recommendation", "")).strip()
                                else []
                            )
                        )
                    )[:6],
                    "defer_reasons": (
                        experiment_economics.get("defer_candidates", [])
                        if isinstance(experiment_economics.get("defer_candidates", []), list)
                        else []
                    )[:6],
                    "adjudication_questions": (
                        lab_meeting_consensus.get("agenda_items", [])
                        if isinstance(lab_meeting_consensus.get("agenda_items", []), list)
                        else []
                    )[:8],
                }
                self.save_experimental_protocol(payload, **identity)

            experiment_run = parsed.get("experiment_run", {})
            if isinstance(experiment_run, dict) and experiment_run.get("run_id"):
                run_experiment_id = str(experiment_run.get("experiment_id", "")).strip()
                if not run_experiment_id and isinstance(experimental_protocol, dict):
                    run_experiment_id = str(experimental_protocol.get("experiment_id", "")).strip()
                if run_experiment_id:
                    experiment_run = {**experiment_run, "experiment_id": run_experiment_id}
                    run_to_experiment_id[str(experiment_run.get("run_id", "")).strip()] = run_experiment_id
                experiment_run = {
                    **experiment_run,
                    "governance_stage": (
                        "awaiting_adjudication"
                        if lab_meeting_consensus.get("agenda_items")
                        else "ready_for_execution"
                    ),
                    "paused_reason": (
                        str(lab_meeting_consensus.get("chair_recommendation", "")).strip()
                        if lab_meeting_consensus.get("agenda_items")
                        else ""
                    ),
                    "cost_pressure": str(experiment_economics.get("cost_pressure", "")).strip(),
                    "adjudication_status": (
                        "open" if lab_meeting_consensus.get("agenda_items") else "clear"
                    ),
                }
                self.save_experiment_run_record(experiment_run, **identity)

        for step in steps:
            parsed = getattr(step, "parsed_output", {})
            if not isinstance(parsed, dict):
                continue

            quality_control_review = parsed.get("quality_control_review", {})
            if isinstance(quality_control_review, dict) and quality_control_review.get("review_id"):
                run_id = str(quality_control_review.get("run_id", "")).strip()
                experiment_id = str(quality_control_review.get("experiment_id", "")).strip() or run_to_experiment_id.get(run_id, "")
                payload = {
                    **quality_control_review,
                    "experiment_id": experiment_id,
                }
                self.save_quality_control_review_record(payload, **identity)

            interpretation_record = parsed.get("interpretation_record", {})
            if isinstance(interpretation_record, dict) and interpretation_record.get("interpretation_id"):
                run_id = str(interpretation_record.get("run_id", "")).strip()
                experiment_id = str(interpretation_record.get("experiment_id", "")).strip() or run_to_experiment_id.get(run_id, "")
                payload = {
                    **interpretation_record,
                    "experiment_id": experiment_id,
                }
                self.save_interpretation_record(payload, **identity)

    async def submit_workflow(
        self,
        *,
        topic: str,
        dynamic_routing: bool = True,
        report_path: str | None = None,
        discipline: str = "",
        user_id: str = "",
        project_id: str = "",
        group_id: str = "",
        group_role: str = "",
    ) -> RunRecord:
        run_id = uuid4().hex
        record = RunRecord(
            run_id=run_id,
            topic=topic,
            status="queued",
            discipline=discipline,
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
        )
        self._runs[run_id] = record
        task = asyncio.create_task(
            self._run_workflow(
                run_id=run_id,
                topic=topic,
                dynamic_routing=dynamic_routing,
                report_path=report_path,
                discipline=discipline,
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                group_role=group_role,
            )
        )
        self._tasks[run_id] = task
        return record

    async def _run_workflow(
        self,
        *,
        run_id: str,
        topic: str,
        dynamic_routing: bool,
        report_path: str | None,
        discipline: str,
        user_id: str,
        project_id: str,
        group_id: str,
        group_role: str,
    ) -> None:
        record = self._runs[run_id]
        record.status = "running"
        try:
            skill_runtime = SkillRuntime(load_skills(self.root / "kaivu" / "skills_builtin"))
            model_registry = ModelRegistry(default_model="gpt-5")
            config_path = self.root / "config" / "agents.json"
            if config_path.exists():
                model_registry.load_config_file(config_path)
            layout = self._layout_for_scope(
                discipline=discipline,
                project_id=project_id,
                group_id=group_id,
                user_id=user_id,
            )
            director = ResearchDirector(
                cwd=self.root,
                model_name="gpt-5",
                permission_policy=PermissionPolicy(
                    mode="deny_destructive",
                    allow_tools={"write_file"},
                ),
                report_path=report_path or str(layout.reports_root / f"{run_id}.md"),
                dynamic_routing=dynamic_routing,
                skill_runtime=skill_runtime,
                model_registry=model_registry,
                collaboration_context={
                    "discipline": discipline,
                    "primary_discipline": discipline,
                    "user_id": user_id,
                    "project_id": project_id,
                    "group_id": group_id,
                    "evaluation_history_summary": self.build_evaluation_history_signal(
                        discipline=discipline,
                        project_id=project_id,
                        group_id=group_id,
                        user_id=user_id,
                        topic=topic,
                    ),
                },
            )
            harness = ScientificRuntimeHarness(
                root=self.root,
                runtime_dir=layout.state_root / "runtime",
                trajectory_dir=layout.state_root / "runtime" / "trajectories",
                learning_dir=layout.state_root / "runtime" / "learning",
            )
            harness_run = await harness.run_workflow(
                director,
                topic=topic,
                tools=self._build_tools(),
                model="gpt-5",
            )
            result = harness_run.result
            self._sync_experiment_records_from_workflow_result(
                result=result,
                discipline=discipline,
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                group_role=group_role,
            )
            self.save_evaluation_record(
                run_id,
                {
                    "run_id": run_id,
                    "discipline": discipline,
                    "user_id": user_id,
                    "project_id": project_id,
                    "group_id": group_id,
                    "topic": topic,
                    "evaluation_summary": result.research_state.get("evaluation_summary", {}),
                    "runtime_harness_summary": result.research_state.get(
                        "runtime_harness_summary", {}
                    ),
                    "termination_strategy_summary": result.research_state.get(
                        "termination_strategy_summary", {}
                    ),
                    "project_distill": result.research_state.get("project_distill", {}),
                },
            )
            record.result = result
            record.report_markdown = result.final_report
            record.status = "completed"
            record.usage_summary = director._collect_usage_summary(result.steps)
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc)
        finally:
            self._tasks.pop(run_id, None)

    def _build_tools(self) -> ToolRegistry:
        return ToolRegistry(
            [
                ReadFileTool(),
                WriteFileTool(),
                PythonExecTool(),
                NotebookTool(),
                ReadTableTool(),
                BasicStatsTool(),
                PlotCsvTool(),
                PubMedSearchTool(),
                ArxivSearchTool(),
                CrossrefSearchTool(),
                ResolveCitationTool(),
                SaveMemoryTool(),
                SearchMemoryTool(),
                ForgetMemoryTool(),
                ReviewMemoryTool(),
            ]
        )



