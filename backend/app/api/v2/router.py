from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.app.application.v2.quote_service import (
    QuoteV2NotFoundError,
    QuoteV2Service,
)


router = APIRouter(prefix="/api/v2", tags=["api-v2"])


class CreateQuoteCaseRequest(BaseModel):
    case_id: str | None = None
    customer_name: str = ""
    part_name: str
    part_no: str = ""
    quantity: int = Field(default=1, gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateAnalysisRunRequest(BaseModel):
    options: dict[str, Any] = Field(default_factory=dict)


class CreateRoutePlanRequest(BaseModel):
    operations: list[dict[str, Any]] | None = None
    assumptions: list[dict[str, Any]] = Field(default_factory=list)


class CreateRoutePlanEnvelopeRequest(CreateRoutePlanRequest):
    run_id: str


class CreateRoutePlanForCaseRequest(CreateRoutePlanRequest):
    run_id: str | None = None


class CreateRouteRevisionRequest(BaseModel):
    action: str = "change_method"
    target_operation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class CreateCostScenarioRequest(BaseModel):
    currency: str = "CNY"
    items: list[dict[str, Any]] | None = None


class CreateCostScenarioEnvelopeRequest(CreateCostScenarioRequest):
    route_plan_id: str


class ApproveQuoteRequest(BaseModel):
    approved_by: str = "system"
    approval_note: str = ""


class ExportQuoteRequest(BaseModel):
    format: str = "json"


@router.post("/quote-cases")
async def create_quote_case(payload: CreateQuoteCaseRequest, request: Request) -> JSONResponse:
    quote_case = service_for(request).create_quote_case(model_to_dict(payload))
    return api_success({"quote_case": quote_case}, status_code=201)


@router.get("/quote-cases")
async def list_quote_cases(request: Request) -> JSONResponse:
    return api_success({"quote_cases": service_for(request).list_quote_cases()})


@router.post("/quote-cases/{case_id}/files")
async def add_quote_case_file(
    case_id: str,
    request: Request,
    file: UploadFile | None = File(None),
    file_type: str = Form("attachment"),
    uploaded_by: str = Form("system"),
) -> JSONResponse:
    try:
        if file is None:
            payload = await request.json()
            file_record = service_for(request).add_file(
                case_id=case_id,
                filename=payload.get("filename") or "unnamed",
                file_type=payload.get("file_type") or "attachment",
                content_type=payload.get("content_type"),
                size_bytes=int(payload.get("size_bytes") or 0),
                uploaded_by=payload.get("uploaded_by") or "system",
                metadata=payload.get("metadata") or {},
            )
        else:
            content = await file.read()
            file_record = service_for(request).add_file(
                case_id=case_id,
                filename=file.filename or "unnamed",
                file_type=file_type,
                content_type=file.content_type,
                size_bytes=len(content),
                uploaded_by=uploaded_by,
            )
        return api_success({"file": file_record}, status_code=201)
    except QuoteV2NotFoundError as exc:
        return not_found(exc)
    finally:
        if file is not None:
            await file.close()


@router.get("/quote-cases/{case_id}/files")
async def list_quote_case_files(case_id: str, request: Request) -> JSONResponse:
    try:
        return api_success({"files": service_for(request).list_files(case_id)})
    except QuoteV2NotFoundError as exc:
        return not_found(exc)


@router.post("/quote-cases/{case_id}/analysis-runs")
async def create_analysis_run(
    case_id: str,
    payload: CreateAnalysisRunRequest,
    request: Request,
) -> JSONResponse:
    try:
        run = service_for(request).create_analysis_run(case_id, model_to_dict(payload))
        return api_success({"analysis_run": run}, status_code=201)
    except QuoteV2NotFoundError as exc:
        return not_found(exc)


@router.get("/analysis-runs/{run_id}")
async def get_analysis_run(run_id: str, request: Request) -> JSONResponse:
    try:
        return api_success({"analysis_run": service_for(request).get_analysis_run(run_id)})
    except QuoteV2NotFoundError as exc:
        return not_found(exc)


@router.get("/analysis-runs/{run_id}/facts")
async def list_analysis_facts(run_id: str, request: Request) -> JSONResponse:
    try:
        return api_success({"facts": service_for(request).list_facts(run_id)})
    except QuoteV2NotFoundError as exc:
        return not_found(exc)


@router.post("/route-plans")
async def create_route_plan_from_collection(
    payload: CreateRoutePlanEnvelopeRequest,
    request: Request,
) -> JSONResponse:
    request_payload = model_to_dict(payload)
    run_id = request_payload.pop("run_id")
    try:
        plan = service_for(request).create_route_plan(run_id, request_payload)
        return api_success({"route_plan": plan}, status_code=201)
    except QuoteV2NotFoundError as exc:
        return not_found(exc)


@router.get("/route-plans/{route_plan_id}")
async def get_route_plan(route_plan_id: str, request: Request) -> JSONResponse:
    try:
        return api_success({"route_plan": service_for(request).get_route_plan(route_plan_id)})
    except QuoteV2NotFoundError as exc:
        return not_found(exc)


@router.post("/route-plans/{route_plan_id}/revisions")
async def create_route_revision(
    route_plan_id: str,
    payload: CreateRouteRevisionRequest,
    request: Request,
) -> JSONResponse:
    try:
        revision = service_for(request).create_route_revision(
            route_plan_id,
            model_to_dict(payload),
        )
        return api_success({"route_revision": revision}, status_code=201)
    except QuoteV2NotFoundError as exc:
        return not_found(exc)


@router.get("/route-plans")
async def list_route_plans_from_collection(
    run_id: str,
    request: Request,
) -> JSONResponse:
    try:
        return api_success({"route_plans": service_for(request).list_route_plans(run_id)})
    except QuoteV2NotFoundError as exc:
        return not_found(exc)


@router.post("/quote-cases/{case_id}/route-plans")
async def create_route_plan_for_case(
    case_id: str,
    payload: CreateRoutePlanForCaseRequest,
    request: Request,
) -> JSONResponse:
    service = service_for(request)
    request_payload = model_to_dict(payload)
    try:
        run_id = request_payload.pop("run_id") or latest_run_id_for_case(service, case_id)
        plan = service.create_route_plan(run_id, request_payload)
        return api_success({"route_plan": plan}, status_code=201)
    except QuoteV2NotFoundError as exc:
        return not_found(exc)


@router.post("/analysis-runs/{run_id}/route-plans")
async def create_route_plan(
    run_id: str,
    payload: CreateRoutePlanRequest,
    request: Request,
) -> JSONResponse:
    try:
        plan = service_for(request).create_route_plan(run_id, model_to_dict(payload))
        return api_success({"route_plan": plan}, status_code=201)
    except QuoteV2NotFoundError as exc:
        return not_found(exc)


@router.get("/analysis-runs/{run_id}/route-plans")
async def list_route_plans(run_id: str, request: Request) -> JSONResponse:
    try:
        return api_success({"route_plans": service_for(request).list_route_plans(run_id)})
    except QuoteV2NotFoundError as exc:
        return not_found(exc)


@router.post("/cost-scenarios")
async def create_cost_scenario_from_collection(
    payload: CreateCostScenarioEnvelopeRequest,
    request: Request,
) -> JSONResponse:
    request_payload = model_to_dict(payload)
    route_plan_id = request_payload.pop("route_plan_id")
    try:
        scenario = service_for(request).create_cost_scenario(route_plan_id, request_payload)
        return api_success({"cost_scenario": scenario}, status_code=201)
    except QuoteV2NotFoundError as exc:
        return not_found(exc)


@router.post("/route-plans/{route_plan_id}/cost-scenarios")
async def create_cost_scenario(
    route_plan_id: str,
    payload: CreateCostScenarioRequest,
    request: Request,
) -> JSONResponse:
    try:
        scenario = service_for(request).create_cost_scenario(route_plan_id, model_to_dict(payload))
        return api_success({"cost_scenario": scenario}, status_code=201)
    except QuoteV2NotFoundError as exc:
        return not_found(exc)


@router.get("/cost-scenarios/{scenario_id}")
async def get_cost_scenario(scenario_id: str, request: Request) -> JSONResponse:
    try:
        return api_success({"cost_scenario": service_for(request).get_cost_scenario(scenario_id)})
    except QuoteV2NotFoundError as exc:
        return not_found(exc)


@router.post("/cost-scenarios/{scenario_id}/quotes")
async def create_quote_for_cost_scenario(
    scenario_id: str,
    request: Request,
) -> JSONResponse:
    try:
        quote = service_for(request).create_quote_revision(scenario_id)
        return api_success({"quote": quote}, status_code=201)
    except QuoteV2NotFoundError as exc:
        return not_found(exc)


@router.post("/quotes/{quote_id}/approve")
async def approve_quote(
    quote_id: str,
    payload: ApproveQuoteRequest,
    request: Request,
) -> JSONResponse:
    try:
        quote = service_for(request).approve_quote(quote_id, model_to_dict(payload))
        return api_success({"quote": quote})
    except QuoteV2NotFoundError as exc:
        return not_found(exc)


@router.post("/quotes/{quote_id}/export")
async def export_quote(
    quote_id: str,
    payload: ExportQuoteRequest,
    request: Request,
) -> JSONResponse:
    try:
        export_record = service_for(request).export_quote(quote_id, model_to_dict(payload))
        return api_success({"export": export_record}, status_code=201)
    except QuoteV2NotFoundError as exc:
        return not_found(exc)


def service_for(request: Request) -> QuoteV2Service:
    service = getattr(request.app.state, "quote_v2_service", None)
    if service is None:
        service = QuoteV2Service()
        request.app.state.quote_v2_service = service
    return service


def latest_run_id_for_case(service: QuoteV2Service, case_id: str) -> str:
    run_ids = [
        run_id
        for run_id, run in service.analysis_runs.items()
        if run.get("case_id") == case_id
    ]
    if not run_ids:
        raise QuoteV2NotFoundError("analysis_run", case_id)
    return run_ids[-1]


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def api_success(data: dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "data": data,
            "error": None,
        },
    )


def not_found(exc: QuoteV2NotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": f"{exc.resource.upper()}_NOT_FOUND",
                "message": str(exc),
                "details": [{"resource": exc.resource, "id": exc.resource_id}],
            },
        },
    )
