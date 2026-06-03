from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class MaterialDefinition:
    code: str
    name: str
    aliases: tuple[str, ...]
    density: Decimal
    density_unit: str
    category: str
    status: str = "active"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "aliases": list(self.aliases),
            "density": str(self.density),
            "density_unit": self.density_unit,
            "category": self.category,
            "status": self.status,
        }


@dataclass(frozen=True)
class OperationDefinition:
    code: str
    name: str
    item_type: str
    sequence: int
    auto_pricing: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "item_type": self.item_type,
            "sequence": self.sequence,
            "auto_pricing": self.auto_pricing,
        }


@dataclass(frozen=True)
class SurfaceTreatmentDefinition:
    code: str
    name: str
    aliases: tuple[str, ...]
    default_unit: str
    status: str = "active"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "aliases": list(self.aliases),
            "default_unit": self.default_unit,
            "status": self.status,
        }


@dataclass(frozen=True)
class RiskTagDefinition:
    code: str
    level: str
    requires_review: bool
    default_message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "level": self.level,
            "requires_review": self.requires_review,
            "default_message": self.default_message,
        }


@dataclass(frozen=True)
class UnitDefinition:
    code: str
    name: str
    unit_type: str
    to_base_factor: Decimal
    base_unit: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "unit_type": self.unit_type,
            "to_base_factor": str(self.to_base_factor),
            "base_unit": self.base_unit,
        }


MATERIALS = [
    MaterialDefinition("SKD11", "SKD11", ("SKD11", "Cr12MoV equivalent"), Decimal("0.00000785"), "kg/mm3", "tool_steel"),
    MaterialDefinition("S45C", "S45C", ("S45C", "45# steel", "45 steel"), Decimal("0.00000785"), "kg/mm3", "carbon_steel"),
    MaterialDefinition("SUS304", "SUS304", ("SUS304", "304", "304 stainless"), Decimal("0.00000793"), "kg/mm3", "stainless_steel"),
    MaterialDefinition("AL6061", "AL6061", ("AL6061", "6061", "6061-T6"), Decimal("0.00000270"), "kg/mm3", "aluminum"),
]

OPERATIONS = [
    OperationDefinition("MATERIAL_PREP", "Material prep", "material", 10),
    OperationDefinition("CUTTING", "Cutting", "process", 20),
    OperationDefinition("CNC", "CNC", "process", 30),
    OperationDefinition("WIRE_CUTTING", "Wire cutting", "process", 35),
    OperationDefinition("DRILLING", "Drilling", "process", 40),
    OperationDefinition("COUNTERBORE", "Counterbore", "process", 45),
    OperationDefinition("TAPPING", "Tapping", "process", 50),
    OperationDefinition("HEAT_TREATMENT", "Heat treatment", "process", 60),
    OperationDefinition("GRINDING", "Grinding", "process", 70),
    OperationDefinition("PRECISION_HOLE", "Precision hole", "process", 75),
    OperationDefinition("DEBURRING", "Deburring", "process", 80),
    OperationDefinition("CHEMICAL_PLATING", "Chemical plating", "surface_treatment", 90),
    OperationDefinition("INSPECTION", "Inspection", "process", 100),
    OperationDefinition("PACKAGING", "Packaging", "process", 110),
    OperationDefinition("MANUAL_REVIEW", "Manual review", "other", 999, auto_pricing=False),
]

SURFACE_TREATMENTS = [
    SurfaceTreatmentDefinition("CHEMICAL_PLATING", "Chemical plating", ("chemical nickel plating", "nickel plating", "chemical plating"), "mm2"),
]

RISK_TAGS = [
    RiskTagDefinition("MISSING_PDF", "warning", True, "PDF drawing is missing."),
    RiskTagDefinition("MISSING_STEP", "warning", True, "STEP model is missing."),
    RiskTagDefinition("WEIGHT_MISMATCH", "warning", True, "PDF weight and STEP weight differ beyond threshold."),
    RiskTagDefinition("UNKNOWN_MATERIAL", "blocking", True, "Material cannot be normalized."),
    RiskTagDefinition("MISSING_QUANTITY_BASIS", "blocking", True, "Required quantity basis is missing."),
    RiskTagDefinition("MISSING_PRICE", "blocking", True, "Approved price rule is missing."),
    RiskTagDefinition("PRICE_OUTLIER", "warning", True, "Price is outside historical range."),
    RiskTagDefinition("HIGH_PRECISION_REQUIREMENT", "warning", True, "High precision requirement needs review."),
    RiskTagDefinition("HIGH_RISK_GEOMETRY", "blocking", True, "Geometry requires manual process review."),
]

UNITS = [
    UnitDefinition("mm", "millimeter", "length", Decimal("1"), "mm"),
    UnitDefinition("cm", "centimeter", "length", Decimal("10"), "mm"),
    UnitDefinition("m", "meter", "length", Decimal("1000"), "mm"),
    UnitDefinition("mm2", "square millimeter", "area", Decimal("1"), "mm2"),
    UnitDefinition("cm2", "square centimeter", "area", Decimal("100"), "mm2"),
    UnitDefinition("kg", "kilogram", "weight", Decimal("1"), "kg"),
    UnitDefinition("g", "gram", "weight", Decimal("0.001"), "kg"),
    UnitDefinition("pcs", "pieces", "count", Decimal("1"), "pcs"),
    UnitDefinition("hour", "hour", "time", Decimal("1"), "hour"),
    UnitDefinition("score", "score", "score", Decimal("1"), "score"),
    UnitDefinition("risk", "risk item", "risk", Decimal("1"), "risk"),
    UnitDefinition("CNY", "Chinese yuan", "currency", Decimal("1"), "CNY"),
]

DICTIONARIES = {
    "materials": MATERIALS,
    "operations": OPERATIONS,
    "surface_treatments": SURFACE_TREATMENTS,
    "risk_tags": RISK_TAGS,
    "units": UNITS,
}


def list_dictionary(kind: str) -> list[dict[str, Any]]:
    return [item.to_dict() for item in get_dictionary(kind)]


def get_dictionary(kind: str) -> list[Any]:
    try:
        return list(DICTIONARIES[kind])
    except KeyError as exc:
        raise ValueError(f"Unknown dictionary kind: {kind}") from exc


def get_dictionary_item(kind: str, code: str) -> dict[str, Any] | None:
    code_upper = code.upper()
    for item in get_dictionary(kind):
        if getattr(item, "code").upper() == code_upper:
            return item.to_dict()
    return None


def normalize_material(raw_text: str | None) -> MaterialDefinition | None:
    if not raw_text:
        return None
    normalized = raw_text.strip().upper().replace(" ", "")
    for material in MATERIALS:
        candidates = {material.code.upper().replace(" ", ""), material.name.upper().replace(" ", "")}
        candidates.update(alias.upper().replace(" ", "") for alias in material.aliases)
        if normalized in candidates:
            return material
    return None


def convert_unit(value: Decimal | int | float | str, from_unit: str, to_unit: str) -> Decimal:
    source = unit_definition(from_unit)
    target = unit_definition(to_unit)
    if source.unit_type != target.unit_type:
        raise ValueError(f"Cannot convert {from_unit} to {to_unit}.")
    base_value = Decimal(str(value)) * source.to_base_factor
    return base_value / target.to_base_factor


def unit_definition(code: str) -> UnitDefinition:
    for unit in UNITS:
        if unit.code == code:
            return unit
    raise ValueError(f"Unknown unit: {code}")
