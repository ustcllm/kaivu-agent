from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas import (
    MemoryAuditResponse,
    MemoryAutoGovernRequest,
    MemoryAutoGovernResponse,
    MemoryCompactRequest,
    MemoryCompactResponse,
    MemoryMutationResponse,
    MemoryProposalListResponse,
    MemoryProposalDecisionRequest,
    MemoryPromoteRequest,
    MemoryPromoteResponse,
    MemoryReviewRequest,
    MemorySaveRequest,
    MemorySearchRequest,
    MemorySearchResponse,
)


router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("/search", response_model=MemorySearchResponse)
async def search_memory(request: Request, payload: MemorySearchRequest) -> MemorySearchResponse:
    runtime = request.app.state.workflow_runtime
    results = runtime.search_memory(
        payload.query,
        max_results=payload.max_results,
        discipline=payload.discipline,
        user_id=payload.user_id,
        project_id=payload.project_id,
        group_id=payload.group_id,
        scopes=payload.scopes,
    )
    return MemorySearchResponse(results=results)


@router.get("/proposals", response_model=MemoryProposalListResponse)
async def list_memory_proposals(
    request: Request,
    discipline: str = "",
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    group_role: str = "",
) -> MemoryProposalListResponse:
    runtime = request.app.state.workflow_runtime
    results = runtime.list_memory_proposals(
        discipline=discipline,
        user_id=user_id,
        project_id=project_id,
        group_id=group_id,
        group_role=group_role,
    )
    return MemoryProposalListResponse(results=results)


@router.get("/audit", response_model=MemoryAuditResponse)
async def get_memory_audit(
    request: Request,
    filename: str,
    discipline: str = "",
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    group_role: str = "",
) -> MemoryAuditResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.get_memory_audit(
        filename=filename,
        discipline=discipline,
        user_id=user_id,
        project_id=project_id,
        group_id=group_id,
        group_role=group_role,
    )
    return MemoryAuditResponse(**result)


@router.post("/save", response_model=MemoryMutationResponse)
async def save_memory(request: Request, payload: MemorySaveRequest) -> MemoryMutationResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.save_memory(payload.model_dump())
    return MemoryMutationResponse(
        ok=True,
        path=result.get("path"),
        mode=result.get("mode"),
        message=result.get("message"),
    )


@router.post("/review", response_model=MemoryMutationResponse)
async def review_memory(request: Request, payload: MemoryReviewRequest) -> MemoryMutationResponse:
    runtime = request.app.state.workflow_runtime
    updated = runtime.review_memory(payload.model_dump())
    return MemoryMutationResponse(ok=updated, filename=payload.filename)


@router.post("/promote", response_model=MemoryPromoteResponse)
async def promote_memory(request: Request, payload: MemoryPromoteRequest) -> MemoryPromoteResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.promote_memory(payload.model_dump())
    return MemoryPromoteResponse(**result)


@router.post("/auto-govern", response_model=MemoryAutoGovernResponse)
async def auto_govern_memory(request: Request, payload: MemoryAutoGovernRequest) -> MemoryAutoGovernResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.auto_govern_memory(payload.model_dump())
    return MemoryAutoGovernResponse(**result)


@router.post("/compact", response_model=MemoryCompactResponse)
async def compact_memory(request: Request, payload: MemoryCompactRequest) -> MemoryCompactResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.compact_memory(payload.model_dump())
    return MemoryCompactResponse(**result)


@router.post("/proposals/approve", response_model=MemoryPromoteResponse)
async def approve_memory_proposal(request: Request, payload: MemoryProposalDecisionRequest) -> MemoryPromoteResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.promote_memory(
        {
            "filename": payload.filename,
            "discipline": payload.discipline,
            "target_scope": payload.target_scope or "group",
            "target_visibility": payload.target_visibility,
            "user_id": payload.user_id,
            "project_id": payload.project_id,
            "group_id": payload.group_id,
            "group_role": payload.group_role,
        }
    )
    return MemoryPromoteResponse(**result)


@router.post("/proposals/reject", response_model=MemoryPromoteResponse)
async def reject_memory_proposal(request: Request, payload: MemoryProposalDecisionRequest) -> MemoryPromoteResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.reject_memory_proposal(payload.model_dump())
    return MemoryPromoteResponse(**result)


