from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas import ResearchEventListResponse, ResearchEventSummaryResponse


router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=ResearchEventListResponse)
async def list_research_events(
    request: Request,
    discipline: str = "",
    project_id: str = "",
    group_id: str = "",
    user_id: str = "",
    topic: str = "",
    event_type: str = "",
    limit: int = 100,
) -> ResearchEventListResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.list_research_events(
        discipline=discipline,
        project_id=project_id,
        group_id=group_id,
        user_id=user_id,
        topic=topic,
        event_type=event_type,
        limit=max(1, min(limit, 1000)),
    )
    return ResearchEventListResponse(**result)


@router.get("/summary", response_model=ResearchEventSummaryResponse)
async def summarize_research_events(
    request: Request,
    discipline: str = "",
    project_id: str = "",
    group_id: str = "",
    user_id: str = "",
    topic: str = "",
) -> ResearchEventSummaryResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.summarize_research_events(
        discipline=discipline,
        project_id=project_id,
        group_id=group_id,
        user_id=user_id,
        topic=topic,
    )
    return ResearchEventSummaryResponse(**result)


