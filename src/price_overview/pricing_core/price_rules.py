from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from typing import Any


PRICE_VERSION = "mock-v0.2"
PRICE_TYPES = {"material", "process", "surface_treatment", "risk_surcharge"}
SOURCE_TYPES = {"archive_import", "manual", "supplier_quote", "history_reference"}
APPROVAL_STATUSES = {"draft", "approved", "disabled"}


@dataclass(frozen=True)
class PriceRule:
    rule_id: str
    price_type: str
    target_code: str
    unit: str | None
    unit_price: Decimal
    source_type: str
    source_id: str
    version: str = PRICE_VERSION
    min_amount: Decimal | None = None
    setup_fee: Decimal = Decimal("0.00")
    approval_status: str = "approved"
    effective_from: date | None = None
    effective_to: date | None = None
    priority: int = 100

    def is_active(self, *, as_of_date: date, version: str) -> bool:
        if self.approval_status != "approved":
            return False
        if self.version != version:
            return False
        if self.effective_from and self.effective_from > as_of_date:
            return False
        if self.effective_to and self.effective_to < as_of_date:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "price_type": self.price_type,
            "target_code": self.target_code,
            "unit": self.unit,
            "unit_price": str(self.unit_price),
            "source_type": self.source_type,
            "source_id": self.source_id,
            "version": self.version,
            "min_amount": str(self.min_amount) if self.min_amount is not None else None,
            "setup_fee": str(self.setup_fee),
            "approval_status": self.approval_status,
            "effective_from": self.effective_from.isoformat() if self.effective_from else None,
            "effective_to": self.effective_to.isoformat() if self.effective_to else None,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, default_approval_status: str = "draft") -> PriceRule:
        return cls(
            rule_id=required_text(payload, "rule_id"),
            price_type=required_text(payload, "price_type"),
            target_code=required_text(payload, "target_code"),
            unit=optional_text(payload, "unit"),
            unit_price=decimal_field(payload, "unit_price"),
            source_type=required_text(payload, "source_type"),
            source_id=required_text(payload, "source_id"),
            version=optional_text(payload, "version") or PRICE_VERSION,
            min_amount=decimal_field(payload, "min_amount", required=False),
            setup_fee=decimal_field(payload, "setup_fee", required=False) or Decimal("0.00"),
            approval_status=optional_text(payload, "approval_status") or default_approval_status,
            effective_from=date_field(payload, "effective_from"),
            effective_to=date_field(payload, "effective_to"),
            priority=int(payload.get("priority", 100)),
        )


DEFAULT_PRICE_RULES = [
    PriceRule("material_skd11", "material", "SKD11", "kg", Decimal("45.00"), "archive_import", "mock_material_prices"),
    PriceRule("material_s45c", "material", "S45C", "kg", Decimal("12.00"), "archive_import", "mock_material_prices"),
    PriceRule("material_sus304", "material", "SUS304", "kg", Decimal("28.00"), "archive_import", "mock_material_prices"),
    PriceRule("material_al6061", "material", "AL6061", "kg", Decimal("25.00"), "archive_import", "mock_material_prices"),
    PriceRule("process_cutting", "process", "CUTTING", "pcs", Decimal("0.12"), "archive_import", "mock_process_prices"),
    PriceRule("process_cnc", "process", "CNC", "hour", Decimal("160.00"), "archive_import", "mock_process_prices", min_amount=Decimal("120.00")),
    PriceRule("process_drilling", "process", "DRILLING", "pcs", Decimal("8.00"), "archive_import", "mock_process_prices"),
    PriceRule("process_counterbore", "process", "COUNTERBORE", "pcs", Decimal("12.00"), "archive_import", "mock_process_prices"),
    PriceRule("process_tapping", "process", "TAPPING", "pcs", Decimal("10.00"), "archive_import", "mock_process_prices"),
    PriceRule("process_precision_hole", "process", "PRECISION_HOLE", "pcs", Decimal("35.00"), "archive_import", "mock_process_prices"),
    PriceRule("process_wire_cutting", "process", "WIRE_CUTTING", "mm2", Decimal("0.03"), "archive_import", "mock_process_prices", min_amount=Decimal("80.00")),
    PriceRule("process_grinding", "process", "GRINDING", "mm2", Decimal("0.02"), "archive_import", "mock_process_prices", min_amount=Decimal("60.00")),
    PriceRule("process_heat_treatment", "process", "HEAT_TREATMENT", "kg", Decimal("18.00"), "archive_import", "mock_process_prices", min_amount=Decimal("50.00")),
    PriceRule("surface_chemical_plating", "surface_treatment", "CHEMICAL_PLATING", "mm2", Decimal("0.02"), "archive_import", "mock_process_prices", min_amount=Decimal("50.00")),
    PriceRule("process_deburring", "process", "DEBURRING", "score", Decimal("15.00"), "archive_import", "mock_process_prices"),
    PriceRule("process_inspection", "process", "INSPECTION", "pcs", Decimal("8.00"), "archive_import", "mock_process_prices"),
    PriceRule("process_packaging", "process", "PACKAGING", "pcs", Decimal("5.00"), "archive_import", "mock_process_prices"),
    PriceRule("risk_high_precision", "risk_surcharge", "HIGH_PRECISION_REQUIREMENT", "risk", Decimal("30.00"), "manual", "mock_risk_surcharges"),
]


def find_active_price_rule(
    price_type: str,
    target_code: str,
    rules: list[PriceRule] | None = None,
    *,
    unit: str | None = None,
    as_of_date: date | None = None,
    version: str = PRICE_VERSION,
) -> PriceRule | None:
    rule_book = DEFAULT_PRICE_RULES if rules is None else rules
    match_date = as_of_date or date.today()
    matches = [
        rule
        for rule in rule_book
        if rule.price_type == price_type
        and rule.target_code == target_code
        and (unit is None or rule.unit is None or rule.unit == unit)
        and rule.is_active(as_of_date=match_date, version=version)
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda rule: (rule.priority, -(rule.effective_from or date.min).toordinal()))[0]


def list_price_rules(
    rules: list[PriceRule] | None = None,
    *,
    active_only: bool = False,
    price_type: str | None = None,
    target_code: str | None = None,
    as_of_date: date | None = None,
    version: str = PRICE_VERSION,
) -> list[PriceRule]:
    rule_book = DEFAULT_PRICE_RULES if rules is None else rules
    match_date = as_of_date or date.today()
    result = []
    for rule in rule_book:
        if price_type is not None and rule.price_type != price_type:
            continue
        if target_code is not None and rule.target_code != target_code:
            continue
        if active_only and not rule.is_active(as_of_date=match_date, version=version):
            continue
        result.append(rule)
    return sorted(result, key=lambda rule: (rule.price_type, rule.target_code, rule.unit or "", rule.priority, rule.rule_id))


def load_price_rules_from_json(path: str | Path, *, default_approval_status: str = "draft") -> list[PriceRule]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return price_rules_from_payload(payload, default_approval_status=default_approval_status)


def price_rules_from_payload(payload: Any, *, default_approval_status: str = "draft") -> list[PriceRule]:
    if isinstance(payload, dict):
        raw_rules = payload.get("price_rules")
    else:
        raw_rules = payload
    if not isinstance(raw_rules, list):
        raise ValueError("Price rule payload must be a list or an object with price_rules.")
    rules = [PriceRule.from_dict(item, default_approval_status=default_approval_status) for item in raw_rules]
    errors = validate_price_rules(rules)
    if errors:
        raise ValueError("; ".join(errors))
    return rules


def dump_price_rules_to_json(rules: list[PriceRule], path: str | Path) -> None:
    errors = validate_price_rules(rules)
    if errors:
        raise ValueError("; ".join(errors))
    payload = {"price_rules": [rule.to_dict() for rule in rules]}
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_price_rules(rules: list[PriceRule]) -> list[str]:
    errors: list[str] = []
    seen_rule_ids: set[str] = set()
    for index, rule in enumerate(rules, start=1):
        label = rule.rule_id or f"rule #{index}"
        if not rule.rule_id:
            errors.append(f"{label}: rule_id is required.")
        if rule.rule_id in seen_rule_ids:
            errors.append(f"{label}: duplicate rule_id.")
        seen_rule_ids.add(rule.rule_id)
        if rule.price_type not in PRICE_TYPES:
            errors.append(f"{label}: unsupported price_type {rule.price_type}.")
        if not rule.target_code:
            errors.append(f"{label}: target_code is required.")
        if rule.unit_price < 0:
            errors.append(f"{label}: unit_price must be non-negative.")
        if rule.min_amount is not None and rule.min_amount < 0:
            errors.append(f"{label}: min_amount must be non-negative.")
        if rule.setup_fee < 0:
            errors.append(f"{label}: setup_fee must be non-negative.")
        if rule.source_type not in SOURCE_TYPES:
            errors.append(f"{label}: unsupported source_type {rule.source_type}.")
        if not rule.source_id:
            errors.append(f"{label}: source_id is required.")
        if rule.approval_status not in APPROVAL_STATUSES:
            errors.append(f"{label}: unsupported approval_status {rule.approval_status}.")
        if rule.effective_from and rule.effective_to and rule.effective_from > rule.effective_to:
            errors.append(f"{label}: effective_from cannot be later than effective_to.")
        if rule.priority < 0:
            errors.append(f"{label}: priority must be non-negative.")
    return errors


def item_type_for_operation(operation_code: str) -> str:
    if operation_code == "MATERIAL_PREP":
        return "material"
    if operation_code == "CHEMICAL_PLATING":
        return "surface_treatment"
    return "process"


def decimal_field(payload: dict[str, Any], name: str, *, required: bool = True) -> Decimal | None:
    value = payload.get(name)
    if value is None or value == "":
        if required:
            raise ValueError(f"{name} is required.")
        return None
    return Decimal(str(value))


def date_field(payload: dict[str, Any], name: str) -> date | None:
    value = payload.get(name)
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def required_text(payload: dict[str, Any], name: str) -> str:
    value = optional_text(payload, name)
    if not value:
        raise ValueError(f"{name} is required.")
    return value


def optional_text(payload: dict[str, Any], name: str) -> str | None:
    value = payload.get(name)
    if value is None:
        return None
    return str(value)
