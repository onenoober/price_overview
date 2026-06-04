from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .mock_parser import risk_item, source_ref
from .mock_quote import has_review_risk


OPERATION_NAMES = {
    "MATERIAL_PREP": "Material prep",
    "CUTTING": "Cutting",
    "CNC": "CNC machining",
    "DRILLING": "Drilling",
    "COUNTERBORE": "Counterbore",
    "TAPPING": "Tapping",
    "PRECISION_HOLE": "Precision hole",
    "WIRE_CUTTING": "Wire cutting",
    "GRINDING": "Grinding",
    "HEAT_TREATMENT": "Heat treatment",
    "CHEMICAL_PLATING": "Chemical plating",
    "DEBURRING": "Deburring",
    "INSPECTION": "Inspection",
    "PACKAGING": "Packaging",
    "MANUAL_REVIEW": "Manual review",
}

OPERATION_SEQUENCE = [
    "MATERIAL_PREP",
    "CUTTING",
    "CNC",
    "DRILLING",
    "COUNTERBORE",
    "TAPPING",
    "PRECISION_HOLE",
    "WIRE_CUTTING",
    "GRINDING",
    "HEAT_TREATMENT",
    "CHEMICAL_PLATING",
    "DEBURRING",
    "INSPECTION",
    "PACKAGING",
    "MANUAL_REVIEW",
]

MATERIAL_UNIT_PRICES_PER_KG = {
    "SUS304": 32.0,
    "SKD11": 45.0,
    "S45C": 12.0,
    "AL6061": 28.0,
}

PROCESS_UNIT_PRICES = {
    "CUTTING": 0.0008,
    "CNC": 120.0,
    "DRILLING": 6.0,
    "COUNTERBORE": 8.0,
    "TAPPING": 8.0,
    "PRECISION_HOLE": 15.0,
    "WIRE_CUTTING": 80.0,
    "GRINDING": 60.0,
    "HEAT_TREATMENT": 35.0,
    "CHEMICAL_PLATING": 45.0,
    "DEBURRING": 0.5,
    "INSPECTION": 10.0,
    "PACKAGING": 8.0,
}

PRICE_SOURCE = {
    "source_type": "manual",
    "source_id": "a_basic_core_bridge",
    "rule_id": "A_BASIC_CORE_FIRST_PASS",
    "version": "a-basic-v1",
}


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


def build_process_route(
    *,
    task_id: str,
    route_id: str,
    part_feature: dict[str, Any],
    inherited_risks: list[dict[str, Any]],
) -> dict[str, Any]:
    operations: list[dict[str, Any]] = []
    material = part_feature.get("material") or {}
    features = part_feature.get("features") or {}
    requirements = part_feature.get("manufacturing_requirements") or {}

    material_code = material.get("standard_code")
    add_operation(
        operations,
        operation_code="MATERIAL_PREP",
        rule_code="MATERIAL_PRESENT" if material_code else "MATERIAL_MISSING",
        message="Material prep is required for quoting.",
        source=material.get("source"),
        confidence=0.85 if material_code else 0.3,
        requires_review=not bool(material_code),
        review_reason=None if material_code else "Material is missing or not normalized.",
    )
    add_operation(
        operations,
        operation_code="CUTTING",
        rule_code="BASE_CUTTING",
        message="First-pass route includes blank cutting.",
        source=system_source("BASE_CUTTING"),
        confidence=0.75,
    )
    add_operation(
        operations,
        operation_code="CNC",
        rule_code="BASE_CNC",
        message="First-pass route includes CNC machining.",
        source=system_source("BASE_CNC"),
        confidence=0.65,
        requires_review=True,
        review_reason="CNC routing is a first-pass bridge rule and should be replaced by A.",
    )

    for hole in features.get("holes") or []:
        hole_type = hole.get("hole_type")
        count = hole.get("count") or 0
        if not count:
            continue
        if hole_type == "through":
            add_operation(
                operations,
                operation_code="DRILLING",
                rule_code="HOLE_THROUGH",
                message=f"Detected through holes: {count}.",
                source=first_source(hole.get("evidence")),
                confidence=hole.get("confidence", 0.7),
            )
        elif hole_type == "counterbore":
            add_operation(
                operations,
                operation_code="COUNTERBORE",
                rule_code="HOLE_COUNTERBORE",
                message=f"Detected counterbores: {count}.",
                source=first_source(hole.get("evidence")),
                confidence=hole.get("confidence", 0.7),
            )
        elif hole_type == "thread_candidate":
            add_operation(
                operations,
                operation_code="TAPPING",
                rule_code="HOLE_THREAD_CANDIDATE",
                message=f"Detected thread-hole candidates: {count}.",
                source=first_source(hole.get("evidence")),
                confidence=hole.get("confidence", 0.65),
                requires_review=True,
                review_reason="Thread holes are candidates and need manual or A-side confirmation.",
            )
        elif hole_type == "precision_candidate":
            add_operation(
                operations,
                operation_code="PRECISION_HOLE",
                rule_code="HOLE_PRECISION_CANDIDATE",
                message=f"Detected precision-hole candidates: {count}.",
                source=first_source(hole.get("evidence")),
                confidence=hole.get("confidence", 0.65),
                requires_review=True,
                review_reason="Precision holes are candidates and need manual or A-side confirmation.",
            )

    precision_requirements = features.get("precision_requirements") or []
    if any("RA" in str(item.get("standard_type") or "").upper() for item in precision_requirements):
        add_operation(
            operations,
            operation_code="GRINDING",
            rule_code="ROUGHNESS_REQUIREMENT",
            message="Detected roughness requirement candidate.",
            source=first_source([item.get("source") for item in precision_requirements]),
            confidence=0.55,
            requires_review=True,
            review_reason="Roughness-to-grinding mapping is a first-pass candidate.",
        )

    heat_treatment = requirements.get("heat_treatment") or {}
    if heat_treatment.get("required"):
        add_operation(
            operations,
            operation_code="HEAT_TREATMENT",
            rule_code="HEAT_TREATMENT_REQUIRED",
            message=f"Detected heat treatment: {heat_treatment.get('raw_text')}.",
            source=heat_treatment.get("source"),
            confidence=heat_treatment.get("confidence", 0.7),
        )

    surface_treatment = requirements.get("surface_treatment") or {}
    if surface_treatment.get("required"):
        add_operation(
            operations,
            operation_code="CHEMICAL_PLATING",
            rule_code="SURFACE_TREATMENT_REQUIRED",
            message=f"Detected surface treatment: {surface_treatment.get('raw_text')}.",
            source=surface_treatment.get("source"),
            confidence=surface_treatment.get("confidence", 0.7),
            requires_review=not is_chemical_plating(surface_treatment),
            review_reason=None
            if is_chemical_plating(surface_treatment)
            else "Surface treatment was mapped to chemical plating as a bridge rule.",
        )

    deburring = requirements.get("deburring") or {}
    if deburring.get("required"):
        add_operation(
            operations,
            operation_code="DEBURRING",
            rule_code="DEBURRING_REQUIRED",
            message="Detected deburring requirement.",
            source=deburring.get("source"),
            confidence=deburring.get("confidence", 0.65),
        )

    inspection = requirements.get("inspection") or {}
    add_operation(
        operations,
        operation_code="INSPECTION",
        rule_code="BASE_INSPECTION",
        message="First-pass quote includes inspection.",
        source=inspection.get("source") or system_source("BASE_INSPECTION"),
        confidence=inspection.get("confidence", 0.7) if inspection else 0.7,
    )

    packaging = requirements.get("packaging") or {}
    add_operation(
        operations,
        operation_code="PACKAGING",
        rule_code="BASE_PACKAGING",
        message="First-pass quote includes packaging.",
        source=packaging.get("source") or system_source("BASE_PACKAGING"),
        confidence=packaging.get("confidence") or 0.65,
    )

    if any(risk.get("requires_review") for risk in inherited_risks):
        add_operation(
            operations,
            operation_code="MANUAL_REVIEW",
            rule_code="INHERITED_REVIEW_RISK",
            message="Parsing or feature fusion produced review risks.",
            source=system_source("INHERITED_REVIEW_RISK"),
            confidence=0.9,
            requires_review=True,
            review_reason="Inherited parse/fusion risks require review before formal quoting.",
        )

    ordered = sorted(
        operations,
        key=lambda item: OPERATION_SEQUENCE.index(item["operation_code"]),
    )
    for index, operation in enumerate(ordered, start=1):
        operation["sequence"] = index
        operation["operation_id"] = f"op_{index:03d}_{operation['operation_code'].lower()}"

    risks = []
    if any(operation.get("requires_review") for operation in ordered):
        risks.append(
            risk_item(
                "PROCESS_ROUTE_REQUIRES_REVIEW",
                "warning",
                "The process route contains bridge rules or candidates that need A-side confirmation.",
                "pricing_core",
                True,
                [system_source("PROCESS_ROUTE_REQUIRES_REVIEW")],
            )
        )

    return {
        "schema_version": "1.0",
        "task_id": task_id,
        "route_id": route_id,
        "operations": ordered,
        "requires_review": bool(risks),
        "risks": risks,
    }


def add_operation(
    operations: list[dict[str, Any]],
    *,
    operation_code: str,
    rule_code: str,
    message: str,
    source: dict[str, Any] | None,
    confidence: float,
    requires_review: bool = False,
    review_reason: str | None = None,
) -> None:
    existing = next(
        (item for item in operations if item["operation_code"] == operation_code),
        None,
    )
    reason = {
        "rule_code": rule_code,
        "message": message,
        "source": source or system_source(rule_code),
    }
    if existing:
        existing["trigger_reasons"].append(reason)
        existing["confidence"] = max(existing["confidence"], clamp_confidence(confidence))
        existing["requires_review"] = bool(existing["requires_review"] or requires_review)
        existing["review_reason"] = existing.get("review_reason") or review_reason
        return

    operations.append(
        {
            "operation_id": "",
            "operation_code": operation_code,
            "operation_name": OPERATION_NAMES[operation_code],
            "sequence": 1,
            "trigger_reasons": [reason],
            "confidence": clamp_confidence(confidence),
            "requires_review": requires_review,
            "review_reason": review_reason,
            "explanation": message,
        }
    )


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

    weight_source = geometry.get("step_net_weight") or {}
    weight_value = measured_value(weight_source)
    if weight_value is None:
        weight_source = geometry.get("pdf_weight") or {}
        weight_value = measured_value(weight_source)
    weight_unit = weight_source.get("unit") or "kg"

    if weight_value is not None:
        items.append(
            quantity_item(
                quantity_id="qty_material_gross_weight",
                operation_code="MATERIAL_PREP",
                quantity_type="gross_weight",
                value=round(weight_value, 4),
                unit=weight_unit,
                formula="Prefer STEP net weight, otherwise use PDF weight.",
                basis=[
                    basis_item("material", material.get("standard_code"), None, material.get("source")),
                    basis_item("weight", weight_value, weight_unit, weight_source.get("source")),
                ],
            )
        )
    else:
        risks.append(
            risk_item(
                "QUANTITY_WEIGHT_MISSING",
                "warning",
                "No usable material weight was found; material and heat-treatment quantities need review.",
                "pricing_core",
                True,
                [system_source("QUANTITY_WEIGHT_MISSING")],
            )
        )

    bounding_box = geometry.get("bounding_box") or {}
    cut_area = bbox_cut_area(bounding_box)
    if "CUTTING" in operations:
        items.append(
            quantity_item(
                quantity_id="qty_cutting_area",
                operation_code="CUTTING",
                quantity_type="cut_area",
                value=cut_area,
                unit="mm2",
                formula="length * width from bounding box.",
                basis=[basis_item("bounding_box", bounding_box_text(bounding_box), "mm", system_source("CUT_AREA"))],
                requires_review=cut_area is None,
                review_reason=None if cut_area is not None else "Bounding box is missing; cut area cannot be calculated.",
            )
        )

    if "CNC" in operations:
        complexity = features.get("complexity") or {}
        cnc_hours = estimate_cnc_hours(complexity)
        items.append(
            quantity_item(
                quantity_id="qty_cnc_estimated_hours",
                operation_code="CNC",
                quantity_type="estimated_hours",
                value=cnc_hours,
                unit="hour",
                formula="Bridge estimate: 1.0h + complexity_score / 100.",
                basis=[
                    basis_item(
                        "complexity_score",
                        complexity.get("complexity_score"),
                        None,
                        system_source("CNC_ESTIMATE"),
                    )
                ],
                requires_review=True,
                review_reason="CNC hours are bridge estimates and should be replaced by A.",
            )
        )

    add_hole_quantities(items, features.get("holes") or [])

    if "HEAT_TREATMENT" in operations:
        items.append(
            quantity_item(
                quantity_id="qty_heat_treatment_weight",
                operation_code="HEAT_TREATMENT",
                quantity_type="heat_weight",
                value=round(weight_value, 4) if weight_value is not None else None,
                unit=weight_unit,
                formula="Use material gross/net weight for heat treatment.",
                basis=[basis_item("weight", weight_value, weight_unit, weight_source.get("source"))],
                requires_review=weight_value is None,
                review_reason=None if weight_value is not None else "Heat-treatment quantity needs weight.",
            )
        )

    if "CHEMICAL_PLATING" in operations:
        surface_area = measured_value(geometry.get("surface_area") or {})
        surface_value = round(surface_area / 1_000_000, 6) if surface_area is not None else None
        surface = requirements.get("surface_treatment") or {}
        items.append(
            quantity_item(
                quantity_id="qty_surface_treatment_area",
                operation_code="CHEMICAL_PLATING",
                quantity_type="surface_area",
                value=surface_value,
                unit="m2",
                formula="STEP surface_area(mm2) / 1,000,000.",
                basis=[
                    basis_item("surface_area", surface_area, "mm2", (geometry.get("surface_area") or {}).get("source")),
                    basis_item("surface_treatment", surface.get("standard_code"), None, surface.get("source")),
                ],
                requires_review=surface_value is None,
                review_reason=None if surface_value is not None else "Surface area is missing.",
            )
        )

    if "DEBURRING" in operations:
        complexity = features.get("complexity") or {}
        score = complexity.get("complexity_score")
        items.append(
            quantity_item(
                quantity_id="qty_deburring_complexity",
                operation_code="DEBURRING",
                quantity_type="deburr_complexity",
                value=round(float(score), 2) if score is not None else 1,
                unit="score",
                formula="Use STEP complexity_score, fallback to 1.",
                basis=[basis_item("complexity_score", score, None, system_source("DEBURRING"))],
                requires_review=score is None,
                review_reason=None if score is not None else "STEP complexity is missing.",
            )
        )

    if "INSPECTION" in operations:
        items.append(
            quantity_item(
                quantity_id="qty_inspection_count",
                operation_code="INSPECTION",
                quantity_type="inspection_count",
                value=1,
                unit="pcs",
                formula="First-pass inspection per part.",
                basis=[basis_item("part_quantity", 1, "pcs", system_source("INSPECTION"))],
            )
        )

    if "PACKAGING" in operations:
        items.append(
            quantity_item(
                quantity_id="qty_packaging_lot",
                operation_code="PACKAGING",
                quantity_type="manual_quantity",
                value=1,
                unit="lot",
                formula="First-pass packaging per lot.",
                basis=[basis_item("lot", 1, "lot", system_source("PACKAGING"))],
            )
        )

    return {
        "schema_version": "1.0",
        "task_id": task_id,
        "route_id": route_id,
        "items": dedupe_quantity_items(items),
        "risks": risks,
    }


def add_hole_quantities(items: list[dict[str, Any]], holes: list[dict[str, Any]]) -> None:
    mappings = {
        "through": ("qty_drilling_hole_count", "DRILLING", "hole_count"),
        "counterbore": ("qty_counterbore_count", "COUNTERBORE", "counterbore_count"),
        "thread_candidate": ("qty_tapping_thread_count", "TAPPING", "thread_count"),
        "precision_candidate": ("qty_precision_hole_count", "PRECISION_HOLE", "precision_hole_count"),
    }
    counts: dict[str, int] = {}
    sources: dict[str, dict[str, Any] | None] = {}
    for hole in holes:
        hole_type = hole.get("hole_type")
        if hole_type not in mappings:
            continue
        counts[hole_type] = counts.get(hole_type, 0) + int(hole.get("count") or 0)
        sources[hole_type] = sources.get(hole_type) or first_source(hole.get("evidence"))

    for hole_type, count in counts.items():
        if not count:
            continue
        quantity_id, operation_code, quantity_type = mappings[hole_type]
        requires_review = hole_type in {"thread_candidate", "precision_candidate"}
        items.append(
            quantity_item(
                quantity_id=quantity_id,
                operation_code=operation_code,
                quantity_type=quantity_type,
                value=count,
                unit="pcs",
                formula="Sum detected hole candidates by type.",
                basis=[basis_item(hole_type, count, "pcs", sources.get(hole_type))],
                requires_review=requires_review,
                review_reason="Hole type is a candidate and needs confirmation." if requires_review else None,
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
    material_code = material.get("standard_code")
    material_quantity = find_quantity(quantity_result, "gross_weight")
    material_kg = quantity_to_kg(material_quantity)
    material_unit_price = MATERIAL_UNIT_PRICES_PER_KG.get(material_code)

    if material_kg is not None and material_unit_price is not None:
        amount = round(material_kg * material_unit_price, 2)
        items.append(
            quote_item(
                item_id="item_material",
                item_type="material",
                operation_code="MATERIAL_PREP",
                quantity=material_kg,
                unit="kg",
                unit_price=material_unit_price,
                amount=amount,
                explanation=f"Material {material_code} priced by weight.",
            )
        )
    else:
        items.append(
            quote_item(
                item_id="item_material_needs_review",
                item_type="material",
                operation_code="MATERIAL_PREP",
                quantity=material_kg,
                unit="kg" if material_kg is not None else None,
                unit_price=material_unit_price,
                amount=None,
                explanation="Material price or weight is missing.",
                requires_review=True,
            )
        )
        quote_risks.append(missing_price_risk("MATERIAL_PREP"))

    for operation in process_route.get("operations") or []:
        operation_code = operation["operation_code"]
        if operation_code in {"MATERIAL_PREP", "CHEMICAL_PLATING", "MANUAL_REVIEW"}:
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

    surface_quantity = quantity_for_operation(quantity_result, "CHEMICAL_PLATING")
    if surface_quantity:
        value = numeric_value(surface_quantity.get("value"))
        unit_price = PROCESS_UNIT_PRICES["CHEMICAL_PLATING"]
        amount = round(value * unit_price, 2) if value is not None else None
        items.append(
            quote_item(
                item_id="item_surface_chemical_plating",
                item_type="surface_treatment",
                operation_code="CHEMICAL_PLATING",
                quantity=value,
                unit=surface_quantity.get("unit"),
                unit_price=unit_price,
                amount=amount,
                explanation="Surface treatment priced by bridge surface-area rule.",
                requires_review=bool(surface_quantity.get("requires_review")) or amount is None,
            )
        )
        if amount is None:
            quote_risks.append(missing_price_risk("CHEMICAL_PLATING"))

    material_amount = sum_amount(items, "material")
    process_amount = sum_amount(items, "process")
    surface_amount = sum_amount(items, "surface_treatment")
    subtotal = material_amount + process_amount + surface_amount
    management_fee = round(subtotal * 0.08, 2)
    tax_base = subtotal + management_fee
    tax_amount = round(tax_base * 0.13, 2)
    risk_surcharge = 30.0 if has_review_risk(quote_risks) else 0.0

    if management_fee:
        items.append(summary_item("item_management_fee", "management_fee", management_fee))
    if tax_amount:
        items.append(summary_item("item_tax", "tax", tax_amount))
    if risk_surcharge:
        items.append(
            summary_item(
                "item_risk_surcharge",
                "risk_surcharge",
                risk_surcharge,
                requires_review=True,
            )
        )

    system_calculated = round(subtotal + management_fee + tax_amount + risk_surcharge, 2)
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
            "risk_surcharge_amount": risk_surcharge,
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


def quantity_to_kg(quantity: dict[str, Any] | None) -> float | None:
    if not quantity:
        return None
    value = numeric_value(quantity.get("value"))
    if value is None:
        return None
    unit = str(quantity.get("unit") or "").lower()
    if unit == "kg":
        return value
    if unit == "g":
        return value / 1000
    return value


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
    length = numeric_value(bounding_box.get("length"))
    width = numeric_value(bounding_box.get("width"))
    if length is None or width is None:
        return None
    return round(length * width, 4)


def bounding_box_text(bounding_box: dict[str, Any]) -> str | None:
    length = bounding_box.get("length")
    width = bounding_box.get("width")
    height = bounding_box.get("height")
    if length is None or width is None or height is None:
        return None
    return f"{length}x{width}x{height}"


def estimate_cnc_hours(complexity: dict[str, Any]) -> float:
    score = numeric_value(complexity.get("complexity_score"))
    if score is None:
        score = 30.0
    return round(1.0 + score / 100, 2)


def is_chemical_plating(requirement: dict[str, Any]) -> bool:
    text = " ".join(
        str(value or "")
        for value in [
            requirement.get("standard_code"),
            requirement.get("raw_text"),
        ]
    ).upper()
    return "CHEMICAL" in text or "NICKEL" in text or "NI" in text


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
    return risk_item(
        "MISSING_PRICE_OR_QUANTITY",
        "warning",
        f"{operation_code} is missing price or quantity and needs review.",
        "pricing_core",
        True,
        [system_source(f"MISSING_PRICE_OR_QUANTITY:{operation_code}")],
    )


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
