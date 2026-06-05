from __future__ import annotations

import json
from typing import Any

from .pricing_core import OPERATION_NAMES


class ManualOverrideError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
        status_code: int = 400,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or []
        self.status_code = status_code
        super().__init__(message)


def build_manual_override(
    *,
    override_id: str,
    target_type: str,
    target_id: str,
    field: str,
    old_value: Any,
    new_value: Any,
    reason: str,
    operator_id: str,
    created_at: str,
) -> dict[str, Any]:
    return {
        "override_id": override_id,
        "target_type": target_type,
        "target_id": target_id,
        "field": field,
        "old_value": old_value,
        "new_value": new_value,
        "reason": reason,
        "operator_id": operator_id,
        "created_at": created_at,
    }


def apply_mock_manual_override(
    quote_result: dict[str, Any],
    override: dict[str, Any],
    *,
    process_route: dict[str, Any] | None = None,
    quantity_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if quote_result["status"] in {"confirmed", "voided"}:
        raise ManualOverrideError(
            "QUOTE_READONLY",
            "已确认或作废的报价不可修改",
            [{"field": "quote_id", "message": quote_result["quote_id"]}],
            status_code=409,
        )

    target_type = override["target_type"]
    if target_type == "quote_item":
        apply_quote_item_override(quote_result, override)
    elif target_type == "quote_summary":
        apply_quote_summary_override(quote_result, override)
    elif target_type == "quantity":
        apply_quantity_override(quote_result, quantity_result, override)
    elif target_type == "risk":
        validate_risk_override(quote_result, process_route, quantity_result, override)
    elif target_type == "operation":
        apply_operation_override(process_route, override)
    else:
        raise ManualOverrideError(
            "INVALID_TARGET_TYPE",
            "人工修改目标类型不合法",
            [{"field": "target_type", "message": target_type}],
        )

    quote_result["manual_overrides"].append(manual_override_record(override))
    refresh_mock_summary_adjustment(quote_result)
    return quote_result


def apply_quote_item_override(
    quote_result: dict[str, Any],
    override: dict[str, Any],
) -> None:
    item = find_quote_item(quote_result, override["target_id"])
    field = override["field"]

    if field in {"amount", "final_amount"}:
        item["final_amount"] = coerce_number(override["new_value"], field)
    elif field == "unit_price":
        item["unit_price"] = coerce_number(override["new_value"], field)
        item["final_amount"] = calculate_final_amount(
            item.get("quantity"),
            item.get("unit_price"),
        )
    elif field == "explanation":
        item["explanation"] = str(override["new_value"])
    else:
        raise ManualOverrideError(
            "INVALID_OVERRIDE_FIELD",
            "报价明细修改字段不合法",
            [{"field": "field", "message": field}],
        )


def apply_quote_summary_override(
    quote_result: dict[str, Any],
    override: dict[str, Any],
) -> None:
    field = override["field"]
    if field == "final_confirmed_amount":
        quote_result["summary"]["final_confirmed_amount"] = coerce_number(
            override["new_value"],
            field,
        )
    else:
        raise ManualOverrideError(
            "INVALID_OVERRIDE_FIELD",
            "报价汇总修改字段不合法",
            [{"field": "field", "message": field}],
        )


def apply_quantity_override(
    quote_result: dict[str, Any],
    quantity_result: dict[str, Any] | None,
    override: dict[str, Any],
) -> None:
    if quantity_result is None:
        raise ManualOverrideError(
            "QUANTITY_RESULT_MISSING",
            "当前报价没有可修改的工程量结果",
            [{"field": "target_type", "message": "quantity"}],
            status_code=409,
        )

    field = override["field"]
    if field != "value":
        raise ManualOverrideError(
            "INVALID_OVERRIDE_FIELD",
            "工程量目前仅支持修改 value",
            [{"field": "field", "message": field}],
        )

    quantity_item = find_quantity_item(quantity_result, override["target_id"])
    new_value = coerce_number(override["new_value"], field)
    quantity_item["value"] = new_value
    quantity_item["requires_review"] = False
    quantity_item["review_reason"] = None

    operation_code = quantity_item.get("operation_code")
    if not operation_code:
        return

    for quote_item in quote_result["items"]:
        if quote_item.get("operation_code") != operation_code:
            continue
        quote_item["quantity"] = new_value
        if quote_item.get("unit_price") is not None:
            quote_item["final_amount"] = calculate_final_amount(
                new_value,
                quote_item.get("unit_price"),
            )


def apply_operation_override(
    process_route: dict[str, Any] | None,
    override: dict[str, Any],
) -> None:
    if process_route is None:
        raise ManualOverrideError(
            "PROCESS_ROUTE_MISSING",
            "当前报价没有可修改的工艺路线",
            [{"field": "target_type", "message": "operation"}],
            status_code=409,
        )

    operations = process_route.get("operations")
    if not isinstance(operations, list):
        raise ManualOverrideError(
            "PROCESS_ROUTE_INVALID",
            "工艺路线数据不完整",
            [{"field": "operations", "message": operations}],
            status_code=409,
        )

    resequence_operations(process_route, sort=True)
    field = override["field"]
    if field == "add":
        payload = coerce_mapping(override.get("new_value"), field)
        operation_code = coerce_operation_code(payload.get("operation_code"))
        ensure_operation_code_unique(
            operations,
            operation_code,
            exclude_operation_id=None,
        )
        sequence = coerce_sequence(
            payload.get("sequence"),
            field,
            default=len(operations) + 1,
            upper=len(operations) + 1,
        )
        operation = build_manual_operation(
            operations,
            operation_code=operation_code,
            explanation=str(payload.get("explanation") or override["reason"]).strip(),
            reason=override["reason"],
        )
        operations.insert(sequence - 1, operation)
    elif field == "delete":
        index, _operation = find_operation_with_index(operations, override["target_id"])
        del operations[index]
    elif field == "sequence":
        _index, operation = find_operation_with_index(operations, override["target_id"])
        sequence = coerce_sequence(
            override.get("new_value"),
            field,
            default=operation.get("sequence"),
            upper=len(operations),
        )
        move_operation(operations, operation, sequence)
        mark_operation_reviewed(operation, override, "MANUAL_OPERATION_REORDERED")
    elif field in {"operation", "operation_code"}:
        _index, operation = find_operation_with_index(operations, override["target_id"])
        payload = operation_update_payload(override.get("new_value"))
        operation_code = coerce_operation_code(payload.get("operation_code"))
        ensure_operation_code_unique(
            operations,
            operation_code,
            exclude_operation_id=operation.get("operation_id"),
        )
        operation["operation_code"] = operation_code
        operation["operation_name"] = operation_name_for_code(operation_code)
        explanation = str(payload.get("explanation") or "").strip()
        if explanation:
            operation["explanation"] = explanation
        mark_operation_reviewed(operation, override, "MANUAL_OPERATION_UPDATED")
    elif field == "explanation":
        _index, operation = find_operation_with_index(operations, override["target_id"])
        explanation = str(override.get("new_value") or "").strip()
        if not explanation:
            raise ManualOverrideError(
                "INVALID_OVERRIDE_VALUE",
                "工序说明不能为空",
                [{"field": field, "message": override.get("new_value")}],
            )
        operation["explanation"] = explanation
        mark_operation_reviewed(operation, override, "MANUAL_OPERATION_EXPLANATION")
    else:
        raise ManualOverrideError(
            "INVALID_OVERRIDE_FIELD",
            "工艺路线修改字段不合法",
            [{"field": "field", "message": field}],
        )

    resequence_operations(process_route)
    refresh_process_route_review_state(process_route)


def validate_risk_override(
    quote_result: dict[str, Any],
    process_route: dict[str, Any] | None,
    quantity_result: dict[str, Any] | None,
    override: dict[str, Any],
) -> None:
    field = override["field"]
    if field != "confirmed":
        raise ManualOverrideError(
            "INVALID_OVERRIDE_FIELD",
            "风险目前仅支持确认 confirmed",
            [{"field": "field", "message": field}],
        )
    if not coerce_bool(override["new_value"]):
        raise ManualOverrideError(
            "INVALID_OVERRIDE_VALUE",
            "风险确认值必须为 true",
            [{"field": field, "message": override["new_value"]}],
        )

    target_id = str(override["target_id"])
    if not risk_exists(quote_result, process_route, quantity_result, target_id):
        raise ManualOverrideError(
            "TARGET_NOT_FOUND",
            "风险不存在",
            [{"field": "target_id", "message": target_id}],
            status_code=404,
        )


def find_quote_item(
    quote_result: dict[str, Any],
    item_id: str,
) -> dict[str, Any]:
    for item in quote_result["items"]:
        if item["item_id"] == item_id:
            return item

    raise ManualOverrideError(
        "TARGET_NOT_FOUND",
        "人工修改目标不存在",
        [{"field": "target_id", "message": item_id}],
        status_code=404,
    )


def find_quantity_item(
    quantity_result: dict[str, Any],
    quantity_id: str,
) -> dict[str, Any]:
    for item in quantity_result.get("items") or []:
        if item.get("quantity_id") == quantity_id:
            return item

    raise ManualOverrideError(
        "TARGET_NOT_FOUND",
        "工程量修改目标不存在",
        [{"field": "target_id", "message": quantity_id}],
        status_code=404,
    )


def find_operation_with_index(
    operations: list[dict[str, Any]],
    operation_id: str,
) -> tuple[int, dict[str, Any]]:
    for index, item in enumerate(operations):
        if item.get("operation_id") == operation_id:
            return index, item

    raise ManualOverrideError(
        "TARGET_NOT_FOUND",
        "工艺路线修改目标不存在",
        [{"field": "target_id", "message": operation_id}],
        status_code=404,
    )


def build_manual_operation(
    operations: list[dict[str, Any]],
    *,
    operation_code: str,
    explanation: str,
    reason: str,
) -> dict[str, Any]:
    rule_code = "MANUAL_OPERATION_ADDED"
    return {
        "operation_id": next_operation_id(operations, operation_code),
        "operation_code": operation_code,
        "operation_name": operation_name_for_code(operation_code),
        "sequence": 1,
        "trigger_reasons": [
            manual_trigger_reason(
                rule_code,
                reason or f"Manual operation added: {operation_code}",
            )
        ],
        "confidence": 1.0,
        "requires_review": False,
        "review_reason": None,
        "explanation": explanation or reason or operation_name_for_code(operation_code),
    }


def mark_operation_reviewed(
    operation: dict[str, Any],
    override: dict[str, Any],
    rule_code: str,
) -> None:
    reasons = operation.setdefault("trigger_reasons", [])
    if not isinstance(reasons, list):
        reasons = []
        operation["trigger_reasons"] = reasons
    reasons.append(manual_trigger_reason(rule_code, override["reason"]))
    operation["confidence"] = 1.0
    operation["requires_review"] = False
    operation["review_reason"] = None


def move_operation(
    operations: list[dict[str, Any]],
    operation: dict[str, Any],
    sequence: int,
) -> None:
    operations.remove(operation)
    operations.insert(sequence - 1, operation)


def resequence_operations(process_route: dict[str, Any], *, sort: bool = False) -> None:
    operations = process_route.get("operations") or []
    if sort:
        operations.sort(key=lambda item: int(item.get("sequence") or 0))
    for index, operation in enumerate(operations, start=1):
        operation["sequence"] = index


def refresh_process_route_review_state(process_route: dict[str, Any]) -> None:
    operations = process_route.get("operations") or []
    risks = process_route.get("risks") or []
    operation_review_required = any(
        bool(operation.get("requires_review")) for operation in operations
    )
    if not operation_review_required:
        risks = [
            risk
            for risk in risks
            if not (
                isinstance(risk, dict)
                and risk.get("code") == "PROCESS_ROUTE_REQUIRES_REVIEW"
            )
        ]
        process_route["risks"] = risks
    process_route["requires_review"] = operation_review_required or any(
        bool(risk.get("requires_review")) for risk in risks if isinstance(risk, dict)
    )


def coerce_mapping(value: Any, field: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ManualOverrideError(
                "INVALID_OVERRIDE_VALUE",
                "工艺路线修改值必须是对象",
                [{"field": field, "message": value}],
            ) from exc
        if isinstance(payload, dict):
            return payload

    raise ManualOverrideError(
        "INVALID_OVERRIDE_VALUE",
        "工艺路线修改值必须是对象",
        [{"field": field, "message": value}],
    )


def operation_update_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{"):
            return coerce_mapping(text, "operation")
        return {"operation_code": text}
    return coerce_mapping(value, "operation")


def coerce_operation_code(value: Any) -> str:
    operation_code = str(value or "").strip().upper()
    if operation_code not in OPERATION_NAMES:
        raise ManualOverrideError(
            "INVALID_OVERRIDE_VALUE",
            "工序编码不合法",
            [{"field": "operation_code", "message": value}],
        )
    return operation_code


def coerce_sequence(
    value: Any,
    field: str,
    *,
    default: Any,
    upper: int,
) -> int:
    if value in (None, ""):
        sequence = default
    else:
        try:
            sequence = int(value)
        except (TypeError, ValueError) as exc:
            raise ManualOverrideError(
                "INVALID_OVERRIDE_VALUE",
                "工序顺序必须是正整数",
                [{"field": field, "message": value}],
            ) from exc
    if sequence < 1:
        raise ManualOverrideError(
            "INVALID_OVERRIDE_VALUE",
            "工序顺序不能小于 1",
            [{"field": field, "message": value}],
        )
    return min(sequence, upper)


def ensure_operation_code_unique(
    operations: list[dict[str, Any]],
    operation_code: str,
    *,
    exclude_operation_id: Any,
) -> None:
    for operation in operations:
        if operation.get("operation_id") == exclude_operation_id:
            continue
        if operation.get("operation_code") != operation_code:
            continue
        raise ManualOverrideError(
            "DUPLICATED_OPERATION",
            "工艺路线中已存在该工序",
            [{"field": "operation_code", "message": operation_code}],
            status_code=409,
        )


def next_operation_id(
    operations: list[dict[str, Any]],
    operation_code: str,
) -> str:
    existing_ids = {str(item.get("operation_id")) for item in operations}
    index = len(operations) + 1
    while True:
        operation_id = f"op_manual_{index:03d}_{operation_code.lower()}"
        if operation_id not in existing_ids:
            return operation_id
        index += 1


def operation_name_for_code(operation_code: str) -> str:
    return OPERATION_NAMES[operation_code]


def manual_trigger_reason(rule_code: str, message: str) -> dict[str, Any]:
    return {
        "rule_code": rule_code,
        "message": message,
        "source": manual_source(rule_code, message),
    }


def manual_source(rule_code: str, raw_text: str) -> dict[str, Any]:
    return {
        "source_type": "manual",
        "raw_text": raw_text,
        "rule_code": rule_code,
    }


def risk_exists(
    quote_result: dict[str, Any],
    process_route: dict[str, Any] | None,
    quantity_result: dict[str, Any] | None,
    risk_code: str,
) -> bool:
    risk_groups = [
        quote_result.get("risks") or [],
        (process_route or {}).get("risks") or [],
        (quantity_result or {}).get("risks") or [],
    ]
    return any(
        str(risk.get("code")) == risk_code
        for risks in risk_groups
        for risk in risks
        if isinstance(risk, dict)
    )


def coerce_number(value: str | int | float | bool | None, field: str) -> float:
    if isinstance(value, bool) or value is None:
        raise ManualOverrideError(
            "INVALID_OVERRIDE_VALUE",
            "人工修改数值不合法",
            [{"field": field, "message": value}],
        )

    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ManualOverrideError(
            "INVALID_OVERRIDE_VALUE",
            "人工修改数值不合法",
            [{"field": field, "message": value}],
        ) from exc

    if number < 0:
        raise ManualOverrideError(
            "INVALID_OVERRIDE_VALUE",
            "人工修改数值不能小于 0",
            [{"field": field, "message": value}],
        )

    return number


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "是"}
    return bool(value)


def manual_override_record(override: dict[str, Any]) -> dict[str, Any]:
    record = dict(override)
    record["old_value"] = scalar_override_value(record.get("old_value"))
    record["new_value"] = scalar_override_value(record.get("new_value"))
    return record


def scalar_override_value(value: Any) -> str | int | float | bool | None:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def calculate_final_amount(quantity: Any, unit_price: Any) -> float | None:
    try:
        return round(float(quantity) * float(unit_price), 2)
    except (TypeError, ValueError):
        return None


def refresh_mock_summary_adjustment(quote_result: dict[str, Any]) -> None:
    final_items_total = sum(
        item["final_amount"] or 0
        for item in quote_result["items"]
    )
    system_calculated_amount = quote_result["summary"]["system_calculated_amount"]
    quote_result["summary"]["manual_adjustment_amount"] = round(
        final_items_total - system_calculated_amount,
        2,
    )
