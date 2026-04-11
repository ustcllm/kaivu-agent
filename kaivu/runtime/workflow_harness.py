from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .events import RuntimeEventStream
from .session import RuntimeSession
from .trajectory import RuntimeTrajectory, TrajectoryStore


@dataclass(slots=True)
class WorkflowHarnessRun:
    result: Any
    session: RuntimeSession
    events: list[dict[str, Any]]
    trajectory_path: str


class ScientificRuntimeHarness:
    def __init__(self, *, root: str | Path, trajectory_dir: str | Path | None = None) -> None:
        self.root = Path(root).resolve()
        self.runtime_dir = self.root / ".state" / "runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.trajectory_store = TrajectoryStore(trajectory_dir or self.runtime_dir / "trajectories")

    async def run_workflow(
        self,
        workflow: Any,
        *,
        topic: str,
        tools: Any,
        profiles: list[Any] | None = None,
        session: RuntimeSession | None = None,
        model: str = "",
    ) -> WorkflowHarnessRun:
        runtime_session = session or RuntimeSession(
            topic=topic,
            user_id=str(getattr(workflow, "collaboration_context", {}).get("user_id", "")),
            project_id=str(getattr(workflow, "collaboration_context", {}).get("project_id", "")),
            group_id=str(getattr(workflow, "collaboration_context", {}).get("group_id", "")),
        )
        event_path = self.runtime_dir / "events" / f"{runtime_session.session_id}.jsonl"
        stream = RuntimeEventStream(session_id=runtime_session.session_id, sink_path=event_path)
        memory_before = self._snapshot_memory_files()
        setattr(workflow, "runtime_event_stream", stream)
        runtime_context = dict(getattr(workflow, "collaboration_context", {}) or {})
        runtime_context["_runtime_event_stream"] = stream
        runtime_context["_runtime_session_id"] = runtime_session.session_id
        setattr(workflow, "collaboration_context", runtime_context)
        runtime_session.append_message("user", topic, metadata={"kind": "workflow_topic"})
        stream.emit(
            "workflow.started",
            actor="scientific_runtime_harness",
            project_id=runtime_session.project_id,
            user_id=runtime_session.user_id,
            group_id=runtime_session.group_id,
            payload={"topic": topic, "profiles": [getattr(profile, "name", str(profile)) for profile in profiles or []]},
        )
        try:
            result = await workflow.run(topic, tools=tools, profiles=profiles)
        except Exception as exc:
            stream.emit(
                "workflow.failed",
                actor="scientific_runtime_harness",
                project_id=runtime_session.project_id,
                user_id=runtime_session.user_id,
                group_id=runtime_session.group_id,
                payload={"error": str(exc), "error_type": type(exc).__name__},
            )
            raise

        self._emit_step_events(stream, runtime_session, result)
        self._emit_tool_events(stream, runtime_session, result)
        self._emit_scheduler_events(stream, runtime_session, result)
        self._emit_memory_events(stream, runtime_session, before=memory_before, after=self._snapshot_memory_files())
        runtime_session.append_message(
            "assistant",
            str(getattr(result, "final_report", ""))[:8000],
            metadata={"kind": "workflow_report", "report_path": getattr(result, "report_path", "")},
        )
        stream.emit(
            "workflow.completed",
            actor="scientific_runtime_harness",
            project_id=runtime_session.project_id,
            user_id=runtime_session.user_id,
            group_id=runtime_session.group_id,
            payload={
                "topic": topic,
                "step_count": len(getattr(result, "steps", []) or []),
                "report_path": getattr(result, "report_path", ""),
                "scheduler_state": getattr(result, "research_state", {}).get("experiment_execution_loop_summary", {}).get("scheduler_state", ""),
                "evaluation_release_state": getattr(result, "research_state", {}).get("kaivu_evaluation_harness_summary", {}).get("release_state", ""),
                "runtime_event_counts": self._event_type_counts(stream.snapshot()),
            },
        )
        trajectory = RuntimeTrajectory(
            session_id=runtime_session.session_id,
            topic=topic,
            model=model or getattr(workflow, "model_name", ""),
            completed=True,
            messages=[message.to_dict() for message in runtime_session.messages],
            events=stream.snapshot(),
            usage_summary=getattr(result, "run_manifest", {}).get("usage_summary", {}),
            evaluation_summary=getattr(result, "research_state", {}).get("kaivu_evaluation_harness_summary", {}),
        )
        trajectory_path = self.trajectory_store.append(trajectory)
        replay_case_path = self.trajectory_store.append_scientific_replay_case(
            trajectory,
            research_state=getattr(result, "research_state", {}),
            claim_graph=getattr(result, "claim_graph", {}),
        )
        if hasattr(result, "research_state") and isinstance(result.research_state, dict):
            result.research_state["runtime_harness_summary"] = {
                "session_id": runtime_session.session_id,
                "event_path": str(event_path),
                "trajectory_path": str(trajectory_path),
                "replay_case_path": str(replay_case_path),
                "event_count": len(stream.snapshot()),
            }
        if hasattr(result, "claim_graph") and isinstance(result.claim_graph, dict):
            result.claim_graph["runtime_harness_summary"] = getattr(result, "research_state", {}).get("runtime_harness_summary", {})
        return WorkflowHarnessRun(
            result=result,
            session=runtime_session,
            events=stream.snapshot(),
            trajectory_path=str(trajectory_path),
        )

    def _emit_tool_events(self, stream: RuntimeEventStream, session: RuntimeSession, result: Any) -> None:
        for step_index, step in enumerate(getattr(result, "steps", []) or [], start=1):
            state = getattr(step, "state", None)
            scratchpad = getattr(state, "scratchpad", {}) if state is not None else {}
            records = scratchpad.get("execution_records", []) if isinstance(scratchpad, dict) else []
            if not isinstance(records, list):
                continue
            for record_index, record in enumerate(records, start=1):
                if not isinstance(record, dict):
                    continue
                stream.emit(
                    "tool.call.completed",
                    actor=str(getattr(step, "profile_name", "")) or "specialist",
                    project_id=session.project_id,
                    user_id=session.user_id,
                    group_id=session.group_id,
                    payload={
                        "step_index": step_index,
                        "record_index": record_index,
                        "profile_name": str(getattr(step, "profile_name", "")),
                        "task_id": str(record.get("task_id", "")),
                        "tool_name": str(record.get("tool_name", "")),
                        "status": str(record.get("status", "")),
                        "timestamp": str(record.get("timestamp", "")),
                        "inputs": record.get("inputs", {}) if isinstance(record.get("inputs", {}), dict) else {},
                        "outputs": record.get("outputs", {}) if isinstance(record.get("outputs", {}), dict) else {},
                        "artifacts": record.get("artifacts", []) if isinstance(record.get("artifacts", []), list) else [],
                        "error": str(record.get("error", "") or ""),
                    },
                )

    def _emit_scheduler_events(self, stream: RuntimeEventStream, session: RuntimeSession, result: Any) -> None:
        research_state = getattr(result, "research_state", {})
        state = research_state if isinstance(research_state, dict) else {}
        scheduler = state.get("experiment_execution_loop_summary", {})
        if not isinstance(scheduler, dict) or not scheduler:
            return
        stream.emit(
            "experiment.scheduler.planned",
            actor="experiment_scheduler",
            project_id=session.project_id,
            user_id=session.user_id,
            group_id=session.group_id,
            payload={
                "scheduler_id": str(scheduler.get("scheduler_id", "")),
                "scheduler_state": str(scheduler.get("scheduler_state", "")),
                "candidate_count": int(scheduler.get("candidate_count", 0) or 0),
                "top_experiment_id": str(scheduler.get("top_experiment_id", "")),
                "top_action": str(scheduler.get("top_action", "")),
                "parameter_optimization_supported": bool(scheduler.get("parameter_optimization_supported", False)),
                "mcts_like_search": scheduler.get("mcts_like_search", {}) if isinstance(scheduler.get("mcts_like_search", {}), dict) else {},
            },
        )
        for index, item in enumerate(scheduler.get("execution_queue", []) or [], start=1):
            if not isinstance(item, dict):
                continue
            stream.emit(
                "experiment.schedule.item.selected",
                actor="experiment_scheduler",
                project_id=session.project_id,
                user_id=session.user_id,
                group_id=session.group_id,
                payload=self._scheduler_item_payload(item, index, queue="execution_queue"),
            )
        for index, item in enumerate(scheduler.get("blocked_candidates", []) or [], start=1):
            if not isinstance(item, dict):
                continue
            stream.emit(
                "experiment.schedule.item.blocked",
                actor="experiment_scheduler",
                project_id=session.project_id,
                user_id=session.user_id,
                group_id=session.group_id,
                payload=self._scheduler_item_payload(item, index, queue="blocked_candidates"),
            )

    def _emit_memory_events(
        self,
        stream: RuntimeEventStream,
        session: RuntimeSession,
        *,
        before: dict[str, dict[str, Any]],
        after: dict[str, dict[str, Any]],
    ) -> None:
        changed: list[dict[str, Any]] = []
        for path, metadata in sorted(after.items()):
            prior = before.get(path)
            if prior == metadata:
                continue
            changed.append(
                {
                    "path": path,
                    "action": "created" if prior is None else "updated",
                    "size": metadata.get("size", 0),
                    "mtime": metadata.get("mtime", 0.0),
                    "prior_size": prior.get("size", 0) if prior else 0,
                    "scope_hint": self._memory_scope_hint(path),
                }
            )
        for path, prior in sorted(before.items()):
            if path in after:
                continue
            changed.append(
                {
                    "path": path,
                    "action": "deleted",
                    "size": 0,
                    "mtime": 0.0,
                    "prior_size": prior.get("size", 0),
                    "scope_hint": self._memory_scope_hint(path),
                }
            )
        if not changed:
            return
        stream.emit(
            "memory.files.changed",
            actor="runtime_memory_observer",
            project_id=session.project_id,
            user_id=session.user_id,
            group_id=session.group_id,
            payload={
                "changed_count": len(changed),
                "created_count": sum(1 for item in changed if item["action"] == "created"),
                "updated_count": sum(1 for item in changed if item["action"] == "updated"),
                "deleted_count": sum(1 for item in changed if item["action"] == "deleted"),
                "changes": changed[:50],
            },
        )

    def _snapshot_memory_files(self) -> dict[str, dict[str, Any]]:
        memory_dir = self.root / "memory"
        if not memory_dir.exists():
            return {}
        snapshot: dict[str, dict[str, Any]] = {}
        for path in sorted(memory_dir.rglob("*.md")):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            snapshot[path.relative_to(memory_dir).as_posix()] = {
                "size": stat.st_size,
                "mtime": round(stat.st_mtime, 6),
            }
        return snapshot

    @staticmethod
    def _memory_scope_hint(relative_path: str) -> str:
        first = relative_path.split("/", 1)[0].strip().lower()
        known = {
            "personal": "personal",
            "projects": "project",
            "groups": "group",
            "public": "public",
            "agents": "agent",
            "session": "session",
        }
        if relative_path == "MEMORY.md":
            return "index"
        return known.get(first, "shared")

    @staticmethod
    def _scheduler_item_payload(item: dict[str, Any], index: int, *, queue: str) -> dict[str, Any]:
        return {
            "queue": queue,
            "queue_index": index,
            "experiment_id": str(item.get("experiment_id", "")),
            "hypothesis_id": str(item.get("hypothesis_id", "")),
            "action": str(item.get("action", "")),
            "discipline": str(item.get("discipline", "")),
            "score": item.get("score", item.get("priority_score", 0)),
            "expected_information_gain": item.get("expected_information_gain", 0),
            "estimated_cost": item.get("estimated_cost", item.get("cost", 0)),
            "risk_level": str(item.get("risk_level", "")),
            "requires_human_approval": bool(item.get("requires_human_approval", False)),
            "blockers": item.get("blockers", []) if isinstance(item.get("blockers", []), list) else [],
            "rationale": str(item.get("rationale", ""))[:500],
        }

    @staticmethod
    def _event_type_counts(events: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in events:
            event_type = str(event.get("event_type", "") or "unknown")
            counts[event_type] = counts.get(event_type, 0) + 1
        return counts

    def _emit_step_events(self, stream: RuntimeEventStream, session: RuntimeSession, result: Any) -> None:
        if any(event.get("event_type") == "specialist.step.completed" for event in stream.snapshot()):
            return
        steps = getattr(result, "steps", []) or []
        for index, step in enumerate(steps, start=1):
            stream.emit(
                "specialist.step.completed",
                actor="scientific_runtime_harness",
                project_id=session.project_id,
                user_id=session.user_id,
                group_id=session.group_id,
                payload=self._step_event_payload(step, index),
            )

    @staticmethod
    def _step_event_payload(step: Any, index: int) -> dict[str, Any]:
        parsed = getattr(step, "parsed_output", {})
        parsed_output = parsed if isinstance(parsed, dict) else {}
        model_meta = getattr(step, "model_meta", {})
        safe_model_meta = model_meta if isinstance(model_meta, dict) else {}
        state = getattr(step, "state", None)
        scratchpad = getattr(state, "scratchpad", {}) if state is not None else {}
        safe_scratchpad = scratchpad if isinstance(scratchpad, dict) else {}
        usage_totals = safe_scratchpad.get("model_usage_totals", {})
        safe_usage_totals = usage_totals if isinstance(usage_totals, dict) else {}
        raw_output = str(getattr(step, "raw_output", ""))
        return {
            "step_index": index,
            "profile_name": str(getattr(step, "profile_name", "")),
            "model_meta": safe_model_meta,
            "usage_summary": {
                "input_tokens": int(safe_usage_totals.get("input_tokens", 0) or 0),
                "output_tokens": int(safe_usage_totals.get("output_tokens", 0) or 0),
                "total_tokens": int(safe_usage_totals.get("total_tokens", 0) or 0),
                "estimated_cost_usd": round(float(safe_usage_totals.get("estimated_cost_usd", 0.0) or 0.0), 6),
                "rounds": int(safe_usage_totals.get("rounds", 0) or 0),
            },
            "parsed_keys": sorted(str(key) for key in parsed_output.keys()),
            "raw_output_preview": raw_output[:800],
            "structured_object_flags": ScientificRuntimeHarness._structured_object_flags(parsed_output),
            "structured_object_counts": ScientificRuntimeHarness._structured_object_counts(parsed_output),
        }

    @staticmethod
    def _structured_object_flags(parsed_output: dict[str, Any]) -> dict[str, bool]:
        keys = [
            "literature_synthesis",
            "systematic_review",
            "hypotheses",
            "hypothesis_validations",
            "hypothesis_gates",
            "mechanism_map",
            "experiment_specification",
            "experiment_run",
            "quality_control_review",
            "interpretation_record",
            "scientific_decision",
            "negative_results",
            "lab_meeting_consensus",
            "program_management",
        ]
        return {f"has_{key}": bool(parsed_output.get(key)) for key in keys}

    @staticmethod
    def _structured_object_counts(parsed_output: dict[str, Any]) -> dict[str, int]:
        counted_keys = [
            "claims",
            "evidence",
            "uncertainties",
            "negative_results",
            "hypotheses",
            "hypothesis_validations",
            "hypothesis_gates",
            "mechanism_map",
            "domain_playbooks",
        ]
        counts: dict[str, int] = {}
        for key in counted_keys:
            value = parsed_output.get(key)
            if isinstance(value, list):
                counts[f"{key}_count"] = len(value)
            elif isinstance(value, dict):
                counts[f"{key}_count"] = len(value)
            else:
                counts[f"{key}_count"] = 0
        return counts

