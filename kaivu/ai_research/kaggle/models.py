from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CompetitionInfo:
    competition_name: str
    competition_url: str = ""
    overview: str = ""
    metric: str = ""
    metric_direction: str = ""
    task_type: str = ""
    target_column: str = ""
    id_column: str = ""
    submission_format: dict[str, Any] = field(default_factory=dict)
    rules_summary: dict[str, Any] = field(default_factory=dict)
    timeline: dict[str, Any] = field(default_factory=dict)
    confidence: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DataInventory:
    data_dir: str
    files: list[dict[str, Any]] = field(default_factory=list)
    detected_train_file: str = ""
    detected_test_file: str = ""
    detected_sample_submission: str = ""
    inferred_target_column: str = ""
    inferred_id_column: str = ""
    inferred_task_type: str = ""
    inventory_state: str = "draft"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class KaggleCommunityResearch:
    discussion_findings: list[dict[str, Any]] = field(default_factory=list)
    notebook_patterns: list[dict[str, Any]] = field(default_factory=list)
    winner_solution_patterns: list[dict[str, Any]] = field(default_factory=list)
    anti_patterns: list[dict[str, Any]] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    research_state: str = "local_context_only"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class KaggleMethodLiteratureReview:
    recommended_methods: list[dict[str, Any]] = field(default_factory=list)
    method_risks: list[dict[str, Any]] = field(default_factory=list)
    transferable_principles: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CompetitionResearchDossier:
    competition_info: CompetitionInfo
    data_inventory: DataInventory
    community_research: KaggleCommunityResearch
    method_literature_review: KaggleMethodLiteratureReview
    prior_kaggle_memory: dict[str, Any] = field(default_factory=dict)
    context_pack: dict[str, Any] = field(default_factory=dict)
    open_questions: list[str] = field(default_factory=list)
    confidence: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "competition_info": self.competition_info.to_dict(),
            "data_inventory": self.data_inventory.to_dict(),
            "community_research": self.community_research.to_dict(),
            "method_literature_review": self.method_literature_review.to_dict(),
            "prior_kaggle_memory": self.prior_kaggle_memory,
            "context_pack": self.context_pack,
            "open_questions": self.open_questions,
            "confidence": self.confidence,
        }


@dataclass(slots=True)
class ValidationProtocol:
    protocol_id: str
    split_strategy: str
    folds: int = 5
    metric: str = ""
    metric_direction: str = ""
    group_column: str = ""
    time_column: str = ""
    leakage_guards: list[str] = field(default_factory=list)
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SubmissionPlan:
    should_submit: bool
    submission_file_name: str = "submission.csv"
    max_submissions_this_cycle: int = 1
    public_leaderboard_overfit_risk: str = "medium"
    validation_required_before_submit: bool = True
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class KaggleExperimentCandidate:
    experiment_id: str
    title: str
    hypothesis: str
    model_family: str
    action: str = "train_validate_predict"
    priority: str = "medium"
    expected_cv_gain: float = 0.0
    estimated_cost: float = 1.0
    leakage_risk: str = "medium"
    leaderboard_overfit_risk: str = "medium"
    search_space: dict[str, Any] = field(default_factory=dict)
    success_criteria: list[str] = field(default_factory=list)
    failure_criteria: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class KaggleTaskAdapterInput:
    competition_name: str
    data_dir: str
    work_dir: str
    user_goal: str = "build reliable baseline"
    competition_url: str = ""
    target_column: str = ""
    id_column: str = ""
    metric: str = ""
    task_type: str = ""
    constraints: dict[str, Any] = field(default_factory=dict)
    dossier: dict[str, Any] = field(default_factory=dict)
    ai_research_context: dict[str, Any] = field(default_factory=dict)
    context_pack: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def resolved_work_dir(self, cwd: str | Path) -> Path:
        path = Path(self.work_dir) if self.work_dir else Path("artifacts") / "kaggle" / _slugify(self.competition_name)
        return path if path.is_absolute() else Path(cwd).resolve() / path


@dataclass(slots=True)
class KaggleTaskAdapterOutput:
    competition_spec: dict[str, Any]
    dataset_profile: dict[str, Any]
    leakage_report: dict[str, Any]
    validation_protocol: dict[str, Any]
    modeling_hypotheses: list[dict[str, Any]]
    experiment_candidates: list[dict[str, Any]]
    execution_plan: dict[str, Any]
    submission_plan: dict[str, Any]
    memory_items: list[dict[str, Any]]
    graph_facts: list[dict[str, Any]]
    learning_metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "kaggle"


