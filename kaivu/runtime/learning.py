from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCIENTIFIC_LEARNING_SCHEMA_VERSION = "1.0"


@dataclass(slots=True)
class ScientificLearningActor:
    actor_id: str
    actor_type: str = "agent"
    role: str = ""
    model: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScientificLearningStep:
    step_id: str
    step_type: str
    actor_id: str = ""
    timestamp: str = ""
    observation: dict[str, Any] = field(default_factory=dict)
    action: dict[str, Any] = field(default_factory=dict)
    outcome: dict[str, Any] = field(default_factory=dict)
    reward_signals: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["timestamp"]:
            data["timestamp"] = datetime.now(timezone.utc).isoformat()
        return data


@dataclass(slots=True)
class ScientificLearningEpisode:
    episode_id: str
    source_session_id: str
    topic: str = ""
    schema_version: str = SCIENTIFIC_LEARNING_SCHEMA_VERSION
    mode: str = "observation_only"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    scope: dict[str, Any] = field(default_factory=dict)
    task: dict[str, Any] = field(default_factory=dict)
    actors: list[ScientificLearningActor] = field(default_factory=list)
    steps: list[ScientificLearningStep] = field(default_factory=list)
    multi_agent_trace: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    state_changes: list[dict[str, Any]] = field(default_factory=list)
    memory_diffs: list[dict[str, Any]] = field(default_factory=list)
    graph_diffs: list[dict[str, Any]] = field(default_factory=list)
    collaboration_graph: dict[str, Any] = field(default_factory=dict)
    evaluation_scores: dict[str, Any] = field(default_factory=dict)
    human_feedback: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    replay: dict[str, Any] = field(default_factory=dict)
    dataset_manifest: dict[str, Any] = field(default_factory=dict)
    training_interfaces: dict[str, Any] = field(default_factory=dict)
    governance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["actors"] = [actor.to_dict() for actor in self.actors]
        data["steps"] = [step.to_dict() for step in self.steps]
        return data


class ScientificLearningEpisodeStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, episode: ScientificLearningEpisode, *, filename: str = "scientific_learning_episodes.jsonl") -> Path:
        path = self.root / filename
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(episode.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return path

    def save(self, episode: ScientificLearningEpisode) -> Path:
        path = self.root / "episodes" / f"{_safe_name(episode.episode_id)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(episode.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path

    def load(self, *, filename: str = "scientific_learning_episodes.jsonl", limit: int = 100) -> list[dict[str, Any]]:
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

    def append_benchmark_seed(
        self,
        episode: ScientificLearningEpisode,
        *,
        filename: str = "benchmark_seed_episodes.jsonl",
    ) -> Path:
        seed = build_benchmark_seed_from_learning_episode(episode)
        path = self.root / filename
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(seed, ensure_ascii=False, sort_keys=True) + "\n")
        return path

    def load_feedback(self, *, filename: str = "human_feedback.jsonl", limit: int = 1000) -> list[dict[str, Any]]:
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
        return rows[-max(1, min(limit, 10000)) :]

    def validate_episodes(self, *, limit: int = 1000) -> dict[str, Any]:
        episodes = self.load(limit=limit)
        results = [validate_scientific_learning_episode(item) for item in episodes]
        invalid = [item for item in results if not item.get("valid", False)]
        return {
            "schema_version": SCIENTIFIC_LEARNING_SCHEMA_VERSION,
            "episode_count": len(episodes),
            "valid_count": len(results) - len(invalid),
            "invalid_count": len(invalid),
            "results": results,
        }

    def aggregate_feedback(self, *, limit: int = 1000) -> dict[str, Any]:
        episodes = self.load(limit=limit)
        feedback = self.load_feedback(limit=limit * 10)
        return aggregate_learning_feedback(episodes=episodes, feedback=feedback)

    def export_training_dataset(
        self,
        *,
        target: str = "policy",
        limit: int = 1000,
        filename: str | None = None,
    ) -> Path:
        episodes = self.load(limit=limit)
        feedback = self.load_feedback(limit=limit * 10)
        rows = build_training_dataset_from_learning_episodes(
            episodes=episodes,
            feedback=feedback,
            target=target,
        )
        output = self.root / "exports" / (filename or f"{_safe_name(target)}_training_dataset.jsonl")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        manifest_path = output.with_suffix(".manifest.json")
        manifest_path.write_text(
            json.dumps(
                build_learning_dataset_manifest(
                    dataset_path=output,
                    episodes=episodes,
                    rows=rows,
                    dataset_type=f"{target}_training_dataset",
                    filters={"target": target, "limit": limit},
                ),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return output

    def build_benchmark_dataset(
        self,
        *,
        limit: int = 1000,
        filename: str = "learning_benchmark_dataset.jsonl",
    ) -> Path:
        episodes = self.load(limit=limit)
        output = self.root / "benchmarks" / filename
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as handle:
            for item in episodes:
                seed = build_benchmark_seed_from_episode_dict(item)
                handle.write(json.dumps(seed, ensure_ascii=False, sort_keys=True) + "\n")
        manifest_path = output.with_suffix(".manifest.json")
        seeds = [build_benchmark_seed_from_episode_dict(item) for item in episodes if isinstance(item, dict)]
        manifest_path.write_text(
            json.dumps(
                build_learning_dataset_manifest(
                    dataset_path=output,
                    episodes=episodes,
                    rows=seeds,
                    dataset_type="learning_benchmark_dataset",
                    filters={"limit": limit},
                ),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return output

    def build_replay_index(
        self,
        *,
        limit: int = 1000,
        filename: str = "learning_replay_index.json",
    ) -> Path:
        episodes = self.load(limit=limit)
        index = build_learning_replay_index(episodes)
        output = self.root / "replay" / filename
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return output

    def run_replay_checks(self, *, limit: int = 1000, filename: str = "learning_replay_report.json") -> Path:
        episodes = self.load(limit=limit)
        report = run_learning_replay_checks(episodes)
        output = self.root / "replay" / filename
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return output

    def run_benchmark_checks(self, *, limit: int = 1000, filename: str = "learning_benchmark_report.json") -> Path:
        episodes = self.load(limit=limit)
        report = run_learning_benchmark_checks(episodes)
        output = self.root / "benchmarks" / filename
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return output


def build_scientific_learning_episode(
    *,
    session: Any,
    events: list[dict[str, Any]],
    result: Any,
    trajectory_path: str = "",
    replay_case_path: str = "",
) -> ScientificLearningEpisode:
    research_state = getattr(result, "research_state", {})
    claim_graph = getattr(result, "claim_graph", {})
    run_manifest = getattr(result, "run_manifest", {})
    safe_state = research_state if isinstance(research_state, dict) else {}
    safe_graph = claim_graph if isinstance(claim_graph, dict) else {}
    safe_manifest = run_manifest if isinstance(run_manifest, dict) else {}
    session_id = str(getattr(session, "session_id", ""))
    topic = str(getattr(session, "topic", "") or getattr(result, "topic", ""))

    actors = _derive_actors(events=events, result=result, model=str(safe_manifest.get("model", "")))
    steps = _derive_learning_steps(events)
    tool_calls = _extract_tool_calls(events)
    memory_diffs = _extract_event_payloads(events, "memory.files.changed")
    graph_diffs = _derive_graph_diffs(safe_graph)
    state_changes = _derive_state_changes(events=events, research_state=safe_state)
    evaluation_scores = _derive_evaluation_scores(safe_state)
    collaboration_graph = build_multi_agent_collaboration_graph(events)

    return ScientificLearningEpisode(
        episode_id=f"learning::{_safe_name(session_id)}",
        source_session_id=session_id,
        topic=topic,
        scope={
            "project_id": str(getattr(session, "project_id", "") or safe_manifest.get("project_id", "")),
            "user_id": str(getattr(session, "user_id", "") or safe_manifest.get("user_id", "")),
            "group_id": str(getattr(session, "group_id", "") or safe_manifest.get("group_id", "")),
            "discipline": _state_value(safe_state, "workspace_layout_summary", "discipline"),
        },
        task={
            "topic": topic,
            "task_type": _infer_task_type(safe_state),
            "business_decision_policy": "not_controlled_by_learning_layer",
            "observation_only": True,
        },
        actors=actors,
        steps=steps,
        multi_agent_trace=_extract_multi_agent_trace(events),
        tool_calls=tool_calls,
        state_changes=state_changes,
        memory_diffs=memory_diffs,
        graph_diffs=graph_diffs,
        collaboration_graph=collaboration_graph,
        evaluation_scores=evaluation_scores,
        human_feedback=[],
        artifacts=_derive_artifacts(safe_manifest, trajectory_path=trajectory_path, replay_case_path=replay_case_path),
        replay={
            "trajectory_path": trajectory_path,
            "replay_case_path": replay_case_path,
            "event_count": len(events),
            "step_count": len(steps),
            "tool_call_count": len(tool_calls),
        },
        dataset_manifest={
            "dataset_ready": True,
            "source": "runtime_harness",
            "schema_version": SCIENTIFIC_LEARNING_SCHEMA_VERSION,
            "episode_hash": _stable_hash(
                {
                    "session_id": session_id,
                    "topic": topic,
                    "event_count": len(events),
                    "step_count": len(steps),
                }
            ),
        },
        training_interfaces={
            "single_agent_policy_optimization": {
                "enabled_now": False,
                "ready_fields": ["observation", "action", "outcome", "reward_signals"],
            },
            "multi_agent_collaboration_optimization": {
                "enabled_now": False,
                "ready_fields": ["actors", "multi_agent_trace", "state_changes"],
            },
            "reward_modeling": {
                "enabled_now": False,
                "ready_fields": ["evaluation_scores", "human_feedback", "outcome"],
            },
            "preference_learning": {
                "enabled_now": False,
                "ready_fields": ["human_feedback", "alternative_actions"],
            },
            "agentic_reinforcement_learning": {
                "enabled_now": False,
                "ready_fields": ["steps", "tool_calls", "state_changes", "replay"],
            },
        },
        governance={
            "intervenes_in_business_logic": False,
            "allowed_current_uses": ["observability", "replay", "benchmarking", "data_accumulation"],
            "disallowed_current_uses": ["routing_control", "scheduler_override", "hypothesis_gate_override"],
            "privacy_review_required_before_training": True,
        },
    )


def build_learning_episode_summary(episode: ScientificLearningEpisode) -> dict[str, Any]:
    data = episode.to_dict()
    return {
        "episode_id": episode.episode_id,
        "schema_version": episode.schema_version,
        "mode": episode.mode,
        "topic": episode.topic,
        "actor_count": len(episode.actors),
        "step_count": len(episode.steps),
        "tool_call_count": len(episode.tool_calls),
        "state_change_count": len(episode.state_changes),
        "memory_diff_count": len(episode.memory_diffs),
        "graph_diff_count": len(episode.graph_diffs),
        "collaboration_edge_count": int(episode.collaboration_graph.get("edge_count", 0) or 0),
        "human_feedback_count": len(episode.human_feedback),
        "intervenes_in_business_logic": bool(data.get("governance", {}).get("intervenes_in_business_logic", True)),
        "training_interfaces": episode.training_interfaces,
    }


def validate_scientific_learning_episode(episode: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(episode, dict):
        return {"valid": False, "errors": ["episode must be a dict"], "warnings": []}
    required = ["episode_id", "source_session_id", "schema_version", "mode", "task", "steps", "governance"]
    for key in required:
        if key not in episode:
            errors.append(f"missing required field: {key}")
    if str(episode.get("schema_version", "")) != SCIENTIFIC_LEARNING_SCHEMA_VERSION:
        warnings.append("schema_version differs from current runtime version")
    if str(episode.get("mode", "")) != "observation_only":
        errors.append("mode must remain observation_only")
    governance = episode.get("governance", {})
    if not isinstance(governance, dict):
        errors.append("governance must be a dict")
        governance = {}
    if bool(governance.get("intervenes_in_business_logic", True)):
        errors.append("learning episode cannot intervene in business logic")
    steps = episode.get("steps", [])
    if not isinstance(steps, list):
        errors.append("steps must be a list")
        steps = []
    for index, step in enumerate(steps[:1000], start=1):
        if not isinstance(step, dict):
            errors.append(f"step {index} must be a dict")
            continue
        for key in ["step_id", "step_type", "observation", "action", "outcome", "reward_signals"]:
            if key not in step:
                warnings.append(f"step {index} missing {key}")
    training_interfaces = episode.get("training_interfaces", {})
    if isinstance(training_interfaces, dict):
        enabled = [
            name
            for name, config in training_interfaces.items()
            if isinstance(config, dict) and bool(config.get("enabled_now", False))
        ]
        if enabled:
            errors.append(f"training interfaces must be disabled in current layer: {', '.join(enabled)}")
    else:
        warnings.append("training_interfaces should be a dict")
    collaboration_graph = episode.get("collaboration_graph", {})
    if collaboration_graph and not isinstance(collaboration_graph, dict):
        warnings.append("collaboration_graph should be a dict")
    return {
        "episode_id": str(episode.get("episode_id", "")),
        "valid": not errors,
        "errors": errors,
        "warnings": warnings[:50],
        "step_count": len(steps),
        "tool_call_count": len(episode.get("tool_calls", []) if isinstance(episode.get("tool_calls", []), list) else []),
        "collaboration_edge_count": int(collaboration_graph.get("edge_count", 0) or 0) if isinstance(collaboration_graph, dict) else 0,
    }


def aggregate_learning_feedback(
    *,
    episodes: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
) -> dict[str, Any]:
    by_episode: dict[str, list[dict[str, Any]]] = {}
    ratings: list[float] = []
    preference_count = 0
    for item in feedback:
        if not isinstance(item, dict):
            continue
        episode_id = str(item.get("episode_id", "")).strip()
        if not episode_id:
            continue
        by_episode.setdefault(episode_id, []).append(item)
        rating = item.get("rating")
        if isinstance(rating, int | float):
            ratings.append(float(rating))
        if item.get("preferred_step_id") or item.get("rejected_step_id"):
            preference_count += 1
    episode_ids = {str(item.get("episode_id", "")) for item in episodes if isinstance(item, dict)}
    return {
        "episode_count": len(episodes),
        "feedback_count": sum(len(items) for items in by_episode.values()),
        "episode_feedback_count": len(by_episode),
        "orphan_feedback_count": len([episode_id for episode_id in by_episode if episode_id not in episode_ids]),
        "preference_pair_count": preference_count,
        "average_rating": round(sum(ratings) / len(ratings), 4) if ratings else None,
        "episodes": [
            {
                "episode_id": episode_id,
                "feedback_count": len(items),
                "average_rating": _average_rating(items),
                "preference_pair_count": len([item for item in items if item.get("preferred_step_id") or item.get("rejected_step_id")]),
            }
            for episode_id, items in sorted(by_episode.items())
        ],
    }


def build_training_dataset_from_learning_episodes(
    *,
    episodes: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
    target: str = "policy",
) -> list[dict[str, Any]]:
    feedback_by_episode: dict[str, list[dict[str, Any]]] = {}
    for item in feedback:
        if isinstance(item, dict) and str(item.get("episode_id", "")).strip():
            feedback_by_episode.setdefault(str(item.get("episode_id", "")).strip(), []).append(item)
    target = target.strip().lower() or "policy"
    rows: list[dict[str, Any]] = []
    for episode in episodes:
        if not isinstance(episode, dict):
            continue
        validation = validate_scientific_learning_episode(episode)
        if not validation.get("valid", False):
            continue
        if target in {"policy", "single_agent_policy"}:
            rows.extend(_policy_rows(episode))
        elif target in {"collaboration", "multi_agent"}:
            rows.extend(_collaboration_rows(episode))
        elif target in {"reward", "reward_model"}:
            rows.extend(_reward_rows(episode, feedback_by_episode.get(str(episode.get("episode_id", "")), [])))
        elif target in {"preference", "preference_learning"}:
            rows.extend(_preference_rows(episode, feedback_by_episode.get(str(episode.get("episode_id", "")), [])))
        else:
            rows.append(_episode_level_row(episode, feedback_by_episode.get(str(episode.get("episode_id", "")), []), target=target))
    return rows


def build_benchmark_seed_from_episode_dict(episode: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "scientific_learning_benchmark_seed",
        "schema_version": SCIENTIFIC_LEARNING_SCHEMA_VERSION,
        "case_id": f"benchmark-seed::{_safe_name(str(episode.get('episode_id', '')))}",
        "source_episode_id": str(episode.get("episode_id", "")),
        "topic": str(episode.get("topic", "")),
        "scope": episode.get("scope", {}) if isinstance(episode.get("scope", {}), dict) else {},
        "input": {
            "task": episode.get("task", {}) if isinstance(episode.get("task", {}), dict) else {},
            "actor_count": len(episode.get("actors", []) if isinstance(episode.get("actors", []), list) else []),
            "tool_call_count": len(episode.get("tool_calls", []) if isinstance(episode.get("tool_calls", []), list) else []),
            "state_change_count": len(episode.get("state_changes", []) if isinstance(episode.get("state_changes", []), list) else []),
            "collaboration_edge_count": int(
                episode.get("collaboration_graph", {}).get("edge_count", 0)
                if isinstance(episode.get("collaboration_graph", {}), dict)
                else 0
            ),
        },
        "expected_behavior": {
            "must_validate_episode_schema": True,
            "must_preserve_business_logic": True,
            "must_keep_learning_layer_observation_only": True,
            "must_emit_replayable_trace": bool(episode.get("replay", {})),
        },
        "rubric": [
            "validates the scientific learning episode",
            "does not enable training interfaces during normal workflow",
            "preserves tool/memory/graph traces",
            "can be replayed or inspected offline",
        ],
    }


def build_learning_replay_index(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for episode in episodes:
        if not isinstance(episode, dict):
            continue
        replay = episode.get("replay", {}) if isinstance(episode.get("replay", {}), dict) else {}
        items.append(
            {
                "episode_id": str(episode.get("episode_id", "")),
                "topic": str(episode.get("topic", "")),
                "source_session_id": str(episode.get("source_session_id", "")),
                "trajectory_path": str(replay.get("trajectory_path", "")),
                "replay_case_path": str(replay.get("replay_case_path", "")),
                "event_count": int(replay.get("event_count", 0) or 0),
                "step_count": int(replay.get("step_count", 0) or 0),
                "tool_call_count": int(replay.get("tool_call_count", 0) or 0),
                "valid": validate_scientific_learning_episode(episode).get("valid", False),
                "episode_hash": str(
                    episode.get("dataset_manifest", {}).get("episode_hash", "")
                    if isinstance(episode.get("dataset_manifest", {}), dict)
                    else ""
                ),
            }
        )
    return {
        "kind": "scientific_learning_replay_index",
        "schema_version": SCIENTIFIC_LEARNING_SCHEMA_VERSION,
        "episode_count": len(items),
        "items": items,
    }


def run_learning_replay_checks(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for episode in episodes:
        if not isinstance(episode, dict):
            continue
        validation = validate_scientific_learning_episode(episode)
        replay = episode.get("replay", {}) if isinstance(episode.get("replay", {}), dict) else {}
        steps = episode.get("steps", []) if isinstance(episode.get("steps", []), list) else []
        tool_calls = episode.get("tool_calls", []) if isinstance(episode.get("tool_calls", []), list) else []
        expected_step_count = int(replay.get("step_count", len(steps)) or 0)
        expected_tool_count = int(replay.get("tool_call_count", len(tool_calls)) or 0)
        checks = {
            "schema_valid": bool(validation.get("valid", False)),
            "step_count_matches": expected_step_count == len(steps),
            "tool_call_count_matches": expected_tool_count == len(tool_calls),
            "trajectory_reference_present": bool(str(replay.get("trajectory_path", "")).strip()),
            "business_logic_not_intervened": not bool(
                episode.get("governance", {}).get("intervenes_in_business_logic", True)
                if isinstance(episode.get("governance", {}), dict)
                else True
            ),
        }
        results.append(
            {
                "episode_id": str(episode.get("episode_id", "")),
                "replayable": all(checks.values()),
                "checks": checks,
                "validation_errors": validation.get("errors", []),
            }
        )
    return {
        "kind": "scientific_learning_replay_report",
        "schema_version": SCIENTIFIC_LEARNING_SCHEMA_VERSION,
        "episode_count": len(results),
        "replayable_count": len([item for item in results if item.get("replayable")]),
        "results": results,
    }


def run_learning_benchmark_checks(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for episode in episodes:
        if not isinstance(episode, dict):
            continue
        validation = validate_scientific_learning_episode(episode)
        scorecard = score_learning_episode_for_benchmark(episode)
        passed = bool(validation.get("valid", False)) and float(scorecard.get("total_score", 0.0) or 0.0) >= 0.65
        results.append(
            {
                "episode_id": str(episode.get("episode_id", "")),
                "passed": passed,
                "scorecard": scorecard,
                "validation": validation,
            }
        )
    return {
        "kind": "scientific_learning_benchmark_report",
        "schema_version": SCIENTIFIC_LEARNING_SCHEMA_VERSION,
        "episode_count": len(results),
        "passed_count": len([item for item in results if item.get("passed")]),
        "failed_count": len([item for item in results if not item.get("passed")]),
        "average_score": round(
            sum(float(item.get("scorecard", {}).get("total_score", 0.0) or 0.0) for item in results) / len(results),
            4,
        )
        if results
        else 0.0,
        "results": results,
    }


def score_learning_episode_for_benchmark(episode: dict[str, Any]) -> dict[str, Any]:
    steps = episode.get("steps", []) if isinstance(episode.get("steps", []), list) else []
    tool_calls = episode.get("tool_calls", []) if isinstance(episode.get("tool_calls", []), list) else []
    state_changes = episode.get("state_changes", []) if isinstance(episode.get("state_changes", []), list) else []
    memory_diffs = episode.get("memory_diffs", []) if isinstance(episode.get("memory_diffs", []), list) else []
    graph_diffs = episode.get("graph_diffs", []) if isinstance(episode.get("graph_diffs", []), list) else []
    eval_scores = episode.get("evaluation_scores", {}) if isinstance(episode.get("evaluation_scores", {}), dict) else {}
    collaboration_graph = episode.get("collaboration_graph", {}) if isinstance(episode.get("collaboration_graph", {}), dict) else {}
    components = {
        "schema": 1.0 if validate_scientific_learning_episode(episode).get("valid", False) else 0.0,
        "trace": min(1.0, len(steps) / 3.0),
        "tools": 1.0 if tool_calls else 0.5,
        "state": 1.0 if state_changes else 0.4,
        "memory_graph": min(1.0, (len(memory_diffs) + len(graph_diffs)) / 3.0),
        "evaluation": 1.0 if any(bool(v) for v in eval_scores.values()) else 0.4,
        "collaboration": 1.0 if int(collaboration_graph.get("edge_count", 0) or 0) > 0 else 0.5,
    }
    total = round(sum(components.values()) / len(components), 4)
    return {
        "total_score": total,
        "components": components,
        "interpretation": "ready" if total >= 0.8 else "usable" if total >= 0.65 else "needs_more_trace",
    }


def build_learning_dataset_manifest(
    *,
    dataset_path: Path,
    episodes: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    dataset_type: str,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    episode_ids = [str(item.get("episode_id", "")) for item in episodes if isinstance(item, dict)]
    return {
        "kind": "scientific_learning_dataset_manifest",
        "schema_version": SCIENTIFIC_LEARNING_SCHEMA_VERSION,
        "dataset_type": dataset_type,
        "dataset_path": str(dataset_path),
        "dataset_id": f"{_safe_name(dataset_type)}::{_stable_hash({'episodes': episode_ids, 'rows': len(rows), 'filters': filters or {}})[:12]}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "episode_count": len(episode_ids),
        "row_count": len(rows),
        "episode_ids": episode_ids[:1000],
        "filters": filters or {},
        "governance": {
            "training_enabled": False,
            "privacy_review_required_before_training": True,
            "source_layer": "observation_only_learning_runtime",
        },
        "content_hash": _stable_hash({"episode_ids": episode_ids, "rows": rows[:1000], "dataset_type": dataset_type}),
    }


def build_multi_agent_collaboration_graph(events: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    previous_actor = ""
    for index, event in enumerate(events, start=1):
        actor = str(event.get("actor", "") or "runtime")
        event_type = str(event.get("event_type", ""))
        nodes.setdefault(actor, {"actor_id": actor, "actor_type": _actor_type(actor), "event_count": 0})
        nodes[actor]["event_count"] += 1
        if previous_actor and previous_actor != actor:
            edges.append(
                {
                    "source": previous_actor,
                    "target": actor,
                    "relation": _collaboration_relation(event_type),
                    "event_index": index,
                    "event_type": event_type,
                }
            )
        previous_actor = actor
    return {
        "kind": "multi_agent_collaboration_graph",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": list(nodes.values()),
        "edges": edges,
        "interpretation": "temporal influence graph derived from runtime event order",
    }


def build_benchmark_seed_from_learning_episode(episode: ScientificLearningEpisode) -> dict[str, Any]:
    return {
        "kind": "scientific_learning_benchmark_seed",
        "schema_version": SCIENTIFIC_LEARNING_SCHEMA_VERSION,
        "case_id": f"benchmark-seed::{_safe_name(episode.episode_id)}",
        "source_episode_id": episode.episode_id,
        "topic": episode.topic,
        "scope": episode.scope,
        "input": {
            "task": episode.task,
            "actor_count": len(episode.actors),
            "tool_call_count": len(episode.tool_calls),
            "state_change_count": len(episode.state_changes),
        },
        "expected_behavior": {
            "must_preserve_business_logic": True,
            "must_emit_replayable_trace": True,
            "must_record_evaluation_scores": bool(episode.evaluation_scores),
            "must_keep_learning_layer_observation_only": True,
        },
        "rubric": [
            "episode schema is valid",
            "agent/tool/state/memory/graph traces are present when available",
            "human feedback slot exists even if empty",
            "training interfaces are declared but disabled",
        ],
    }


def _derive_actors(*, events: list[dict[str, Any]], result: Any, model: str) -> list[ScientificLearningActor]:
    actors: dict[str, ScientificLearningActor] = {}
    for event in events:
        actor = str(event.get("actor", "") or "runtime")
        if actor not in actors:
            actors[actor] = ScientificLearningActor(actor_id=actor, actor_type=_actor_type(actor), model=model)
    for step in getattr(result, "steps", []) or []:
        actor = str(getattr(step, "profile_name", "") or "specialist")
        actors.setdefault(
            actor,
            ScientificLearningActor(
                actor_id=actor,
                actor_type="agent",
                role=actor,
                model=str(getattr(step, "model_meta", {}).get("model", "") if isinstance(getattr(step, "model_meta", {}), dict) else ""),
            ),
        )
    return list(actors.values())


def _policy_rows(episode: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for step in episode.get("steps", []) if isinstance(episode.get("steps", []), list) else []:
        if not isinstance(step, dict):
            continue
        rows.append(
            {
                "kind": "policy_sample",
                "schema_version": SCIENTIFIC_LEARNING_SCHEMA_VERSION,
                "episode_id": str(episode.get("episode_id", "")),
                "step_id": str(step.get("step_id", "")),
                "actor_id": str(step.get("actor_id", "")),
                "observation": step.get("observation", {}) if isinstance(step.get("observation", {}), dict) else {},
                "action": step.get("action", {}) if isinstance(step.get("action", {}), dict) else {},
                "outcome": step.get("outcome", {}) if isinstance(step.get("outcome", {}), dict) else {},
                "reward_signals": step.get("reward_signals", {}) if isinstance(step.get("reward_signals", {}), dict) else {},
                "training_enabled": False,
            }
        )
    return rows


def _collaboration_rows(episode: dict[str, Any]) -> list[dict[str, Any]]:
    trace = episode.get("multi_agent_trace", []) if isinstance(episode.get("multi_agent_trace", []), list) else []
    return [
        {
            "kind": "multi_agent_collaboration_sample",
            "schema_version": SCIENTIFIC_LEARNING_SCHEMA_VERSION,
            "episode_id": str(episode.get("episode_id", "")),
            "topic": str(episode.get("topic", "")),
            "actors": episode.get("actors", []) if isinstance(episode.get("actors", []), list) else [],
            "multi_agent_trace": trace,
            "state_changes": episode.get("state_changes", []) if isinstance(episode.get("state_changes", []), list) else [],
            "training_enabled": False,
        }
    ]


def _reward_rows(episode: dict[str, Any], feedback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    episode_rating = _average_rating(feedback)
    for step in episode.get("steps", []) if isinstance(episode.get("steps", []), list) else []:
        if not isinstance(step, dict):
            continue
        rows.append(
            {
                "kind": "reward_model_sample",
                "schema_version": SCIENTIFIC_LEARNING_SCHEMA_VERSION,
                "episode_id": str(episode.get("episode_id", "")),
                "step_id": str(step.get("step_id", "")),
                "observation": step.get("observation", {}) if isinstance(step.get("observation", {}), dict) else {},
                "action": step.get("action", {}) if isinstance(step.get("action", {}), dict) else {},
                "outcome": step.get("outcome", {}) if isinstance(step.get("outcome", {}), dict) else {},
                "proxy_reward_signals": step.get("reward_signals", {}) if isinstance(step.get("reward_signals", {}), dict) else {},
                "human_episode_rating": episode_rating,
                "training_enabled": False,
            }
        )
    return rows


def _preference_rows(episode: dict[str, Any], feedback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    step_by_id = {
        str(step.get("step_id", "")): step
        for step in episode.get("steps", [])
        if isinstance(step, dict) and str(step.get("step_id", "")).strip()
    } if isinstance(episode.get("steps", []), list) else {}
    for item in feedback:
        preferred = str(item.get("preferred_step_id", "")).strip()
        rejected = str(item.get("rejected_step_id", "")).strip()
        if not preferred and not rejected:
            continue
        rows.append(
            {
                "kind": "preference_sample",
                "schema_version": SCIENTIFIC_LEARNING_SCHEMA_VERSION,
                "episode_id": str(episode.get("episode_id", "")),
                "preferred_step_id": preferred,
                "rejected_step_id": rejected,
                "preferred": step_by_id.get(preferred, {}),
                "rejected": step_by_id.get(rejected, {}),
                "feedback": item,
                "training_enabled": False,
            }
        )
    return rows


def _episode_level_row(episode: dict[str, Any], feedback: list[dict[str, Any]], *, target: str) -> dict[str, Any]:
    return {
        "kind": f"{_safe_name(target)}_episode_sample",
        "schema_version": SCIENTIFIC_LEARNING_SCHEMA_VERSION,
        "episode_id": str(episode.get("episode_id", "")),
        "topic": str(episode.get("topic", "")),
        "task": episode.get("task", {}) if isinstance(episode.get("task", {}), dict) else {},
        "evaluation_scores": episode.get("evaluation_scores", {}) if isinstance(episode.get("evaluation_scores", {}), dict) else {},
        "feedback_summary": {
            "feedback_count": len(feedback),
            "average_rating": _average_rating(feedback),
        },
        "training_enabled": False,
    }


def _average_rating(items: list[dict[str, Any]]) -> float | None:
    ratings = [float(item["rating"]) for item in items if isinstance(item.get("rating"), int | float)]
    if not ratings:
        return None
    return round(sum(ratings) / len(ratings), 4)


def _derive_learning_steps(events: list[dict[str, Any]]) -> list[ScientificLearningStep]:
    steps: list[ScientificLearningStep] = []
    for index, event in enumerate(events, start=1):
        event_type = str(event.get("event_type", "") or "runtime.event")
        payload = event.get("payload", {}) if isinstance(event.get("payload", {}), dict) else {}
        steps.append(
            ScientificLearningStep(
                step_id=f"step-{index:04d}",
                step_type=event_type,
                actor_id=str(event.get("actor", "") or "runtime"),
                timestamp=str(event.get("timestamp", "")),
                observation=_observation_from_event(event_type, payload),
                action=_action_from_event(event_type, payload),
                outcome=_outcome_from_event(event_type, payload),
                reward_signals=_reward_signals_from_event(event_type, payload),
                metadata={
                    "event_id": str(event.get("event_id", "")),
                    "project_id": str(event.get("project_id", "")),
                    "user_id": str(event.get("user_id", "")),
                    "group_id": str(event.get("group_id", "")),
                },
            )
        )
    return steps


def _extract_tool_calls(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for event in events:
        event_type = str(event.get("event_type", ""))
        if not event_type.startswith("tool.call"):
            continue
        payload = event.get("payload", {}) if isinstance(event.get("payload", {}), dict) else {}
        calls.append(
            {
                "event_id": str(event.get("event_id", "")),
                "actor": str(event.get("actor", "")),
                "tool_name": str(payload.get("tool_name", "")),
                "status": str(payload.get("status", "")),
                "inputs": payload.get("inputs", {}) if isinstance(payload.get("inputs", {}), dict) else {},
                "outputs": payload.get("outputs", {}) if isinstance(payload.get("outputs", {}), dict) else {},
                "artifacts": payload.get("artifacts", []) if isinstance(payload.get("artifacts", []), list) else [],
                "error": str(payload.get("error", "")),
            }
        )
    return calls


def _extract_multi_agent_trace(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    for event in events:
        event_type = str(event.get("event_type", ""))
        if not (
            event_type.startswith("specialist.")
            or event_type.startswith("agent.")
            or event_type.startswith("workflow.mid_run_control")
            or event_type.startswith("experiment.scheduler")
        ):
            continue
        payload = event.get("payload", {}) if isinstance(event.get("payload", {}), dict) else {}
        trace.append(
            {
                "event_type": event_type,
                "actor": str(event.get("actor", "")),
                "timestamp": str(event.get("timestamp", "")),
                "profile_name": str(payload.get("profile_name", "")),
                "state": str(payload.get("scheduler_state", payload.get("status", ""))),
                "summary": str(payload.get("rationale", payload.get("raw_output_preview", "")))[:500],
            }
        )
    return trace


def _extract_event_payloads(events: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    return [
        event.get("payload", {})
        for event in events
        if str(event.get("event_type", "")) == event_type and isinstance(event.get("payload", {}), dict)
    ]


def _derive_graph_diffs(claim_graph: dict[str, Any]) -> list[dict[str, Any]]:
    keys = ["claims", "hypotheses", "evidence", "asset_registry", "typed_research_graph_summary"]
    diffs: list[dict[str, Any]] = []
    for key in keys:
        value = claim_graph.get(key)
        if isinstance(value, list):
            count = len(value)
            identifiers = [_item_identifier(item) for item in value[:100] if isinstance(item, dict)]
        elif isinstance(value, dict):
            count = len(value)
            identifiers = sorted(str(item) for item in value.keys())[:100]
        else:
            count = 0
            identifiers = []
        if count:
            diffs.append(
                {
                    "target": key,
                    "action": "observed_final_state",
                    "count": count,
                    "identifiers": [item for item in identifiers if item],
                    "content_hash": _stable_hash(value),
                }
            )
    return diffs


def _derive_state_changes(*, events: list[dict[str, Any]], research_state: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for event in events:
        event_type = str(event.get("event_type", ""))
        if event_type in {"workflow.started", "workflow.completed", "workflow.failed"} or "scheduler" in event_type:
            changes.append(
                {
                    "event_type": event_type,
                    "actor": str(event.get("actor", "")),
                    "timestamp": str(event.get("timestamp", "")),
                    "payload": event.get("payload", {}) if isinstance(event.get("payload", {}), dict) else {},
                }
            )
    for key in [
        "research_program_summary",
        "experiment_execution_loop_summary",
        "hypothesis_system_summary",
        "kaivu_evaluation_harness_summary",
        "scientific_decision_summary",
    ]:
        value = research_state.get(key)
        if isinstance(value, dict) and value:
            changes.append({"event_type": "state.final_summary", "target": key, "payload": value})
    return changes


def _derive_evaluation_scores(research_state: dict[str, Any]) -> dict[str, Any]:
    evaluation = research_state.get("kaivu_evaluation_harness_summary", {})
    if not isinstance(evaluation, dict):
        evaluation = {}
    benchmark = research_state.get("scientific_evaluation_benchmark_summary", {})
    if not isinstance(benchmark, dict):
        benchmark = {}
    release = research_state.get("scientific_release_gate_summary", {})
    if not isinstance(release, dict):
        release = {}
    return {
        "kaivu_evaluation_harness": evaluation,
        "scientific_evaluation_benchmark": benchmark,
        "scientific_release_gate": release,
    }


def _derive_artifacts(run_manifest: dict[str, Any], *, trajectory_path: str, replay_case_path: str) -> list[dict[str, Any]]:
    artifacts = run_manifest.get("artifacts", []) if isinstance(run_manifest.get("artifacts", []), list) else []
    derived = [item for item in artifacts if isinstance(item, dict)]
    if trajectory_path:
        derived.append({"kind": "trajectory", "path": trajectory_path})
    if replay_case_path:
        derived.append({"kind": "replay_case", "path": replay_case_path})
    return derived


def _observation_from_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "profile_name": str(payload.get("profile_name", "")),
        "parsed_keys": payload.get("parsed_keys", []) if isinstance(payload.get("parsed_keys", []), list) else [],
        "scheduler_state": str(payload.get("scheduler_state", "")),
        "tool_name": str(payload.get("tool_name", "")),
    }


def _action_from_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "action_name": str(payload.get("action", payload.get("top_action", ""))),
        "tool_name": str(payload.get("tool_name", "")),
        "selected_experiment_id": str(payload.get("top_experiment_id", payload.get("experiment_id", ""))),
        "requires_human_approval": bool(payload.get("requires_human_approval", False)),
    }


def _outcome_from_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "status": str(payload.get("status", "")),
        "error": str(payload.get("error", "")),
        "report_path": str(payload.get("report_path", "")),
        "structured_object_counts": payload.get("structured_object_counts", {})
        if isinstance(payload.get("structured_object_counts", {}), dict)
        else {},
    }


def _reward_signals_from_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    usage = payload.get("usage_summary", {}) if isinstance(payload.get("usage_summary", {}), dict) else {}
    structured_counts = (
        payload.get("structured_object_counts", {})
        if isinstance(payload.get("structured_object_counts", {}), dict)
        else {}
    )
    scientific_quality_proxy = min(
        1.0,
        (
            int(structured_counts.get("hypotheses_count", 0) or 0)
            + int(structured_counts.get("evidence_count", 0) or 0)
            + int(structured_counts.get("claims_count", 0) or 0)
            + int(structured_counts.get("negative_results_count", 0) or 0)
        )
        / 8.0,
    )
    return {
        "proxy_only": True,
        "status_success": str(payload.get("status", "")).lower() in {"ok", "completed", "success"},
        "token_cost_usd": usage.get("estimated_cost_usd", 0.0),
        "has_error": bool(payload.get("error", "")),
        "scientific_quality_proxy": round(scientific_quality_proxy, 4),
        "has_hypothesis_signal": int(structured_counts.get("hypotheses_count", 0) or 0) > 0,
        "has_evidence_signal": int(structured_counts.get("evidence_count", 0) or 0) > 0,
        "has_negative_result_signal": int(structured_counts.get("negative_results_count", 0) or 0) > 0,
    }


def _infer_task_type(research_state: dict[str, Any]) -> str:
    if research_state.get("discipline_agent_summary"):
        agent = research_state.get("discipline_agent_summary", {})
        return (
            str(agent.get("task_type", "")).strip()
            or str(agent.get("discipline", "")).strip()
            or "discipline_agent"
        )
    if research_state.get("experiment_execution_loop_summary"):
        return "scientific_experiment_planning"
    if research_state.get("systematic_review_summary"):
        return "literature_review"
    return "scientific_workflow"


def _state_value(state: dict[str, Any], key: str, subkey: str) -> str:
    value = state.get(key, {})
    if not isinstance(value, dict):
        return ""
    return str(value.get(subkey, ""))


def _actor_type(actor: str) -> str:
    lowered = actor.lower()
    if "tool" in lowered:
        return "tool"
    if "scheduler" in lowered or "controller" in lowered:
        return "controller"
    if "harness" in lowered or "runtime" in lowered:
        return "runtime"
    return "agent"


def _collaboration_relation(event_type: str) -> str:
    if "scheduler" in event_type:
        return "influenced_scheduler_state"
    if "tool.call" in event_type:
        return "provided_tool_context"
    if "mid_run_control" in event_type:
        return "triggered_control_review"
    if "specialist.step" in event_type:
        return "handoff_between_specialists"
    return "temporal_precedes"


def _item_identifier(item: dict[str, Any]) -> str:
    for key in ["id", "claim_id", "hypothesis_id", "evidence_id", "asset_id", "node_id", "path", "title"]:
        value = str(item.get(key, "")).strip()
        if value:
            return value
    return _stable_hash(item)[:12]


def _stable_hash(value: Any) -> str:
    import hashlib

    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe_name(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "learning-episode"


