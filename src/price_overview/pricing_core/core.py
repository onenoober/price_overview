from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from .price_rules import PRICE_VERSION, PriceRule, find_active_price_rule, item_type_for_operation

SCHEMA_VERSION = "1.0"

OPERATION_NAMES = {
    "MATERIAL_PREP": "Material prep",
    "CUTTING": "Cutting",
    "CNC": "CNC",
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

OPERATION_ORDER = {
    "MATERIAL_PREP": 10,
    "CUTTING": 20,
    "CNC": 30,
    "WIRE_CUTTING": 35,
    "DRILLING": 40,
    "COUNTERBORE": 45,
    "TAPPING": 50,
    "HEAT_TREATMENT": 60,
    "GRINDING": 70,
    "PRECISION_HOLE": 75,
    "DEBURRING": 80,
    "CHEMICAL_PLATING": 90,
    "INSPECTION": 100,
    "PACKAGING": 110,
    "MANUAL_REVIEW": 999,
}

MANAGEMENT_FEE_RATE = Decimal("0.05")
TAX_RATE = Decimal("0.13")


def run_mock_pricing(part_feature: dict[str, Any], price_rules: list[PriceRule] | None = None) -> dict[str, Any]:
    process_route = recognize_process_route(part_feature)
    quantity_result = calculate_quantities(part_feature, process_route)
    quote_result = calculate_quote(part_feature, quantity_result, price_rules)
    return {
        "part_feature": part_feature,
        "process_route": process_route,
        "quantity_result": quantity_result,
        "quote_result": quote_result,
    }


def recognize_process_route(part_feature: dict[str, Any]) -> dict[str, Any]:
    task_id = part_feature["task_id"]
    risks = list(part_feature.get("risks", []))
    operations: dict[str, dict[str, Any]] = {}

    def add_operation(code: str, rule_code: str, message: str, confidence: float = 0.9, requires_review: bool = False, review_reason: str | None = None) -> None:
        reason = {"rule_code": rule_code, "message": message, "source": source_ref("rule", rule_code=rule_code)}
        existing = operations.get(code)
        if existing:
            existing["trigger_reasons"].append(reason)
            existing["confidence"] = min(existing["confidence"], confidence)
            existing["requires_review"] = existing["requires_review"] or requires_review
            if review_reason and not existing.get("review_reason"):
                existing["review_reason"] = review_reason
            return
        operation = {
            "operation_id": f"op_{code.lower()}",
            "operation_code": code,
            "operation_name": OPERATION_NAMES[code],
            "sequence": 0,
            "trigger_reasons": [reason],
            "confidence": confidence,
            "requires_review": requires_review,
            "explanation": message,
        }
        if review_reason:
            operation["review_reason"] = review_reason
        operations[code] = operation

    geometry = part_feature.get("geometry", {})
    part_type = geometry.get("part_type")
    requirements = part_feature.get("manufacturing_requirements", {})
    holes = part_feature.get("features", {}).get("holes", [])
    precision_requirements = part_feature.get("features", {}).get("precision_requirements", [])
    complexity = part_feature.get("features", {}).get("complexity", {})

    add_operation("MATERIAL_PREP", "PROC_BASE_PREP", "Every supported part needs material preparation.")
    add_operation("CUTTING", "PROC_BASE_CUTTING", "Every supported part needs rough stock cutting.")
    add_operation("INSPECTION", "PROC_BASE_INSPECTION", "Every quote needs inspection before confirmation.")
    add_operation("PACKAGING", "PROC_BASE_PACKAGING", "Every quote includes basic packaging.")

    if part_type in {"block", "small_irregular"}:
        add_operation("CNC", "PROC_GEOM_CNC", "Block or irregular parts need CNC machining.")
    if part_type in {"thin_plate", "plate"}:
        add_operation("WIRE_CUTTING", "PROC_GEOM_WIRE", "Plate or thin plate parts are wire-cutting candidates.")
    if part_type in {"shaft", "complex"}:
        risks.append(risk_item("HIGH_RISK_GEOMETRY", "blocking", "Unsupported geometry requires manual review.", "process_recognition", True, [source_ref("rule", rule_code="PROC_UNSUPPORTED_GEOMETRY")]))
        add_operation("MANUAL_REVIEW", "PROC_UNSUPPORTED_GEOMETRY", "Unsupported geometry is routed to manual review.", 0.5, True, "Unsupported geometry for automatic pricing.")

    for hole in holes:
        hole_type = hole.get("hole_type")
        count = int(hole.get("count", 0) or 0)
        confidence = float(hole.get("confidence", 0.8))
        review = confidence < 0.7
        if count <= 0:
            continue
        if hole_type in {"through", "blind"}:
            add_operation("DRILLING", "PROC_HOLE_DRILLING", "Common holes trigger drilling.", confidence, review)
        if hole_type in {"counterbore", "countersink"}:
            add_operation("COUNTERBORE", "PROC_HOLE_COUNTERBORE", "Counterbore holes trigger counterbore work.", confidence, review)
        if hole_type == "thread_candidate":
            add_operation("TAPPING", "PROC_HOLE_TAPPING", "Thread candidates trigger tapping.", confidence, review)
        if hole_type == "precision_candidate":
            add_operation("PRECISION_HOLE", "PROC_HOLE_PRECISION", "Precision hole candidates trigger precision hole work.", confidence, True, "Precision hole candidate needs confirmation.")

    if precision_requirements:
        add_operation("PRECISION_HOLE", "PROC_PRECISION_REQUIREMENT", "High precision requirements trigger precision hole review.", 0.75, True, "High precision requirement.")
        add_operation("GRINDING", "PROC_PRECISION_GRINDING", "High precision requirements may need grinding.", 0.7, True, "Grinding method needs confirmation.")
    if requirements.get("heat_treatment", {}).get("required"):
        add_operation("HEAT_TREATMENT", "PROC_HEAT_TREATMENT", "Heat treatment requirement found.")
    if requirements.get("surface_treatment", {}).get("required"):
        add_operation("CHEMICAL_PLATING", "PROC_SURFACE_TREATMENT", "Surface treatment requirement found.", 0.9, True, "Surface treatment must be confirmed.")
    if requirements.get("deburring", {}).get("required"):
        add_operation("DEBURRING", "PROC_DEBURRING", "Deburring requirement found.")
    if (complexity.get("complexity_score") or 0) >= 70:
        risks.append(risk_item("HIGH_RISK_GEOMETRY", "warning", "High geometry complexity requires process review.", "process_recognition", True, [source_ref("rule", rule_code="PROC_COMPLEXITY_SCORE")]))

    ordered = sorted(operations.values(), key=lambda item: OPERATION_ORDER[item["operation_code"]])
    for index, operation in enumerate(ordered, start=1):
        operation["sequence"] = index

    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "route_id": f"route_{task_id}",
        "operations": ordered,
        "requires_review": any_review(risks) or any(operation["requires_review"] for operation in ordered),
        "risks": risks,
    }


def calculate_quantities(part_feature: dict[str, Any], process_route: dict[str, Any]) -> dict[str, Any]:
    risks = list(process_route.get("risks", []))
    items: list[dict[str, Any]] = []
    geometry = part_feature.get("geometry", {})
    bbox = geometry.get("bounding_box", {})
    material = part_feature.get("material", {})
    features = part_feature.get("features", {})
    holes = features.get("holes", [])
    complexity = features.get("complexity", {})
    part_quantity = part_feature.get("part", {}).get("quantity", 1) or 1

    def add(operation_code: str, quantity_type: str, value: float | None, unit: str, formula: str, basis_items: list[dict[str, Any]], requires_review: bool = False, review_reason: str | None = None) -> None:
        item = {
            "quantity_id": f"qty_{operation_code.lower()}_{len(items) + 1}",
            "operation_code": operation_code,
            "quantity_type": quantity_type,
            "value": value,
            "unit": unit,
            "formula": formula,
            "basis": basis_items,
            "requires_review": requires_review,
        }
        if review_reason:
            item["review_reason"] = review_reason
        items.append(item)

    def basis(name: str, value: Any, unit: str | None, rule_code: str) -> dict[str, Any]:
        return {"name": name, "value": value, "unit": unit, "source": source_ref("rule", rule_code=rule_code)}

    def hole_count(*types: str) -> int:
        return sum(int(hole.get("count", 0) or 0) for hole in holes if hole.get("hole_type") in types)

    length, width, height = bbox.get("length"), bbox.get("width"), bbox.get("height")
    density = material.get("density")
    volume = geometry.get("volume", {}).get("value")
    surface_area = geometry.get("surface_area", {}).get("value")
    step_weight = geometry.get("step_net_weight", {}).get("value")
    complexity_score = complexity.get("complexity_score") or 0
    edge_count = complexity.get("edge_count") or 0

    for operation in process_route["operations"]:
        code = operation["operation_code"]
        if code == "MATERIAL_PREP":
            if None in (length, width, height, density):
                risks.append(risk_item("MISSING_QUANTITY_BASIS", "blocking", "Missing size or density for gross weight.", "quantity_calculation", True))
                add(code, "gross_weight", None, "kg", "length * width * height * density", [basis("length", length, "mm", "QTY_GROSS_WEIGHT")], True, "Missing size or density.")
            else:
                value = Decimal(str(length)) * Decimal(str(width)) * Decimal(str(height)) * Decimal(str(density))
                add(code, "gross_weight", q(value), "kg", "length_mm * width_mm * height_mm * density_kg_per_mm3", [basis("length", length, "mm", "QTY_GROSS_WEIGHT"), basis("width", width, "mm", "QTY_GROSS_WEIGHT"), basis("height", height, "mm", "QTY_GROSS_WEIGHT"), basis("density", density, material.get("density_unit"), "QTY_GROSS_WEIGHT")])
        elif code == "WIRE_CUTTING":
            if None in (length, width, height):
                risks.append(risk_item("MISSING_QUANTITY_BASIS", "blocking", "Missing size for wire cutting.", "quantity_calculation", True))
                add(code, "cut_area", None, "mm2", "2 * (length + width) * height", [basis("length", length, "mm", "QTY_WIRE_AREA")], True, "Missing size.")
            else:
                value = Decimal("2") * (Decimal(str(length)) + Decimal(str(width))) * Decimal(str(height))
                add(code, "cut_area", q(value), "mm2", "2 * (length_mm + width_mm) * height_mm", [basis("length", length, "mm", "QTY_WIRE_AREA"), basis("width", width, "mm", "QTY_WIRE_AREA"), basis("height", height, "mm", "QTY_WIRE_AREA")])
        elif code == "CNC":
            if volume is None:
                risks.append(risk_item("MISSING_QUANTITY_BASIS", "blocking", "Missing volume for CNC estimate.", "quantity_calculation", True))
                add(code, "estimated_hours", None, "hour", "max(0.5, volume / 50000 + complexity_score / 50)", [basis("volume", volume, "mm3", "QTY_CNC_HOURS")], True, "Missing volume.")
            else:
                value = max(Decimal("0.5"), Decimal(str(volume)) / Decimal("50000") + Decimal(str(complexity_score)) / Decimal("50"))
                add(code, "estimated_hours", q(value), "hour", "max(0.5, volume_mm3 / 50000 + complexity_score / 50)", [basis("volume", volume, "mm3", "QTY_CNC_HOURS"), basis("complexity_score", complexity_score, null_unit(), "QTY_CNC_HOURS")])
        elif code == "DRILLING":
            add(code, "hole_count", float(hole_count("through", "blind")), "pcs", "count(through holes + blind holes)", [basis("hole_count", hole_count("through", "blind"), "pcs", "QTY_DRILLING_COUNT")])
        elif code == "COUNTERBORE":
            add(code, "counterbore_count", float(hole_count("counterbore", "countersink")), "pcs", "count(counterbore holes + countersink holes)", [basis("counterbore_count", hole_count("counterbore", "countersink"), "pcs", "QTY_COUNTERBORE_COUNT")])
        elif code == "TAPPING":
            add(code, "thread_count", float(hole_count("thread_candidate")), "pcs", "count(thread candidate holes)", [basis("thread_count", hole_count("thread_candidate"), "pcs", "QTY_TAPPING_COUNT")])
        elif code == "PRECISION_HOLE":
            add(code, "precision_hole_count", float(hole_count("precision_candidate")), "pcs", "count(precision candidate holes)", [basis("precision_hole_count", hole_count("precision_candidate"), "pcs", "QTY_PRECISION_HOLE_COUNT")], True, "Precision hole count must be confirmed.")
        elif code == "GRINDING":
            if surface_area is None:
                risks.append(risk_item("MISSING_QUANTITY_BASIS", "warning", "Missing surface area for grinding.", "quantity_calculation", True))
                add(code, "grinding_area", None, "mm2", "surface_area * 0.25", [basis("surface_area", surface_area, "mm2", "QTY_GRINDING_AREA")], True, "Missing surface area.")
            else:
                add(code, "grinding_area", q(Decimal(str(surface_area)) * Decimal("0.25")), "mm2", "surface_area_mm2 * 0.25", [basis("surface_area", surface_area, "mm2", "QTY_GRINDING_AREA")], True, "Grinding area estimate must be confirmed.")
        elif code == "HEAT_TREATMENT":
            add(code, "heat_weight", q(step_weight) if step_weight is not None else None, "kg", "step_net_weight", [basis("step_net_weight", step_weight, "kg", "QTY_HEAT_WEIGHT")], step_weight is None, "Missing weight." if step_weight is None else None)
        elif code == "CHEMICAL_PLATING":
            add(code, "surface_area", q(surface_area) if surface_area is not None else None, "mm2", "surface_area", [basis("surface_area", surface_area, "mm2", "QTY_SURFACE_AREA")], True, "Surface treatment must be confirmed.")
        elif code == "DEBURRING":
            value = Decimal(str(part_quantity)) + Decimal(str(edge_count)) / Decimal("100")
            add(code, "deburr_complexity", q(value), "score", "part_quantity + edge_count / 100", [basis("part_quantity", part_quantity, "pcs", "QTY_DEBURR_COMPLEXITY"), basis("edge_count", edge_count, null_unit(), "QTY_DEBURR_COMPLEXITY")])
        elif code in {"INSPECTION", "PACKAGING"}:
            add(code, "inspection_count", float(part_quantity), "pcs", "part_quantity", [basis("part_quantity", part_quantity, "pcs", "QTY_COUNT")])
        elif code == "CUTTING":
            add(code, "manual_quantity", float(part_quantity), "pcs", "part_quantity", [basis("part_quantity", part_quantity, "pcs", "QTY_CUTTING_COUNT")])

    return {"schema_version": SCHEMA_VERSION, "task_id": part_feature["task_id"], "route_id": process_route["route_id"], "items": items, "risks": risks}


def calculate_quote(part_feature: dict[str, Any], quantity_result: dict[str, Any], price_rules: list[PriceRule] | None = None) -> dict[str, Any]:
    risks = list(quantity_result.get("risks", []))
    items: list[dict[str, Any]] = []
    material_amount = Decimal("0")
    process_amount = Decimal("0")
    surface_amount = Decimal("0")
    risk_amount = Decimal("0")
    material_code = part_feature.get("material", {}).get("standard_code")

    for quantity_item in quantity_result["items"]:
        quote_item, quote_risks = quote_item_from_quantity(quantity_item, material_code, price_rules)
        risks.extend(quote_risks)
        items.append(quote_item)
        if quote_item["amount"] is None:
            continue
        amount = Decimal(str(quote_item["amount"]))
        if quote_item["item_type"] == "material":
            material_amount += amount
        elif quote_item["item_type"] == "surface_treatment":
            surface_amount += amount
        else:
            process_amount += amount

    if any(risk.get("code") == "HIGH_PRECISION_REQUIREMENT" for risk in part_feature.get("risks", [])):
        risk_rule = find_active_price_rule("risk_surcharge", "HIGH_PRECISION_REQUIREMENT", price_rules, unit="risk")
        if risk_rule is None:
            risks.append(risk_item("MISSING_PRICE", "blocking", "Missing high precision risk surcharge rule.", "quote_calculation", True, [source_ref("price_rule", rule_code="risk_high_precision")]))
            surcharge = None
        else:
            surcharge = risk_rule.unit_price
            risk_amount += surcharge
        items.append(make_quote_item(f"item_{len(items) + 1}", "risk_surcharge", None, 1, "risk", risk_rule.unit_price if risk_rule else None, surcharge, "fixed high precision surcharge", "High precision requirement adds a mock review surcharge.", price_source_from_rule(risk_rule), True))

    subtotal = material_amount + process_amount + surface_amount + risk_amount
    management_fee = material_amount * MANAGEMENT_FEE_RATE
    tax_amount = (subtotal + management_fee) * TAX_RATE
    system_calculated = subtotal + management_fee + tax_amount
    system_initial_quote = system_calculated.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    all_risks = list(part_feature.get("risks", [])) + risks

    items.append(make_quote_item(f"item_{len(items) + 1}", "management_fee", None, m(material_amount), "CNY", MANAGEMENT_FEE_RATE, management_fee, "material_amount * management_fee_rate", "Management fee is calculated from material amount.", price_source("manual", "mock_parameters", "management_fee_rate", PRICE_VERSION)))
    items.append(make_quote_item(f"item_{len(items) + 1}", "tax", None, m(subtotal + management_fee), "CNY", TAX_RATE, tax_amount, "tax_base * tax_rate", "Tax is calculated from subtotal plus management fee.", price_source("manual", "mock_parameters", "tax_rate", PRICE_VERSION)))

    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": part_feature["task_id"],
        "quote_id": f"quote_{part_feature['task_id']}",
        "status": "pending_review" if any_review(all_risks) or any(item.get("requires_review") for item in items) else "priced",
        "currency": "CNY",
        "price_version": PRICE_VERSION,
        "priced_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "confirmed_at": None,
        "confirmed_by": None,
        "items": items,
        "summary": {
            "material_amount": m(material_amount),
            "process_amount": m(process_amount),
            "surface_treatment_amount": m(surface_amount),
            "management_fee": m(management_fee),
            "tax_amount": m(tax_amount),
            "risk_surcharge_amount": m(risk_amount),
            "system_calculated_amount": m(system_calculated),
            "system_initial_quote": m(system_initial_quote),
            "manual_adjustment_amount": 0.0,
            "final_confirmed_amount": None,
        },
        "risks": all_risks,
        "manual_overrides": [],
    }


def apply_manual_override(quote_result: dict[str, Any], *, target_type: str, target_id: str, field: str, new_value: Any, reason: str, operator_id: str) -> dict[str, Any]:
    if not reason:
        raise ValueError("Manual override reason is required.")
    old_value = None
    if target_type == "quote_item":
        for item in quote_result["items"]:
            if item["item_id"] == target_id:
                old_value = item.get(field)
                item[field] = m(new_value) if field in {"amount", "final_amount", "unit_price"} and new_value is not None else new_value
                break
        else:
            raise ValueError(f"Unknown quote item: {target_id}")
    elif target_type == "quote_summary":
        old_value = quote_result["summary"].get(field)
        quote_result["summary"][field] = m(new_value) if new_value is not None else None
    else:
        raise ValueError(f"Unsupported manual override target type: {target_type}")
    quote_result["manual_overrides"].append({"override_id": f"override_{len(quote_result['manual_overrides']) + 1}", "target_type": target_type, "target_id": target_id, "field": field, "old_value": old_value, "new_value": new_value, "reason": reason, "operator_id": operator_id, "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()})
    quote_result["status"] = "pending_review"
    return quote_result


def confirm_risk(quote_result: dict[str, Any], *, risk_code: str, reason: str, operator_id: str) -> dict[str, Any]:
    if not reason:
        raise ValueError("Risk confirmation reason is required.")
    matched = False
    for risk in quote_result["risks"]:
        if risk["code"] == risk_code and risk.get("requires_review"):
            matched = True
            risk["requires_review"] = False
    if not matched:
        raise ValueError(f"No reviewable risk found for code: {risk_code}")
    quote_result["manual_overrides"].append(
        {
            "override_id": f"override_{len(quote_result['manual_overrides']) + 1}",
            "target_type": "risk",
            "target_id": risk_code,
            "field": "requires_review",
            "old_value": True,
            "new_value": False,
            "reason": reason,
            "operator_id": operator_id,
            "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
    )
    quote_result["status"] = "pending_review" if quote_requires_review(quote_result) else "priced"
    return quote_result


def confirm_quote(quote_result: dict[str, Any], *, confirmed_by: str, confirmed_total_amount: float | int | Decimal | None = None, confirm_note: str = "") -> dict[str, Any]:
    if quote_has_blocking_review_risk(quote_result):
        raise ValueError("Cannot confirm quote while blocking risks still require review.")
    if quote_requires_review(quote_result):
        raise ValueError("Cannot confirm quote while review items remain unresolved.")
    final_amount = confirmed_total_amount if confirmed_total_amount is not None else quote_result["summary"]["system_initial_quote"]
    quote_result["summary"]["final_confirmed_amount"] = m(final_amount)
    quote_result["summary"]["manual_adjustment_amount"] = m(Decimal(str(final_amount)) - Decimal(str(quote_result["summary"]["system_initial_quote"])))
    quote_result["confirmed_by"] = confirmed_by
    quote_result["confirmed_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    quote_result["status"] = "confirmed"
    if confirm_note:
        quote_result["manual_overrides"].append(
            {
                "override_id": f"override_{len(quote_result['manual_overrides']) + 1}",
                "target_type": "quote_summary",
                "target_id": quote_result["quote_id"],
                "field": "final_confirmed_amount",
                "old_value": None,
                "new_value": m(final_amount),
                "reason": confirm_note,
                "operator_id": confirmed_by,
                "created_at": quote_result["confirmed_at"],
            }
        )
    return quote_result


def quote_item_from_quantity(quantity_item: dict[str, Any], material_code: str | None, price_rules: list[PriceRule] | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    code = quantity_item["operation_code"]
    if code == "MATERIAL_PREP":
        item_type = "material"
        target_code = material_code or ""
    else:
        item_type = item_type_for_operation(code)
        target_code = code
    rule = find_active_price_rule(item_type, target_code, price_rules, unit=quantity_item["unit"])
    unit_price = rule.unit_price if rule else None

    risks: list[dict[str, Any]] = []
    requires_review = bool(quantity_item.get("requires_review"))
    if unit_price is None:
        risks.append(risk_item("MISSING_PRICE", "blocking", f"Missing approved price rule for {code}.", "quote_calculation", True, [source_ref("price_rule", rule_code=f"{item_type}_{target_code}")]))
        amount = None
        requires_review = True
    elif quantity_item["value"] is None:
        amount = None
        requires_review = True
    else:
        amount = Decimal(str(quantity_item["value"])) * unit_price
        if rule and rule.setup_fee:
            amount += rule.setup_fee
        if rule and rule.min_amount is not None and amount < rule.min_amount:
            amount = rule.min_amount

    return make_quote_item(f"item_{code.lower()}", item_type, code, quantity_item["value"], quantity_item["unit"], unit_price, amount, f"{quantity_item['quantity_type']} * unit_price", f"Mock pricing for {code} based on {quantity_item['quantity_type']}.", price_source_from_rule(rule), requires_review), risks


def make_quote_item(item_id: str, item_type: str, operation_code: str | None, qty_value: Any, unit: str | None, unit_price: Decimal | None, amount: Decimal | None, formula: str, explanation: str, price_source_value: dict[str, Any], requires_review: bool = False) -> dict[str, Any]:
    amount_value = m(amount) if amount is not None else None
    return {"item_id": item_id, "item_type": item_type, "operation_code": operation_code, "quantity": qty_value, "unit": unit, "unit_price": m(unit_price) if unit_price is not None else None, "amount": amount_value, "price_source": price_source_value, "formula": formula, "explanation": explanation, "system_amount": amount_value, "final_amount": amount_value, "requires_review": requires_review}


def source_ref(source_type: str, *, rule_code: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {"source_type": source_type}
    if rule_code is not None:
        value["rule_code"] = rule_code
    return value


def risk_item(code: str, level: str, message: str, source: str, requires_review: bool, evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"code": code, "level": level, "message": message, "source": source, "requires_review": requires_review, "evidence": evidence or [source_ref("system")]}


def price_source(source_type: str | None, source_id: str | None, rule_id: str | None, version: str | None) -> dict[str, Any]:
    return {"source_type": source_type, "source_id": source_id, "rule_id": rule_id, "version": version}


def price_source_from_rule(rule: PriceRule | None) -> dict[str, Any]:
    if rule is None:
        return price_source(None, None, None, None)
    return price_source(rule.source_type, rule.source_id, rule.rule_id, rule.version)


def any_review(risks: list[dict[str, Any]]) -> bool:
    return any(risk.get("requires_review") for risk in risks)


def quote_has_blocking_review_risk(quote_result: dict[str, Any]) -> bool:
    return any(risk.get("level") == "blocking" and risk.get("requires_review") for risk in quote_result["risks"])


def quote_requires_review(quote_result: dict[str, Any]) -> bool:
    return any_review(quote_result["risks"]) or any(item.get("requires_review") for item in quote_result["items"])


def q(value: Any) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def m(value: Any) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def null_unit() -> None:
    return None
