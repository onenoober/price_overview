from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator


QuantityScope = Literal["batch", "piece", "feature", "length", "area", "volume", "time", "tooling"]


class QuantityLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    operation_code: str
    scope: QuantityScope
    quantity: Decimal
    unit: str
    formula_trace: dict[str, Any]
    requires_review: bool = False

    @field_validator("quantity", mode="before")
    @classmethod
    def quantity_must_be_decimal(cls, value: Decimal) -> Decimal:
        if not isinstance(value, Decimal):
            raise TypeError("QuantityLine.quantity must be Decimal.")
        return value

    @property
    def value(self) -> Decimal:
        return self.quantity
