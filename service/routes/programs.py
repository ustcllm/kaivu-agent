from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request


router = APIRouter(prefix="/programs", tags=["programs"])


@router.get("", response_model=list[dict[str, Any]])
async def list_research_programs(
    request: Request,
    project_id: str = "",
    topic: str = "",
) -> list[dict[str, Any]]:
    runtime = request.app.state.workflow_runtime
    return runtime.list_research_programs(project_id=project_id, topic=topic)


@router.get("/latest", response_model=dict[str, Any])
async def latest_research_program(
    request: Request,
    project_id: str = "",
    topic: str = "",
) -> dict[str, Any]:
    runtime = request.app.state.workflow_runtime
    program = runtime.latest_research_program(project_id=project_id, topic=topic)
    if program is None:
        raise HTTPException(status_code=404, detail="Research program not found")
    return program
