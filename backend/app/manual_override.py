from __future__ import annotations

from typing import Any


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
    old_value: str | int | float | bool | None,
    new_value: str | int | float | bool | None,
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
    elif target_type not in {"operation", "quantity", "risk"}:
        raise ManualOverrideError(
            "INVALID_TARGET_TYPE",
            "人工修改目标类型不合法",
            [{"field": "target_type", "message": target_type}],
        )

    quote_result["manual_overrides"].append(override)
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
    elif field == "explanation":
        item["explanation"] = str(override["new_value"])


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

