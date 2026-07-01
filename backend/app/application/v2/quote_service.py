from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.app.domain_v2.facts import FactSnapshot, FactValue

try:  # Planning is being introduced behind this service contract.
    from backend.app.domain_v2.planning import build_route_for_snapshot
except ImportError:  # pragma: no cover - exercised through the fallback path.
    build_route_for_snapshot = None  # type: ignore[assignment]


CHINA_TZ = timezone(timedelta(hours=8))
UNMAPPED_CATEGORY_REVIEW = "UNMAPPED_CATEGORY_REVIEW"

CASE_STAGES = [
    "case_created",
    "files_uploaded",
    "analysis_completed",
    "route_planned",
    "costed",
    "approved",
    "exported",
]


class QuoteV2NotFoundError(ValueError):
    def __init__(self, resource: str, resource_id: str) -> None:
        super().__init__(f"{resource} not found: {resource_id}")
        self.resource = resource
        self.resource_id = resource_id


class QuoteV2Service:
    """Small in-memory implementation for the first API V2 contract slice."""

    def __init__(self) -> None:
        self.quote_cases: dict[str, dict[str, Any]] = {}
        self.files_by_case: dict[str, list[dict[str, Any]]] = {}
        self.analysis_runs: dict[str, dict[str, Any]] = {}
        self.facts_by_run: dict[str, list[dict[str, Any]]] = {}
        self.route_plans: dict[str, dict[str, Any]] = {}
        self.route_plans_by_run: dict[str, list[str]] = {}
        self.cost_scenarios: dict[str, dict[str, Any]] = {}
        self.quotes: dict[str, dict[str, Any]] = {}
        self.exports: dict[str, dict[str, Any]] = {}

    def create_quote_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        case_id = payload.get("case_id") or self._id("case")
        now = now_iso()
        quote_case = {
            "case_id": case_id,
            "customer_name": payload.get("customer_name") or "",
            "part_name": payload.get("part_name") or "",
            "part_no": payload.get("part_no") or "",
            "quantity": payload.get("quantity") or 1,
            "status": "created",
            "stages": build_stages("case_created"),
            "progress": 10,
            "created_at": now,
            "updated_at": now,
            "metadata": payload.get("metadata") or {},
        }
        self.quote_cases[case_id] = quote_case
        self.files_by_case.setdefault(case_id, [])
        return copy_record(quote_case)

    def list_quote_cases(self) -> list[dict[str, Any]]:
        return [copy_record(item) for item in self.quote_cases.values()]

    def add_file(
        self,
        *,
        case_id: str,
        filename: str,
        file_type: str,
        content_type: str | None = None,
        size_bytes: int = 0,
        uploaded_by: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        quote_case = self._case(case_id)
        now = now_iso()
        file_record = {
            "file_id": self._id("file"),
            "case_id": case_id,
            "filename": filename,
            "file_type": file_type,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "status": "uploaded",
            "uploaded_by": uploaded_by,
            "uploaded_at": now,
            "metadata": metadata or {},
        }
        self.files_by_case.setdefault(case_id, []).append(file_record)
        self._advance_case(quote_case, status="files_uploaded", active_stage="files_uploaded")
        return copy_record(file_record)

    def list_files(self, case_id: str) -> list[dict[str, Any]]:
        self._case(case_id)
        return [copy_record(item) for item in self.files_by_case.get(case_id, [])]

    def create_analysis_run(self, case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        quote_case = self._case(case_id)
        now = now_iso()
        run_id = self._id("run")
        run = {
            "run_id": run_id,
            "case_id": case_id,
            "status": "completed",
            "stages": [
                stage("queued", "completed", 25),
                stage("extract_facts", "completed", 70),
                stage("normalize_facts", "completed", 100),
            ],
            "progress": 100,
            "started_at": now,
            "completed_at": now,
            "options": payload.get("options") or {},
            "summary": "analysis skeleton completed",
        }
        facts = build_default_facts(
            quote_case=quote_case,
            files=self.files_by_case.get(case_id, []),
            run_id=run_id,
        )
        self.analysis_runs[run_id] = run
        self.facts_by_run[run_id] = facts
        self._advance_case(quote_case, status="analyzed", active_stage="analysis_completed")
        return copy_record(run)

    def get_analysis_run(self, run_id: str) -> dict[str, Any]:
        return copy_record(self._run(run_id))

    def list_facts(self, run_id: str) -> list[dict[str, Any]]:
        self._run(run_id)
        return [copy_record(item) for item in self.facts_by_run.get(run_id, [])]

    def create_route_plan(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        run = self._run(run_id)
        quote_case = self._case(run["case_id"])
        now = now_iso()
        plan_id = self._id("route")
        if payload.get("operations"):
            route_data = route_data_from_explicit_operations(payload["operations"])
        else:
            snapshot = fact_snapshot_from_records(
                self.facts_by_run.get(run_id, []),
                snapshot_id=run_id,
            )
            route_data = route_data_from_snapshot(snapshot)

        assumptions = list(payload.get("assumptions") or [])
        assumptions.extend(route_data.get("assumptions") or [])
        plan = {
            "route_plan_id": plan_id,
            "run_id": run_id,
            "case_id": run["case_id"],
            "status": "planned",
            "stages": [
                stage("select_template", "completed", 30),
                stage("build_operations", "completed", 80),
                stage("review_ready", "completed", 100),
            ],
            "progress": 100,
            "operations": route_data["operations"],
            "assumptions": assumptions,
            "business_category": route_data.get("business_category"),
            "route_profile": route_data.get("route_profile"),
            "planner_type": route_data.get("planner_type"),
            "requires_review": route_data.get("requires_review", False),
            "review_reason": route_data.get("review_reason"),
            "metadata": route_data.get("metadata") or {},
            "created_at": now,
        }
        self.route_plans[plan_id] = plan
        self.route_plans_by_run.setdefault(run_id, []).append(plan_id)
        self._advance_case(quote_case, status="route_planned", active_stage="route_planned")
        return copy_record(plan)

    def get_route_plan(self, route_plan_id: str) -> dict[str, Any]:
        return copy_record(self._route_plan(route_plan_id))

    def list_route_plans(self, run_id: str) -> list[dict[str, Any]]:
        self._run(run_id)
        return [
            copy_record(self.route_plans[plan_id])
            for plan_id in self.route_plans_by_run.get(run_id, [])
        ]

    def create_cost_scenario(self, route_plan_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        plan = self._route_plan(route_plan_id)
        quote_case = self._case(plan["case_id"])
        now = now_iso()
        scenario_id = self._id("scenario")
        quote_id = self._id("quote")
        quantity = int(quote_case.get("quantity") or 1)
        items = payload.get("items") or default_cost_items(quantity)
        total_amount = round(
            sum(float(item.get("amount") or 0) for item in items),
            2,
        )
        scenario = {
            "cost_scenario_id": scenario_id,
            "route_plan_id": route_plan_id,
            "case_id": plan["case_id"],
            "status": "costed",
            "stages": [
                stage("collect_quantities", "completed", 35),
                stage("price_operations", "completed", 80),
                stage("build_quote", "completed", 100),
            ],
            "progress": 100,
            "currency": payload.get("currency") or "CNY",
            "items": items,
            "total_amount": total_amount,
            "created_at": now,
        }
        quote = {
            "quote_id": quote_id,
            "cost_scenario_id": scenario_id,
            "case_id": plan["case_id"],
            "status": "draft",
            "currency": scenario["currency"],
            "total_amount": total_amount,
            "items": items,
            "approved_at": None,
            "approved_by": None,
            "created_at": now,
        }
        self.cost_scenarios[scenario_id] = scenario
        self.quotes[quote_id] = quote
        scenario["quote"] = quote
        self._advance_case(quote_case, status="costed", active_stage="costed")
        return copy_record(scenario)

    def get_cost_scenario(self, scenario_id: str) -> dict[str, Any]:
        return copy_record(self._cost_scenario(scenario_id))

    def create_quote_revision(self, scenario_id: str) -> dict[str, Any]:
        scenario = self._cost_scenario(scenario_id)
        quote = scenario.get("quote")
        if not isinstance(quote, dict):
            quote_id = self._id("quote")
            quote = {
                "quote_id": quote_id,
                "cost_scenario_id": scenario_id,
                "case_id": scenario["case_id"],
                "status": "draft",
                "currency": scenario["currency"],
                "total_amount": scenario["total_amount"],
                "items": scenario["items"],
                "approved_at": None,
                "approved_by": None,
                "created_at": now_iso(),
            }
            self.quotes[quote_id] = quote
            scenario["quote"] = quote
        return copy_record(quote)

    def create_route_revision(self, route_plan_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        plan = self._route_plan(route_plan_id)
        revision = {
            "route_revision_id": self._id("route_revision"),
            "route_plan_id": route_plan_id,
            "base_route_plan_id": route_plan_id,
            "status": "created",
            "command": payload,
            "operations": copy_record(plan).get("operations", []),
            "created_at": now_iso(),
        }
        plan.setdefault("revisions", []).append(revision)
        return copy_record(revision)

    def approve_quote(self, quote_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        quote = self._quote(quote_id)
        quote_case = self._case(quote["case_id"])
        quote["status"] = "approved"
        quote["approved_at"] = now_iso()
        quote["approved_by"] = payload.get("approved_by") or "system"
        quote["approval_note"] = payload.get("approval_note") or ""
        self._advance_case(quote_case, status="approved", active_stage="approved")
        return copy_record(quote)

    def export_quote(self, quote_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        quote = self._quote(quote_id)
        quote_case = self._case(quote["case_id"])
        export_id = self._id("export")
        export_record = {
            "export_id": export_id,
            "quote_id": quote_id,
            "case_id": quote["case_id"],
            "format": payload.get("format") or "json",
            "status": "ready",
            "download_url": f"/api/v2/exports/{export_id}/download",
            "created_at": now_iso(),
        }
        self.exports[export_id] = export_record
        self._advance_case(quote_case, status="exported", active_stage="exported")
        return copy_record(export_record)

    def _advance_case(
        self,
        quote_case: dict[str, Any],
        *,
        status: str,
        active_stage: str,
    ) -> None:
        quote_case["status"] = status
        quote_case["stages"] = build_stages(active_stage)
        quote_case["progress"] = stage_progress(active_stage)
        quote_case["updated_at"] = now_iso()

    def _case(self, case_id: str) -> dict[str, Any]:
        try:
            return self.quote_cases[case_id]
        except KeyError as exc:
            raise QuoteV2NotFoundError("quote_case", case_id) from exc

    def _run(self, run_id: str) -> dict[str, Any]:
        try:
            return self.analysis_runs[run_id]
        except KeyError as exc:
            raise QuoteV2NotFoundError("analysis_run", run_id) from exc

    def _route_plan(self, route_plan_id: str) -> dict[str, Any]:
        try:
            return self.route_plans[route_plan_id]
        except KeyError as exc:
            raise QuoteV2NotFoundError("route_plan", route_plan_id) from exc

    def _cost_scenario(self, scenario_id: str) -> dict[str, Any]:
        try:
            return self.cost_scenarios[scenario_id]
        except KeyError as exc:
            raise QuoteV2NotFoundError("cost_scenario", scenario_id) from exc

    def _quote(self, quote_id: str) -> dict[str, Any]:
        try:
            return self.quotes[quote_id]
        except KeyError as exc:
            raise QuoteV2NotFoundError("quote", quote_id) from exc

    @staticmethod
    def _id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"


def build_stages(active_stage: str) -> list[dict[str, Any]]:
    active_index = CASE_STAGES.index(active_stage)
    stages = []
    for index, name in enumerate(CASE_STAGES):
        if index < active_index:
            status = "completed"
        elif index == active_index:
            status = "completed"
        else:
            status = "pending"
        stages.append(stage(name, status, 100 if index <= active_index else 0))
    return stages


def stage(name: str, status: str, progress: int) -> dict[str, Any]:
    return {"name": name, "status": status, "progress": progress}


def stage_progress(active_stage: str) -> int:
    return {
        "case_created": 10,
        "files_uploaded": 25,
        "analysis_completed": 45,
        "route_planned": 65,
        "costed": 80,
        "approved": 90,
        "exported": 100,
    }[active_stage]


def build_default_facts(
    *,
    quote_case: dict[str, Any],
    files: list[dict[str, Any]],
    run_id: str,
) -> list[dict[str, Any]]:
    facts = [
        {
            "fact_id": f"fact_{uuid.uuid4().hex[:12]}",
            "run_id": run_id,
            "field": "part_name",
            "value": quote_case.get("part_name"),
            "confidence": 1.0,
            "source": {"source_type": "quote_case", "case_id": quote_case["case_id"]},
        },
        {
            "fact_id": f"fact_{uuid.uuid4().hex[:12]}",
            "run_id": run_id,
            "field": "quantity",
            "value": quote_case.get("quantity"),
            "confidence": 1.0,
            "source": {"source_type": "quote_case", "case_id": quote_case["case_id"]},
        },
    ]
    for file_record in files:
        facts.append(
            {
                "fact_id": f"fact_{uuid.uuid4().hex[:12]}",
                "run_id": run_id,
                "field": "file",
                "value": file_record["filename"],
                "confidence": 0.8,
                "source": {
                    "source_type": "file",
                    "file_id": file_record["file_id"],
                },
            }
        )
    for key, value in (quote_case.get("metadata") or {}).items():
        facts.append(
            {
                "fact_id": f"fact_{uuid.uuid4().hex[:12]}",
                "run_id": run_id,
                "field": key,
                "value": value,
                "confidence": 1.0,
                "source": {"source_type": "quote_case", "case_id": quote_case["case_id"]},
            }
        )
    return facts


def fact_snapshot_from_records(
    records: list[dict[str, Any]],
    *,
    snapshot_id: str,
) -> FactSnapshot:
    values = [
        FactValue(
            key=str(record.get("field") or record.get("key") or ""),
            value=record.get("value"),
            confidence=float(record.get("confidence", 1.0)),
        )
        for record in records
        if record.get("field") or record.get("key")
    ]
    return FactSnapshot.from_values(values, snapshot_id=snapshot_id)


def route_data_from_explicit_operations(operations: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = [normalize_operation(operation, index) for index, operation in enumerate(operations)]
    return {
        "operations": normalized,
        "business_category": None,
        "route_profile": None,
        "planner_type": "explicit_payload",
        "requires_review": any(bool(operation.get("requires_review")) for operation in normalized),
        "review_reason": first_review_reason(normalized),
        "assumptions": [],
        "metadata": {},
    }


def route_data_from_snapshot(snapshot: FactSnapshot) -> dict[str, Any]:
    audit = audit_fields_from_snapshot(snapshot)
    try:
        builder = resolve_route_builder()
        result = None if builder is None else builder(snapshot)
    except Exception as exc:  # pragma: no cover - defensive service boundary.
        route_data = manual_review_route_data(
            review_reason=getattr(exc, "reason", None) or "ROUTE_PLANNER_BLOCKED",
            metadata={"planner_error": exc.__class__.__name__},
        )
        route_data.update({key: value for key, value in audit.items() if value is not None})
        return route_data

    route_data = route_data_from_planning_result(result)
    if route_data is None:
        route_data = manual_review_route_data(review_reason=UNMAPPED_CATEGORY_REVIEW)
    for key, value in audit.items():
        if value is not None and route_data.get(key) is None:
            route_data[key] = value
    return route_data


def resolve_route_builder() -> Any:
    builder = globals().get("build_route_for_snapshot")
    if builder is not None:
        return builder
    try:
        from backend.app.domain_v2.planning import build_route_for_snapshot as imported_builder
    except ImportError:
        return None
    globals()["build_route_for_snapshot"] = imported_builder
    return imported_builder


def route_data_from_planning_result(result: Any) -> dict[str, Any] | None:
    if result is None:
        return None

    data = object_to_mapping(result)
    category_decision = object_to_mapping(data.get("category_decision"))
    route_profile = object_to_mapping(data.get("route_profile"))
    business_category = business_category_from_decision(
        category_decision,
        fallback=data.get("business_category"),
    )
    route_profile_data = route_profile_from_result(route_profile, data.get("route_profile"))
    planner_type = (
        route_profile.get("planner_type")
        or data.get("planner_type")
        or ("manual_review_fallback" if data.get("status") == "review_required" else "category_planner")
    )
    operations = data.get("operations") or data.get("selected_operations")
    if operations is None and hasattr(result, "selected_operations"):
        operations = result.selected_operations()
    if operations is None and data.get("route_graph") is not None:
        graph = data["route_graph"]
        if hasattr(graph, "selected_operations"):
            operations = graph.selected_operations()
    if not operations:
        return manual_review_route_data(
            review_reason=(
                data.get("review_reason")
                or data.get("blocking_reason")
                or data.get("reason")
                or UNMAPPED_CATEGORY_REVIEW
            ),
            business_category=business_category,
            route_profile=route_profile_data,
            planner_type="manual_review_fallback",
            assumptions=data.get("assumptions") or [],
            metadata=data.get("metadata") or {},
        )

    normalized = [normalize_operation(operation, index) for index, operation in enumerate(operations)]
    requires_review = bool(
        data.get("requires_review")
        or data.get("review_required")
        or any(bool(operation.get("requires_review")) for operation in normalized)
    )
    review_reason = (
        data.get("review_reason")
        or data.get("blocking_reason")
        or data.get("reason")
        or first_review_reason(normalized)
    )
    return {
        "operations": normalized,
        "business_category": business_category,
        "route_profile": route_profile_data,
        "planner_type": planner_type,
        "requires_review": requires_review,
        "review_reason": review_reason,
        "assumptions": data.get("assumptions") or [],
        "metadata": data.get("metadata") or {},
    }


def business_category_from_decision(
    decision: dict[str, Any],
    *,
    fallback: Any,
) -> Any:
    if decision:
        code = (
            decision.get("business_category_code")
            or decision.get("category_code")
            or decision.get("code")
        )
        return {
            "code": code,
            "name": decision.get("category_name") or decision.get("name"),
            "source": decision.get("source"),
            "confidence": decision.get("confidence"),
            "master_data_version": decision.get("master_data_version"),
        }
    return fallback


def route_profile_from_result(profile: dict[str, Any], fallback: Any) -> Any:
    if profile:
        return {
            "profile": profile.get("profile"),
            "business_category_code": (
                profile.get("business_category_code")
                or profile.get("category_code")
            ),
            "planner_type": profile.get("planner_type"),
            "planner_key": profile.get("planner_key"),
            "base_planners": profile.get("base_planners") or [],
            "requires_child_routes": profile.get("requires_child_routes", False),
            "rule_version": profile.get("rule_version"),
        }
    return fallback


def manual_review_route_data(
    *,
    review_reason: str,
    business_category: str | None = None,
    route_profile: str | None = None,
    planner_type: str = "manual_review_fallback",
    assumptions: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "operations": [
            {
                "sequence": 10,
                "operation_code": "manual_review",
                "operation_name": "Manual manufacturing review",
                "work_center": "engineering",
                "requires_review": True,
                "reason": review_reason,
            }
        ],
        "business_category": business_category,
        "route_profile": route_profile,
        "planner_type": planner_type,
        "requires_review": True,
        "review_reason": review_reason,
        "assumptions": assumptions or [],
        "metadata": metadata or {},
    }


def normalize_operation(operation: Any, index: int) -> dict[str, Any]:
    data = object_to_mapping(operation)
    operation_code = data.get("operation_code") or data.get("code") or data.get("operation_id")
    normalized = dict(data)
    normalized["sequence"] = int(normalized.get("sequence") or (index + 1) * 10)
    normalized["operation_code"] = operation_code or "manual_review"
    normalized.setdefault("operation_name", humanize_operation_code(normalized["operation_code"]))
    if normalized.get("work_center") is None and normalized.get("process_family") is not None:
        normalized["work_center"] = normalized["process_family"]
    normalized.setdefault("requires_review", False)
    return normalized


def object_to_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, (str, int, float, bool, list, tuple, set)):
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return {
        key: getattr(value, key)
        for key in dir(value)
        if not key.startswith("_") and not callable(getattr(value, key))
    }


def audit_fields_from_snapshot(snapshot: FactSnapshot) -> dict[str, Any]:
    return {
        "business_category": snapshot.first_value(
            "business_category_code",
            "business_category",
            "category_code",
            "manufacturing_category",
        ),
        "route_profile": snapshot.first_value(
            "route_profile",
            "business_subcategory",
            "manufacturing_subcategory",
            "subcategory",
            "part_type",
        ),
    }


def first_review_reason(operations: list[dict[str, Any]]) -> str | None:
    for operation in operations:
        if operation.get("requires_review") and operation.get("reason"):
            return str(operation["reason"])
    return None


def humanize_operation_code(operation_code: str) -> str:
    return operation_code.replace("_", " ").title()


def default_cost_items(quantity: int) -> list[dict[str, Any]]:
    setup_amount = 80.0
    unit_amount = 25.0 * quantity
    return [
        {
            "item_code": "setup",
            "item_name": "Setup",
            "quantity": 1,
            "unit_price": setup_amount,
            "amount": setup_amount,
        },
        {
            "item_code": "cnc_milling",
            "item_name": "CNC milling",
            "quantity": quantity,
            "unit_price": 25.0,
            "amount": unit_amount,
        },
    ]


def now_iso() -> str:
    return datetime.now(CHINA_TZ).isoformat(timespec="seconds")


def copy_record(record: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(record)
