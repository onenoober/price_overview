from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


def build_quote_history_sample(
    pricing_result: dict[str, Any],
    *,
    final_quote_result: dict[str, Any] | None = None,
    deal_amount: float | int | Decimal | None = None,
    deal_status: str | None = None,
    sample_id: str | None = None,
) -> dict[str, Any]:
    initial_quote = pricing_result["quote_result"]
    final_quote = final_quote_result or initial_quote
    task_id = initial_quote["task_id"]
    quote_id = initial_quote["quote_id"]
    created_at = now_iso()
    return {
        "sample_id": sample_id or f"sample_{task_id}_{quote_id}_{created_at.replace(':', '').replace('+', 'Z')}",
        "task_id": task_id,
        "quote_id": quote_id,
        "part_feature_snapshot": deepcopy(pricing_result["part_feature"]),
        "process_route_snapshot": deepcopy(pricing_result["process_route"]),
        "quantity_result_snapshot": deepcopy(pricing_result["quantity_result"]),
        "initial_quote_snapshot": deepcopy(initial_quote),
        "manual_overrides": deepcopy(final_quote.get("manual_overrides", [])),
        "final_quote_snapshot": deepcopy(final_quote),
        "deal_amount": money_or_none(deal_amount),
        "deal_status": deal_status,
        "created_at": created_at,
    }


def summarize_history_sample(sample: dict[str, Any]) -> dict[str, Any]:
    initial_summary = sample["initial_quote_snapshot"]["summary"]
    final_summary = sample["final_quote_snapshot"]["summary"]
    initial_amount = Decimal(str(initial_summary["system_initial_quote"]))
    final_amount = final_summary.get("final_confirmed_amount")
    comparable_final_amount = Decimal(str(final_amount if final_amount is not None else final_summary["system_initial_quote"]))
    deal_amount = sample.get("deal_amount")
    return {
        "sample_id": sample["sample_id"],
        "task_id": sample["task_id"],
        "quote_id": sample["quote_id"],
        "initial_amount": float(initial_amount),
        "final_amount": float(comparable_final_amount),
        "manual_adjustment_amount": float(comparable_final_amount - initial_amount),
        "deal_amount": deal_amount,
        "deal_delta_amount": float(Decimal(str(deal_amount)) - comparable_final_amount) if deal_amount is not None else None,
        "manual_override_count": len(sample.get("manual_overrides", [])),
    }


def validate_quote_history_sample(sample: dict[str, Any]) -> None:
    required_fields = {
        "sample_id",
        "task_id",
        "quote_id",
        "part_feature_snapshot",
        "process_route_snapshot",
        "quantity_result_snapshot",
        "initial_quote_snapshot",
        "manual_overrides",
        "final_quote_snapshot",
        "deal_amount",
        "deal_status",
        "created_at",
    }
    missing = sorted(required_fields - set(sample))
    if missing:
        raise ValueError(f"Quote history sample is missing fields: {', '.join(missing)}")


def money_or_none(value: float | int | Decimal | None) -> float | None:
    if value is None:
        return None
    return float(Decimal(str(value)).quantize(Decimal("0.01")))


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
