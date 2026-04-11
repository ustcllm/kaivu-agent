from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..schemas import (
    ExperimentRecordListResponse,
    ExperimentRunLifecycleRequest,
    ExperimentRunPayload,
    ExperimentSpecificationLifecycleRequest,
    ExperimentSpecificationPayload,
    EvaluationHistoryResponse,
    ExperimentalProtocolPayload,
    ExperimentalProtocolLifecycleRequest,
    EvaluationSignalResponse,
    InterpretationRecordPayload,
    ProtocolAmendmentRequest,
    QualityControlReviewPayload,
    RunApprovalRequest,
    RunHandoffSubmitRequest,
    RunHandoffSubmitResponse,
)


router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.post("/handoff", response_model=RunHandoffSubmitResponse)
async def submit_run_handoff(
    request: Request,
    payload: RunHandoffSubmitRequest,
) -> RunHandoffSubmitResponse:
    runtime = request.app.state.workflow_runtime
    try:
        result = runtime.submit_run_handoff(
            topic=payload.topic,
            contract=payload.contract,
            payload=payload.payload,
            claim_graph=payload.claim_graph,
            write_memory=payload.write_memory,
            write_events=payload.write_events,
            user_id=payload.user_id,
            project_id=payload.project_id,
            group_id=payload.group_id,
            group_role=payload.group_role,
        )
        return RunHandoffSubmitResponse(**result)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/specifications", response_model=ExperimentRecordListResponse)
async def list_experiment_specifications(
    request: Request,
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    group_role: str = "",
) -> ExperimentRecordListResponse:
    runtime = request.app.state.workflow_runtime
    return ExperimentRecordListResponse(
        results=runtime.list_experiment_specifications(
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
        )
    )


@router.post("/specifications", response_model=dict)
async def create_experiment_specification(
    request: Request,
    payload: ExperimentSpecificationPayload,
) -> dict:
    runtime = request.app.state.workflow_runtime
    try:
        return runtime.save_experiment_specification(
            payload.model_dump(),
            user_id=payload.user_id,
            project_id=payload.project_id,
            group_id=payload.group_id,
            group_role=payload.group_role,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/specifications/{experiment_id}", response_model=dict)
async def get_experiment_specification(
    experiment_id: str,
    request: Request,
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    group_role: str = "",
) -> dict:
    runtime = request.app.state.workflow_runtime
    record = runtime.get_experiment_specification(
        experiment_id,
        user_id=user_id,
        project_id=project_id,
        group_id=group_id,
        group_role=group_role,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Experiment specification not found")
    return record


@router.post("/specifications/freeze", response_model=dict)
async def freeze_experiment_specification(
    request: Request,
    payload: ExperimentSpecificationLifecycleRequest,
) -> dict:
    runtime = request.app.state.workflow_runtime
    try:
        return runtime.freeze_experiment_specification(
            experiment_id=payload.experiment_id,
            reason=payload.reason,
            user_id=payload.user_id,
            project_id=payload.project_id,
            group_id=payload.group_id,
            group_role=payload.group_role,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/specifications/unfreeze", response_model=dict)
async def unfreeze_experiment_specification(
    request: Request,
    payload: ExperimentSpecificationLifecycleRequest,
) -> dict:
    runtime = request.app.state.workflow_runtime
    try:
        return runtime.unfreeze_experiment_specification(
            experiment_id=payload.experiment_id,
            user_id=payload.user_id,
            project_id=payload.project_id,
            group_id=payload.group_id,
            group_role=payload.group_role,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/specifications/retire", response_model=dict)
async def retire_experiment_specification(
    request: Request,
    payload: ExperimentSpecificationLifecycleRequest,
) -> dict:
    runtime = request.app.state.workflow_runtime
    try:
        return runtime.retire_experiment_specification(
            experiment_id=payload.experiment_id,
            reason=payload.reason,
            user_id=payload.user_id,
            project_id=payload.project_id,
            group_id=payload.group_id,
            group_role=payload.group_role,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/protocols", response_model=ExperimentRecordListResponse)
async def list_experimental_protocols(
    request: Request,
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    group_role: str = "",
    experiment_id: str = "",
) -> ExperimentRecordListResponse:
    runtime = request.app.state.workflow_runtime
    return ExperimentRecordListResponse(
        results=runtime.list_experimental_protocols(
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
            experiment_id=experiment_id,
        )
    )


@router.post("/protocols", response_model=dict)
async def create_experimental_protocol(
    request: Request,
    payload: ExperimentalProtocolPayload,
) -> dict:
    runtime = request.app.state.workflow_runtime
    try:
        return runtime.save_experimental_protocol(
            payload.model_dump(),
            user_id=payload.user_id,
            project_id=payload.project_id,
            group_id=payload.group_id,
            group_role=payload.group_role,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/protocols/{protocol_id}", response_model=dict)
async def get_experimental_protocol(
    protocol_id: str,
    request: Request,
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    group_role: str = "",
) -> dict:
    runtime = request.app.state.workflow_runtime
    record = runtime.get_experimental_protocol(
        protocol_id,
        user_id=user_id,
        project_id=project_id,
        group_id=group_id,
        group_role=group_role,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Experimental protocol not found")
    return record


@router.post("/protocols/freeze", response_model=dict)
async def freeze_experimental_protocol(
    request: Request,
    payload: ExperimentalProtocolLifecycleRequest,
) -> dict:
    runtime = request.app.state.workflow_runtime
    try:
        return runtime.freeze_experimental_protocol(
            protocol_id=payload.protocol_id,
            reason=payload.reason,
            user_id=payload.user_id,
            project_id=payload.project_id,
            group_id=payload.group_id,
            group_role=payload.group_role,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/protocols/unfreeze", response_model=dict)
async def unfreeze_experimental_protocol(
    request: Request,
    payload: ExperimentalProtocolLifecycleRequest,
) -> dict:
    runtime = request.app.state.workflow_runtime
    try:
        return runtime.unfreeze_experimental_protocol(
            protocol_id=payload.protocol_id,
            user_id=payload.user_id,
            project_id=payload.project_id,
            group_id=payload.group_id,
            group_role=payload.group_role,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/protocols/amend", response_model=dict)
async def amend_experimental_protocol(
    request: Request,
    payload: ProtocolAmendmentRequest,
) -> dict:
    runtime = request.app.state.workflow_runtime
    try:
        return runtime.amend_experimental_protocol(
            source_protocol_id=payload.source_protocol_id,
            payload={
                "protocol_id": payload.new_protocol_id,
                "version": payload.new_version,
                "amendment_reason": payload.amendment_reason,
                "steps": payload.steps,
                "quality_control_checks": payload.quality_control_checks,
                "governance_checks": payload.governance_checks,
                "approval_requirements": payload.approval_requirements,
                "defer_reasons": payload.defer_reasons,
                "adjudication_questions": payload.adjudication_questions,
            },
            user_id=payload.user_id,
            project_id=payload.project_id,
            group_id=payload.group_id,
            group_role=payload.group_role,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs", response_model=ExperimentRecordListResponse)
async def list_experiment_runs(
    request: Request,
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    group_role: str = "",
    experiment_id: str = "",
) -> ExperimentRecordListResponse:
    runtime = request.app.state.workflow_runtime
    return ExperimentRecordListResponse(
        results=runtime.list_experiment_runs(
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
            experiment_id=experiment_id,
        )
    )


@router.post("/runs", response_model=dict)
async def create_experiment_run(
    request: Request,
    payload: ExperimentRunPayload,
) -> dict:
    runtime = request.app.state.workflow_runtime
    try:
        return runtime.save_experiment_run_record(
            payload.model_dump(),
            user_id=payload.user_id,
            project_id=payload.project_id,
            group_id=payload.group_id,
            group_role=payload.group_role,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs/{run_id}", response_model=dict)
async def get_experiment_run(
    run_id: str,
    request: Request,
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    group_role: str = "",
) -> dict:
    runtime = request.app.state.workflow_runtime
    record = runtime.get_experiment_run_record(
        run_id,
        user_id=user_id,
        project_id=project_id,
        group_id=group_id,
        group_role=group_role,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Experiment run not found")
    return record


@router.post("/runs/retire", response_model=dict)
async def retire_experiment_run(
    request: Request,
    payload: ExperimentRunLifecycleRequest,
) -> dict:
    runtime = request.app.state.workflow_runtime
    try:
        return runtime.retire_experiment_run(
            run_id=payload.run_id,
            reason=payload.reason,
            user_id=payload.user_id,
            project_id=payload.project_id,
            group_id=payload.group_id,
            group_role=payload.group_role,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/approve", response_model=dict)
async def approve_experiment_run(
    request: Request,
    payload: RunApprovalRequest,
) -> dict:
    runtime = request.app.state.workflow_runtime
    try:
        return runtime.approve_experiment_run(
            run_id=payload.run_id,
            approved_by=payload.approved_by,
            approval_note=payload.approval_note,
            approval_status=payload.approval_status,
            user_id=payload.user_id,
            project_id=payload.project_id,
            group_id=payload.group_id,
            group_role=payload.group_role,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/lineage/{experiment_id}", response_model=dict)
async def get_experiment_lineage(
    experiment_id: str,
    request: Request,
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    group_role: str = "",
) -> dict:
    runtime = request.app.state.workflow_runtime
    return runtime.get_experiment_lineage(
        experiment_id=experiment_id,
        user_id=user_id,
        project_id=project_id,
        group_id=group_id,
        group_role=group_role,
    )


@router.get("/quality-control-reviews", response_model=ExperimentRecordListResponse)
async def list_quality_control_reviews(
    request: Request,
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    group_role: str = "",
    experiment_id: str = "",
) -> ExperimentRecordListResponse:
    runtime = request.app.state.workflow_runtime
    return ExperimentRecordListResponse(
        results=runtime.list_quality_control_reviews(
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
            experiment_id=experiment_id,
        )
    )


@router.post("/quality-control-reviews", response_model=dict)
async def create_quality_control_review(
    request: Request,
    payload: QualityControlReviewPayload,
) -> dict:
    runtime = request.app.state.workflow_runtime
    try:
        return runtime.save_quality_control_review_record(
            payload.model_dump(),
            user_id=payload.user_id,
            project_id=payload.project_id,
            group_id=payload.group_id,
            group_role=payload.group_role,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/quality-control-reviews/{review_id}", response_model=dict)
async def get_quality_control_review(
    review_id: str,
    request: Request,
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    group_role: str = "",
) -> dict:
    runtime = request.app.state.workflow_runtime
    record = runtime.get_quality_control_review_record(
        review_id,
        user_id=user_id,
        project_id=project_id,
        group_id=group_id,
        group_role=group_role,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Quality control review not found")
    return record


@router.get("/interpretations", response_model=ExperimentRecordListResponse)
async def list_interpretation_records(
    request: Request,
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    group_role: str = "",
    experiment_id: str = "",
) -> ExperimentRecordListResponse:
    runtime = request.app.state.workflow_runtime
    return ExperimentRecordListResponse(
        results=runtime.list_interpretation_records(
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            group_role=group_role,
            experiment_id=experiment_id,
        )
    )


@router.post("/interpretations", response_model=dict)
async def create_interpretation_record(
    request: Request,
    payload: InterpretationRecordPayload,
) -> dict:
    runtime = request.app.state.workflow_runtime
    try:
        return runtime.save_interpretation_record(
            payload.model_dump(),
            user_id=payload.user_id,
            project_id=payload.project_id,
            group_id=payload.group_id,
            group_role=payload.group_role,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/interpretations/{interpretation_id}", response_model=dict)
async def get_interpretation_record(
    interpretation_id: str,
    request: Request,
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    group_role: str = "",
) -> dict:
    runtime = request.app.state.workflow_runtime
    record = runtime.get_interpretation_record(
        interpretation_id,
        user_id=user_id,
        project_id=project_id,
        group_id=group_id,
        group_role=group_role,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Interpretation record not found")
    return record


@router.get("/evaluation/{run_id}", response_model=EvaluationSignalResponse)
async def get_run_evaluation_signals(
    run_id: str,
    request: Request,
) -> EvaluationSignalResponse:
    runtime = request.app.state.workflow_runtime
    evaluation_record = runtime.get_evaluation_record(run_id)
    if evaluation_record is None:
        record = runtime._runs.get(run_id)
        if record is None or record.result is None:
            raise HTTPException(status_code=404, detail="Run evaluation not found")
        summary = record.result.research_state.get("evaluation_summary", {})
        termination = record.result.research_state.get("termination_strategy_summary", {})
        project_distill = record.result.research_state.get("project_distill", {})
    else:
        summary = (
            evaluation_record.get("evaluation_summary", {})
            if isinstance(evaluation_record.get("evaluation_summary", {}), dict)
            else {}
        )
        termination = (
            evaluation_record.get("termination_strategy_summary", {})
            if isinstance(evaluation_record.get("termination_strategy_summary", {}), dict)
            else {}
        )
        project_distill = (
            evaluation_record.get("project_distill", {})
            if isinstance(evaluation_record.get("project_distill", {}), dict)
            else {}
        )
    return EvaluationSignalResponse(
        benchmark_readiness=str(summary.get("benchmark_readiness", "")),
        regression_risk=(
            "high"
            if str(summary.get("failure_pressure", "")).strip() in {"technical", "evidentiary"}
            else "medium"
            if str(summary.get("failure_pressure", "")).strip()
            else ""
        ),
        validation_targets=[
            str(item)
            for item in project_distill.get("next_cycle_goals", [])
            if str(item).strip()
        ][:8],
        release_blockers=[
            str(item)
            for item in termination.get("human_confirmation_reasons", [])
            if str(item).strip()
        ][:8],
    )


@router.get("/evaluation-history", response_model=EvaluationHistoryResponse)
async def get_evaluation_history(
    request: Request,
    project_id: str = "",
    topic: str = "",
) -> EvaluationHistoryResponse:
    runtime = request.app.state.workflow_runtime
    return EvaluationHistoryResponse(
        results=runtime.list_evaluation_records(project_id=project_id, topic=topic)
    )
