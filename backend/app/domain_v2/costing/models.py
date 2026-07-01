from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator


CostType = Literal[
    "material",
    "setup",
    "machine",
    "labor",
    "consumable",
    "tooling",
    "outsource",
    "inspection",
    "packaging",
    "overhead",
]


class CostLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    operation_code: str
    cost_type: CostType
    quantity: Decimal
    unit: str
    unit_rate: Decimal
    amount: Decimal
    formula_trace: dict[str, Any]
    rate_snapshot_id: str

    @field_validator("quantity", "unit_rate", "amount", mode="before")
    @classmethod
    def money_fields_must_be_decimal(cls, value: Decimal) -> Decimal:
        if not isinstance(value, Decimal):
            raise TypeError("CostLine numeric fields must be Decimal.")
        return value
