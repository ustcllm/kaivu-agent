from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas import (
    LearningArtifactResponse,
    LearningEpisodeListResponse,
    LearningExportRequest,
    LearningFeedbackRequest,
    LearningFeedbackResponse,
    LearningFeedbackSummaryResponse,
    LearningValidationResponse,
)


router = APIRouter(prefix="/learning", tags=["learning"])


@router.get("/episodes", response_model=LearningEpisodeListResponse)
async def list_learning_episodes(
    request: Request,
    limit: int = 50,
    discipline: str = "",
    project_id: str = "",
    group_id: str = "",
    user_id: str = "",
) -> LearningEpisodeListResponse:
    runtime = request.app.state.workflow_runtime
    return LearningEpisodeListResponse(
        results=runtime.list_learning_episodes(
            limit=limit,
            discipline=discipline,
            project_id=project_id,
            group_id=group_id,
            user_id=user_id,
        )
    )


@router.post("/feedback", response_model=LearningFeedbackResponse)
async def append_learning_feedback(
    request: Request,
    payload: LearningFeedbackRequest,
) -> LearningFeedbackResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.append_learning_feedback(payload.model_dump())
    return LearningFeedbackResponse(**result)


@router.get("/validate", response_model=LearningValidationResponse)
async def validate_learning_episodes(
    request: Request,
    limit: int = 1000,
    discipline: str = "",
    project_id: str = "",
    group_id: str = "",
    user_id: str = "",
) -> LearningValidationResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.validate_learning_episodes(
        limit=limit,
        discipline=discipline,
        project_id=project_id,
        group_id=group_id,
        user_id=user_id,
    )
    return LearningValidationResponse(**result)


@router.get("/feedback/summary", response_model=LearningFeedbackSummaryResponse)
async def summarize_learning_feedback(
    request: Request,
    limit: int = 1000,
    discipline: str = "",
    project_id: str = "",
    group_id: str = "",
    user_id: str = "",
) -> LearningFeedbackSummaryResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.summarize_learning_feedback(
        limit=limit,
        discipline=discipline,
        project_id=project_id,
        group_id=group_id,
        user_id=user_id,
    )
    return LearningFeedbackSummaryResponse(**result)


@router.post("/export-training", response_model=LearningArtifactResponse)
async def export_learning_training_dataset(
    request: Request,
    payload: LearningExportRequest,
) -> LearningArtifactResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.export_learning_training_dataset(payload.model_dump())
    return LearningArtifactResponse(**result)


@router.post("/build-benchmark", response_model=LearningArtifactResponse)
async def build_learning_benchmark_dataset(
    request: Request,
    payload: LearningExportRequest,
) -> LearningArtifactResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.build_learning_benchmark_dataset(
        limit=payload.limit,
        discipline=payload.discipline,
        project_id=payload.project_id,
        group_id=payload.group_id,
        user_id=payload.user_id,
    )
    return LearningArtifactResponse(**result)


@router.post("/build-replay", response_model=LearningArtifactResponse)
async def build_learning_replay_index(
    request: Request,
    payload: LearningExportRequest,
) -> LearningArtifactResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.build_learning_replay_index(
        limit=payload.limit,
        discipline=payload.discipline,
        project_id=payload.project_id,
        group_id=payload.group_id,
        user_id=payload.user_id,
    )
    return LearningArtifactResponse(**result)


@router.post("/run-replay-checks", response_model=LearningArtifactResponse)
async def run_learning_replay_checks(
    request: Request,
    payload: LearningExportRequest,
) -> LearningArtifactResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.run_learning_replay_checks(
        limit=payload.limit,
        discipline=payload.discipline,
        project_id=payload.project_id,
        group_id=payload.group_id,
        user_id=payload.user_id,
    )
    return LearningArtifactResponse(**result)


@router.post("/run-benchmark-checks", response_model=LearningArtifactResponse)
async def run_learning_benchmark_checks(
    request: Request,
    payload: LearningExportRequest,
) -> LearningArtifactResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.run_learning_benchmark_checks(
        limit=payload.limit,
        discipline=payload.discipline,
        project_id=payload.project_id,
        group_id=payload.group_id,
        user_id=payload.user_id,
    )
    return LearningArtifactResponse(**result)


