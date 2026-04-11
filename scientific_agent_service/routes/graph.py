from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..schemas import GraphResponse, TypedGraphQueryResponse


router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/typed/query", response_model=TypedGraphQueryResponse)
async def query_typed_graph(
    request: Request,
    project_id: str,
    topic: str = "",
    node_type: str = "",
    relation: str = "",
    search: str = "",
    limit: int = 100,
    source_node_id: str = "",
    target_node_id: str = "",
    specialist_name: str = "",
    include_consulted_only: bool = False,
    user_id: str = "",
    group_id: str = "",
    group_role: str = "",
) -> TypedGraphQueryResponse:
    runtime = request.app.state.workflow_runtime
    if not runtime.can_access_scoped_resource(
        owner_user_id="",
        project_id=project_id,
        group_id="",
        requester_user_id=user_id,
        requester_project_id="",
        requester_group_id=group_id,
        requester_group_role=group_role,
    ):
        raise HTTPException(status_code=403, detail="Typed graph access denied")
    payload = runtime.query_typed_research_graph(
        project_id=project_id,
        topic=topic,
        node_type=node_type,
        relation=relation,
        search=search,
        limit=max(1, min(limit, 200)),
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        specialist_name=specialist_name,
        include_consulted_only=include_consulted_only,
    )
    return TypedGraphQueryResponse(**payload)


@router.get("/{run_id}", response_model=GraphResponse)
async def get_graph(
    run_id: str,
    request: Request,
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    group_role: str = "",
) -> GraphResponse:
    runtime = request.app.state.workflow_runtime
    record = runtime.get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if not runtime.can_access_scoped_resource(
        owner_user_id=record.user_id,
        project_id=record.project_id,
        group_id=record.group_id,
        requester_user_id=user_id,
        requester_project_id=project_id,
        requester_group_id=group_id,
        requester_group_role=group_role,
    ):
        raise HTTPException(status_code=403, detail="Graph access denied")
    return GraphResponse(
        run_id=run_id,
        status=record.status,
        claim_graph=runtime.get_claim_graph(run_id),
    )
