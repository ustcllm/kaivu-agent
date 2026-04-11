from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AIResearchWorkflowInput:
    research_question: str
    dataset_path: str | None = None
    target_column: str = ""
    id_column: str = ""
    task_type: str = ""
    metric: str = ""
    metric_direction: str = ""
    available_compute: str = "local_cpu"
    candidate_models: list[str] = field(default_factory=list)
    research_context: dict[str, Any] = field(default_factory=dict)
    literature_context: dict[str, Any] = field(default_factory=dict)
    benchmark_context: dict[str, Any] = field(default_factory=dict)
    repo_context: dict[str, Any] = field(default_factory=dict)
    prior_memory_context: dict[str, Any] = field(default_factory=dict)
    project_id: str = ""
    output_dir: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def resolved_output_dir(self, cwd: str | Path) -> Path:
        if self.output_dir:
            path = Path(self.output_dir)
            return path if path.is_absolute() else Path(cwd).resolve() / path
        return Path(cwd).resolve() / ".state" / "ai_research" / _slugify(self.research_question)


@dataclass(slots=True)
class AIResearchWorkflowResult:
    problem_profile: dict[str, Any]
    dataset_profile: dict[str, Any]
    contamination_risk_report: dict[str, Any]
    evaluation_protocol: dict[str, Any]
    training_recipe: dict[str, Any]
    ablation_plan: dict[str, Any]
    artifact_contract: dict[str, Any]
    next_actions: list[dict[str, Any]]
    output_dir: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-")[:120] or "ai-research"
