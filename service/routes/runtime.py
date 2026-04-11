from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request


router = APIRouter(prefix="/runtime", tags=["runtime"])


@router.get("/manifests", response_model=list[dict[str, Any]])
async def list_runtime_manifests(request: Request, limit: int = 50) -> list[dict[str, Any]]:
    runtime = request.app.state.workflow_runtime
    return runtime.list_runtime_manifests(limit=limit)


@router.get("/manifests/latest", response_model=dict[str, Any])
async def latest_runtime_manifest(request: Request) -> dict[str, Any]:
    runtime = request.app.state.workflow_runtime
    manifest = runtime.latest_runtime_manifest()
    if manifest is None:
        raise HTTPException(status_code=404, detail="Runtime manifest not found")
    return manifest
