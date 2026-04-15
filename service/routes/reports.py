from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..schemas import ReportResponse


router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{run_id}", response_model=ReportResponse)
async def get_report(
    run_id: str,
    request: Request,
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    group_role: str = "",
) -> ReportResponse:
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
        raise HTTPException(status_code=403, detail="Report access denied")
    report_path = None
    if record.result is not None:
        report_path = record.result.report_path
    return ReportResponse(
        run_id=run_id,
        status=record.status,
        report_markdown=record.report_markdown,
        report_path=report_path,
    )


