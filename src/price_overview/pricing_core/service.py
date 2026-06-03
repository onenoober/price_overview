from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any

from .contract_validation import validate_a_outputs, validate_contract
from .core import apply_manual_override, confirm_quote, confirm_risk, run_mock_pricing
from .price_rules import PriceRule


class PricingCoreService:
    """Thin facade for A-side pricing operations used by integration callers."""

    def __init__(
        self,
        *,
        price_rules: list[PriceRule] | None = None,
        validate_contracts: bool = True,
        copy_inputs: bool = True,
    ) -> None:
        self.price_rules = price_rules
        self.validate_contracts = validate_contracts
        self.copy_inputs = copy_inputs

    def price(self, part_feature: dict[str, Any]) -> dict[str, Any]:
        working_part_feature = self._copy(part_feature)
        if self.validate_contracts:
            validate_contract(working_part_feature, "part_feature.schema.json")

        result = run_mock_pricing(working_part_feature, self.price_rules)
        if self.validate_contracts:
            validate_a_outputs(result)
        return result

    def apply_override(
        self,
        quote_result: dict[str, Any],
        *,
        target_type: str,
        target_id: str,
        field: str,
        new_value: Any,
        reason: str,
        operator_id: str,
    ) -> dict[str, Any]:
        working_quote = self._validated_quote_copy(quote_result)
        updated = apply_manual_override(
            working_quote,
            target_type=target_type,
            target_id=target_id,
            field=field,
            new_value=new_value,
            reason=reason,
            operator_id=operator_id,
        )
        return self._validate_quote_result(updated)

    def confirm_risk(
        self,
        quote_result: dict[str, Any],
        *,
        risk_code: str,
        reason: str,
        operator_id: str,
    ) -> dict[str, Any]:
        working_quote = self._validated_quote_copy(quote_result)
        updated = confirm_risk(working_quote, risk_code=risk_code, reason=reason, operator_id=operator_id)
        return self._validate_quote_result(updated)

    def confirm_quote(
        self,
        quote_result: dict[str, Any],
        *,
        confirmed_by: str,
        confirmed_total_amount: float | int | Decimal | None = None,
        confirm_note: str = "",
    ) -> dict[str, Any]:
        working_quote = self._validated_quote_copy(quote_result)
        updated = confirm_quote(
            working_quote,
            confirmed_by=confirmed_by,
            confirmed_total_amount=confirmed_total_amount,
            confirm_note=confirm_note,
        )
        return self._validate_quote_result(updated)

    def _validated_quote_copy(self, quote_result: dict[str, Any]) -> dict[str, Any]:
        working_quote = self._copy(quote_result)
        if self.validate_contracts:
            validate_contract(working_quote, "quote_result.schema.json")
        return working_quote

    def _validate_quote_result(self, quote_result: dict[str, Any]) -> dict[str, Any]:
        if self.validate_contracts:
            validate_contract(quote_result, "quote_result.schema.json")
        return quote_result

    def _copy(self, payload: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(payload) if self.copy_inputs else payload
