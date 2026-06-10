from __future__ import annotations

from typing import Any


def source_ref(
    source_type: str,
    *,
    file_id: str | None = None,
    page: int | None = None,
    location: str | None = None,
    raw_text: str | None = None,
    rule_code: str | None = None,
) -> dict[str, Any]:
    return {
        "source_type": source_type,
        "file_id": file_id,
        "page": page,
        "location": location,
        "raw_text": raw_text,
        "rule_code": rule_code,
    }


def risk_item(
    code: str,
    level: str,
    message: str,
    source: str,
    requires_review: bool,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "code": code,
        "level": level,
        "message": message,
        "source": source,
        "requires_review": requires_review,
        "evidence": evidence,
    }


def build_part_feature(
    task: dict[str, Any],
    pdf_result: dict[str, Any] | None,
    step_result: dict[str, Any] | None,
    risks: list[dict[str, Any]],
) -> dict[str, Any]:
    pdf_file_id = pdf_result["file_id"] if pdf_result else None
    step_file_id = step_result["file_id"] if step_result else None

    pdf_source = source_ref("pdf", file_id=pdf_file_id)
    step_source = source_ref("step", file_id=step_file_id)
    system_source = source_ref("system", rule_code="PART_FEATURE_FUSION")
    material_raw = pdf_result.get("material_raw") if pdf_result else None
    surface_raw = pdf_result.get("surface_treatment_raw") if pdf_result else None
    heat_raw = pdf_result.get("heat_treatment_raw") if pdf_result else None
    pdf_part_category = build_pdf_part_category(pdf_result)
    pdf_part_type = normalize_pdf_part_type(
        pdf_result.get("part_type_raw") if pdf_result else None
    )
    part_type_candidates = build_part_type_candidates(
        pdf_result=pdf_result,
        step_result=step_result,
        pdf_part_type=pdf_part_type,
    )
    material_standard_code = None
    surface_standard_code = None
    net_weight = step_result.get("net_weight") if step_result else {}
    material_density = net_weight.get("density") if isinstance(net_weight, dict) else None
    material_density_unit = (
        net_weight.get("density_unit") if isinstance(net_weight, dict) else None
    )
    material_source = field_source(
        pdf_result,
        "material_raw",
        pdf_file_id=pdf_file_id,
        raw_text=material_raw,
        fallback=system_source,
    )
    surface_source = field_source(
        pdf_result,
        "surface_treatment_raw",
        pdf_file_id=pdf_file_id,
        raw_text=surface_raw,
        fallback=system_source,
    )
    heat_source = field_source(
        pdf_result,
        "heat_treatment_raw",
        pdf_file_id=pdf_file_id,
        raw_text=heat_raw,
        fallback=system_source,
    )

    if pdf_result:
        risks.extend(pdf_result.get("risks", []))
    if step_result:
        risks.extend(step_result.get("geometry_risks", []))
    add_fusion_risks(
        risks,
        pdf_result=pdf_result,
        step_result=step_result,
        part_type_candidates=part_type_candidates,
        pdf_part_category=pdf_part_category,
    )
    holes = build_hole_features(pdf_result, step_result, risks)

    return {
        "schema_version": "1.0",
        "task_id": task["task_id"],
        "part": {
            "part_name": pdf_result["part_name"] if pdf_result else task["part_name"],
            "drawing_no": pdf_result["drawing_no"] if pdf_result else task["part_no"],
            "revision": pdf_result["revision"] if pdf_result else None,
            "quantity": task["quantity"],
        },
        "material": {
            "raw_text": material_raw,
            "standard_code": material_standard_code,
            "standard_name": None,
            "density": material_density,
            "density_unit": material_density_unit,
            "confidence": pdf_field_confidence(pdf_result, "material_raw"),
            "source": material_source,
        },
        "geometry": {
            "bounding_box": (
                step_result["bounding_box"]
                if step_result
                else {"length": None, "width": None, "height": None, "unit": "mm"}
            ),
            "volume": (
                step_result["volume"]
                if step_result
                else {"value": None, "unit": "mm3", "source": system_source}
            ),
            "surface_area": (
                step_result["surface_area"]
                if step_result
                else {"value": None, "unit": "mm2", "source": system_source}
            ),
            "profile_summary": (
                step_result.get("profile_summary") or {}
                if step_result
                else {}
            ),
            "pdf_weight": {
                "value": pdf_result["weight_value"] if pdf_result else None,
                "unit": pdf_result["weight_unit"] if pdf_result else None,
                "source": (
                    pdf_result["field_evidence"]["weight_raw"]
                    if pdf_result
                    else system_source
                ),
            },
            "step_net_weight": {
                "value": step_result["net_weight"]["value"] if step_result else None,
                "unit": step_result["net_weight"]["unit"] if step_result else None,
                "source": step_result["net_weight"]["source"] if step_result else system_source,
            },
            "part_type": (
                part_type_candidates[0]["part_type"]
                if part_type_candidates
                else None
            ),
            "part_type_confidence": (
                part_type_candidates[0]["confidence"]
                if part_type_candidates
                else 0
            ),
            "part_type_candidates": part_type_candidates,
            "pdf_part_category": pdf_part_category,
        },
        "features": {
            "holes": holes,
            "slots": step_result.get("slots", []) if step_result else [],
            "precision_requirements": build_precision_requirements(pdf_result),
            "complexity": (
                step_result["complexity"]
                if step_result
                else {
                    "face_count": None,
                    "edge_count": None,
                    "small_radius_count": None,
                    "slot_count": None,
                    "thin_wall_candidate": False,
                    "complexity_score": None,
                }
            ),
        },
        "manufacturing_requirements": {
            "heat_treatment": requirement_item(
                bool(heat_raw),
                heat_raw,
                None,
                pdf_field_confidence(pdf_result, "heat_treatment_raw"),
                heat_source,
            ),
            "surface_treatment": requirement_item(
                bool(surface_raw),
                surface_raw,
                surface_standard_code,
                pdf_field_confidence(pdf_result, "surface_treatment_raw"),
                surface_source,
            ),
            "deburring": build_deburring_requirement(pdf_result, system_source),
            "technical_requirements": build_technical_requirements(pdf_result),
            "technical_requirement_details": build_technical_requirement_details(
                pdf_result
            ),
            "inspection": requirement_item(
                True,
                "Standard inspection.",
                "STANDARD_INSPECTION",
                0.7,
                source_ref("system", rule_code="DEFAULT_STANDARD_INSPECTION"),
            ),
            "packaging": requirement_item(False, None, None, 0, system_source),
        },
        "risks": risks,
        "evidence": [item for item in [pdf_source, step_source] if item["file_id"]],
    }


def requirement_item(
    required: bool,
    raw_text: str | None,
    standard_code: str | None,
    confidence: float,
    source: dict[str, Any],
) -> dict[str, Any]:
    return {
        "required": required,
        "raw_text": raw_text,
        "standard_code": standard_code,
        "confidence": confidence,
        "source": source,
    }


def first_available(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def lookup_material(raw_text: str | None) -> dict[str, Any] | None:
    if not raw_text:
        return None
    normalized = normalize_dictionary_key(raw_text)
    return MATERIAL_DICTIONARY.get(normalized)


def lookup_surface_treatment(raw_text: str | None) -> dict[str, Any] | None:
    if not raw_text:
        return None
    normalized = normalize_dictionary_key(raw_text)
    return SURFACE_TREATMENT_DICTIONARY.get(normalized)


def normalize_dictionary_key(raw_text: str) -> str:
    return (
        raw_text.strip()
        .lower()
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
        .replace("/", "")
    )


PDF_PART_CATEGORY_RULES = (
    {
        "category_name": "方件类",
        "aliases": ("方件类",),
        "compatible_part_types": ("thin_plate", "plate", "block"),
        "dimension_rule": "单方向长度 <= 500mm",
    },
    {
        "category_name": "大板类",
        "aliases": ("大板类",),
        "compatible_part_types": ("thin_plate", "plate"),
        "dimension_rule": "单方向长度 > 500mm",
    },
    {
        "category_name": "圆件类",
        "aliases": ("圆件类",),
        "compatible_part_types": ("shaft",),
        "dimension_rule": None,
    },
    {
        "category_name": "钣金类",
        "aliases": ("钣金类",),
        "compatible_part_types": ("thin_plate", "plate", "complex"),
        "dimension_rule": None,
    },
    {
        "category_name": "型材类",
        "aliases": ("型材类",),
        "compatible_part_types": ("complex",),
        "dimension_rule": None,
    },
    {
        "category_name": "拼组类",
        "aliases": ("拼组类",),
        "compatible_part_types": ("complex",),
        "dimension_rule": None,
    },
    {
        "category_name": "焊接类",
        "aliases": ("焊接类",),
        "compatible_part_types": ("complex",),
        "dimension_rule": None,
    },
)


def build_pdf_part_category(
    pdf_result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    raw_text = (pdf_result or {}).get("part_type_raw")
    if not raw_text:
        return None

    normalized = normalize_dictionary_key(str(raw_text))
    for rule in PDF_PART_CATEGORY_RULES:
        if not any(
            normalize_dictionary_key(alias) in normalized
            for alias in rule["aliases"]
        ):
            continue
        return {
            "category_name": rule["category_name"],
            "raw_text": str(raw_text),
            "compatible_part_types": list(rule["compatible_part_types"]),
            "dimension_rule": rule["dimension_rule"],
            "confidence": pdf_field_confidence(pdf_result, "part_type_raw"),
            "source": field_source(
                pdf_result,
                "part_type_raw",
                pdf_file_id=(pdf_result or {}).get("file_id"),
                raw_text=raw_text,
                fallback=source_ref("system", rule_code="PDF_PART_CATEGORY_MISSING"),
            ),
        }
    return None


def normalize_pdf_part_type(raw_text: str | None) -> str | None:
    if not raw_text:
        return None
    normalized = normalize_dictionary_key(raw_text)
    mappings = (
        ("thin_plate", ("薄片", "薄板")),
        ("plate", ("板件", "板状")),
        ("block", ("块件", "方块", "块类", "block")),
        ("shaft", ("轴类", "轴件", "shaft")),
        ("complex", ("复杂", "异形复杂", "complex")),
        ("small_irregular", ("异形", "小件", "irregular")),
    )
    for part_type, aliases in mappings:
        if any(normalize_dictionary_key(alias) in normalized for alias in aliases):
            return part_type
    return None


PART_TYPE_VALUES = {
    "thin_plate",
    "plate",
    "block",
    "small_irregular",
    "shaft",
    "complex",
}


def build_part_type_candidates(
    *,
    pdf_result: dict[str, Any] | None,
    step_result: dict[str, Any] | None,
    pdf_part_type: str | None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    step_file_id = step_result.get("file_id") if step_result else None
    for candidate in ((step_result or {}).get("part_type_candidates") or []):
        if not isinstance(candidate, dict):
            continue
        part_type = candidate.get("part_type")
        if part_type not in PART_TYPE_VALUES:
            continue
        reason = candidate.get("reason")
        source = candidate.get("source")
        if not isinstance(source, dict):
            source = source_ref(
                "step",
                file_id=step_file_id,
                raw_text=str(reason) if reason else None,
                rule_code="STEP_PART_TYPE_CANDIDATE",
            )
        candidates.append(
            {
                "part_type": part_type,
                "confidence": clamp_confidence(
                    float(candidate.get("confidence") or 0)
                ),
                "reason": str(reason) if reason else None,
                "source": source,
            }
        )

    if pdf_part_type in PART_TYPE_VALUES:
        raw_text = (pdf_result or {}).get("part_type_raw")
        candidates.append(
            {
                "part_type": pdf_part_type,
                "confidence": pdf_field_confidence(pdf_result, "part_type_raw"),
                "reason": str(raw_text) if raw_text else None,
                "source": field_source(
                    pdf_result,
                    "part_type_raw",
                    pdf_file_id=(pdf_result or {}).get("file_id"),
                    raw_text=raw_text,
                    fallback=source_ref("system", rule_code="PDF_PART_TYPE_MISSING"),
                ),
            }
        )

    return candidates


def top_part_type_candidate(
    candidates: list[dict[str, Any]],
    source_type: str,
) -> dict[str, Any] | None:
    for candidate in candidates:
        source = candidate.get("source") or {}
        if source.get("source_type") == source_type:
            return candidate
    return None


def material_confidence(
    pdf_result: dict[str, Any] | None,
    dictionary_match: dict[str, Any] | None,
) -> float:
    if dictionary_match:
        return clamp_confidence(float(dictionary_match["confidence"]))
    return pdf_field_confidence(pdf_result, "material_raw")


def surface_confidence(
    pdf_result: dict[str, Any] | None,
    dictionary_match: dict[str, Any] | None,
) -> float:
    if dictionary_match:
        return clamp_confidence(float(dictionary_match["confidence"]))
    return pdf_field_confidence(pdf_result, "surface_treatment_raw")


def field_source(
    pdf_result: dict[str, Any] | None,
    field_key: str,
    *,
    pdf_file_id: str | None,
    raw_text: str | None,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    if not pdf_result:
        return fallback
    evidence = (pdf_result.get("field_evidence") or {}).get(field_key)
    if evidence:
        return evidence
    return source_ref(
        "pdf",
        file_id=pdf_file_id,
        raw_text=raw_text,
        rule_code=f"PDF_FIELD:{field_key}",
    )


def pdf_field_confidence(
    pdf_result: dict[str, Any] | None,
    field_key: str,
) -> float:
    if not pdf_result:
        return 0
    confidence = (pdf_result.get("field_confidence") or {}).get(field_key)
    if isinstance(confidence, (int, float)):
        return clamp_confidence(float(confidence))
    return 0.6 if pdf_result.get(field_key) else 0


def clamp_confidence(value: float) -> float:
    if value < 0:
        return 0
    if value > 1:
        return 1
    return value


HOLE_FEATURE_KEYS = {
    "hole_type",
    "diameter",
    "depth",
    "through",
    "counterbore_diameter",
    "counterbore_depth",
    "countersink_diameter",
    "countersink_depth",
    "countersink_angle",
    "count",
    "confidence",
    "evidence",
}
PDF_SUPPLEMENTAL_HOLE_TYPES = {"thread_candidate", "precision_candidate"}


def build_hole_features(
    pdf_result: dict[str, Any] | None,
    step_result: dict[str, Any] | None,
    risks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    step_holes = [
        hole_feature_payload(hole)
        for hole in ((step_result or {}).get("holes") or [])
        if isinstance(hole, dict)
    ]
    annotations = [
        annotation
        for annotation in ((pdf_result or {}).get("hole_annotations") or [])
        if isinstance(annotation, dict)
    ]
    if not annotations:
        return step_holes
    if not step_holes:
        for annotation in annotations:
            add_pdf_only_hole_risk(risks, annotation, step_result)
        return [hole_from_pdf_annotation(annotation) for annotation in annotations]

    remaining_step_holes = [dict(hole) for hole in step_holes]
    fused_holes: list[dict[str, Any]] = []
    for annotation in annotations:
        validate_pdf_hole_depth(risks, annotation, step_result)
        match_index = find_step_hole_match(annotation, remaining_step_holes)
        if annotation.get("hole_type") in PDF_SUPPLEMENTAL_HOLE_TYPES:
            matched_step = (
                remaining_step_holes[match_index]
                if match_index is not None
                else None
            )
            if matched_step is None:
                nearest_step = nearest_step_hole_by_diameter(
                    annotation,
                    remaining_step_holes,
                )
                if nearest_step:
                    add_hole_dimension_mismatch_risk(
                        risks,
                        annotation,
                        nearest_step,
                        step_result,
                    )
                add_pdf_only_hole_risk(risks, annotation, step_result)
            else:
                validate_pdf_step_hole_match(
                    risks,
                    annotation,
                    matched_step,
                    step_result,
                )
            fused_holes.append(hole_from_pdf_annotation(annotation, matched_step))
            continue

        if match_index is None:
            nearest_step = nearest_step_hole_by_diameter(annotation, remaining_step_holes)
            if nearest_step:
                add_hole_dimension_mismatch_risk(
                    risks,
                    annotation,
                    nearest_step,
                    step_result,
                )
            add_pdf_only_hole_risk(risks, annotation, step_result)
            fused_holes.append(hole_from_pdf_annotation(annotation))
            continue

        matched_step = remaining_step_holes[match_index]
        validate_pdf_step_hole_match(risks, annotation, matched_step, step_result)
        annotation_count = int(annotation.get("count") or 1)
        matched_count = int(matched_step.get("count") or 0)
        if matched_count < annotation_count:
            add_hole_count_mismatch_risk(
                risks,
                annotation,
                matched_step,
                step_result,
            )
        consume_count = min(annotation_count, max(matched_count, 0))
        fused_holes.append(hole_from_pdf_annotation(annotation, matched_step))
        if matched_count > consume_count:
            remaining_step_holes[match_index]["count"] = matched_count - consume_count
        else:
            remaining_step_holes.pop(match_index)

    return fused_holes + remaining_step_holes


def hole_feature_payload(hole: dict[str, Any]) -> dict[str, Any]:
    payload = {
        key: value
        for key, value in hole.items()
        if key in HOLE_FEATURE_KEYS and value is not None
    }
    payload.setdefault("hole_type", "through")
    payload.setdefault("count", 0)
    payload.setdefault("confidence", 0.0)
    payload.setdefault("evidence", [])
    return payload


def hole_from_pdf_annotation(
    annotation: dict[str, Any],
    matched_step: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = hole_feature_payload(matched_step or {})
    payload["hole_type"] = str(annotation.get("hole_type") or payload.get("hole_type") or "through")
    payload["diameter"] = number_or_none(annotation.get("diameter")) or number_or_none(payload.get("diameter"))
    if annotation.get("through") is True:
        payload["through"] = True
        payload["depth"] = None
    elif annotation.get("depth") is not None:
        payload["through"] = False
        payload["depth"] = number_or_none(annotation.get("depth"))
    payload["count"] = int(annotation.get("count") or payload.get("count") or 1)
    for optional_key in (
        "counterbore_diameter",
        "counterbore_depth",
        "countersink_diameter",
        "countersink_depth",
        "countersink_angle",
    ):
        value = number_or_none(annotation.get(optional_key))
        if value is not None:
            payload[optional_key] = value
    annotation_confidence = float(annotation.get("confidence") or 0.72)
    step_confidence = float((matched_step or {}).get("confidence") or 0)
    payload["confidence"] = clamp_confidence(
        max(annotation_confidence, step_confidence)
        if matched_step
        else min(annotation_confidence, 0.78)
    )
    payload["evidence"] = combined_hole_evidence(annotation, matched_step)
    return {key: value for key, value in payload.items() if key in HOLE_FEATURE_KEYS}


def combined_hole_evidence(
    annotation: dict[str, Any],
    matched_step: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for item in (matched_step or {}).get("evidence") or []:
        if isinstance(item, dict):
            evidence.append(item)
    for item in annotation.get("evidence") or []:
        if isinstance(item, dict):
            evidence.append(item)
    if not evidence:
        evidence.append(source_ref("pdf", raw_text=annotation.get("raw_text")))
    return evidence


def find_step_hole_match(
    annotation: dict[str, Any],
    step_holes: list[dict[str, Any]],
) -> int | None:
    best_index = None
    best_score = -1
    for index, step_hole in enumerate(step_holes):
        score = hole_match_score(annotation, step_hole)
        if score > best_score:
            best_index = index
            best_score = score
    return best_index if best_score >= 2 else None


def hole_match_score(annotation: dict[str, Any], step_hole: dict[str, Any]) -> int:
    score = 0
    if hole_diameters_match(annotation, step_hole):
        score += 2
    else:
        return -1
    annotation_type = annotation.get("hole_type")
    step_type = step_hole.get("hole_type")
    if annotation_type == step_type:
        score += 2
    elif annotation_type in {"counterbore", "countersink"} and step_type in {"through", "blind"}:
        score += 1
    elif annotation_type in PDF_SUPPLEMENTAL_HOLE_TYPES:
        score += 1
    if optional_hole_dimension_matches(annotation, step_hole, "counterbore_diameter"):
        score += 1
    if optional_hole_dimension_matches(annotation, step_hole, "counterbore_depth"):
        score += 1
    if optional_hole_dimension_matches(annotation, step_hole, "countersink_diameter"):
        score += 1
    if optional_hole_dimension_matches(annotation, step_hole, "countersink_depth"):
        score += 1
    return score


def hole_diameters_match(annotation: dict[str, Any], step_hole: dict[str, Any]) -> bool:
    annotation_diameter = number_or_none(annotation.get("diameter"))
    step_diameter = number_or_none(step_hole.get("diameter"))
    if annotation_diameter is None or step_diameter is None:
        return False
    return abs(annotation_diameter - step_diameter) <= 0.25


def optional_hole_dimension_matches(
    annotation: dict[str, Any],
    step_hole: dict[str, Any],
    key: str,
) -> bool:
    annotation_value = number_or_none(annotation.get(key))
    step_value = number_or_none(step_hole.get(key))
    if annotation_value is None or step_value is None:
        return False
    return abs(annotation_value - step_value) <= 0.25


HOLE_DIMENSION_LABELS = {
    "diameter": "直径",
    "depth": "深度",
    "counterbore_diameter": "沉孔直径",
    "counterbore_depth": "沉孔深度",
    "countersink_diameter": "沉头直径",
    "countersink_depth": "沉头深度",
    "countersink_angle": "沉头角度",
}


def nearest_step_hole_by_diameter(
    annotation: dict[str, Any],
    step_holes: list[dict[str, Any]],
) -> dict[str, Any] | None:
    annotation_diameter = number_or_none(annotation.get("diameter"))
    if annotation_diameter is None:
        return None

    nearest = None
    nearest_delta = None
    for step_hole in step_holes:
        step_diameter = number_or_none(step_hole.get("diameter"))
        if step_diameter is None:
            continue
        delta = abs(annotation_diameter - step_diameter)
        if nearest_delta is None or delta < nearest_delta:
            nearest = step_hole
            nearest_delta = delta
    return nearest


def validate_pdf_step_hole_match(
    risks: list[dict[str, Any]],
    annotation: dict[str, Any],
    step_hole: dict[str, Any],
    step_result: dict[str, Any] | None,
) -> None:
    if not hole_types_compatible(annotation, step_hole):
        add_hole_type_mismatch_risk(risks, annotation, step_hole, step_result)

    if mismatched_hole_dimensions(annotation, step_hole, step_result):
        add_hole_dimension_mismatch_risk(
            risks,
            annotation,
            step_hole,
            step_result,
        )


def hole_types_compatible(
    annotation: dict[str, Any],
    step_hole: dict[str, Any],
) -> bool:
    annotation_type = str(annotation.get("hole_type") or "")
    step_type = str(step_hole.get("hole_type") or "")
    if not annotation_type or not step_type or annotation_type == step_type:
        return True
    if annotation_type in PDF_SUPPLEMENTAL_HOLE_TYPES:
        return True
    if annotation_type in {"counterbore", "countersink"} and step_type in {
        "through",
        "blind",
    }:
        return True
    if annotation.get("through") is True and step_type == "through":
        return True
    return False


def mismatched_hole_dimensions(
    annotation: dict[str, Any],
    step_hole: dict[str, Any],
    step_result: dict[str, Any] | None = None,
) -> list[tuple[str, float, float]]:
    mismatches: list[tuple[str, float, float]] = []
    for key in (
        "diameter",
        "counterbore_diameter",
        "counterbore_depth",
        "countersink_diameter",
        "countersink_depth",
        "countersink_angle",
    ):
        annotation_value = number_or_none(annotation.get(key))
        step_value = number_or_none(step_hole.get(key))
        if annotation_value is None or step_value is None:
            continue
        tolerance = 1.0 if key == "countersink_angle" else 0.25
        if abs(annotation_value - step_value) > tolerance:
            mismatches.append((key, annotation_value, step_value))

    if annotation.get("through") is not True:
        annotation_depth = number_or_none(annotation.get("depth"))
        step_depth = number_or_none(step_hole.get("depth"))
        if (
            annotation_depth is not None
            and step_depth is not None
            and not step_hole_depth_is_bbox_fallback(step_hole, step_result)
        ):
            tolerance = max(0.5, min(annotation_depth, step_depth) * 0.05)
            if abs(annotation_depth - step_depth) > tolerance:
                mismatches.append(("depth", annotation_depth, step_depth))

    return mismatches


def step_hole_depth_is_bbox_fallback(
    step_hole: dict[str, Any],
    step_result: dict[str, Any] | None,
) -> bool:
    step_depth = number_or_none(step_hole.get("depth"))
    bbox = (step_result or {}).get("bounding_box") or {}
    dims = [
        number_or_none(bbox.get(key))
        for key in ("length", "width", "height")
    ]
    dims = [value for value in dims if value is not None and value > 0]
    if step_depth is None or not dims:
        return False
    min_dim = min(dims)
    tolerance = max(0.25, min_dim * 0.02)
    return abs(step_depth - min_dim) <= tolerance


def add_hole_type_mismatch_risk(
    risks: list[dict[str, Any]],
    annotation: dict[str, Any],
    step_hole: dict[str, Any],
    step_result: dict[str, Any] | None,
) -> None:
    append_risk_if_missing(
        risks,
        risk_item(
            "PDF_STEP_HOLE_TYPE_MISMATCH",
            "warning",
            (
                "PDF 孔类型标注与 STEP 孔候选类型不一致，需人工确认。"
                f"PDF={annotation.get('hole_type') or '-'}，"
                f"STEP={step_hole.get('hole_type') or '-'}。"
            ),
            "part_feature_fusion",
            True,
            annotation_evidence(annotation, step_result, step_hole),
        ),
    )


def add_hole_dimension_mismatch_risk(
    risks: list[dict[str, Any]],
    annotation: dict[str, Any],
    step_hole: dict[str, Any],
    step_result: dict[str, Any] | None,
) -> None:
    mismatches = mismatched_hole_dimensions(annotation, step_hole, step_result)
    if not mismatches:
        annotation_diameter = number_or_none(annotation.get("diameter"))
        step_diameter = number_or_none(step_hole.get("diameter"))
        if annotation_diameter is not None and step_diameter is not None:
            mismatches = [("diameter", annotation_diameter, step_diameter)]
    detail = "；".join(
        f"{HOLE_DIMENSION_LABELS.get(key, key)} PDF={pdf:g}，STEP={step:g}"
        for key, pdf, step in mismatches
    )
    append_risk_if_missing(
        risks,
        risk_item(
            "PDF_STEP_HOLE_DIMENSION_MISMATCH",
            "warning",
            (
                "PDF 孔尺寸标注与 STEP 孔候选尺寸不一致，需人工确认。"
                + (f"{detail}。" if detail else "")
            ),
            "part_feature_fusion",
            True,
            annotation_evidence(annotation, step_result, step_hole),
        ),
    )


def validate_pdf_hole_depth(
    risks: list[dict[str, Any]],
    annotation: dict[str, Any],
    step_result: dict[str, Any] | None,
) -> None:
    if annotation.get("through") is True:
        return
    depth = number_or_none(annotation.get("depth"))
    bbox = (step_result or {}).get("bounding_box") or {}
    dims = [
        number_or_none(bbox.get(key))
        for key in ("length", "width", "height")
    ]
    dims = [value for value in dims if value is not None and value > 0]
    if depth is None or not dims:
        return
    min_dim = min(dims)
    if depth <= min_dim * 1.05:
        return
    append_risk_if_missing(
        risks,
        risk_item(
            "PDF_STEP_HOLE_DEPTH_CONFLICT",
            "warning",
            (
                "PDF 孔深标注超过 STEP 最小包络尺寸，需人工确认孔方向或图纸标注。"
                f"PDF depth={depth:g}mm，STEP min dimension={min_dim:g}mm。"
            ),
            "part_feature_fusion",
            True,
            annotation_evidence(annotation, step_result),
        ),
    )


def add_pdf_only_hole_risk(
    risks: list[dict[str, Any]],
    annotation: dict[str, Any],
    step_result: dict[str, Any] | None,
) -> None:
    append_risk_if_missing(
        risks,
        risk_item(
            "PDF_STEP_HOLE_ANNOTATION_MISMATCH",
            "warning",
            "PDF 孔标注未能匹配到 STEP 孔候选，已保留为待确认孔特征。",
            "part_feature_fusion",
            True,
            annotation_evidence(annotation, step_result),
        ),
    )


def add_hole_count_mismatch_risk(
    risks: list[dict[str, Any]],
    annotation: dict[str, Any],
    step_hole: dict[str, Any],
    step_result: dict[str, Any] | None,
) -> None:
    append_risk_if_missing(
        risks,
        risk_item(
            "PDF_STEP_HOLE_COUNT_MISMATCH",
            "warning",
            (
                "PDF 孔数量标注与匹配到的 STEP 孔候选数量不一致，"
                f"PDF={int(annotation.get('count') or 1)}，STEP={int(step_hole.get('count') or 0)}。"
            ),
            "part_feature_fusion",
            True,
            annotation_evidence(annotation, step_result, step_hole),
        ),
    )


def annotation_evidence(
    annotation: dict[str, Any],
    step_result: dict[str, Any] | None,
    step_hole: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    evidence = [
        item
        for item in annotation.get("evidence") or []
        if isinstance(item, dict)
    ]
    if step_hole:
        evidence.extend(
            item
            for item in step_hole.get("evidence") or []
            if isinstance(item, dict)
        )
    elif step_result:
        evidence.append(
            source_ref(
                "step",
                file_id=step_result.get("file_id"),
                rule_code="STEP_HOLE_MATCH_CONTEXT",
            )
        )
    return evidence or [source_ref("pdf", raw_text=annotation.get("raw_text"))]


def number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_precision_requirements(
    pdf_result: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not pdf_result:
        return []
    requirements: list[dict[str, Any]] = []
    pdf_file_id = pdf_result.get("file_id")
    tolerance_texts = pdf_result.get("tolerance_texts") or []
    tolerance_evidence = pdf_result.get("tolerance_evidence") or []
    roughness_texts = pdf_result.get("roughness_texts") or []
    roughness_evidence = pdf_result.get("roughness_evidence") or []

    for index, raw_text in enumerate(tolerance_texts):
        if not raw_text:
            continue
        requirements.append(
            {
                "raw_text": raw_text,
                "standard_type": normalize_precision_code(raw_text, "TOLERANCE"),
                "confidence": 0.82,
                "source": evidence_at(
                    tolerance_evidence,
                    index,
                    pdf_file_id=pdf_file_id,
                    raw_text=raw_text,
                    location="tolerance",
                ),
            }
        )
    for index, raw_text in enumerate(roughness_texts):
        if not raw_text:
            continue
        requirements.append(
            {
                "raw_text": raw_text,
                "standard_type": normalize_precision_code(raw_text, "ROUGHNESS"),
                "confidence": 0.82,
                "source": evidence_at(
                    roughness_evidence,
                    index,
                    pdf_file_id=pdf_file_id,
                    raw_text=raw_text,
                    location="roughness",
                ),
            }
        )
    return requirements


def normalize_precision_code(raw_text: str, fallback_prefix: str) -> str:
    normalized = (
        raw_text.upper()
        .replace("±", "PLUS_MINUS")
        .replace("+/-", "PLUS_MINUS")
        .replace(".", "_")
        .replace(" ", "")
    )
    cleaned = "".join(ch for ch in normalized if ch.isalnum() or ch == "_")
    return cleaned or fallback_prefix


def evidence_at(
    evidence_items: list[dict[str, Any]],
    index: int,
    *,
    pdf_file_id: str | None,
    raw_text: str,
    location: str,
) -> dict[str, Any]:
    if index < len(evidence_items) and evidence_items[index]:
        return evidence_items[index]
    return source_ref(
        "pdf",
        file_id=pdf_file_id,
        location=location,
        raw_text=raw_text,
    )


def build_deburring_requirement(
    pdf_result: dict[str, Any] | None,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    if not pdf_result:
        return requirement_item(False, None, None, 0, fallback)
    technical_requirements = pdf_result.get("technical_requirements") or []
    technical_evidence = pdf_result.get("technical_requirement_evidence") or []
    for index, raw_text in enumerate(technical_requirements):
        if not raw_text:
            continue
        normalized = raw_text.lower()
        if "deburr" in normalized or "burr" in normalized or "毛刺" in raw_text:
            return requirement_item(
                True,
                raw_text,
                "DEBURR",
                0.75,
                evidence_at(
                    technical_evidence,
                    index,
                    pdf_file_id=pdf_result.get("file_id"),
                    raw_text=raw_text,
                    location="technical_requirements",
                ),
            )
    return requirement_item(False, None, None, 0, fallback)


def build_technical_requirements(
    pdf_result: dict[str, Any] | None,
) -> list[str]:
    if not pdf_result:
        return []

    raw_items = pdf_result.get("technical_requirements") or []
    result: list[str] = []
    seen: set[str] = set()

    for raw_text in raw_items:
        if not raw_text:
            continue
        raw_text = str(raw_text).strip()
        if not raw_text or raw_text in seen:
            continue
        seen.add(raw_text)
        result.append(raw_text)
    return result


def build_technical_requirement_details(
    pdf_result: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not pdf_result:
        return []

    raw_items = pdf_result.get("technical_requirements") or []
    evidence_items = pdf_result.get("technical_requirement_evidence") or []
    detail = (pdf_result.get("field_details") or {}).get("technical_requirements") or {}
    candidates = detail.get("candidates") or []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    for index, raw_text in enumerate(raw_items):
        if not raw_text:
            continue
        raw_text = str(raw_text).strip()
        if not raw_text or raw_text in seen:
            continue
        seen.add(raw_text)
        requirement_type = classify_technical_requirement(raw_text)
        result.append(
            {
                "raw_text": raw_text,
                "requirement_type": requirement_type,
                "standard_code": technical_requirement_standard_code(
                    raw_text,
                    requirement_type,
                ),
                "confidence": technical_requirement_confidence(candidates, index),
                "source": evidence_at(
                    evidence_items,
                    index,
                    pdf_file_id=pdf_result.get("file_id"),
                    raw_text=raw_text,
                    location="technical_requirements",
                ),
            }
        )
    return result


def classify_technical_requirement(raw_text: str) -> str:
    normalized = normalize_dictionary_key(raw_text)
    if any(keyword in normalized for keyword in ("deburr", "burr", "去毛刺", "毛刺")):
        return "deburring"
    if any(keyword in normalized for keyword in ("锐边", "倒钝", "倒角", "sharpedge", "breakedge")):
        return "edge_break"
    if any(keyword in normalized for keyword in ("热处理", "heattreatment", "淬火", "调质", "回火", "氮化")):
        return "heat_treatment"
    if any(keyword in normalized for keyword in ("表面处理", "surfacetreatment", "finish", "plating", "发黑", "氧化", "阳极", "镀")):
        return "surface_treatment"
    if any(keyword in normalized for keyword in ("检验", "检测", "全检", "报告", "inspection", "report")):
        return "inspection"
    if any(keyword in normalized for keyword in ("包装", "防锈", "运输", "packaging", "antirust")):
        return "packaging"
    if any(keyword in normalized for keyword in ("ra", "粗糙度", "公差", "未注", "gbt", "gbt1804", "h7", "±", "+/-")):
        return "precision"
    return "general"


def technical_requirement_standard_code(
    raw_text: str,
    requirement_type: str,
) -> str:
    normalized = normalize_precision_code(raw_text, requirement_type.upper())
    return f"TECH_REQ_{requirement_type.upper()}_{normalized}"[:120]


def technical_requirement_confidence(
    candidates: list[dict[str, Any]],
    index: int,
) -> float:
    if index < len(candidates):
        candidate = candidates[index]
        if isinstance(candidate, dict):
            confidence = candidate.get("confidence")
            if isinstance(confidence, (int, float)):
                return clamp_confidence(float(confidence))
    return 0.72


def add_fusion_risks(
    risks: list[dict[str, Any]],
    *,
    pdf_result: dict[str, Any] | None,
    step_result: dict[str, Any] | None,
    part_type_candidates: list[dict[str, Any]],
    pdf_part_category: dict[str, Any] | None,
) -> None:
    mismatch_risk = build_weight_mismatch_risk(pdf_result, step_result)
    if mismatch_risk:
        append_risk_if_missing(risks, mismatch_risk)
    part_type_risk = build_part_type_conflict_risk(
        part_type_candidates,
        pdf_part_category=pdf_part_category,
        step_result=step_result,
    )
    if part_type_risk:
        append_risk_if_missing(risks, part_type_risk)


def append_risk_if_missing(
    risks: list[dict[str, Any]],
    risk: dict[str, Any],
) -> None:
    code = risk.get("code")
    message = risk.get("message")
    if any(
        item.get("code") == code and item.get("message") == message
        for item in risks
    ):
        return
    risks.append(risk)


def build_part_type_conflict_risk(
    part_type_candidates: list[dict[str, Any]],
    *,
    pdf_part_category: dict[str, Any] | None = None,
    step_result: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    step_candidate = top_part_type_candidate(part_type_candidates, "step")
    pdf_candidate = top_part_type_candidate(part_type_candidates, "pdf")
    if not step_candidate:
        return None
    step_type = step_candidate.get("part_type")
    if not step_type:
        return None

    if pdf_part_category:
        if pdf_category_matches_step(
            pdf_part_category,
            str(step_type),
            (step_result or {}).get("bounding_box") or {},
        ):
            return None
        evidence = [
            item
            for item in (
                step_candidate.get("source"),
                pdf_part_category.get("source"),
            )
            if isinstance(item, dict)
        ]
        return risk_item(
            "PDF_STEP_PART_TYPE_CONFLICT",
            "warning",
            (
                "PDF 物料小类与 STEP 几何类型不兼容，需人工确认。"
                f"PDF物料小类={pdf_part_category.get('category_name')}，"
                f"STEP几何类型={step_type}。"
            ),
            "part_feature_fusion",
            True,
            evidence,
        )

    if not pdf_candidate:
        return None
    pdf_type = pdf_candidate.get("part_type")
    if not pdf_type or step_type == pdf_type:
        return None

    evidence = [
        item.get("source")
        for item in (step_candidate, pdf_candidate)
        if isinstance(item.get("source"), dict)
    ]
    return risk_item(
        "PDF_STEP_PART_TYPE_CONFLICT",
        "warning",
        (
            "PDF 和 STEP 零件类型判断不一致，已保留候选，需人工确认。"
            f"PDF={pdf_type}，STEP={step_type}。"
        ),
        "part_feature_fusion",
        True,
        evidence,
    )


def pdf_category_matches_step(
    pdf_part_category: dict[str, Any],
    step_type: str,
    bounding_box: dict[str, Any],
) -> bool:
    compatible_types = set(pdf_part_category.get("compatible_part_types") or [])
    if step_type not in compatible_types:
        return False

    category_name = pdf_part_category.get("category_name")
    max_dimension = max_bbox_dimension(bounding_box)
    if max_dimension is None:
        return True
    if category_name == "方件类":
        return max_dimension <= 500
    if category_name == "大板类":
        return max_dimension > 500
    return True


def max_bbox_dimension(bounding_box: dict[str, Any]) -> float | None:
    values = [
        numeric
        for numeric in (
            number_or_none(bounding_box.get("length")),
            number_or_none(bounding_box.get("width")),
            number_or_none(bounding_box.get("height")),
        )
        if numeric is not None
    ]
    if len(values) != 3:
        return None
    return max(values)


def build_weight_mismatch_risk(
    pdf_result: dict[str, Any] | None,
    step_result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not pdf_result or not step_result:
        return None
    pdf_weight = weight_to_kg(
        pdf_result.get("weight_value"),
        pdf_result.get("weight_unit"),
    )
    net_weight = step_result.get("net_weight") or {}
    step_weight = weight_to_kg(net_weight.get("value"), net_weight.get("unit"))
    if pdf_weight is None or step_weight is None or step_weight == 0:
        return None
    delta_ratio = abs(pdf_weight - step_weight) / step_weight
    if delta_ratio <= 0.15:
        return None
    pdf_evidence = field_source(
        pdf_result,
        "weight_raw",
        pdf_file_id=pdf_result.get("file_id"),
        raw_text=pdf_result.get("weight_raw"),
        fallback=source_ref("system", rule_code="WEIGHT_MISMATCH:PDF_WEIGHT"),
    )
    step_evidence = net_weight.get("source") or source_ref(
        "step",
        file_id=step_result.get("file_id"),
        rule_code="WEIGHT_MISMATCH:STEP_WEIGHT",
    )
    return risk_item(
        "WEIGHT_MISMATCH",
        "warning",
        (
            "PDF 标注重量与 STEP 理论净重偏差超过 15%，"
            f"PDF={pdf_weight:.4g}kg，STEP={step_weight:.4g}kg。"
        ),
        "part_feature_fusion",
        True,
        [pdf_evidence, step_evidence],
    )


def weight_to_kg(value: Any, unit: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    normalized_unit = str(unit or "").strip().lower()
    if normalized_unit in {"kg", "kgs", "kilogram", "kilograms", ""}:
        return float(value)
    if normalized_unit in {"g", "gram", "grams"}:
        return float(value) / 1000
    if normalized_unit in {"mg", "milligram", "milligrams"}:
        return float(value) / 1_000_000
    return None


def missing_file_risk(task_id: str, file_type: str) -> dict[str, Any]:
    if file_type == "pdf":
        return risk_item(
            "MISSING_PDF",
            "warning",
            "缺少 PDF 图纸文件，当前只能基于已上传资料继续，需人工确认。",
            "file_management",
            True,
            [source_ref("system", rule_code=f"MISSING_PDF:{task_id}")],
        )

    return risk_item(
        "MISSING_STEP",
        "warning",
        "缺少 STEP 模型文件，当前只能基于已上传资料继续，需人工确认。",
        "file_management",
        True,
        [source_ref("system", rule_code=f"MISSING_STEP:{task_id}")],
    )
