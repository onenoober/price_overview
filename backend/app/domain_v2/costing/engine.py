from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from backend.app.domain_v2.planning.models import RouteCandidate
from backend.app.domain_v2.quantities.models import QuantityLine

from .models import CostLine


class RateSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    rates: dict[str, Decimal]

    @field_validator("rates")
    @classmethod
    def rates_must_be_decimal(cls, value: dict[str, Decimal]) -> dict[str, Decimal]:
        for rate in value.values():
            if not isinstance(rate, Decimal):
                raise TypeError("RateSnapshot rates must be Decimal.")
        return value

    def rate_for(self, operation_code: str) -> Decimal:
        return self.rates[operation_code]


class CostEngine:
    def calculate(
        self,
        selected_route: RouteCandidate,
        quantities: tuple[QuantityLine, ...],
        rate_snapshot: RateSnapshot,
    ) -> tuple[CostLine, ...]:
        selected_codes = set(selected_route.operation_codes)
        quantity_by_operation = {
            quantity.operation_code: quantity
            for quantity in quantities
            if quantity.operation_code in selected_codes
        }

        lines: list[CostLine] = []
        for operation_code in selected_route.operation_codes:
            quantity = quantity_by_operation.get(operation_code)
            if quantity is None:
                continue
            unit_rate = rate_snapshot.rate_for(operation_code)
            amount = quantity.value * unit_rate
            lines.append(
                CostLine(
                    operation_code=operation_code,
                    cost_type="machine",
                    quantity=quantity.value,
                    unit=quantity.unit,
                    unit_rate=unit_rate,
                    amount=amount,
                    formula_trace={
                        **quantity.formula_trace,
                        "cost_formula": f"{quantity.value} * {unit_rate} = {amount}",
                    },
                    rate_snapshot_id=rate_snapshot.snapshot_id,
                )
            )
        return tuple(lines)
