from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..schemas import (
    WorkflowRunAccepted,
    WorkflowRunListItem,
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowStepResponse,
)


router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.get("/runs", response_model=list[WorkflowRunListItem])
async def list_workflows(
    request: Request,
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    group_role: str = "",
) -> list[WorkflowRunListItem]:
    runtime = request.app.state.workflow_runtime
    items: list[WorkflowRunListItem] = []
    for record in runtime.list_runs():
        if not runtime.can_access_scoped_resource(
            owner_user_id=record.user_id,
            project_id=record.project_id,
            group_id=record.group_id,
            requester_user_id=user_id,
            requester_project_id=project_id,
            requester_group_id=group_id,
            requester_group_role=group_role,
        ):
            continue
        report_path = record.result.report_path if record.result is not None else None
        items.append(
            WorkflowRunListItem(
                run_id=record.run_id,
                topic=record.topic,
                status=record.status,
                discipline=record.discipline,
                user_id=record.user_id,
                project_id=record.project_id,
                group_id=record.group_id,
                group_role=record.group_role,
                report_path=report_path,
                error=record.error,
            )
        )
    return items


@router.post("/run", response_model=WorkflowRunAccepted)
async def run_workflow(request: Request, payload: WorkflowRunRequest) -> WorkflowRunAccepted:
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
        raise HTTPException(status_code=403, detail="Workflow submission denied")
    record = await runtime.submit_workflow(
        topic=payload.topic,
        dynamic_routing=payload.dynamic_routing,
        report_path=payload.report_path,
        discipline=payload.discipline,
        user_id=payload.user_id,
        project_id=payload.project_id,
        group_id=payload.group_id,
        group_role=payload.group_role,
    )
    return WorkflowRunAccepted(run_id=record.run_id, status=record.status)


@router.get("/{run_id}", response_model=WorkflowRunResponse)
async def get_workflow(
    run_id: str,
    request: Request,
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    group_role: str = "",
) -> WorkflowRunResponse:
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
        raise HTTPException(status_code=403, detail="Run access denied")

    steps: list[WorkflowStepResponse] = []
    claim_graph: dict = {}
    research_state: dict = {}
    run_manifest: dict = {}
    report_path: str | None = None
    if record.result is not None:
        steps = [
            WorkflowStepResponse(
                profile_name=step.profile_name,
                raw_output=step.raw_output,
                parsed_output=step.parsed_output,
                model_meta=step.model_meta,
            )
            for step in record.result.steps
        ]
        claim_graph = record.result.claim_graph
        research_state = record.result.research_state
        run_manifest = record.result.run_manifest
        report_path = record.result.report_path

    return WorkflowRunResponse(
        run_id=record.run_id,
        status=record.status,
        topic=record.topic,
        discipline=record.discipline,
        user_id=record.user_id,
        project_id=record.project_id,
        group_id=record.group_id,
        group_role=record.group_role,
        report_path=report_path,
        error=record.error,
        steps=steps,
        claim_graph=claim_graph,
        research_state=research_state,
        run_manifest=run_manifest,
    )
