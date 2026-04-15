from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas import (
    CollaborationMemberListResponse,
    CollaborationMemberResponse,
    CollaborationMemberUpsertRequest,
    GroupRoleResponse,
    GroupRoleUpdateRequest,
)


router = APIRouter(prefix="/collaboration", tags=["collaboration"])


@router.post("/group-role", response_model=GroupRoleResponse)
async def set_group_role(request: Request, payload: GroupRoleUpdateRequest) -> GroupRoleResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.set_group_role(group_id=payload.group_id, user_id=payload.user_id, role=payload.role)
    return GroupRoleResponse(**result)


@router.get("/groups/{group_id}/members", response_model=CollaborationMemberListResponse)
async def list_group_members(group_id: str, request: Request) -> CollaborationMemberListResponse:
    runtime = request.app.state.workflow_runtime
    members = runtime.list_group_members(group_id=group_id)
    return CollaborationMemberListResponse(
        scope="group",
        scope_id=group_id,
        members=[CollaborationMemberResponse(**item) for item in members],
    )


@router.post("/groups/{group_id}/members", response_model=CollaborationMemberResponse)
async def upsert_group_member(
    group_id: str, request: Request, payload: CollaborationMemberUpsertRequest
) -> CollaborationMemberResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.upsert_group_member(
        group_id=group_id,
        user_id=payload.user_id,
        role=payload.role,
        display_name=payload.display_name,
    )
    return CollaborationMemberResponse(**result)


@router.get("/projects/{project_id}/members", response_model=CollaborationMemberListResponse)
async def list_project_members(project_id: str, request: Request) -> CollaborationMemberListResponse:
    runtime = request.app.state.workflow_runtime
    members = runtime.list_project_members(project_id=project_id)
    return CollaborationMemberListResponse(
        scope="project",
        scope_id=project_id,
        members=[CollaborationMemberResponse(**item) for item in members],
    )


@router.post("/projects/{project_id}/members", response_model=CollaborationMemberResponse)
async def upsert_project_member(
    project_id: str, request: Request, payload: CollaborationMemberUpsertRequest
) -> CollaborationMemberResponse:
    runtime = request.app.state.workflow_runtime
    result = runtime.upsert_project_member(
        project_id=project_id,
        user_id=payload.user_id,
        role=payload.role,
        display_name=payload.display_name,
    )
    return CollaborationMemberResponse(**result)


