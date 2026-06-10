from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .part_feature_builder import risk_item, source_ref
from .process_dictionary import process_name_for_code


REPO_ROOT = Path(__file__).resolve().parents[2]
EXPORT_ROOT = REPO_ROOT / "exports"


def build_export_payload(
    *,
    export_id: str,
    quote_id: str,
    exported_at: str,
    task: dict[str, Any],
    files: list[dict[str, Any]],
    parse_result: dict[str, Any] | None,
    process_route: dict[str, Any] | None,
    quantity_result: dict[str, Any] | None,
    quote_result: dict[str, Any],
    include_initial_quote: bool,
    include_manual_overrides: bool,
    include_risks: bool,
) -> dict[str, Any]:
    quote_for_export = copy.deepcopy(quote_result)

    if not include_initial_quote:
        quote_for_export["summary"].pop("system_initial_quote", None)

    if not include_manual_overrides:
        quote_for_export["manual_overrides"] = []

    if not include_risks:
        quote_for_export["risks"] = []

    part_feature = parse_result["part_feature"] if parse_result else None
    process_for_export = copy.deepcopy(process_route) if process_route else None
    quantity_for_export = copy.deepcopy(quantity_result) if quantity_result else None
    if process_for_export is None:
        process_for_export = build_process_route_placeholder(quote_for_export)
    if quantity_for_export is None:
        quantity_for_export = build_quantity_result_placeholder(quote_for_export)

    if not include_risks:
        process_for_export["risks"] = []
        quantity_for_export["risks"] = []

    return {
        "schema_version": "1.0",
        "export_id": export_id,
        "quote_id": quote_id,
        "exported_at": exported_at,
        "format": "json",
        "task": task,
        "files": files,
        "part_feature": part_feature,
        "process_route": process_for_export,
        "quantity_result": quantity_for_export,
        "quote_result": quote_for_export,
        "notes": [
            "process_route, quantity_result, and quote_result are exported as one pricing bundle.",
            "If old quote records lack process_route or quantity_result, review placeholders are emitted.",
            "This first-phase export mirrors the review page data and is not a formal quote template.",
        ],
    }


def build_process_route_placeholder(quote_result: dict[str, Any]) -> dict[str, Any]:
    route_id = f"route_{quote_result.get('quote_id') or 'legacy'}"
    source = system_source("LEGACY_PROCESS_ROUTE_PLACEHOLDER")
    return {
        "schema_version": "1.0",
        "task_id": quote_result["task_id"],
        "route_id": route_id,
        "operations": [
            {
                "operation_id": "op_001_manual_review",
                "operation_code": "manual_review",
                "operation_name": process_name_for_code("manual_review"),
                "sequence": 1,
                "trigger_reasons": [
                    {
                        "rule_code": "LEGACY_PROCESS_ROUTE_PLACEHOLDER",
                        "message": "This legacy quote has no saved process_route.",
                        "source": source,
                    }
                ],
                "confidence": 0.0,
                "requires_review": True,
                "review_reason": "Legacy quote record lacks process_route.",
                "explanation": "Manual review required because process_route was not saved.",
            }
        ],
        "requires_review": True,
        "risks": [
            risk_item(
                "LEGACY_PROCESS_ROUTE_MISSING",
                "warning",
                "Legacy quote record has no saved process_route.",
                "export_service",
                True,
                [source],
            )
        ],
    }


def build_quantity_result_placeholder(quote_result: dict[str, Any]) -> dict[str, Any]:
    route_id = f"route_{quote_result.get('quote_id') or 'legacy'}"
    source = system_source("LEGACY_QUANTITY_RESULT_PLACEHOLDER")
    return {
        "schema_version": "1.0",
        "task_id": quote_result["task_id"],
        "route_id": route_id,
        "items": [
            {
                "quantity_id": "qty_manual_review",
                "operation_code": "manual_review",
                "quantity_type": "manual_quantity",
                "value": None,
                "unit": "lot",
                "formula": "Legacy quote record lacks quantity_result.",
                "basis": [
                    {
                        "name": "legacy_quote_id",
                        "value": quote_result.get("quote_id"),
                        "unit": None,
                        "source": source,
                    }
                ],
                "requires_review": True,
                "review_reason": "Legacy quote record lacks quantity_result.",
            }
        ],
        "risks": [
            risk_item(
                "LEGACY_QUANTITY_RESULT_MISSING",
                "warning",
                "Legacy quote record has no saved quantity_result.",
                "export_service",
                True,
                [source],
            )
        ],
    }


def system_source(rule_code: str) -> dict[str, Any]:
    return source_ref("system", rule_code=rule_code)


def write_json_export(
    *,
    export_id: str,
    payload: dict[str, Any],
    export_root: Path = EXPORT_ROOT,
) -> str:
    export_root.mkdir(parents=True, exist_ok=True)
    target_path = export_root / f"{export_id}.json"

    with target_path.open("x", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False, indent=2)

    return format_export_path(target_path)


def format_export_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()
