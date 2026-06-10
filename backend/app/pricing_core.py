from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .part_feature_builder import risk_item, source_ref
from .process_dictionary import (
    PROCESS_NAMES,
    PROCESS_SEQUENCE,
    PROCESS_UNIT_PRICES,
)
from .process_recognition import build_process_route


OPERATION_NAMES = PROCESS_NAMES
OPERATION_LABELS_ZH = PROCESS_NAMES
OPERATION_SEQUENCE = PROCESS_SEQUENCE

MATERIAL_UNIT_PRICES_PER_KG = {
    "SUS304": 32.0,
    "SKD11": 45.0,
    "S45C": 12.0,
    "45#": 12.0,
    "AL6061": 28.0,
    "6061": 28.0,
    "6061T6": 28.0,
}

PRICE_SOURCE = {
    "source_type": "manual",
    "source_id": "a_basic_core_bridge",
    "rule_id": "A_BASIC_CORE_FIRST_PASS",
    "version": "a-basic-v1",
}

HOLE_QUANTITY_REVIEW_CONFIDENCE_THRESHOLD = 0.7


@dataclass
class PricingCoreResult:
    process_route: dict[str, Any]
    quantity_result: dict[str, Any]
    quote_result: dict[str, Any]


class PricingCoreService:
    service_name = "a_basic_core_bridge"

    def build_quote(
        self,
        *,
        task_id: str,
        quote_id: str,
        part_feature: dict[str, Any],
        risks: list[dict[str, Any]],
        priced_at: str,
        price_version: str,
    ) -> PricingCoreResult:
        route_id = f"route_{quote_id.removeprefix('quote_')}"
        inherited_risks = dedupe_risks(list(risks))
        process_route = build_process_route(
            task_id=task_id,
            route_id=route_id,
            part_feature=part_feature,
            inherited_risks=inherited_risks,
        )
        quantity_result = build_quantity_result(
            task_id=task_id,
            route_id=route_id,
            part_feature=part_feature,
            process_route=process_route,
        )
        all_risks = merge_risks(
            inherited_risks,
            process_route.get("risks", []),
            quantity_result.get("risks", []),
        )
        quote_result = build_quote_result(
            task_id=task_id,
            quote_id=quote_id,
            priced_at=priced_at,
            price_version=price_version,
            part_feature=part_feature,
            process_route=process_route,
            quantity_result=quantity_result,
            risks=all_risks,
        )
        return PricingCoreResult(
            process_route=process_route,
            quantity_result=quantity_result,
            quote_result=quote_result,
        )


def build_pricing_core_service() -> PricingCoreService:
    return PricingCoreService()


def has_review_risk(risks: list[dict[str, Any]]) -> bool:
    return any(risk.get("requires_review") for risk in risks)


def build_quantity_result(
    *,
    task_id: str,
    route_id: str,
    part_feature: dict[str, Any],
    process_route: dict[str, Any],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    material = part_feature.get("material") or {}
    geometry = part_feature.get("geometry") or {}
    features = part_feature.get("features") or {}
    requirements = part_feature.get("manufacturing_requirements") or {}
    operations = {item["operation_code"] for item in process_route.get("operations", [])}

    measured_weight_source = geometry.get("step_net_weight") or {}
    measured_weight_value = measured_value(measured_weight_source)
    if measured_weight_value is None:
        measured_weight_source = geometry.get("pdf_weight") or {}
        measured_weight_value = measured_value(measured_weight_source)
    measured_weight_unit = measured_weight_source.get("unit") or "kg"

    bounding_box = geometry.get("bounding_box") or {}
    gross_weight = calculate_gross_weight_from_bbox(material, bounding_box)
    risks.extend(gross_weight["risks"])
    items.append(
        quantity_item(
            quantity_id="qty_material_gross_weight",
            operation_code="material_prepare",
            quantity_type="gross_weight",
            value=gross_weight["value"],
            unit="kg",
            formula="length_mm * width_mm * height_mm * density_kg_per_mm3.",
            basis=gross_weight["basis"],
            requires_review=gross_weight["value"] is None,
            review_reason=(
                None
                if gross_weight["value"] is not None
                else "Bounding box or material density is missing; gross weight cannot be calculated."
            ),
        )
    )

    cut_area = bbox_cut_area(bounding_box)
    if "saw_cut" in operations:
        if cut_area is None:
            append_risk_if_missing(
                risks,
                quantity_risk(
                    "QUANTITY_DIMENSION_MISSING",
                    "缺少下料面积所需的长宽尺寸，无法计算锯切下料工程量。",
                    "QUANTITY_DIMENSION_MISSING:SAW_CUT",
                ),
            )
        items.append(
            quantity_item(
                quantity_id="qty_cutting_area",
                operation_code="saw_cut",
                quantity_type="cut_area",
                value=cut_area,
                unit="mm2",
                formula="length * width from bounding box.",
                basis=[basis_item("bounding_box", bounding_box_text(bounding_box), "mm", system_source("CUT_AREA"))],
                requires_review=cut_area is None,
                review_reason=None if cut_area is not None else "Bounding box is missing; cut area cannot be calculated.",
            )
        )

    if "cnc_milling" in operations:
        complexity = features.get("complexity") or {}
        cnc_quantity = calculate_cnc_estimated_hours(geometry, complexity)
        risks.extend(cnc_quantity["risks"])
        items.append(
            quantity_item(
                quantity_id="qty_cnc_estimated_hours",
                operation_code="cnc_milling",
                quantity_type="estimated_hours",
                value=cnc_quantity["value"],
                unit="hour",
                formula="Requires machining parameters such as removal rate or cycle-time rule; not inferred from complexity alone.",
                basis=cnc_quantity["basis"],
                requires_review=True,
                review_reason="CNC hours need configured machining parameters or manual input.",
            )
        )

    add_hole_quantities(items, features.get("holes") or [], operations, risks)

    for operation_code in ("wire_cut_blank", "wire_cut_profile"):
        if operation_code in operations:
            wire_quantity = calculate_wire_cut_area(operation_code, geometry)
            risks.extend(wire_quantity["risks"])
            items.append(
                quantity_item(
                    quantity_id=f"qty_{operation_code}_cut_area",
                    operation_code=operation_code,
                    quantity_type="cut_area",
                    value=wire_quantity["value"],
                    unit="mm2",
                    formula="outer_profile_length_mm * material_thickness_mm.",
                    basis=wire_quantity["basis"],
                    requires_review=wire_quantity["requires_review"],
                    review_reason=wire_quantity["review_reason"],
                )
            )

    for operation_code in ("surface_grinding_rough", "finish_grinding"):
        if operation_code in operations:
            grinding_quantity = calculate_grinding_area(operation_code, bounding_box)
            risks.extend(grinding_quantity["risks"])
            items.append(
                quantity_item(
                    quantity_id=f"qty_{operation_code}_area",
                    operation_code=operation_code,
                    quantity_type="grinding_area",
                    value=grinding_quantity["value"],
                    unit="mm2",
                    formula="grinding_face_count * grinding_face_area_mm2.",
                    basis=grinding_quantity["basis"],
                    requires_review=True,
                    review_reason="Grinding face count is not available in part_feature; quantity needs confirmation.",
                )
            )

    if "heat_treatment" in operations:
        heat_weight = calculate_heat_treatment_weight(
            gross_weight_value=gross_weight["value"],
            gross_weight_basis=gross_weight["basis"],
            measured_weight_value=measured_weight_value,
            measured_weight_unit=measured_weight_unit,
            measured_weight_source=measured_weight_source,
        )
        risks.extend(heat_weight["risks"])
        items.append(
            quantity_item(
                quantity_id="qty_heat_treatment_weight",
                operation_code="heat_treatment",
                quantity_type="heat_weight",
                value=heat_weight["value"],
                unit=heat_weight["unit"],
                formula="Prefer calculated gross_weight; fallback to STEP/PDF measured weight when gross weight is unavailable.",
                basis=heat_weight["basis"],
                requires_review=heat_weight["requires_review"],
                review_reason=heat_weight["review_reason"],
            )
        )

    if "chemical_nickel" in operations:
        surface_quantity = calculate_surface_treatment_area(geometry)
        risks.extend(surface_quantity["risks"])
        surface = requirements.get("surface_treatment") or {}
        items.append(
            quantity_item(
                quantity_id="qty_surface_treatment_area",
                operation_code="chemical_nickel",
                quantity_type="surface_area",
                value=surface_quantity["value"],
                unit=surface_quantity["unit"],
                formula="Convert STEP surface_area to m2.",
                basis=[
                    *surface_quantity["basis"],
                    basis_item("surface_treatment", surface.get("raw_text"), None, surface.get("source")),
                ],
                requires_review=surface_quantity["value"] is None,
                review_reason=None if surface_quantity["value"] is not None else "Surface area is missing or unit is unsupported.",
            )
        )

    if "deburr" in operations:
        complexity = features.get("complexity") or {}
        deburring_quantity = calculate_deburr_complexity(complexity)
        risks.extend(deburring_quantity["risks"])
        items.append(
            quantity_item(
                quantity_id="qty_deburring_complexity",
                operation_code="deburr",
                quantity_type="deburr_complexity",
                value=deburring_quantity["value"],
                unit="score",
                formula="Prefer STEP complexity_score; fallback to STEP edge_count when complexity_score is unavailable.",
                basis=deburring_quantity["basis"],
                requires_review=deburring_quantity["requires_review"],
                review_reason=deburring_quantity["review_reason"],
            )
        )

    part_quantity = numeric_value((part_feature.get("part") or {}).get("quantity"))
    if part_quantity is None and ("inspection" in operations or "protective_packaging" in operations):
        append_risk_if_missing(
            risks,
            quantity_risk(
                "QUANTITY_PART_COUNT_MISSING",
                "缺少零件数量，无法计算检验或包装工程量。",
                "QUANTITY_PART_COUNT_MISSING",
            ),
        )
    if "inspection" in operations:
        items.append(
            quantity_item(
                quantity_id="qty_inspection_count",
                operation_code="inspection",
                quantity_type="inspection_count",
                value=part_quantity,
                unit="pcs",
                formula="part.quantity.",
                basis=[basis_item("part_quantity", part_quantity, "pcs", system_source("INSPECTION"))],
                requires_review=part_quantity is None,
                review_reason=None if part_quantity is not None else "Part quantity is missing.",
            )
        )

    if "protective_packaging" in operations:
        items.append(
            quantity_item(
                quantity_id="qty_packaging_lot",
                operation_code="protective_packaging",
                quantity_type="manual_quantity",
                value=part_quantity,
                unit="pcs",
                formula="part.quantity for protective packaging pieces.",
                basis=[basis_item("part_quantity", part_quantity, "pcs", system_source("PACKAGING"))],
                requires_review=part_quantity is None,
                review_reason=None if part_quantity is not None else "Part quantity is missing.",
            )
        )

    return {
        "schema_version": "1.0",
        "task_id": task_id,
        "route_id": route_id,
        "items": dedupe_quantity_items(items),
        "risks": risks,
    }


def add_hole_quantities(
    items: list[dict[str, Any]],
    holes: list[dict[str, Any]],
    operations: set[str],
    risks: list[dict[str, Any]],
) -> None:
    drilling_types = {
        "through",
        "blind",
        "counterbore",
        "countersink",
        "thread_candidate",
        "precision_candidate",
    }
    countersink_types = {"counterbore", "countersink"}
    counts = {
        "drilling": 0,
        "countersink": 0,
        "tapping": 0,
        "precision_hole": 0,
    }
    sources: dict[str, dict[str, Any] | None] = {
        "drilling": None,
        "countersink": None,
        "tapping": None,
        "precision_hole": None,
    }
    review_flags = {
        "drilling": False,
        "countersink": False,
        "tapping": False,
        "precision_hole": False,
    }

    for hole in holes:
        hole_type = hole.get("hole_type")
        count = int(hole.get("count") or 0)
        if not count:
            continue
        source = first_source(hole.get("evidence"))
        low_confidence = clamp_confidence(hole.get("confidence")) < HOLE_QUANTITY_REVIEW_CONFIDENCE_THRESHOLD
        if hole_type in drilling_types:
            counts["drilling"] += count
            sources["drilling"] = sources["drilling"] or source
            review_flags["drilling"] = review_flags["drilling"] or low_confidence
        if hole_type in countersink_types:
            counts["countersink"] += count
            sources["countersink"] = sources["countersink"] or source
            review_flags["countersink"] = review_flags["countersink"] or low_confidence
        if hole_type == "thread_candidate":
            counts["tapping"] += count
            sources["tapping"] = sources["tapping"] or source
            review_flags["tapping"] = True
        if hole_type == "precision_candidate":
            counts["precision_hole"] += count
            sources["precision_hole"] = sources["precision_hole"] or source
            review_flags["precision_hole"] = True
        if low_confidence:
            append_risk_if_missing(
                risks,
                quantity_risk(
                    "QUANTITY_LOW_CONFIDENCE_HOLE_COUNT",
                    "孔特征置信度低，孔类工程量需人工确认。",
                    "QUANTITY_LOW_CONFIDENCE_HOLE_COUNT",
                    evidence=[source or system_source("QUANTITY_LOW_CONFIDENCE_HOLE_COUNT")],
                ),
            )

    quantity_specs = {
        "drilling": ("qty_drilling_hole_count", "hole_count", False),
        "countersink": ("qty_counterbore_count", "counterbore_count", False),
        "tapping": ("qty_tapping_thread_count", "thread_count", True),
        "precision_hole": ("qty_precision_hole_count", "precision_hole_count", True),
    }
    for operation_code, count in counts.items():
        if count <= 0 or operation_code not in operations:
            continue
        quantity_id, quantity_type, candidate_requires_review = quantity_specs[operation_code]
        requires_review = candidate_requires_review or review_flags[operation_code]
        items.append(
            quantity_item(
                quantity_id=quantity_id,
                operation_code=operation_code,
                quantity_type=quantity_type,
                value=count,
                unit="pcs",
                formula="Sum detected hole candidates by operation type.",
                basis=[basis_item(operation_code, count, "pcs", sources.get(operation_code))],
                requires_review=requires_review,
                review_reason="Hole type is a candidate or low-confidence and needs confirmation." if requires_review else None,
            )
        )


def build_quote_result(
    *,
    task_id: str,
    quote_id: str,
    priced_at: str,
    price_version: str,
    part_feature: dict[str, Any],
    process_route: dict[str, Any],
    quantity_result: dict[str, Any],
    risks: list[dict[str, Any]],
) -> dict[str, Any]:
    quote_risks = list(risks)
    items: list[dict[str, Any]] = []
    material = part_feature.get("material") or {}
    material_text = material.get("raw_text") or material.get("standard_code")
    material_quantity = find_quantity(quantity_result, "gross_weight")
    material_kg = quantity_to_kg(material_quantity)
    material_unit_price = material_unit_price_from_text(material_text)

    if material_kg is not None and material_unit_price is not None:
        amount = round(material_kg * material_unit_price, 2)
        items.append(
            quote_item(
                item_id="item_material",
                item_type="material",
                operation_code="material_prepare",
                quantity=material_kg,
                unit="kg",
                unit_price=material_unit_price,
                amount=amount,
                explanation=f"Material {material_text} priced by weight.",
            )
        )
    else:
        items.append(
            quote_item(
                item_id="item_material_needs_review",
                item_type="material",
                operation_code="material_prepare",
                quantity=material_kg,
                unit="kg" if material_kg is not None else None,
                unit_price=material_unit_price,
                amount=None,
                explanation="Material price or weight is missing.",
                requires_review=True,
            )
        )
        quote_risks.append(missing_price_risk("material_prepare"))

    for operation in process_route.get("operations") or []:
        operation_code = operation["operation_code"]
        if operation_code in {"material_prepare", "chemical_nickel", "manual_review"}:
            continue

        quantity = quantity_for_operation(quantity_result, operation_code)
        unit_price = PROCESS_UNIT_PRICES.get(operation_code)
        value = numeric_value(quantity.get("value")) if quantity else None
        amount = round(value * unit_price, 2) if value is not None and unit_price is not None else None
        items.append(
            quote_item(
                item_id=f"item_process_{operation_code.lower()}",
                item_type="process",
                operation_code=operation_code,
                quantity=value,
                unit=quantity.get("unit") if quantity else None,
                unit_price=unit_price,
                amount=amount,
                explanation=operation.get("explanation") or OPERATION_NAMES[operation_code],
                requires_review=bool(operation.get("requires_review")) or amount is None,
            )
        )
        if amount is None:
            quote_risks.append(missing_price_risk(operation_code))

    surface_quantity = quantity_for_operation(quantity_result, "chemical_nickel")
    if surface_quantity:
        value = numeric_value(surface_quantity.get("value"))
        unit_price = PROCESS_UNIT_PRICES["chemical_nickel"]
        amount = round(value * unit_price, 2) if value is not None else None
        items.append(
            quote_item(
                item_id="item_surface_chemical_plating",
                item_type="surface_treatment",
                operation_code="chemical_nickel",
                quantity=value,
                unit=surface_quantity.get("unit"),
                unit_price=unit_price,
                amount=amount,
                explanation="Surface treatment priced by bridge surface-area rule.",
                requires_review=bool(surface_quantity.get("requires_review")) or amount is None,
            )
        )
        if amount is None:
            quote_risks.append(missing_price_risk("chemical_nickel"))

    material_amount = sum_amount(items, "material")
    process_amount = sum_amount(items, "process")
    surface_amount = sum_amount(items, "surface_treatment")
    subtotal = material_amount + process_amount + surface_amount
    management_fee = round(subtotal * 0.08, 2)
    tax_base = subtotal + management_fee
    tax_amount = round(tax_base * 0.13, 2)

    if management_fee:
        items.append(summary_item("item_management_fee", "management_fee", management_fee))
    if tax_amount:
        items.append(summary_item("item_tax", "tax", tax_amount))

    system_calculated = round(subtotal + management_fee + tax_amount, 2)
    system_initial_quote = round_up_to_10(system_calculated)
    quote_risks = dedupe_risks(quote_risks)
    status = "pending_review" if has_review_risk(quote_risks) else "priced"

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
        "summary": {
            "material_amount": material_amount,
            "process_amount": process_amount,
            "surface_treatment_amount": surface_amount,
            "management_fee": management_fee,
            "tax_amount": tax_amount,
            "risk_surcharge_amount": 0.0,
            "system_calculated_amount": system_calculated,
            "system_initial_quote": system_initial_quote,
            "manual_adjustment_amount": 0.0,
            "final_confirmed_amount": None,
        },
        "risks": quote_risks,
        "manual_overrides": [],
    }


def quote_item(
    *,
    item_id: str,
    item_type: str,
    operation_code: str | None,
    quantity: float | int | None,
    unit: str | None,
    unit_price: float | None,
    amount: float | None,
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
        "price_source": PRICE_SOURCE,
        "formula": "A_BASIC_CORE_FIRST_PASS",
        "explanation": explanation,
        "system_amount": amount,
        "final_amount": amount,
        "requires_review": requires_review,
    }


def quantity_item(
    *,
    quantity_id: str,
    operation_code: str,
    quantity_type: str,
    value: float | int | None,
    unit: str,
    formula: str,
    basis: list[dict[str, Any]],
    requires_review: bool = False,
    review_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "quantity_id": quantity_id,
        "operation_code": operation_code,
        "quantity_type": quantity_type,
        "value": value,
        "unit": unit,
        "formula": formula,
        "basis": basis,
        "requires_review": requires_review,
        "review_reason": review_reason,
    }


def basis_item(
    name: str,
    value: str | float | int | bool | None,
    unit: str | None,
    source: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "name": name,
        "value": value,
        "unit": unit,
        "source": source or system_source(name),
    }


def calculate_gross_weight_from_bbox(
    material: dict[str, Any],
    bounding_box: dict[str, Any],
) -> dict[str, Any]:
    dimensions = bbox_dimensions_mm(bounding_box)
    density = density_kg_per_mm3(material)
    basis = [
        basis_item("bounding_box", bounding_box_text(bounding_box), bounding_box.get("unit") or "mm", system_source("GROSS_WEIGHT_BBOX")),
        basis_item("material", material.get("raw_text") or material.get("standard_code"), None, material.get("source")),
        basis_item("density", material.get("density"), material.get("density_unit"), material.get("source")),
    ]
    risks: list[dict[str, Any]] = []

    if dimensions is None:
        risks.append(
            quantity_risk(
                "QUANTITY_DIMENSION_MISSING",
                "缺少毛坯长宽厚，无法按长×宽×厚×密度计算材料毛重。",
                "QUANTITY_DIMENSION_MISSING:GROSS_WEIGHT",
            )
        )
    if density is None:
        risks.append(
            quantity_risk(
                "MATERIAL_DENSITY_MISSING",
                "材料密度缺失或单位不支持，无法计算材料毛重。",
                "MATERIAL_DENSITY_MISSING:GROSS_WEIGHT",
                evidence=[material.get("source") or system_source("MATERIAL_DENSITY_MISSING:GROSS_WEIGHT")],
            )
        )

    if dimensions is None or density is None:
        return {"value": None, "basis": basis, "risks": risks}

    length, width, height = dimensions
    value = round(length * width * height * density, 6)
    basis.append(basis_item("density_kg_per_mm3", density, "kg/mm3", material.get("source")))
    return {"value": value, "basis": basis, "risks": risks}


def calculate_cnc_estimated_hours(
    geometry: dict[str, Any],
    complexity: dict[str, Any],
) -> dict[str, Any]:
    bounding_box = geometry.get("bounding_box") or {}
    bbox_volume = bbox_volume_mm3(bounding_box)
    part_volume = measured_value(geometry.get("volume") or {})
    basis = [
        basis_item("bounding_box_volume", bbox_volume, "mm3", system_source("CNC_ESTIMATE:BBOX_VOLUME")),
        basis_item("part_volume", part_volume, (geometry.get("volume") or {}).get("unit"), (geometry.get("volume") or {}).get("source")),
        basis_item("face_count", complexity.get("face_count"), None, system_source("CNC_ESTIMATE:FACE_COUNT")),
        basis_item("edge_count", complexity.get("edge_count"), None, system_source("CNC_ESTIMATE:EDGE_COUNT")),
        basis_item("complexity_score", complexity.get("complexity_score"), None, system_source("CNC_ESTIMATE:COMPLEXITY_SCORE")),
    ]
    risks = [
        quantity_risk(
            "QUANTITY_CNC_PARAMETER_MISSING",
            "缺少 CNC 去除率、装夹或节拍规则，不能仅凭复杂度生成真实工时。",
            "QUANTITY_CNC_PARAMETER_MISSING",
        )
    ]
    return {"value": None, "basis": basis, "risks": risks}


def calculate_wire_cut_area(
    operation_code: str,
    geometry: dict[str, Any],
) -> dict[str, Any]:
    bounding_box = geometry.get("bounding_box") or {}
    profile_summary = geometry.get("profile_summary") or {}
    outer_profile_length = numeric_value(profile_summary.get("outer_profile_length"))
    thickness = material_thickness_mm(bounding_box)
    basis = [
        basis_item(
            "outer_profile_length",
            outer_profile_length,
            "mm",
            step_profile_source(geometry, f"WIRE_CUT:{operation_code}:OUTER_PROFILE_LENGTH"),
        ),
        basis_item("material_thickness", thickness, "mm", system_source(f"WIRE_CUT:{operation_code}:THICKNESS")),
    ]
    risks: list[dict[str, Any]] = []
    if outer_profile_length is None:
        risks.append(
            quantity_risk(
                "QUANTITY_WIRE_CUT_LENGTH_MISSING",
                "缺少线切割外轮廓长度，无法按外轮廓长度×材料厚度计算线切割工程量。",
                f"QUANTITY_WIRE_CUT_LENGTH_MISSING:{operation_code}",
            )
        )
    if thickness is None:
        risks.append(
            quantity_risk(
                "QUANTITY_DIMENSION_MISSING",
                "缺少材料厚度，无法计算线切割工程量。",
                f"QUANTITY_DIMENSION_MISSING:{operation_code}",
            )
        )
    if outer_profile_length is None or thickness is None:
        return {
            "value": None,
            "basis": basis,
            "risks": risks,
            "requires_review": True,
            "review_reason": "Wire-cut outer profile length or material thickness is missing.",
        }

    return {
        "value": round(outer_profile_length * thickness, 4),
        "basis": basis,
        "risks": risks,
        "requires_review": False,
        "review_reason": None,
    }


def calculate_grinding_area(
    operation_code: str,
    bounding_box: dict[str, Any],
) -> dict[str, Any]:
    face_area = major_face_area_mm2(bounding_box)
    basis = [
        basis_item("grinding_face_count", None, None, system_source(f"GRINDING:{operation_code}:FACE_COUNT_MISSING")),
        basis_item("major_face_area", face_area, "mm2", system_source(f"GRINDING:{operation_code}:MAJOR_FACE_AREA")),
    ]
    risks = [
        quantity_risk(
            "QUANTITY_GRINDING_FACE_COUNT_MISSING",
            "缺少磨削面数量，无法按磨削面积计算真实工程量。",
            f"QUANTITY_GRINDING_FACE_COUNT_MISSING:{operation_code}",
        )
    ]
    if face_area is None:
        risks.append(
            quantity_risk(
                "QUANTITY_DIMENSION_MISSING",
                "缺少长宽高，无法计算磨削基准面积。",
                f"QUANTITY_DIMENSION_MISSING:{operation_code}",
            )
        )
    return {"value": None, "basis": basis, "risks": risks}


def step_profile_source(geometry: dict[str, Any], rule_code: str) -> dict[str, Any]:
    volume_source = (geometry.get("volume") or {}).get("source") or {}
    if isinstance(volume_source, dict) and volume_source.get("source_type") == "step":
        return source_ref(
            "step",
            file_id=volume_source.get("file_id"),
            rule_code=rule_code,
        )
    return system_source(rule_code)


def calculate_heat_treatment_weight(
    *,
    gross_weight_value: float | None,
    gross_weight_basis: list[dict[str, Any]],
    measured_weight_value: float | None,
    measured_weight_unit: str,
    measured_weight_source: dict[str, Any],
) -> dict[str, Any]:
    if gross_weight_value is not None:
        return {
            "value": gross_weight_value,
            "unit": "kg",
            "basis": [basis_item("gross_weight", gross_weight_value, "kg", system_source("HEAT_TREATMENT:GROSS_WEIGHT"))],
            "requires_review": False,
            "review_reason": None,
            "risks": [],
        }

    measured_kg = convert_weight_to_kg(measured_weight_value, measured_weight_unit)
    if measured_kg is not None:
        return {
            "value": round(measured_kg, 6),
            "unit": "kg",
            "basis": [
                *gross_weight_basis,
                basis_item("fallback_weight", measured_weight_value, measured_weight_unit, measured_weight_source.get("source")),
            ],
            "requires_review": True,
            "review_reason": "Gross weight is unavailable; STEP/PDF measured weight is used as heat-treatment fallback.",
            "risks": [
                quantity_risk(
                    "QUANTITY_HEAT_WEIGHT_FALLBACK",
                    "热处理毛坯重量缺失，已使用 STEP/PDF 重量作为待确认工程量。",
                    "QUANTITY_HEAT_WEIGHT_FALLBACK",
                )
            ],
        }

    return {
        "value": None,
        "unit": "kg",
        "basis": gross_weight_basis,
        "requires_review": True,
        "review_reason": "No gross, STEP, or PDF weight is available for heat treatment.",
        "risks": [
            quantity_risk(
                "QUANTITY_WEIGHT_MISSING",
                "未找到可用材料重量，热处理工程量需人工复核。",
                "QUANTITY_WEIGHT_MISSING:HEAT_TREATMENT",
            )
        ],
    }


def calculate_surface_treatment_area(geometry: dict[str, Any]) -> dict[str, Any]:
    surface = geometry.get("surface_area") or {}
    value = measured_value(surface)
    unit = str(surface.get("unit") or "mm2")
    converted = convert_area_to_m2(value, unit)
    basis = [
        basis_item("surface_area", value, unit, surface.get("source")),
        basis_item("surface_area_m2", converted, "m2", surface.get("source")),
    ]
    if converted is None:
        return {
            "value": None,
            "unit": "m2",
            "basis": basis,
            "risks": [
                quantity_risk(
                    "QUANTITY_SURFACE_AREA_MISSING",
                    "缺少可用表面积或单位不支持，无法计算表面处理工程量。",
                    "QUANTITY_SURFACE_AREA_MISSING",
                )
            ],
        }
    return {"value": round(converted, 6), "unit": "m2", "basis": basis, "risks": []}


def calculate_deburr_complexity(complexity: dict[str, Any]) -> dict[str, Any]:
    score = numeric_value(complexity.get("complexity_score"))
    if score is not None:
        return {
            "value": round(score, 2),
            "basis": [basis_item("complexity_score", score, None, system_source("DEBURRING:COMPLEXITY_SCORE"))],
            "requires_review": False,
            "review_reason": None,
            "risks": [],
        }

    edge_count = numeric_value(complexity.get("edge_count"))
    if edge_count is not None:
        return {
            "value": round(edge_count, 2),
            "basis": [basis_item("edge_count", edge_count, None, system_source("DEBURRING:EDGE_COUNT"))],
            "requires_review": True,
            "review_reason": "complexity_score is missing; edge_count is used as deburring complexity proxy.",
            "risks": [
                quantity_risk(
                    "QUANTITY_DEBURR_COMPLEXITY_FALLBACK",
                    "去毛刺复杂度评分缺失，已使用边数量作为待确认工程量。",
                    "QUANTITY_DEBURR_COMPLEXITY_FALLBACK",
                )
            ],
        }

    return {
        "value": None,
        "basis": [basis_item("complexity_score", None, None, system_source("DEBURRING:COMPLEXITY_SCORE"))],
        "requires_review": True,
        "review_reason": "STEP complexity_score and edge_count are missing; deburring quantity needs manual input.",
        "risks": [
            quantity_risk(
                "QUANTITY_DEBURR_COMPLEXITY_MISSING",
                "缺少复杂度评分和边数量，无法计算去毛刺工程量。",
                "QUANTITY_DEBURR_COMPLEXITY_MISSING",
            )
        ],
    }


def summary_item(
    item_id: str,
    item_type: str,
    amount: float,
    *,
    requires_review: bool = False,
) -> dict[str, Any]:
    return quote_item(
        item_id=item_id,
        item_type=item_type,
        operation_code=None,
        quantity=1,
        unit="lot",
        unit_price=amount,
        amount=amount,
        explanation="First-pass quote summary item.",
        requires_review=requires_review,
    )


def measured_value(value: dict[str, Any] | None) -> float | None:
    if not value:
        return None
    return numeric_value(value.get("value"))


def numeric_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def dimension_factor_to_mm(unit: Any) -> float | None:
    text = str(unit or "mm").strip().lower()
    if text in {"mm", "millimeter", "millimeters"}:
        return 1.0
    if text in {"cm", "centimeter", "centimeters"}:
        return 10.0
    if text in {"m", "meter", "meters"}:
        return 1000.0
    return None


def bbox_dimensions_mm(bounding_box: dict[str, Any]) -> tuple[float, float, float] | None:
    factor = dimension_factor_to_mm(bounding_box.get("unit"))
    length = numeric_value(bounding_box.get("length"))
    width = numeric_value(bounding_box.get("width"))
    height = numeric_value(bounding_box.get("height"))
    if factor is None or length is None or width is None or height is None:
        return None
    return (length * factor, width * factor, height * factor)


def bbox_volume_mm3(bounding_box: dict[str, Any]) -> float | None:
    dimensions = bbox_dimensions_mm(bounding_box)
    if dimensions is None:
        return None
    length, width, height = dimensions
    return round(length * width * height, 4)


def material_thickness_mm(bounding_box: dict[str, Any]) -> float | None:
    dimensions = bbox_dimensions_mm(bounding_box)
    if dimensions is None:
        return None
    return round(min(dimensions), 4)


def major_face_area_mm2(bounding_box: dict[str, Any]) -> float | None:
    dimensions = bbox_dimensions_mm(bounding_box)
    if dimensions is None:
        return None
    ordered = sorted(dimensions, reverse=True)
    return round(ordered[0] * ordered[1], 4)


def density_kg_per_mm3(material: dict[str, Any]) -> float | None:
    density = numeric_value(material.get("density"))
    if density is None:
        return None
    unit = str(material.get("density_unit") or "").strip().lower()
    if unit in {"kg/mm3", "kg/mm^3"}:
        return density
    if unit in {"g/cm3", "g/cm^3", "g/cc"}:
        return density / 1_000_000
    if unit in {"kg/m3", "kg/m^3"}:
        return density / 1_000_000_000
    if unit in {"g/mm3", "g/mm^3"}:
        return density / 1000
    return None


def convert_area_to_m2(value: float | None, unit: Any) -> float | None:
    if value is None:
        return None
    text = str(unit or "mm2").strip().lower()
    if text in {"m2", "m^2", "㎡"}:
        return value
    if text in {"mm2", "mm^2"}:
        return value / 1_000_000
    if text in {"cm2", "cm^2"}:
        return value / 10_000
    return None


def convert_weight_to_kg(value: float | None, unit: Any) -> float | None:
    if value is None:
        return None
    text = str(unit or "kg").strip().lower()
    if text == "kg":
        return value
    if text == "g":
        return value / 1000
    return None


def quantity_to_kg(quantity: dict[str, Any] | None) -> float | None:
    if not quantity:
        return None
    value = numeric_value(quantity.get("value"))
    if value is None:
        return None
    converted = convert_weight_to_kg(value, quantity.get("unit"))
    return converted if converted is not None else value


def quantity_for_operation(
    quantity_result: dict[str, Any],
    operation_code: str,
) -> dict[str, Any] | None:
    for item in quantity_result.get("items") or []:
        if item.get("operation_code") == operation_code:
            return item
    return None


def find_quantity(
    quantity_result: dict[str, Any],
    quantity_type: str,
) -> dict[str, Any] | None:
    for item in quantity_result.get("items") or []:
        if item.get("quantity_type") == quantity_type:
            return item
    return None


def bbox_cut_area(bounding_box: dict[str, Any]) -> float | None:
    dimensions = bbox_dimensions_mm(bounding_box)
    if dimensions is None:
        return None
    length, width, _height = dimensions
    return round(length * width, 4)


def bounding_box_text(bounding_box: dict[str, Any]) -> str | None:
    length = bounding_box.get("length")
    width = bounding_box.get("width")
    height = bounding_box.get("height")
    if length is None or width is None or height is None:
        return None
    return f"{length}x{width}x{height}"


def estimate_cnc_hours(complexity: dict[str, Any]) -> float | None:
    return None


def is_chemical_plating(requirement: dict[str, Any]) -> bool:
    text = " ".join(
        str(value or "")
        for value in [
            requirement.get("standard_code"),
            requirement.get("raw_text"),
        ]
    ).upper()
    return (
        "CHEMICAL" in text
        or "NICKEL" in text
        or "NI" in text
        or "化学" in text
        or "镍" in text
    )


def material_unit_price_from_text(raw_text: Any) -> float | None:
    if raw_text in (None, ""):
        return None
    text = str(raw_text).strip().upper().replace(" ", "").replace("-", "")
    if text in MATERIAL_UNIT_PRICES_PER_KG:
        return MATERIAL_UNIT_PRICES_PER_KG[text]
    for material_key, unit_price in MATERIAL_UNIT_PRICES_PER_KG.items():
        if material_key in text:
            return unit_price
    return None


def sum_amount(items: list[dict[str, Any]], item_type: str) -> float:
    return round(
        sum(float(item.get("amount") or 0) for item in items if item.get("item_type") == item_type),
        2,
    )


def round_up_to_10(value: float) -> float:
    if value <= 0:
        return 0.0
    return float(int((value + 9.99) // 10 * 10))


def missing_price_risk(operation_code: str) -> dict[str, Any]:
    operation_name = OPERATION_LABELS_ZH.get(operation_code, operation_code)
    return risk_item(
        "MISSING_PRICE_OR_QUANTITY",
        "warning",
        f"{operation_name}缺少单价或工程量，需补录后复核报价。",
        "pricing_core",
        True,
        [system_source(f"MISSING_PRICE_OR_QUANTITY:{operation_code}")],
    )


def quantity_risk(
    code: str,
    message: str,
    rule_code: str,
    *,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return risk_item(
        code,
        "warning",
        message,
        "pricing_core",
        True,
        evidence or [system_source(rule_code)],
    )


def append_risk_if_missing(
    risks: list[dict[str, Any]],
    risk: dict[str, Any],
) -> None:
    code = risk.get("code")
    message = risk.get("message")
    if any(item.get("code") == code and item.get("message") == message for item in risks):
        return
    risks.append(risk)


def merge_risks(*risk_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return dedupe_risks([risk for group in risk_groups for risk in group])


def dedupe_risks(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped = []
    for risk in risks:
        key = (str(risk.get("code")), str(risk.get("message")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(risk)
    return deduped


def dedupe_quantity_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped = []
    for item in items:
        quantity_id = item["quantity_id"]
        if quantity_id in seen:
            continue
        seen.add(quantity_id)
        deduped.append(item)
    return deduped


def first_source(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
        return None
    return value if isinstance(value, dict) else None


def system_source(rule_code: str) -> dict[str, Any]:
    return source_ref("system", rule_code=rule_code)


def clamp_confidence(value: Any) -> float:
    number = numeric_value(value)
    if number is None:
        return 0.0
    return min(1.0, max(0.0, number))
