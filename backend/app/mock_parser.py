from __future__ import annotations

from typing import Any


MATERIAL_DICTIONARY = {
    "sus304": {
        "standard_code": "SUS304",
        "standard_name": "SUS304 stainless steel",
        "density": 7.93,
        "density_unit": "g/cm3",
        "confidence": 0.88,
    },
    "skd11": {
        "standard_code": "SKD11",
        "standard_name": "SKD11 tool steel",
        "density": 7.85,
        "density_unit": "g/cm3",
        "confidence": 0.86,
    },
    "s45c": {
        "standard_code": "S45C",
        "standard_name": "S45C carbon steel",
        "density": 7.85,
        "density_unit": "g/cm3",
        "confidence": 0.84,
    },
    "45#": {
        "standard_code": "S45C",
        "standard_name": "S45C carbon steel",
        "density": 7.85,
        "density_unit": "g/cm3",
        "confidence": 0.78,
    },
    "al6061": {
        "standard_code": "AL6061",
        "standard_name": "6061 aluminum alloy",
        "density": 2.7,
        "density_unit": "g/cm3",
        "confidence": 0.84,
    },
    "6061": {
        "standard_code": "AL6061",
        "standard_name": "6061 aluminum alloy",
        "density": 2.7,
        "density_unit": "g/cm3",
        "confidence": 0.8,
    },
    "6061t6": {
        "standard_code": "AL6061",
        "standard_name": "6061 aluminum alloy",
        "density": 2.7,
        "density_unit": "g/cm3",
        "confidence": 0.8,
    },
}

SURFACE_TREATMENT_DICTIONARY = {
    "chemicalnickelplating": {
        "standard_code": "CHEMICAL_NICKEL_PLATING",
        "standard_name": "Chemical nickel plating",
        "confidence": 0.82,
    },
    "electrolessnickelplating": {
        "standard_code": "CHEMICAL_NICKEL_PLATING",
        "standard_name": "Chemical nickel plating",
        "confidence": 0.82,
    },
    "化学镍": {
        "standard_code": "CHEMICAL_NICKEL_PLATING",
        "standard_name": "Chemical nickel plating",
        "confidence": 0.82,
    },
    "化学镀镍": {
        "standard_code": "CHEMICAL_NICKEL_PLATING",
        "standard_name": "Chemical nickel plating",
        "confidence": 0.82,
    },
    "镀化学镍": {
        "standard_code": "CHEMICAL_NICKEL_PLATING",
        "standard_name": "Chemical nickel plating",
        "confidence": 0.82,
    },
}


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


def build_mock_pdf_extract_result(
    task: dict[str, Any],
    pdf_file: dict[str, Any],
) -> dict[str, Any]:
    file_id = pdf_file["file_id"]
    evidence = {
        "drawing_no": source_ref(
            "pdf",
            file_id=file_id,
            page=1,
            location="title_block",
            raw_text=task["part_no"],
        ),
        "part_name": source_ref(
            "pdf",
            file_id=file_id,
            page=1,
            location="title_block",
            raw_text=task["part_name"],
        ),
        "material_raw": source_ref(
            "pdf",
            file_id=file_id,
            page=1,
            location="title_block",
            raw_text="SUS304",
        ),
        "weight_raw": source_ref(
            "pdf",
            file_id=file_id,
            page=1,
            location="title_block",
            raw_text="0.76 kg",
        ),
        "surface_treatment_raw": source_ref(
            "pdf",
            file_id=file_id,
            page=1,
            location="technical_requirements",
            raw_text="Chemical nickel plating",
        ),
    }

    return {
        "schema_version": "1.0",
        "task_id": task["task_id"],
        "file_id": file_id,
        "drawing_no": task["part_no"],
        "part_name": task["part_name"],
        "revision": "A",
        "material_raw": "SUS304",
        "weight_raw": "0.76 kg",
        "weight_value": 0.76,
        "weight_unit": "kg",
        "scale": "1:1",
        "heat_treatment_raw": None,
        "surface_treatment_raw": "Chemical nickel plating",
        "tolerance_texts": ["+/-0.01"],
        "roughness_texts": ["Ra0.8"],
        "technical_requirements": [
            "Remove burrs.",
            "Protect surface after plating.",
        ],
        "field_evidence": evidence,
        "risks": [
            risk_item(
                "HIGH_PRECISION_REQUIREMENT",
                "warning",
                "PDF mock contains +/-0.01 and Ra0.8 precision requirements.",
                "pdf_parser",
                True,
                [
                    source_ref(
                        "pdf",
                        file_id=file_id,
                        page=1,
                        location="technical_requirements",
                        raw_text="+/-0.01; Ra0.8",
                    )
                ],
            )
        ],
    }


def build_mock_step_feature_result(
    task: dict[str, Any],
    step_file: dict[str, Any],
) -> dict[str, Any]:
    file_id = step_file["file_id"]
    geometry_evidence = source_ref(
        "step",
        file_id=file_id,
        location="mock_geometry",
        raw_text=step_file["filename"],
    )

    return {
        "schema_version": "1.0",
        "task_id": task["task_id"],
        "file_id": file_id,
        "bounding_box": {
            "length": 120.0,
            "width": 80.0,
            "height": 10.0,
            "unit": "mm",
        },
        "volume": {
            "value": 96000.0,
            "unit": "mm3",
            "source": geometry_evidence,
        },
        "surface_area": {
            "value": 22000.0,
            "unit": "mm2",
            "source": geometry_evidence,
        },
        "net_weight": {
            "value": 0.761,
            "unit": "kg",
            "density_source": "mock_material_density",
            "source": geometry_evidence,
        },
        "part_type_candidates": [
            {
                "part_type": "plate",
                "confidence": 0.86,
                "evidence": [geometry_evidence],
            }
        ],
        "holes": [
            {
                "hole_type": "through",
                "diameter": 6.0,
                "depth": None,
                "count": 4,
                "confidence": 0.82,
                "evidence": [geometry_evidence],
            }
        ],
        "complexity": {
            "face_count": 42,
            "edge_count": 128,
            "small_radius_count": 2,
            "slot_count": 1,
            "thin_wall_candidate": False,
            "complexity_score": 35.0,
        },
        "geometry_risks": [],
    }


def build_mock_part_feature(
    task: dict[str, Any],
    pdf_result: dict[str, Any] | None,
    step_result: dict[str, Any] | None,
    risks: list[dict[str, Any]],
    *,
    material_normalization: dict[str, Any] | None = None,
    surface_treatment_normalization: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pdf_file_id = pdf_result["file_id"] if pdf_result else None
    step_file_id = step_result["file_id"] if step_result else None

    pdf_source = source_ref("pdf", file_id=pdf_file_id)
    step_source = source_ref("step", file_id=step_file_id)
    system_source = source_ref("system", rule_code="PART_FEATURE_FUSION")
    material_content = (
        material_normalization["content"] if material_normalization else {}
    )
    surface_content = (
        surface_treatment_normalization["content"]
        if surface_treatment_normalization
        else {}
    )
    material_raw = pdf_result.get("material_raw") if pdf_result else None
    surface_raw = pdf_result.get("surface_treatment_raw") if pdf_result else None
    heat_raw = pdf_result.get("heat_treatment_raw") if pdf_result else None
    material_dictionary_match = lookup_material(material_raw)
    surface_dictionary_match = lookup_surface_treatment(surface_raw)
    material_standard_code = material_content.get("standard_code") or (
        material_dictionary_match or {}
    ).get("standard_code")
    surface_standard_code = surface_content.get("standard_code") or (
        surface_dictionary_match or {}
    ).get("standard_code")
    material_source = field_source(
        pdf_result,
        "material_raw",
        pdf_file_id=pdf_file_id,
        raw_text=material_raw,
        fallback=system_source,
    )
    if material_content.get("standard_code"):
        material_source = source_ref(
            "ai",
            file_id=pdf_file_id,
            raw_text=material_content.get("raw_text"),
            rule_code=material_normalization["prompt_version"],
        )
    elif material_dictionary_match:
        material_source = source_ref(
            "rule",
            file_id=pdf_file_id,
            raw_text=material_raw,
            rule_code="MATERIAL_DICTIONARY",
        )
    surface_source = field_source(
        pdf_result,
        "surface_treatment_raw",
        pdf_file_id=pdf_file_id,
        raw_text=surface_raw,
        fallback=system_source,
    )
    if surface_content.get("standard_code"):
        surface_source = source_ref(
            "ai",
            file_id=pdf_file_id,
            raw_text=surface_content.get("raw_text"),
            rule_code=surface_treatment_normalization["prompt_version"],
        )
    elif surface_dictionary_match:
        surface_source = source_ref(
            "rule",
            file_id=pdf_file_id,
            raw_text=surface_raw,
            rule_code="SURFACE_TREATMENT_DICTIONARY",
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
        material_standard_code=material_standard_code,
        material_source=material_source,
        surface_standard_code=surface_standard_code,
        surface_source=surface_source,
    )

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
            "standard_name": first_available(
                material_content.get("standard_name"),
                (material_dictionary_match or {}).get("standard_name"),
            ),
            "density": first_available(
                material_content.get("density"),
                (material_dictionary_match or {}).get("density"),
            ),
            "density_unit": first_available(
                material_content.get("density_unit"),
                (material_dictionary_match or {}).get("density_unit"),
            ),
            "confidence": material_confidence(
                pdf_result,
                material_normalization,
                material_dictionary_match,
            ),
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
                step_result["part_type_candidates"][0]["part_type"]
                if step_result and step_result["part_type_candidates"]
                else None
            ),
            "part_type_confidence": (
                step_result["part_type_candidates"][0]["confidence"]
                if step_result and step_result["part_type_candidates"]
                else 0
            ),
        },
        "features": {
            "holes": step_result["holes"] if step_result else [],
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
                surface_confidence(
                    pdf_result,
                    surface_treatment_normalization,
                    surface_dictionary_match,
                ),
                surface_source,
            ),
            "deburring": build_deburring_requirement(pdf_result, system_source),
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


def material_confidence(
    pdf_result: dict[str, Any] | None,
    material_normalization: dict[str, Any] | None,
    dictionary_match: dict[str, Any] | None,
) -> float:
    if material_normalization and (
        material_normalization.get("content") or {}
    ).get("standard_code"):
        return clamp_confidence(float(material_normalization["confidence"]))
    if dictionary_match:
        return clamp_confidence(float(dictionary_match["confidence"]))
    return pdf_field_confidence(pdf_result, "material_raw")


def surface_confidence(
    pdf_result: dict[str, Any] | None,
    surface_treatment_normalization: dict[str, Any] | None,
    dictionary_match: dict[str, Any] | None,
) -> float:
    if surface_treatment_normalization and (
        surface_treatment_normalization.get("content") or {}
    ).get("standard_code"):
        return clamp_confidence(float(surface_treatment_normalization["confidence"]))
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


def add_fusion_risks(
    risks: list[dict[str, Any]],
    *,
    pdf_result: dict[str, Any] | None,
    step_result: dict[str, Any] | None,
    material_standard_code: str | None,
    material_source: dict[str, Any],
    surface_standard_code: str | None,
    surface_source: dict[str, Any],
) -> None:
    if pdf_result and pdf_result.get("material_raw") and not material_standard_code:
        append_risk_if_missing(
            risks,
            risk_item(
                "UNKNOWN_MATERIAL",
                "warning",
                "PDF 已抽取材料原文，但材料未归一为标准编码，需要人工确认。",
                "part_feature_fusion",
                True,
                [material_source],
            ),
        )
    if (
        pdf_result
        and pdf_result.get("surface_treatment_raw")
        and not surface_standard_code
    ):
        append_risk_if_missing(
            risks,
            risk_item(
                "UNKNOWN_SURFACE_TREATMENT",
                "warning",
                "PDF 已抽取表面处理原文，但表面处理未归一为标准编码，需要人工确认。",
                "part_feature_fusion",
                True,
                [surface_source],
            ),
        )
    mismatch_risk = build_weight_mismatch_risk(pdf_result, step_result)
    if mismatch_risk:
        append_risk_if_missing(risks, mismatch_risk)


def append_risk_if_missing(
    risks: list[dict[str, Any]],
    risk: dict[str, Any],
) -> None:
    code = risk.get("code")
    if any(item.get("code") == code for item in risks):
        return
    risks.append(risk)


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
            "PDF file is missing. Mock parsing will continue with partial data.",
            "mock_parser",
            True,
            [source_ref("system", rule_code=f"MISSING_PDF:{task_id}")],
        )

    return risk_item(
        "MISSING_STEP",
        "warning",
        "STEP file is missing. Mock parsing will continue with partial data.",
        "mock_parser",
        True,
        [source_ref("system", rule_code=f"MISSING_STEP:{task_id}")],
    )
