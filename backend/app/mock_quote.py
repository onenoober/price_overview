from __future__ import annotations

from typing import Any


MOCK_PRICE_SOURCE = {
    "source_type": "manual",
    "source_id": "mock_quote_ui_only",
    "rule_id": "MOCK_QUOTE_UI_ONLY",
    "version": "mock-v1",
}


def build_mock_quote_result(
    *,
    task_id: str,
    quote_id: str,
    part_feature: dict[str, Any],
    risks: list[dict[str, Any]],
    priced_at: str,
    price_version: str = "mock-v1",
) -> dict[str, Any]:
    status = "pending_review" if has_review_risk(risks) else "priced"

    items = [
        quote_item(
            item_id="mock_item_material",
            item_type="material",
            operation_code=None,
            quantity=1,
            unit="lot",
            unit_price=120.0,
            amount=120.0,
            explanation="Mock material fee for PyQt review page display only.",
        ),
        quote_item(
            item_id="mock_item_process",
            item_type="process",
            operation_code="MOCK_PROCESS",
            quantity=1,
            unit="lot",
            unit_price=450.0,
            amount=450.0,
            explanation="Mock process fee for PyQt review page display only.",
        ),
        quote_item(
            item_id="mock_item_surface",
            item_type="surface_treatment",
            operation_code="MOCK_SURFACE",
            quantity=1,
            unit="lot",
            unit_price=80.0,
            amount=80.0,
            explanation="Mock surface treatment fee for PyQt review page display only.",
        ),
        quote_item(
            item_id="mock_item_management_fee",
            item_type="management_fee",
            operation_code=None,
            quantity=1,
            unit="lot",
            unit_price=65.0,
            amount=65.0,
            explanation="Mock management fee for PyQt review page display only.",
        ),
        quote_item(
            item_id="mock_item_tax",
            item_type="tax",
            operation_code=None,
            quantity=1,
            unit="lot",
            unit_price=68.0,
            amount=68.0,
            explanation="Mock tax amount for PyQt review page display only.",
        ),
        quote_item(
            item_id="mock_item_risk_surcharge",
            item_type="risk_surcharge",
            operation_code=None,
            quantity=1,
            unit="lot",
            unit_price=30.0,
            amount=30.0,
            explanation="Mock risk surcharge for PyQt review page display only.",
            requires_review=True,
        ),
    ]

    summary = {
        "material_amount": 120.0,
        "process_amount": 450.0,
        "surface_treatment_amount": 80.0,
        "management_fee": 65.0,
        "tax_amount": 68.0,
        "risk_surcharge_amount": 30.0,
        "system_calculated_amount": 813.0,
        "system_initial_quote": 820.0,
        "manual_adjustment_amount": 0.0,
        "final_confirmed_amount": None,
    }

    return {
        "schema_version": "1.0",
        "task_id": task_id,
        "quote_id": quote_id,
        "status": status,
        "currency": "CNY",
        "price_version": price_version,
        "priced_at": priced_at,
        "confirmed_at": None,
        "confirmed_by": None,
        "items": items,
        "summary": summary,
        "risks": risks,
        "manual_overrides": [],
    }


def quote_item(
    *,
    item_id: str,
    item_type: str,
    operation_code: str | None,
    quantity: float,
    unit: str,
    unit_price: float,
    amount: float,
    explanation: str,
    requires_review: bool = False,
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "item_type": item_type,
        "operation_code": operation_code,
        "quantity": quantity,
        "unit": unit,
        "unit_price": unit_price,
        "amount": amount,
        "price_source": MOCK_PRICE_SOURCE,
        "formula": "MOCK_FIXED_AMOUNT_UI_ONLY",
        "explanation": explanation,
        "system_amount": amount,
        "final_amount": amount,
        "requires_review": requires_review,
    }


def has_review_risk(risks: list[dict[str, Any]]) -> bool:
    return any(risk.get("requires_review") for risk in risks)

