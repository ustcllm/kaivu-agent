from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


RunStatus = Literal["queued", "running", "completed", "failed"]


class WorkflowRunRequest(BaseModel):
    topic: str = Field(..., description="Research topic or scientific question.")
    dynamic_routing: bool = Field(default=True)
    report_path: str | None = Field(default=None)
    discipline: str = ""
    user_id: str = ""
    project_id: str = ""
    group_id: str = ""
    group_role: str = ""


class WorkflowRunAccepted(BaseModel):
    run_id: str
    status: RunStatus


class WorkflowRunListItem(BaseModel):
    run_id: str
    topic: str
    status: RunStatus
    discipline: str = ""
    user_id: str = ""
    project_id: str = ""
    group_id: str = ""
    group_role: str = ""
    report_path: str | None = None
    error: str | None = None


class WorkflowStepResponse(BaseModel):
    profile_name: str
    raw_output: str
    parsed_output: dict[str, Any]
    model_meta: dict[str, Any]


class WorkflowRunResponse(BaseModel):
    run_id: str
    status: RunStatus
    topic: str
    discipline: str = ""
    user_id: str = ""
    project_id: str = ""
    group_id: str = ""
    group_role: str = ""
    report_path: str | None = None
    error: str | None = None
    steps: list[WorkflowStepResponse] = Field(default_factory=list)
    claim_graph: dict[str, Any] = Field(default_factory=dict)
    research_state: dict[str, Any] = Field(default_factory=dict)
    run_manifest: dict[str, Any] = Field(default_factory=dict)


class ReportResponse(BaseModel):
    run_id: str
    status: RunStatus
    report_markdown: str | None = None
    report_path: str | None = None


class UsageProfileSummary(BaseModel):
    profile_name: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    rounds: int


class UsageSummaryResponse(BaseModel):
    run_id: str
    status: RunStatus
    total: dict[str, Any] = Field(default_factory=dict)
    by_profile: list[UsageProfileSummary] = Field(default_factory=list)


class MemorySearchRequest(BaseModel):
    query: str
    max_results: int = Field(default=5, ge=1, le=20)
    discipline: str = ""
    user_id: str | None = None
    project_id: str | None = None
    group_id: str | None = None
    scopes: list[str] = Field(default_factory=list)


class MemorySaveRequest(BaseModel):
    title: str
    summary: str
    memory_type: str
    scope: str
    content: str
    tags: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    evidence_level: str = "medium"
    confidence: str = "medium"
    status: str = "active"
    owner_agent: str = "service"
    discipline: str = ""
    user_id: str = ""
    project_id: str = ""
    group_id: str = ""
    visibility: str | None = None
    promotion_status: str | None = None
    needs_review: bool = False
    review_due_at: str | None = None
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    derived_from: list[str] = Field(default_factory=list)
    conflicts_with: list[str] = Field(default_factory=list)
    validated_by: list[str] = Field(default_factory=list)
    filename: str | None = None


class MemoryReviewRequest(BaseModel):
    filename: str
    status: str | None = None
    needs_review: bool | None = None
    review_due_at: str | None = None
    superseded_by: str | None = None
    conflicts_with: list[str] | None = None
    validated_by: list[str] | None = None
    last_verified_at: str | None = None
    visibility: str | None = None
    promotion_status: str | None = None
    discipline: str = ""
    user_id: str = ""
    project_id: str = ""
    group_id: str = ""
    group_role: str = ""


class MemoryPromoteRequest(BaseModel):
    filename: str
    target_scope: str
    target_visibility: str | None = None
    discipline: str = ""
    user_id: str = ""
    project_id: str = ""
    group_id: str = ""
    group_role: str = ""


class MemoryPromoteResponse(BaseModel):
    ok: bool
    mode: str
    path: str | None = None
    filename: str | None = None
    message: str = ""


class MemoryProposalRecord(BaseModel):
    path: str
    filename: str
    title: str
    summary: str
    source_scope: str
    target_scope: str
    user_id: str = ""
    project_id: str = ""
    group_id: str = ""
    visibility: str
    proposed_by: str = ""
    validated_by: list[str] = Field(default_factory=list)
    needs_review: bool = True


class MemoryProposalListResponse(BaseModel):
    results: list[MemoryProposalRecord] = Field(default_factory=list)


class MemoryProposalDecisionRequest(BaseModel):
    filename: str
    discipline: str = ""
    user_id: str = ""
    project_id: str = ""
    group_id: str = ""
    group_role: str = ""
    target_scope: str | None = None
    target_visibility: str | None = None


class MemoryAutoGovernRequest(BaseModel):
    target_scope: str = "project"
    automation_mode: str = "safe"
    dry_run: bool = False
    max_items: int = Field(default=25, ge=1, le=100)
    discipline: str = ""
    user_id: str = ""
    project_id: str = ""
    group_id: str = ""
    group_role: str = ""


class MemoryAutoGovernResponse(BaseModel):
    ok: bool
    automation_mode: str = ""
    target_scope: str = ""
    planned_count: int = 0
    applied_count: int = 0
    events_written: int = 0
    results: list[dict[str, Any]] = Field(default_factory=list)


class MemoryCompactRequest(BaseModel):
    discipline: str = ""
    user_id: str = ""
    project_id: str = ""
    group_id: str = ""
    scopes: list[str] = Field(default_factory=list)
    max_groups: int = Field(default=20, ge=1, le=100)
    dry_run: bool = False
    semantic_guard: bool = True


class MemoryCompactResponse(BaseModel):
    ok: bool
    dry_run: bool = False
    candidate_group_count: int = 0
    action_count: int = 0
    skipped_count: int = 0
    archive_dir: str = ""
    rollback_manifest_path: str = ""
    actions: list[dict[str, Any]] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)


class MemoryAuditEvent(BaseModel):
    kind: str
    actor: str = ""
    detail: str = ""
    timestamp: str = ""


class MemoryAuditResponse(BaseModel):
    filename: str
    title: str = ""
    status: str = ""
    scope: str = ""
    promotion_status: str = ""
    needs_review: bool = False
    events: list[MemoryAuditEvent] = Field(default_factory=list)


class MemoryRecordResponse(BaseModel):
    path: str
    title: str
    summary: str
    memory_type: str
    scope: str
    tags: list[str]
    source_refs: list[str]
    evidence_level: str
    confidence: str
    status: str
    user_id: str
    project_id: str
    group_id: str
    visibility: str
    promotion_status: str
    last_verified_at: str
    needs_review: bool
    review_due_at: str
    derived_from: list[str]
    conflicts_with: list[str]
    validated_by: list[str]


class MemorySearchResponse(BaseModel):
    results: list[MemoryRecordResponse] = Field(default_factory=list)


class MemoryMutationResponse(BaseModel):
    ok: bool
    path: str | None = None
    filename: str | None = None
    mode: str | None = None
    message: str | None = None


class GraphResponse(BaseModel):
    run_id: str
    status: RunStatus
    claim_graph: dict[str, Any] = Field(default_factory=dict)


class TypedGraphNodeResponse(BaseModel):
    node_id: str
    node_type: str
    label: str
    project_id: str = ""
    topic: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TypedGraphEdgeResponse(BaseModel):
    edge_id: str
    source_id: str
    target_id: str
    relation: str
    project_id: str = ""
    topic: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TypedGraphSnapshotResponse(BaseModel):
    snapshot_id: str
    project_id: str
    topic: str
    node_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TypedGraphQueryResponse(BaseModel):
    project_id: str = ""
    topic: str = ""
    summary: dict[str, Any] = Field(default_factory=dict)
    nodes: list[TypedGraphNodeResponse] = Field(default_factory=list)
    edges: list[TypedGraphEdgeResponse] = Field(default_factory=list)
    snapshots: list[TypedGraphSnapshotResponse] = Field(default_factory=list)


class ResearchEventListResponse(BaseModel):
    results: list[dict[str, Any]] = Field(default_factory=list)


class ResearchEventSummaryResponse(BaseModel):
    project_id: str = ""
    topic: str = ""
    event_count: int = 0
    event_type_counts: dict[str, int] = Field(default_factory=dict)
    asset_type_counts: dict[str, int] = Field(default_factory=dict)
    actor_counts: dict[str, int] = Field(default_factory=dict)
    latest_event_id: str = ""
    latest_timestamp: str = ""


class LiteratureIngestRequest(BaseModel):
    source_type: str
    title: str
    content: str
    filename: str | None = None
    discipline: str = ""
    user_id: str = ""
    project_id: str = ""
    group_id: str = ""
    target_scope: str = "project"
    user_mode: str = "auto"
    impact_level: str = "medium"
    conflict_level: str = "low"
    confidence: str = "medium"
    group_role: str = ""


class LiteratureIngestResponse(BaseModel):
    saved: bool
    path: str
    bucket: str
    mode: str = "autonomous"
    requires_confirmation: bool = False
    needs_review: bool = False
    policy: dict[str, Any] = Field(default_factory=dict)


class LiteratureQueryResponse(BaseModel):
    results: list[dict[str, Any]] = Field(default_factory=list)


class LiteratureLintResponse(BaseModel):
    findings: list[str] = Field(default_factory=list)
    lint_path: str


class ThreadMessageRequest(BaseModel):
    role: str
    content: str
    created_at: str


class ThreadCreateRequest(BaseModel):
    title: str
    created_at: str
    user_id: str = ""
    project_id: str = ""
    group_id: str = ""
    group_role: str = ""
    initial_message: ThreadMessageRequest | None = None


class ThreadUpdateRequest(BaseModel):
    title: str | None = None
    run_id: str | None = None
    snapshot: dict[str, Any] | None = None
    archived: bool | None = None
    user_id: str | None = None
    project_id: str | None = None
    group_id: str | None = None
    group_role: str | None = None
    updated_at: str


class ThreadMessageCreateRequest(BaseModel):
    role: str
    content: str
    created_at: str


class ThreadMessageResponse(BaseModel):
    role: str
    content: str
    created_at: str


class ThreadResponse(BaseModel):
    thread_id: str
    title: str
    run_id: str | None = None
    user_id: str = ""
    project_id: str = ""
    group_id: str = ""
    group_role: str = ""
    snapshot: dict[str, Any] = Field(default_factory=dict)
    archived: bool = False
    chat: list[ThreadMessageResponse] = Field(default_factory=list)
    created_at: str
    updated_at: str


class GroupRoleUpdateRequest(BaseModel):
    group_id: str
    user_id: str
    role: str


class GroupRoleResponse(BaseModel):
    group_id: str
    user_id: str
    role: str


class CollaborationMemberUpsertRequest(BaseModel):
    user_id: str
    role: str
    display_name: str = ""


class CollaborationMemberResponse(BaseModel):
    user_id: str
    role: str
    display_name: str = ""


class CollaborationMemberListResponse(BaseModel):
    scope: str
    scope_id: str
    members: list[CollaborationMemberResponse] = Field(default_factory=list)


class ExperimentScopeFields(BaseModel):
    discipline: str = ""
    user_id: str = ""
    project_id: str = ""
    group_id: str = ""
    group_role: str = ""


class ExperimentSpecificationPayload(ExperimentScopeFields):
    experiment_id: str
    title: str
    discipline: str
    hypothesis_ids: list[str] = Field(default_factory=list)
    research_question: str = ""
    goal: str = ""
    decision_type: str = "validate"
    success_criteria: list[str] = Field(default_factory=list)
    failure_criteria: list[str] = Field(default_factory=list)
    priority: str = "medium"
    status: str = "planned"
    lineage_parent_experiment_id: str = ""
    lineage_note: str = ""
    economics_summary: dict[str, Any] = Field(default_factory=dict)
    adjudication_context: dict[str, Any] = Field(default_factory=dict)
    discipline_payload: dict[str, Any] = Field(default_factory=dict)


class ExperimentalProtocolPayload(ExperimentScopeFields):
    protocol_id: str
    experiment_id: str
    version: str
    inputs: list[str] = Field(default_factory=list)
    controls: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    measurement_plan: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    risk_points: list[str] = Field(default_factory=list)
    quality_control_checks: list[str] = Field(default_factory=list)
    lineage_parent_protocol_id: str = ""
    amendment_reason: str = ""
    governance_checks: list[str] = Field(default_factory=list)
    approval_requirements: list[str] = Field(default_factory=list)
    defer_reasons: list[str] = Field(default_factory=list)
    adjudication_questions: list[str] = Field(default_factory=list)
    discipline_payload: dict[str, Any] = Field(default_factory=dict)


class ExperimentRunPayload(ExperimentScopeFields):
    run_id: str
    experiment_id: str
    protocol_id: str
    status: str = "planned"
    operator: str = ""
    started_at: str = ""
    ended_at: str = ""
    configuration_snapshot: dict[str, Any] = Field(default_factory=dict)
    environment_snapshot: dict[str, Any] = Field(default_factory=dict)
    seed: int | None = None
    approval_status: str = "pending"
    approved_by: str = ""
    approval_note: str = ""
    supersedes_run_id: str = ""
    governance_stage: str = ""
    paused_reason: str = ""
    cost_pressure: str = ""
    adjudication_status: str = ""
    discipline_payload: dict[str, Any] = Field(default_factory=dict)


class QualityControlReviewPayload(ExperimentScopeFields):
    review_id: str
    run_id: str
    experiment_id: str = ""
    quality_control_status: str
    issues: list[str] = Field(default_factory=list)
    possible_artifacts: list[str] = Field(default_factory=list)
    protocol_deviations: list[str] = Field(default_factory=list)
    quality_control_checks_run: list[str] = Field(default_factory=list)
    missing_quality_control_checks: list[str] = Field(default_factory=list)
    affected_outputs: list[str] = Field(default_factory=list)
    repeat_required: bool = False
    blocking_severity: str = "low"
    evidence_reliability: str = "medium"
    usable_for_interpretation: bool = True
    recommended_action: str = ""
    discipline_payload: dict[str, Any] = Field(default_factory=dict)


class InterpretationRecordPayload(ExperimentScopeFields):
    interpretation_id: str
    run_id: str
    experiment_id: str = ""
    supported_hypothesis_ids: list[str] = Field(default_factory=list)
    weakened_hypothesis_ids: list[str] = Field(default_factory=list)
    inconclusive_hypothesis_ids: list[str] = Field(default_factory=list)
    negative_result: bool = False
    claim_updates: list[str] = Field(default_factory=list)
    confidence: str = "medium"
    next_decision: str = ""
    discipline_payload: dict[str, Any] = Field(default_factory=dict)


class ExperimentRecordListResponse(BaseModel):
    results: list[dict[str, Any]] = Field(default_factory=list)


class RunHandoffSubmitRequest(ExperimentScopeFields):
    topic: str
    discipline: str = ""
    contract: dict[str, Any]
    payload: dict[str, Any]
    claim_graph: dict[str, Any] = Field(default_factory=dict)
    write_memory: bool = True
    write_events: bool = True


class RunHandoffSubmitResponse(BaseModel):
    ok: bool
    bundle: dict[str, Any] = Field(default_factory=dict)
    backpropagation: dict[str, Any] = Field(default_factory=dict)
    updated_claim_graph: dict[str, Any] = Field(default_factory=dict)
    memory_results: list[dict[str, Any]] = Field(default_factory=list)
    events_written: int = 0
    registry_summary: dict[str, Any] = Field(default_factory=dict)


class ProtocolAmendmentRequest(ExperimentScopeFields):
    source_protocol_id: str
    new_protocol_id: str
    new_version: str
    amendment_reason: str
    steps: list[str] = Field(default_factory=list)
    quality_control_checks: list[str] = Field(default_factory=list)
    governance_checks: list[str] = Field(default_factory=list)
    approval_requirements: list[str] = Field(default_factory=list)
    defer_reasons: list[str] = Field(default_factory=list)
    adjudication_questions: list[str] = Field(default_factory=list)


class RunApprovalRequest(ExperimentScopeFields):
    run_id: str
    approved_by: str
    approval_note: str = ""
    approval_status: str = "approved"


class ExperimentSpecificationLifecycleRequest(ExperimentScopeFields):
    experiment_id: str
    reason: str = ""


class ExperimentalProtocolLifecycleRequest(ExperimentScopeFields):
    protocol_id: str
    reason: str = ""


class ExperimentRunLifecycleRequest(ExperimentScopeFields):
    run_id: str
    reason: str = ""


class EvaluationSignalResponse(BaseModel):
    benchmark_readiness: str = ""
    regression_risk: str = ""
    validation_targets: list[str] = Field(default_factory=list)
    release_blockers: list[str] = Field(default_factory=list)


class EvaluationHistoryResponse(BaseModel):
    results: list[dict[str, Any]] = Field(default_factory=list)


class LearningEpisodeListResponse(BaseModel):
    results: list[dict[str, Any]] = Field(default_factory=list)


class LearningFeedbackRequest(BaseModel):
    episode_id: str
    feedback_type: str = "human_preference"
    rating: float | None = None
    preferred_step_id: str = ""
    rejected_step_id: str = ""
    comment: str = ""
    reviewer_id: str = ""
    discipline: str = ""
    user_id: str = ""
    project_id: str = ""
    group_id: str = ""


class LearningFeedbackResponse(BaseModel):
    ok: bool
    path: str = ""
    message: str = ""


class LearningValidationResponse(BaseModel):
    schema_version: str = ""
    episode_count: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    results: list[dict[str, Any]] = Field(default_factory=list)


class LearningFeedbackSummaryResponse(BaseModel):
    episode_count: int = 0
    feedback_count: int = 0
    episode_feedback_count: int = 0
    orphan_feedback_count: int = 0
    preference_pair_count: int = 0
    average_rating: float | None = None
    episodes: list[dict[str, Any]] = Field(default_factory=list)


class LearningExportRequest(BaseModel):
    target: str = "policy"
    limit: int = Field(default=1000, ge=1, le=10000)
    filename: str | None = None
    discipline: str = ""
    user_id: str = ""
    project_id: str = ""
    group_id: str = ""


class LearningArtifactResponse(BaseModel):
    ok: bool
    path: str = ""
    kind: str = ""
    message: str = ""


class ContextPackRequest(BaseModel):
    query: str
    discipline: str = ""
    user_id: str = ""
    project_id: str = ""
    group_id: str = ""
    max_memory_items: int = Field(default=8, ge=0, le=50)
    max_literature_items: int = Field(default=6, ge=0, le=50)
    max_graph_items: int = Field(default=8, ge=0, le=50)
    max_failed_attempt_items: int = Field(default=6, ge=0, le=50)
    render_prompt: bool = False
    max_prompt_chars: int = Field(default=12000, ge=1000, le=50000)


class ContextPackResponse(BaseModel):
    pack: dict[str, Any] = Field(default_factory=dict)
    rendered_prompt_context: str = ""


