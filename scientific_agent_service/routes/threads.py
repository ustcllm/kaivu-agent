from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..schemas import (
    ThreadCreateRequest,
    ThreadMessageCreateRequest,
    ThreadMessageResponse,
    ThreadResponse,
    ThreadUpdateRequest,
)


router = APIRouter(prefix="/threads", tags=["threads"])


def _to_thread_response(record) -> ThreadResponse:
    return ThreadResponse(
        thread_id=record.thread_id,
        title=record.title,
        run_id=record.run_id,
        user_id=record.user_id,
        project_id=record.project_id,
        group_id=record.group_id,
        group_role=record.group_role,
        snapshot=record.snapshot,
        archived=record.archived,
        chat=[
            ThreadMessageResponse(
                role=message.role,
                content=message.content,
                created_at=message.created_at,
            )
            for message in record.chat
        ],
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("", response_model=list[ThreadResponse])
async def list_threads(
    request: Request,
    include_archived: bool = True,
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    group_role: str = "",
) -> list[ThreadResponse]:
    runtime = request.app.state.workflow_runtime
    return [
        _to_thread_response(record)
        for record in runtime.list_threads(include_archived=include_archived)
        if runtime.can_access_scoped_resource(
            owner_user_id=record.user_id,
            project_id=record.project_id,
            group_id=record.group_id,
            requester_user_id=user_id,
            requester_project_id=project_id,
            requester_group_id=group_id,
            requester_group_role=group_role,
        )
    ]


@router.post("", response_model=ThreadResponse)
async def create_thread(request: Request, payload: ThreadCreateRequest) -> ThreadResponse:
    runtime = request.app.state.workflow_runtime
    if not runtime.can_modify_scoped_resource(
        owner_user_id=payload.user_id,
        project_id=payload.project_id,
        group_id=payload.group_id,
        requester_user_id=payload.user_id,
        requester_project_id=payload.project_id,
        requester_group_id=payload.group_id,
        requester_group_role=payload.group_role,
    ):
        raise HTTPException(status_code=403, detail="Thread creation denied")
    record = runtime.create_thread(
        title=payload.title,
        created_at=payload.created_at,
        user_id=payload.user_id,
        project_id=payload.project_id,
        group_id=payload.group_id,
        group_role=payload.group_role,
        initial_message=payload.initial_message.model_dump() if payload.initial_message else None,
    )
    return _to_thread_response(record)


@router.get("/{thread_id}", response_model=ThreadResponse)
async def get_thread(
    thread_id: str,
    request: Request,
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    group_role: str = "",
) -> ThreadResponse:
    runtime = request.app.state.workflow_runtime
    record = runtime.get_thread(thread_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not runtime.can_access_scoped_resource(
        owner_user_id=record.user_id,
        project_id=record.project_id,
        group_id=record.group_id,
        requester_user_id=user_id,
        requester_project_id=project_id,
        requester_group_id=group_id,
        requester_group_role=group_role,
    ):
        raise HTTPException(status_code=403, detail="Thread access denied")
    return _to_thread_response(record)


@router.patch("/{thread_id}", response_model=ThreadResponse)
async def update_thread(thread_id: str, request: Request, payload: ThreadUpdateRequest) -> ThreadResponse:
    runtime = request.app.state.workflow_runtime
    user_id = str(request.query_params.get("user_id", payload.user_id or ""))
    project_id = str(request.query_params.get("project_id", payload.project_id or ""))
    group_id = str(request.query_params.get("group_id", payload.group_id or ""))
    group_role = str(request.query_params.get("group_role", payload.group_role or ""))
    existing = runtime.get_thread(thread_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not runtime.can_modify_scoped_resource(
        owner_user_id=existing.user_id,
        project_id=existing.project_id,
        group_id=existing.group_id,
        requester_user_id=user_id,
        requester_project_id=project_id,
        requester_group_id=group_id,
        requester_group_role=group_role,
    ):
        raise HTTPException(status_code=403, detail="Thread update denied")
    record = runtime.update_thread(
        thread_id,
        title=payload.title,
        run_id=payload.run_id,
        snapshot=payload.snapshot,
        archived=payload.archived,
        user_id=payload.user_id,
        project_id=payload.project_id,
        group_id=payload.group_id,
        group_role=payload.group_role,
        updated_at=payload.updated_at,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return _to_thread_response(record)


@router.delete("/{thread_id}")
async def delete_thread(thread_id: str, request: Request) -> dict[str, bool]:
    runtime = request.app.state.workflow_runtime
    user_id = str(request.query_params.get("user_id", ""))
    project_id = str(request.query_params.get("project_id", ""))
    group_id = str(request.query_params.get("group_id", ""))
    group_role = str(request.query_params.get("group_role", ""))
    existing = runtime.get_thread(thread_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not runtime.can_modify_scoped_resource(
        owner_user_id=existing.user_id,
        project_id=existing.project_id,
        group_id=existing.group_id,
        requester_user_id=user_id,
        requester_project_id=project_id,
        requester_group_id=group_id,
        requester_group_role=group_role,
    ):
        raise HTTPException(status_code=403, detail="Thread delete denied")
    ok = runtime.delete_thread(thread_id)
    return {"ok": True}


@router.post("/{thread_id}/messages", response_model=ThreadResponse)
async def append_thread_message(
    thread_id: str, request: Request, payload: ThreadMessageCreateRequest
) -> ThreadResponse:
    runtime = request.app.state.workflow_runtime
    user_id = str(request.query_params.get("user_id", ""))
    project_id = str(request.query_params.get("project_id", ""))
    group_id = str(request.query_params.get("group_id", ""))
    group_role = str(request.query_params.get("group_role", ""))
    existing = runtime.get_thread(thread_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not runtime.can_modify_scoped_resource(
        owner_user_id=existing.user_id,
        project_id=existing.project_id,
        group_id=existing.group_id,
        requester_user_id=user_id,
        requester_project_id=project_id,
        requester_group_id=group_id,
        requester_group_role=group_role,
    ):
        raise HTTPException(status_code=403, detail="Thread message append denied")
    record = runtime.append_thread_message(
        thread_id,
        role=payload.role,
        content=payload.content,
        created_at=payload.created_at,
    )
    return _to_thread_response(record)
