from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas import ContextPackRequest, ContextPackResponse


router = APIRouter(prefix="/context", tags=["context"])


@router.post("/pack", response_model=ContextPackResponse)
async def build_context_pack(request: Request, payload: ContextPackRequest) -> ContextPackResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.build_context_pack(payload.model_dump())
    return ContextPackResponse(**result)


