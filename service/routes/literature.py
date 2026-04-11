from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas import LiteratureIngestRequest, LiteratureIngestResponse, LiteratureLintResponse, LiteratureQueryResponse


router = APIRouter(prefix="/literature", tags=["literature"])


@router.post("/ingest", response_model=LiteratureIngestResponse)
async def ingest_literature_source(
    payload: LiteratureIngestRequest,
    request: Request,
) -> LiteratureIngestResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.ingest_literature_source(
        source_type=payload.source_type,
        title=payload.title,
        content=payload.content,
        filename=payload.filename,
        discipline=payload.discipline,
        user_id=payload.user_id,
        project_id=payload.project_id,
        group_id=payload.group_id,
        target_scope=payload.target_scope,
        user_mode=payload.user_mode,
        impact_level=payload.impact_level,
        conflict_level=payload.conflict_level,
        confidence=payload.confidence,
        group_role=payload.group_role,
    )
    return LiteratureIngestResponse(**result)


@router.get("/query", response_model=LiteratureQueryResponse)
async def query_literature_wiki(
    request: Request,
    query: str,
    limit: int = 10,
    sections: str = "",
    discipline: str = "",
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
) -> LiteratureQueryResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.query_literature_wiki(
        query=query,
        limit=max(1, min(limit, 50)),
        sections=[item.strip() for item in sections.split(",") if item.strip()] if sections else None,
        discipline=discipline,
        user_id=user_id,
        project_id=project_id,
        group_id=group_id,
    )
    return LiteratureQueryResponse(**result)


@router.post("/lint", response_model=LiteratureLintResponse)
async def lint_literature_workspace(
    request: Request,
    discipline: str = "",
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
) -> LiteratureLintResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.lint_literature_workspace(
        discipline=discipline,
        user_id=user_id,
        project_id=project_id,
        group_id=group_id,
    )
    return LiteratureLintResponse(**result)
