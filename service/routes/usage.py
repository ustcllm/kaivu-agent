from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..schemas import UsageProfileSummary, UsageSummaryResponse


router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/{run_id}", response_model=UsageSummaryResponse)
async def get_usage(
    run_id: str,
    request: Request,
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    group_role: str = "",
) -> UsageSummaryResponse:
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
        raise HTTPException(status_code=403, detail="Usage access denied")
    usage_summary = record.usage_summary or {"total": {}, "by_profile": []}
    return UsageSummaryResponse(
        run_id=run_id,
        status=record.status,
        total=usage_summary.get("total", {}),
        by_profile=[
            UsageProfileSummary(**item)
            for item in usage_summary.get("by_profile", [])
        ],
    )


