from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RuntimeTrajectory:
    session_id: str
    topic: str = ""
    model: str = ""
    completed: bool = False
    messages: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    usage_summary: dict[str, Any] = field(default_factory=dict)
    evaluation_summary: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TrajectoryStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, trajectory: RuntimeTrajectory, *, filename: str = "runtime_trajectories.jsonl") -> Path:
        path = self.root / filename
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(trajectory.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return path

    def load(self, *, filename: str = "runtime_trajectories.jsonl", limit: int = 100) -> list[dict[str, Any]]:
        path = self.root / filename
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
        return rows[-max(1, min(limit, 1000)) :]

    def append_scientific_replay_case(
        self,
        trajectory: RuntimeTrajectory,
        *,
        research_state: dict[str, Any],
        claim_graph: dict[str, Any],
        filename: str = "scientific_replay_cases.jsonl",
    ) -> Path:
        case = build_scientific_replay_case(
            trajectory=trajectory,
            research_state=research_state,
            claim_graph=claim_graph,
        )
        path = self.root / filename
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n")
        return path


def build_scientific_replay_case(
    *,
    trajectory: RuntimeTrajectory,
    research_state: dict[str, Any],
    claim_graph: dict[str, Any],
) -> dict[str, Any]:
    program = research_state.get("research_program_summary", {}) if isinstance(research_state.get("research_program_summary", {}), dict) else {}
    scheduler = research_state.get("experiment_execution_loop_summary", {}) if isinstance(research_state.get("experiment_execution_loop_summary", {}), dict) else {}
    evidence = research_state.get("evidence_review_summary", {}) if isinstance(research_state.get("evidence_review_summary", {}), dict) else {}
    hypothesis = research_state.get("hypothesis_system_summary", {}) if isinstance(research_state.get("hypothesis_system_summary", {}), dict) else {}
    return {
        "kind": "scientific_replay_case",
        "schema_version": "1.0",
        "case_id": f"trajectory::{_slugify(trajectory.session_id)}",
        "topic": trajectory.topic,
        "model": trajectory.model,
        "completed": trajectory.completed,
        "created_at": trajectory.created_at,
        "input_summary": {
            "message_count": len(trajectory.messages),
            "event_count": len(trajectory.events),
            "claim_count": len(claim_graph.get("claims", []) if isinstance(claim_graph.get("claims", []), list) else []),
            "hypothesis_count": len(claim_graph.get("hypotheses", []) if isinstance(claim_graph.get("hypotheses", []), list) else []),
        },
        "expected_outputs": {
            "research_program_status": program.get("status", ""),
            "scheduler_state": scheduler.get("scheduler_state", ""),
            "evidence_readiness": evidence.get("review_readiness", ""),
            "hypothesis_system_state": hypothesis.get("system_state", ""),
        },
        "rubric": [
            "research program summary exists",
            "scheduler decision is explainable",
            "evidence readiness is explicit",
            "hypothesis lifecycle is represented",
            "failures or blockers are preserved when present",
        ],
        "research_state_extract": {
            "research_program_summary": program,
            "experiment_execution_loop_summary": scheduler,
            "evidence_review_summary": evidence,
            "hypothesis_system_summary": hypothesis,
            "failure_reuse_engine_summary": research_state.get("failure_reuse_engine_summary", {}),
        },
    }


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "trajectory"
