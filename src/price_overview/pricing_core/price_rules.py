from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


PRICE_VERSION = "mock-v0.2"


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


def item_type_for_operation(operation_code: str) -> str:
    if operation_code == "MATERIAL_PREP":
        return "material"
    if operation_code == "CHEMICAL_PLATING":
        return "surface_treatment"
    return "process"
