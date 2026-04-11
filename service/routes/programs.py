from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request


router = APIRouter(prefix="/programs", tags=["programs"])


@router.get("", response_model=list[dict[str, Any]])
async def list_research_programs(
    request: Request,
    discipline: str = "",
    project_id: str = "",
    group_id: str = "",
    user_id: str = "",
    topic: str = "",
) -> list[dict[str, Any]]:
    runtime = request.app.state.workflow_runtime
    return runtime.list_research_programs(
        discipline=discipline,
        project_id=project_id,
        group_id=group_id,
        user_id=user_id,
        topic=topic,
    )


@router.get("/latest", response_model=dict[str, Any])
async def latest_research_program(
    request: Request,
    discipline: str = "",
    project_id: str = "",
    group_id: str = "",
    user_id: str = "",
    topic: str = "",
) -> dict[str, Any]:
    runtime = request.app.state.workflow_runtime
    program = runtime.latest_research_program(
        discipline=discipline,
        project_id=project_id,
        group_id=group_id,
        user_id=user_id,
        topic=topic,
    )
    if program is None:
        raise HTTPException(status_code=404, detail="Research program not found")
    return program
