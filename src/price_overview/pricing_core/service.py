from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any

from .contract_validation import validate_a_outputs, validate_contract
from .core import apply_manual_override, confirm_quote, confirm_risk, run_mock_pricing
from .dictionaries import get_dictionary_item, list_dictionary
from .history import build_quote_history_sample, summarize_history_sample
from .persistence import PricingStore
from .price_rules import PriceRule, list_price_rules, load_price_rules_from_json


class PricingCoreService:
    """Thin facade for A-side pricing operations used by integration callers."""

    def __init__(
        self,
        *,
        price_rules: list[PriceRule] | None = None,
        validate_contracts: bool = True,
        copy_inputs: bool = True,
    ) -> None:
        self._price_rules = price_rules
        self.validate_contracts = validate_contracts
        self.copy_inputs = copy_inputs

    def price(self, part_feature: dict[str, Any]) -> dict[str, Any]:
        working_part_feature = self._copy(part_feature)
        if self.validate_contracts:
            validate_contract(working_part_feature, "part_feature.schema.json")

        result = run_mock_pricing(working_part_feature, self._price_rules)
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

    def dictionary(self, kind: str) -> list[dict[str, Any]]:
        return list_dictionary(kind)

    def dictionary_item(self, kind: str, code: str) -> dict[str, Any] | None:
        return get_dictionary_item(kind, code)

    def list_price_rules(self, *, active_only: bool = False, price_type: str | None = None, target_code: str | None = None) -> list[dict[str, Any]]:
        return [rule.to_dict() for rule in list_price_rules(self._price_rules, active_only=active_only, price_type=price_type, target_code=target_code)]

    def price_rule_objects(self, *, active_only: bool = False, price_type: str | None = None, target_code: str | None = None) -> list[PriceRule]:
        return list_price_rules(self._price_rules, active_only=active_only, price_type=price_type, target_code=target_code)

    def load_price_rules(self, path: str | Path, *, default_approval_status: str = "draft") -> list[PriceRule]:
        self._price_rules = load_price_rules_from_json(path, default_approval_status=default_approval_status)
        return self._price_rules

    def history_sample(
        self,
        pricing_result: dict[str, Any],
        *,
        final_quote_result: dict[str, Any] | None = None,
        deal_amount: float | int | Decimal | None = None,
        deal_status: str | None = None,
        sample_id: str | None = None,
    ) -> dict[str, Any]:
        return build_quote_history_sample(
            pricing_result,
            final_quote_result=final_quote_result,
            deal_amount=deal_amount,
            deal_status=deal_status,
            sample_id=sample_id,
        )

    def history_summary(self, history_sample: dict[str, Any]) -> dict[str, Any]:
        return summarize_history_sample(history_sample)

    def save_pricing_result(self, pricing_result: dict[str, Any], db_path: str | Path) -> None:
        store = PricingStore(db_path)
        store.initialize()
        store.save_pricing_result(pricing_result)

    def save_history_sample(self, history_sample: dict[str, Any], db_path: str | Path) -> None:
        store = PricingStore(db_path)
        store.initialize()
        store.save_history_sample(history_sample)

    def save_price_rules(self, rules: list[PriceRule] | None, db_path: str | Path) -> None:
        store = PricingStore(db_path)
        store.initialize()
        store.save_price_rules(self.price_rule_objects() if rules is None else rules)

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
