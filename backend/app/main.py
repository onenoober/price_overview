from __future__ import annotations

import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .ai_assistance import AiAssistanceService, build_ai_assistance_service
from .database import (
    DEFAULT_DB_PATH,
    FILE_PARSE_STATUSES,
    FILE_STATUSES,
    FILE_TYPES,
    get_connection,
    init_database,
)
from .export_service import EXPORT_ROOT, build_export_payload, write_json_export
from .local_config import load_local_env_files
from .manual_override import (
    ManualOverrideError,
    apply_manual_override,
    build_manual_override,
)
from .material_archive import lookup_material_density
from .part_feature_builder import (
    build_part_feature,
    missing_file_risk,
)
from .parser_service import ParserService, build_parser_service
from .pricing_core import (
    PricingCoreService,
    build_pricing_core_service,
    is_chemical_plating,
)
from .repository import (
    delete_ai_outputs_for_task,
    get_export_record,
    get_latest_part_file,
    get_latest_quote_result_by_task,
    get_next_file_version,
    get_part_file,
    get_parse_result,
    get_quote_result,
    get_quote_task,
    insert_ai_outputs,
    insert_export_record,
    insert_part_file,
    insert_quote_task,
    insert_quote_result,
    list_ai_outputs,
    list_quote_tasks,
    list_part_files,
    mark_task_confirmed,
    mark_task_parsed,
    mark_task_priced,
    mark_task_uploaded,
    update_part_file_parse_status,
    update_part_file_status,
    update_quote_result,
    upsert_parse_result,
)
from .schema_validation import (
    ContractValidationError,
    validate_part_feature,
    validate_process_route,
    validate_quantity_result,
    validate_quote_result,
)
from .storage import FileTooLargeError, REPO_ROOT, UPLOAD_ROOT, save_stream_to_storage


ALLOWED_EXTENSIONS = {
    "pdf": {".pdf"},
    "step": {".step", ".stp"},
    "attachment": None,
}
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024

CHINA_TZ = timezone(timedelta(hours=8))


class CreateTaskRequest(BaseModel):
    customer_name: str
    part_name: str
    part_no: str = ""
    quantity: int = 1
    task_id: str | None = None


class ParseRequest(BaseModel):
    parse_pdf: bool = True
    parse_step: bool = True
    use_ai: bool = False
    pdf_file_id: str | None = None
    step_file_id: str | None = None


class PriceRequest(BaseModel):
    price_version: str = "a-basic-v1"
    rounding_rule: str = "a_basic_rounding_ui_only"
    use_ai: bool = False
    use_market_price_search: bool = True
    material_region: str = "south_china"


class OverrideRequest(BaseModel):
    target_type: str
    target_id: str
    field: str
    old_value: Any = None
    new_value: Any = None
    reason: str
    operator_id: str
    use_ai: bool = False


class ConfirmQuoteRequest(BaseModel):
    confirmed_total_amount: float
    confirmed_by: str
    confirm_note: str


class ExportRequest(BaseModel):
    format: str = "json"
    include_initial_quote: bool = True
    include_manual_overrides: bool = True
    include_risks: bool = True


def create_app(
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    upload_root: Path | str = UPLOAD_ROOT,
    export_root: Path | str = EXPORT_ROOT,
    ai_service: AiAssistanceService | None = None,
    parser_service: ParserService | None = None,
    pricing_core_service: PricingCoreService | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_database(app.state.db_path)
        yield

    app = FastAPI(title="price_overview backend", lifespan=lifespan)
    app.state.db_path = Path(db_path)
    app.state.upload_root = Path(upload_root)
    app.state.export_root = Path(export_root)
    load_local_env_files()
    app.state.ai_service = ai_service or build_ai_assistance_service()
    app.state.parser_service = parser_service or build_parser_service()
    app.state.pricing_core_service = pricing_core_service or build_pricing_core_service()

    @app.get("/api/quote-tasks")
    async def list_tasks(request: Request) -> JSONResponse:
        connection = get_connection(request.app.state.db_path)

        try:
            tasks = list_quote_tasks(connection)
            return api_success({"tasks": tasks})
        finally:
            connection.close()

    @app.post("/api/quote-tasks")
    async def create_quote_task(
        request: Request,
        task_request: CreateTaskRequest,
    ) -> JSONResponse:
        customer_name = task_request.customer_name.strip()
        part_name = task_request.part_name.strip()
        part_no = task_request.part_no.strip()
        task_id = (
            task_request.task_id.strip()
            if task_request.task_id and task_request.task_id.strip()
            else f"task_{uuid.uuid4().hex[:12]}"
        )

        validation_errors = []
        if not customer_name:
            validation_errors.append(
                {"field": "customer_name", "message": "customer_name is required"}
            )
        if not part_name:
            validation_errors.append(
                {"field": "part_name", "message": "part_name is required"}
            )
        if task_request.quantity <= 0:
            validation_errors.append(
                {"field": "quantity", "message": "quantity must be greater than 0"}
            )

        if validation_errors:
            return api_error(
                "VALIDATION_ERROR",
                "报价任务参数不合法",
                validation_errors,
            )

        connection = get_connection(request.app.state.db_path)
        try:
            existing = get_quote_task(connection, task_id)
            if existing is not None:
                return api_error(
                    "TASK_ALREADY_EXISTS",
                    "报价任务ID已存在",
                    [{"field": "task_id", "message": task_id}],
                    status_code=409,
                )

            now = now_iso()
            task = insert_quote_task(
                connection,
                task_id=task_id,
                customer_name=customer_name,
                part_name=part_name,
                part_no=part_no,
                quantity=task_request.quantity,
                now=now,
            )
            connection.commit()
            return api_success({"task": task}, status_code=201)
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            return api_error(
                "DATABASE_ERROR",
                "报价任务创建失败",
                [{"message": str(exc)}],
                status_code=500,
            )
        finally:
            connection.close()

    @app.get("/api/quote-tasks/{task_id}")
    async def read_quote_task(
        request: Request,
        task_id: str,
    ) -> JSONResponse:
        connection = get_connection(request.app.state.db_path)

        try:
            task = get_quote_task(connection, task_id)
            if task is None:
                return api_error(
                    "TASK_NOT_FOUND",
                    "报价任务不存在",
                    [{"field": "task_id", "message": task_id}],
                    status_code=404,
                )

            files = list_part_files(connection, task_id)
            parse_result = get_parse_result(connection, task_id)
            latest_quote_record = get_latest_quote_result_by_task(connection, task_id)
            latest_quote_result = (
                latest_quote_record["quote_result"]
                if latest_quote_record
                else None
            )
            latest_process_route = (
                latest_quote_record["process_route"]
                if latest_quote_record
                else None
            )
            latest_quantity_result = (
                latest_quote_record["quantity_result"]
                if latest_quote_record
                else None
            )
            risks = build_current_risks(parse_result, latest_quote_result)
            ai_outputs = list_ai_outputs(connection, task_id)

            return api_success(
                {
                    "task_id": task["task_id"],
                    "status": task["status"],
                    "task": task,
                    "files": files,
                    "latest_quote_id": latest_quote_record["quote_id"]
                    if latest_quote_record
                    else None,
                    "risks": risks,
                    "parse_result": parse_result,
                    "latest_process_route": latest_process_route,
                    "latest_quantity_result": latest_quantity_result,
                    "latest_quote_result": latest_quote_result,
                    "ai_outputs": ai_outputs,
                }
            )
        finally:
            connection.close()

    @app.post("/api/quote-tasks/{task_id}/files")
    async def upload_quote_task_file(
        request: Request,
        task_id: str,
        file: UploadFile = File(...),
        file_type: str = Form(...),
        uploaded_by: str = Form("system"),
    ) -> JSONResponse:
        connection = get_connection(request.app.state.db_path)
        stored_file_path: Path | None = None

        try:
            task = get_quote_task(connection, task_id)
            if task is None:
                return api_error(
                    "TASK_NOT_FOUND",
                    "报价任务不存在",
                    [{"field": "task_id", "message": task_id}],
                    status_code=404,
                )

            normalized_file_type = file_type.strip().lower()
            if normalized_file_type not in FILE_TYPES:
                return api_error(
                    "INVALID_FILE_TYPE",
                    "文件类型不合法",
                    [{"field": "file_type", "allowed": list(FILE_TYPES)}],
                )

            filename = file.filename or ""
            if not filename:
                return api_error(
                    "VALIDATION_ERROR",
                    "文件名不能为空",
                    [{"field": "file", "message": "missing filename"}],
                )

            if not is_extension_allowed(filename, normalized_file_type):
                return api_error(
                    "INVALID_EXTENSION",
                    "文件扩展名与文件类型不匹配",
                    [
                        {
                            "field": "file",
                            "filename": filename,
                            "file_type": normalized_file_type,
                            "allowed": sorted(
                                ALLOWED_EXTENSIONS[normalized_file_type] or []
                            ),
                        }
                    ],
                )

            version = get_next_file_version(
                connection,
                task_id,
                normalized_file_type,
            )
            file_id = f"file_{uuid.uuid4().hex[:12]}"

            await file.seek(0)
            stored_file = save_stream_to_storage(
                file.file,
                task_id=task_id,
                file_type=normalized_file_type,
                file_id=file_id,
                version=version,
                original_filename=filename,
                upload_root=request.app.state.upload_root,
                max_size_bytes=MAX_UPLOAD_SIZE_BYTES,
            )
            stored_file_path = resolve_storage_path(stored_file.storage_path)

            now = now_iso()
            inserted_file = insert_part_file(
                connection,
                stored_file,
                uploaded_by=uploaded_by.strip() or "system",
                uploaded_at=now,
            )
            mark_task_uploaded(connection, task_id, now)
            connection.commit()

            return api_success(
                {
                    "file_id": inserted_file["file_id"],
                    "task_id": inserted_file["task_id"],
                    "file_type": inserted_file["file_type"],
                    "filename": inserted_file["filename"],
                    "version": inserted_file["version"],
                    "status": inserted_file["status"],
                }
            )
        except ValueError as exc:
            connection.rollback()
            cleanup_stored_file(stored_file_path, request.app.state.upload_root)
            if isinstance(exc, FileTooLargeError):
                return api_error(
                    "FILE_TOO_LARGE",
                    "文件超过大小限制",
                    [
                        {
                            "field": "file",
                            "max_size_bytes": MAX_UPLOAD_SIZE_BYTES,
                        }
                    ],
                    status_code=413,
                )
            if "empty file" in str(exc):
                return api_error(
                    "EMPTY_FILE",
                    "文件不能为空",
                    [{"field": "file", "message": str(exc)}],
                )
            return api_error(
                "VALIDATION_ERROR",
                "参数不合法",
                [{"message": str(exc)}],
            )
        except FileExistsError as exc:
            connection.rollback()
            return api_error(
                "STORAGE_ERROR",
                "文件已存在，无法覆盖旧版本",
                [{"message": str(exc)}],
                status_code=500,
            )
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            cleanup_stored_file(stored_file_path, request.app.state.upload_root)
            return api_error(
                "DATABASE_ERROR",
                "文件记录保存失败",
                [{"message": str(exc)}],
                status_code=500,
            )
        except Exception as exc:
            connection.rollback()
            cleanup_stored_file(stored_file_path, request.app.state.upload_root)
            return api_error(
                "INTERNAL_ERROR",
                "上传失败",
                [{"message": str(exc)}],
                status_code=500,
            )
        finally:
            connection.close()
            await file.close()

    @app.post("/api/quote-tasks/{task_id}/files/{file_id}/invalidate")
    async def invalidate_quote_task_file(
        request: Request,
        task_id: str,
        file_id: str,
    ) -> JSONResponse:
        return update_file_lifecycle_status(
            request=request,
            task_id=task_id,
            file_id=file_id,
            status="invalid",
            parse_status="failed",
        )

    @app.delete("/api/quote-tasks/{task_id}/files/{file_id}")
    async def delete_quote_task_file(
        request: Request,
        task_id: str,
        file_id: str,
    ) -> JSONResponse:
        return update_file_lifecycle_status(
            request=request,
            task_id=task_id,
            file_id=file_id,
            status="deleted",
            parse_status="skipped",
        )

    @app.post("/api/quote-tasks/{task_id}/parse")
    async def parse_quote_task(
        request: Request,
        task_id: str,
        parse_request: ParseRequest | None = None,
    ) -> JSONResponse:
        options = parse_request or ParseRequest()
        connection = get_connection(request.app.state.db_path)

        try:
            task = get_quote_task(connection, task_id)
            if task is None:
                return api_error(
                    "TASK_NOT_FOUND",
                    "报价任务不存在",
                    [{"field": "task_id", "message": task_id}],
                    status_code=404,
                )

            pdf_file = None
            step_file = None
            if options.parse_pdf:
                pdf_file, error = select_parse_file(
                    connection,
                    task_id=task_id,
                    file_type="pdf",
                    file_id=options.pdf_file_id,
                )
                if error:
                    return error
            if options.parse_step:
                step_file, error = select_parse_file(
                    connection,
                    task_id=task_id,
                    file_type="step",
                    file_id=options.step_file_id,
                )
                if error:
                    return error

            risks: list[dict[str, Any]] = []
            ai_outputs: list[dict[str, Any]] = []
            pdf_result = None
            step_result = None
            material_density = None
            parser_service: ParserService = request.app.state.parser_service

            if options.parse_pdf:
                if pdf_file:
                    pdf_result, parser_risks = parser_service.parse_pdf(
                        task=task,
                        pdf_file=pdf_file,
                    )
                    risks.extend(parser_risks)
                else:
                    risks.append(missing_file_risk(task_id, "pdf"))

            if pdf_result:
                material_density = lookup_material_density(pdf_result.get("material_raw"))

            if options.parse_step:
                if step_file:
                    step_result, parser_risks = parser_service.parse_step(
                        task=task,
                        step_file=step_file,
                        material_density=(
                            material_density.to_step_density()
                            if material_density
                            else None
                        ),
                    )
                    risks.extend(parser_risks)
                else:
                    risks.append(missing_file_risk(task_id, "step"))

            part_feature = build_part_feature(
                task,
                pdf_result,
                step_result,
                risks,
            )
            validate_part_feature(part_feature)

            if options.use_ai:
                ai_outputs = build_parse_ai_outputs(
                    ai_service=request.app.state.ai_service,
                    task_id=task_id,
                    pdf_result=pdf_result,
                    risks=part_feature["risks"],
                    material_density=material_density,
                )

            parse_job_id = f"parse_job_{uuid.uuid4().hex[:12]}"
            now = now_iso()

            upsert_parse_result(
                connection,
                task_id=task_id,
                parse_job_id=parse_job_id,
                status="completed",
                pdf_extract_result=pdf_result,
                step_feature_result=step_result,
                part_feature=part_feature,
                risks=part_feature["risks"],
                now=now,
            )
            if pdf_result and pdf_file:
                update_part_file_parse_status(
                    connection,
                    file_id=pdf_file["file_id"],
                    parse_status="parsed",
                )
            elif options.parse_pdf and pdf_file:
                update_part_file_parse_status(
                    connection,
                    file_id=pdf_file["file_id"],
                    parse_status="failed",
                )
            if step_result and step_file:
                update_part_file_parse_status(
                    connection,
                    file_id=step_file["file_id"],
                    parse_status="parsed",
                )
            elif options.parse_step and step_file:
                update_part_file_parse_status(
                    connection,
                    file_id=step_file["file_id"],
                    parse_status="failed",
                )
            delete_ai_outputs_for_task(connection, task_id)
            insert_ai_outputs(connection, ai_outputs)

            if pdf_result or step_result:
                mark_task_parsed(connection, task_id, now)

            connection.commit()

            return api_success(
                {
                    "parse_job_id": parse_job_id,
                    "status": "completed",
                }
            )
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            return api_error(
                "DATABASE_ERROR",
                "解析结果保存失败",
                [{"message": str(exc)}],
                status_code=500,
            )
        except ContractValidationError as exc:
            connection.rollback()
            return api_error(
                "PART_FEATURE_CONTRACT_ERROR",
                "part_feature 不符合数据契约",
                exc.details,
                status_code=500,
            )
        except Exception as exc:
            connection.rollback()
            return api_error(
                "INTERNAL_ERROR",
                "解析失败",
                [{"message": str(exc)}],
                status_code=500,
            )
        finally:
            connection.close()

    @app.get("/api/quote-tasks/{task_id}/parse-result")
    async def read_parse_result(
        request: Request,
        task_id: str,
    ) -> JSONResponse:
        connection = get_connection(request.app.state.db_path)

        try:
            task = get_quote_task(connection, task_id)
            if task is None:
                return api_error(
                    "TASK_NOT_FOUND",
                    "报价任务不存在",
                    [{"field": "task_id", "message": task_id}],
                    status_code=404,
                )

            result = get_parse_result(connection, task_id)
            if result is None:
                return api_error(
                    "PARSE_RESULT_NOT_FOUND",
                    "解析结果不存在",
                    [{"field": "task_id", "message": task_id}],
                    status_code=404,
                )

            return api_success(
                {
                    "pdf_extract_result": result["pdf_extract_result"],
                    "step_feature_result": result["step_feature_result"],
                    "part_feature": result["part_feature"],
                    "risks": result["risks"],
                }
            )
        finally:
            connection.close()

    @app.post("/api/quote-tasks/{task_id}/price")
    async def create_price(
        request: Request,
        task_id: str,
        price_request: PriceRequest | None = None,
    ) -> JSONResponse:
        options = price_request or PriceRequest()
        connection = get_connection(request.app.state.db_path)

        try:
            task = get_quote_task(connection, task_id)
            if task is None:
                return api_error(
                    "TASK_NOT_FOUND",
                    "报价任务不存在",
                    [{"field": "task_id", "message": task_id}],
                    status_code=404,
                )

            parse_result = get_parse_result(connection, task_id)
            if parse_result is None:
                return api_error(
                    "PARSE_RESULT_NOT_FOUND",
                    "请先生成 part_feature，再生成报价结果",
                    [{"field": "task_id", "message": task_id}],
                    status_code=409,
                )

            quote_id = f"quote_{uuid.uuid4().hex[:12]}"
            now = now_iso()
            pricing_core_service: PricingCoreService = request.app.state.pricing_core_service
            pricing_result = pricing_core_service.build_quote(
                task_id=task_id,
                quote_id=quote_id,
                part_feature=parse_result["part_feature"],
                risks=parse_result["risks"],
                priced_at=now,
                price_version=options.price_version or "a-basic-v1",
                use_market_price_search=options.use_market_price_search,
                material_region=options.material_region or "south_china",
            )
            process_route = pricing_result.process_route
            quantity_result = pricing_result.quantity_result
            quote_result = pricing_result.quote_result

            validate_process_route(process_route)
            validate_quantity_result(quantity_result)
            validate_quote_result(quote_result)

            ai_outputs: list[dict[str, Any]] = []
            if options.use_ai:
                ai_service: AiAssistanceService = request.app.state.ai_service
                ai_outputs = [
                    ai_service.explain_operation(task_id=task_id, operation=operation)
                    for operation in process_route.get("operations") or []
                ]
            insert_quote_result(
                connection,
                quote_result=quote_result,
                process_route=process_route,
                quantity_result=quantity_result,
                now=now,
            )
            insert_ai_outputs(connection, ai_outputs)
            mark_task_priced(connection, task_id, quote_result["status"], now)
            connection.commit()

            return api_success(
                {
                    "quote_id": quote_id,
                    "status": quote_result["status"],
                    "process_route": process_route,
                    "quantity_result": quantity_result,
                    "quote_result": quote_result,
                }
            )
        except ContractValidationError as exc:
            connection.rollback()
            return api_error(
                "QUOTE_RESULT_CONTRACT_ERROR",
                "报价结果不符合数据契约",
                exc.details,
                status_code=500,
            )
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            return api_error(
                "DATABASE_ERROR",
                "报价结果保存失败",
                [{"message": str(exc)}],
                status_code=500,
            )
        except Exception as exc:
            connection.rollback()
            return api_error(
                "INTERNAL_ERROR",
                "报价结果生成失败",
                [{"message": str(exc)}],
                status_code=500,
            )
        finally:
            connection.close()

    @app.get("/api/quotes/{quote_id}")
    async def read_quote_result(
        request: Request,
        quote_id: str,
    ) -> JSONResponse:
        connection = get_connection(request.app.state.db_path)

        try:
            result = get_quote_result(connection, quote_id)
            if result is None:
                return api_error(
                    "QUOTE_RESULT_NOT_FOUND",
                    "报价结果不存在",
                    [{"field": "quote_id", "message": quote_id}],
                    status_code=404,
                )

            return api_success(
                {
                    "process_route": result["process_route"],
                    "quantity_result": result["quantity_result"],
                    "quote_result": result["quote_result"],
                }
            )
        finally:
            connection.close()

    @app.post("/api/quotes/{quote_id}/overrides")
    async def save_manual_override(
        request: Request,
        quote_id: str,
        override_request: OverrideRequest,
    ) -> JSONResponse:
        connection = get_connection(request.app.state.db_path)

        try:
            result = get_quote_result(connection, quote_id)
            if result is None:
                return api_error(
                    "QUOTE_RESULT_NOT_FOUND",
                    "报价结果不存在",
                    [{"field": "quote_id", "message": quote_id}],
                    status_code=404,
                )

            reason = override_request.reason.strip()
            if not reason:
                return api_error(
                    "VALIDATION_ERROR",
                    "修改原因必填",
                    [{"field": "reason", "message": "reason is required"}],
                )

            operator_id = override_request.operator_id.strip()
            if not operator_id:
                return api_error(
                    "VALIDATION_ERROR",
                    "操作人必填",
                    [{"field": "operator_id", "message": "operator_id is required"}],
                )

            now = now_iso()
            override = build_manual_override(
                override_id=f"override_{uuid.uuid4().hex[:12]}",
                target_type=override_request.target_type,
                target_id=override_request.target_id,
                field=override_request.field,
                old_value=override_request.old_value,
                new_value=override_request.new_value,
                reason=reason,
                operator_id=operator_id,
                created_at=now,
            )

            process_route = result["process_route"]
            quantity_result = result["quantity_result"]
            quote_result = apply_manual_override(
                result["quote_result"],
                override,
                process_route=process_route,
                quantity_result=quantity_result,
            )
            if process_route is not None:
                validate_process_route(process_route)
            if quantity_result is not None:
                validate_quantity_result(quantity_result)
            validate_quote_result(quote_result)
            update_quote_result(
                connection,
                quote_result=quote_result,
                process_route=process_route,
                quantity_result=quantity_result,
                now=now,
            )
            if override_request.use_ai:
                ai_service: AiAssistanceService = request.app.state.ai_service
                insert_ai_outputs(
                    connection,
                    [
                        ai_service.analyze_override_history(
                            task_id=quote_result["task_id"],
                            overrides=quote_result.get("manual_overrides") or [],
                            quote_result=quote_result,
                        )
                    ],
                )
            connection.commit()

            return api_success(
                {
                    "override_id": override["override_id"],
                    "quote_id": quote_id,
                    "saved": True,
                }
            )
        except ManualOverrideError as exc:
            connection.rollback()
            return api_error(
                exc.code,
                exc.message,
                exc.details,
                status_code=exc.status_code,
            )
        except ContractValidationError as exc:
            connection.rollback()
            return api_error(
                "QUOTE_RESULT_CONTRACT_ERROR",
                "quote_result 不符合数据契约",
                exc.details,
                status_code=500,
            )
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            return api_error(
                "DATABASE_ERROR",
                "人工修改保存失败",
                [{"message": str(exc)}],
                status_code=500,
            )
        finally:
            connection.close()

    @app.post("/api/quotes/{quote_id}/confirm")
    async def confirm_quote_result(
        request: Request,
        quote_id: str,
        confirm_request: ConfirmQuoteRequest,
    ) -> JSONResponse:
        connection = get_connection(request.app.state.db_path)

        try:
            result = get_quote_result(connection, quote_id)
            if result is None:
                return api_error(
                    "QUOTE_RESULT_NOT_FOUND",
                    "报价结果不存在",
                    [{"field": "quote_id", "message": quote_id}],
                    status_code=404,
                )

            quote_result = result["quote_result"]
            if quote_result["status"] in {"confirmed", "voided"}:
                return api_error(
                    "QUOTE_READONLY",
                    "已确认或作废的报价不可再次确认",
                    [{"field": "quote_id", "message": quote_id}],
                    status_code=409,
                )

            confirmed_by = confirm_request.confirmed_by.strip()
            if not confirmed_by:
                return api_error(
                    "VALIDATION_ERROR",
                    "确认人必填",
                    [{"field": "confirmed_by", "message": "confirmed_by is required"}],
                )

            confirm_note = confirm_request.confirm_note.strip()
            if not confirm_note:
                return api_error(
                    "VALIDATION_ERROR",
                    "确认说明必填",
                    [{"field": "confirm_note", "message": "confirm_note is required"}],
                )

            confirmed_total_amount = round(
                float(confirm_request.confirmed_total_amount),
                2,
            )
            if confirmed_total_amount < 0:
                return api_error(
                    "VALIDATION_ERROR",
                    "确认金额不能小于 0",
                    [
                        {
                            "field": "confirmed_total_amount",
                            "message": confirm_request.confirmed_total_amount,
                        }
                    ],
                )

            blocking_risks = unconfirmed_blocking_risks(quote_result)
            if blocking_risks:
                return api_error(
                    "BLOCKING_RISK_UNCONFIRMED",
                    "存在未确认的阻断风险，不能确认报价",
                    [
                        {
                            "code": risk.get("code"),
                            "message": risk.get("message"),
                        }
                        for risk in blocking_risks
                    ],
                    status_code=409,
                )

            now = now_iso()
            summary = quote_result["summary"]
            old_confirmed_amount = summary.get("final_confirmed_amount")
            summary["final_confirmed_amount"] = confirmed_total_amount
            summary["manual_adjustment_amount"] = round(
                confirmed_total_amount - float(summary["system_initial_quote"]),
                2,
            )
            quote_result["status"] = "confirmed"
            quote_result["confirmed_at"] = now
            quote_result["confirmed_by"] = confirmed_by
            quote_result.setdefault("manual_overrides", []).append(
                build_manual_override(
                    override_id=f"override_{uuid.uuid4().hex[:12]}",
                    target_type="quote_summary",
                    target_id="summary",
                    field="final_confirmed_amount",
                    old_value=old_confirmed_amount,
                    new_value=confirmed_total_amount,
                    reason=confirm_note,
                    operator_id=confirmed_by,
                    created_at=now,
                )
            )

            validate_quote_result(quote_result)
            update_quote_result(connection, quote_result=quote_result, now=now)
            mark_task_confirmed(connection, quote_result["task_id"], now)
            connection.commit()

            return api_success(
                {
                    "quote_id": quote_id,
                    "status": "confirmed",
                    "confirmed_at": now,
                }
            )
        except ContractValidationError as exc:
            connection.rollback()
            return api_error(
                "QUOTE_RESULT_CONTRACT_ERROR",
                "quote_result 不符合数据契约",
                exc.details,
                status_code=500,
            )
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            return api_error(
                "DATABASE_ERROR",
                "报价确认保存失败",
                [{"message": str(exc)}],
                status_code=500,
            )
        finally:
            connection.close()

    @app.post("/api/quotes/{quote_id}/export")
    async def export_quote_result(
        request: Request,
        quote_id: str,
        export_request: ExportRequest | None = None,
    ) -> JSONResponse:
        options = export_request or ExportRequest()
        export_format = options.format.strip().lower()
        if export_format != "json":
            return api_error(
                "UNSUPPORTED_EXPORT_FORMAT",
                "第一版仅支持 json 导出",
                [{"field": "format", "message": options.format}],
            )

        connection = get_connection(request.app.state.db_path)
        export_path: Path | None = None

        try:
            quote_record = get_quote_result(connection, quote_id)
            if quote_record is None:
                return api_error(
                    "QUOTE_RESULT_NOT_FOUND",
                    "报价结果不存在",
                    [{"field": "quote_id", "message": quote_id}],
                    status_code=404,
                )

            quote_result = quote_record["quote_result"]
            task = get_quote_task(connection, quote_result["task_id"])
            if task is None:
                return api_error(
                    "TASK_NOT_FOUND",
                    "报价任务不存在",
                    [{"field": "task_id", "message": quote_result["task_id"]}],
                    status_code=404,
                )

            parse_result = get_parse_result(connection, quote_result["task_id"])
            files = list_part_files(connection, quote_result["task_id"])
            export_id = f"export_{uuid.uuid4().hex[:12]}"
            now = now_iso()
            payload = build_export_payload(
                export_id=export_id,
                quote_id=quote_id,
                exported_at=now,
                task=task,
                files=files,
                parse_result=parse_result,
                process_route=quote_record["process_route"],
                quantity_result=quote_record["quantity_result"],
                quote_result=quote_result,
                include_initial_quote=options.include_initial_quote,
                include_manual_overrides=options.include_manual_overrides,
                include_risks=options.include_risks,
            )
            storage_path = write_json_export(
                export_id=export_id,
                payload=payload,
                export_root=request.app.state.export_root,
            )
            export_path = resolve_export_path(
                storage_path,
                request.app.state.export_root,
            )

            insert_export_record(
                connection,
                export_id=export_id,
                quote_id=quote_id,
                export_format=export_format,
                storage_path=storage_path,
                created_at=now,
            )
            connection.commit()

            return api_success(
                {
                    "export_id": export_id,
                    "download_url": f"/api/exports/{export_id}/download",
                }
            )
        except FileExistsError as exc:
            connection.rollback()
            return api_error(
                "EXPORT_FILE_EXISTS",
                "导出文件已存在",
                [{"message": str(exc)}],
                status_code=500,
            )
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            cleanup_export_file(export_path, request.app.state.export_root)
            return api_error(
                "DATABASE_ERROR",
                "导出记录保存失败",
                [{"message": str(exc)}],
                status_code=500,
            )
        except Exception as exc:
            connection.rollback()
            cleanup_export_file(export_path, request.app.state.export_root)
            return api_error(
                "INTERNAL_ERROR",
                "导出失败",
                [{"message": str(exc)}],
                status_code=500,
            )
        finally:
            connection.close()

    @app.get("/api/exports/{export_id}/download")
    async def download_export(
        request: Request,
        export_id: str,
    ):
        connection = get_connection(request.app.state.db_path)

        try:
            record = get_export_record(connection, export_id)
            if record is None:
                return api_error(
                    "EXPORT_NOT_FOUND",
                    "导出记录不存在",
                    [{"field": "export_id", "message": export_id}],
                    status_code=404,
                )

            path = resolve_export_path(
                record["storage_path"],
                request.app.state.export_root,
            )
            if not path.exists():
                return api_error(
                    "EXPORT_FILE_NOT_FOUND",
                    "导出文件不存在",
                    [{"field": "storage_path", "message": record["storage_path"]}],
                    status_code=404,
                )

            return FileResponse(
                path,
                media_type="application/json",
                filename=path.name,
            )
        finally:
            connection.close()

    return app


def update_file_lifecycle_status(
    *,
    request: Request,
    task_id: str,
    file_id: str,
    status: str,
    parse_status: str,
) -> JSONResponse:
    if status not in FILE_STATUSES:
        return api_error(
            "INVALID_FILE_STATUS",
            "文件状态不合法",
            [{"field": "status", "allowed": list(FILE_STATUSES)}],
        )
    if parse_status not in FILE_PARSE_STATUSES:
        return api_error(
            "INVALID_FILE_PARSE_STATUS",
            "文件解析状态不合法",
            [{"field": "parse_status", "allowed": list(FILE_PARSE_STATUSES)}],
        )

    connection = get_connection(request.app.state.db_path)
    try:
        task = get_quote_task(connection, task_id)
        if task is None:
            return api_error(
                "TASK_NOT_FOUND",
                "报价任务不存在",
                [{"field": "task_id", "message": task_id}],
                status_code=404,
            )

        file_record = get_part_file(connection, task_id, file_id)
        if file_record is None:
            return api_error(
                "FILE_NOT_FOUND",
                "文件记录不存在",
                [{"field": "file_id", "message": file_id}],
                status_code=404,
            )

        updated_file = update_part_file_status(
            connection,
            task_id=task_id,
            file_id=file_id,
            status=status,
            parse_status=parse_status,
        )
        connection.commit()
        return api_success({"file": updated_file})
    except sqlite3.IntegrityError as exc:
        connection.rollback()
        return api_error(
            "DATABASE_ERROR",
            "文件状态更新失败",
            [{"message": str(exc)}],
            status_code=500,
        )
    finally:
        connection.close()


def select_parse_file(
    connection: sqlite3.Connection,
    *,
    task_id: str,
    file_type: str,
    file_id: str | None,
) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    requested_file_id = file_id.strip() if file_id else None
    if not requested_file_id:
        return get_latest_part_file(connection, task_id, file_type), None

    file_record = get_part_file(connection, task_id, requested_file_id)
    if file_record is None:
        return None, api_error(
            "FILE_NOT_FOUND",
            "解析文件不存在",
            [{"field": f"{file_type}_file_id", "message": requested_file_id}],
            status_code=404,
        )

    if file_record["file_type"] != file_type:
        return None, api_error(
            "FILE_TYPE_MISMATCH",
            "解析文件类型不匹配",
            [
                {
                    "field": f"{file_type}_file_id",
                    "message": requested_file_id,
                    "actual_file_type": file_record["file_type"],
                }
            ],
        )

    if file_record["status"] != "uploaded":
        return None, api_error(
            "FILE_NOT_AVAILABLE",
            "解析文件不是有效上传状态",
            [
                {
                    "field": f"{file_type}_file_id",
                    "message": requested_file_id,
                    "status": file_record["status"],
                }
            ],
            status_code=409,
        )

    return file_record, None


def build_parse_ai_outputs(
    *,
    ai_service: AiAssistanceService,
    task_id: str,
    pdf_result: dict[str, Any] | None,
    risks: list[dict[str, Any]],
    material_density: Any | None = None,
) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []

    if pdf_result:
        material_raw = normalized_pdf_text(pdf_result.get("material_raw"))
        if material_raw and material_density is None:
            material_evidence = pdf_field_evidence_list(
                pdf_result,
                "material_raw",
                raw_text=material_raw,
            )
            outputs.append(
                ai_service.normalize_material(
                    task_id=task_id,
                    raw_text=material_raw,
                    evidence=material_evidence,
                )
            )

        surface_raw = normalized_pdf_text(pdf_result.get("surface_treatment_raw"))
        if surface_raw and surface_treatment_needs_ai(surface_raw):
            outputs.append(
                ai_service.normalize_surface_treatment(
                    task_id=task_id,
                    raw_text=surface_raw,
                    evidence=pdf_field_evidence_list(
                        pdf_result,
                        "surface_treatment_raw",
                        raw_text=surface_raw,
                    ),
                )
            )

    for risk in risks:
        outputs.append(ai_service.explain_risk(task_id=task_id, risk=risk))

    return outputs


def surface_treatment_needs_ai(raw_text: str) -> bool:
    return not is_chemical_plating({"raw_text": raw_text})


def normalized_pdf_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def pdf_field_evidence_list(
    pdf_result: dict[str, Any],
    field_key: str,
    *,
    raw_text: str | None,
) -> list[dict[str, Any]]:
    evidence = (pdf_result.get("field_evidence") or {}).get(field_key)
    if isinstance(evidence, list):
        return [item for item in evidence if isinstance(item, dict)]
    if isinstance(evidence, dict):
        return [evidence]
    return [
        {
            "source_type": "pdf",
            "file_id": pdf_result.get("file_id"),
            "raw_text": raw_text,
            "rule_code": f"PDF_FIELD:{field_key}",
        }
    ]


def api_success(data: dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "data": data,
            "error": None,
        },
    )


def api_error(
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    *,
    status_code: int = 400,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": code,
                "message": message,
                "details": details or [],
            },
        },
    )


def build_current_risks(
    parse_result: dict[str, Any] | None,
    latest_quote_result: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if latest_quote_result:
        return latest_quote_result.get("risks", [])
    if parse_result:
        return parse_result.get("risks", [])
    return []


def unconfirmed_blocking_risks(quote_result: dict[str, Any]) -> list[dict[str, Any]]:
    confirmed_risk_codes = {
        str(override.get("target_id"))
        for override in quote_result.get("manual_overrides", [])
        if override.get("target_type") == "risk"
        and override.get("field") == "confirmed"
        and truthy_value(override.get("new_value"))
    }
    return [
        risk
        for risk in quote_result.get("risks", [])
        if risk.get("level") == "blocking" and risk.get("requires_review")
        and str(risk.get("code")) not in confirmed_risk_codes
    ]


def truthy_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "是"}
    return bool(value)


def is_extension_allowed(filename: str, file_type: str) -> bool:
    allowed_extensions = ALLOWED_EXTENSIONS[file_type]
    if allowed_extensions is None:
        return True
    return Path(filename).suffix.lower() in allowed_extensions


def now_iso() -> str:
    return datetime.now(CHINA_TZ).isoformat(timespec="seconds")


def resolve_storage_path(storage_path: str) -> Path:
    path = Path(storage_path)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def cleanup_stored_file(path: Path | None, upload_root: Path | str) -> None:
    if path is None or not path.exists():
        return

    resolved = path.resolve()
    resolved_upload_root = Path(upload_root).resolve()
    try:
        resolved.relative_to(resolved_upload_root)
    except ValueError:
        return

    resolved.unlink()


def resolve_export_path(storage_path: str, export_root: Path | str) -> Path:
    path = Path(storage_path)
    if not path.is_absolute():
        path = REPO_ROOT / path

    resolved = path.resolve()
    resolved_export_root = Path(export_root).resolve()

    try:
        resolved.relative_to(resolved_export_root)
        return resolved
    except ValueError:
        default_export_root = EXPORT_ROOT.resolve()
        resolved.relative_to(default_export_root)
        return resolved


def cleanup_export_file(path: Path | None, export_root: Path | str) -> None:
    if path is None or not path.exists():
        return

    try:
        resolved = resolve_export_path(path.as_posix(), export_root)
    except ValueError:
        return

    resolved.unlink()


app = create_app()
