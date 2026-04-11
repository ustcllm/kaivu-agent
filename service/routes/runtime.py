from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request


router = APIRouter(prefix="/runtime", tags=["runtime"])


@router.get("/manifests", response_model=list[dict[str, Any]])
async def list_runtime_manifests(
    request: Request,
    limit: int = 50,
    discipline: str = "",
    project_id: str = "",
    group_id: str = "",
    user_id: str = "",
) -> list[dict[str, Any]]:
    runtime = request.app.state.workflow_runtime
    return runtime.list_runtime_manifests(
        limit=limit,
        discipline=discipline,
        project_id=project_id,
        group_id=group_id,
        user_id=user_id,
    )


@router.get("/manifests/latest", response_model=dict[str, Any])
async def latest_runtime_manifest(
    request: Request,
    discipline: str = "",
    project_id: str = "",
    group_id: str = "",
    user_id: str = "",
) -> dict[str, Any]:
    runtime = request.app.state.workflow_runtime
    manifest = runtime.latest_runtime_manifest(
        discipline=discipline,
        project_id=project_id,
        group_id=group_id,
        user_id=user_id,
    )
    if manifest is None:
        raise HTTPException(status_code=404, detail="Runtime manifest not found")
    return manifest
