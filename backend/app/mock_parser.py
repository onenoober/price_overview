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
    system_source = source_ref("system", rule_code="MOCK_PARSE")
    material_content = (
        material_normalization["content"] if material_normalization else {}
    )
    surface_content = (
        surface_treatment_normalization["content"]
        if surface_treatment_normalization
        else {}
    )
    material_source = (
        source_ref(
            "ai",
            file_id=pdf_file_id,
            raw_text=material_content.get("raw_text"),
            rule_code=material_normalization["prompt_version"],
        )
        if material_normalization
        else (
            pdf_result["field_evidence"]["material_raw"]
            if pdf_result
            else system_source
        )
    )
    surface_source = (
        source_ref(
            "ai",
            file_id=pdf_file_id,
            raw_text=surface_content.get("raw_text"),
            rule_code=surface_treatment_normalization["prompt_version"],
        )
        if surface_treatment_normalization
        else (
            pdf_result["field_evidence"]["surface_treatment_raw"]
            if pdf_result
            else system_source
        )
    )

    if pdf_result:
        risks.extend(pdf_result.get("risks", []))
    if step_result:
        risks.extend(step_result.get("geometry_risks", []))

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
            "raw_text": pdf_result["material_raw"] if pdf_result else None,
            "standard_code": material_content.get("standard_code")
            if material_normalization
            else ("SUS304" if pdf_result else None),
            "standard_name": material_content.get("standard_name")
            if material_normalization
            else ("SUS304 stainless steel" if pdf_result else None),
            "density": material_content.get("density")
            if material_normalization
            else (7.93 if pdf_result else None),
            "density_unit": material_content.get("density_unit")
            if material_normalization
            else ("g/cm3" if pdf_result else None),
            "confidence": material_normalization["confidence"]
            if material_normalization
            else (0.9 if pdf_result else 0),
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
            "slots": [
                {
                    "slot_type": "open_slot",
                    "count": 1,
                    "confidence": 0.72,
                }
            ]
            if step_result
            else [],
            "precision_requirements": [
                {
                    "raw_text": "+/-0.01",
                    "standard_type": "TOLERANCE_0_01",
                    "confidence": 0.88,
                    "source": source_ref(
                        "pdf",
                        file_id=pdf_file_id,
                        page=1,
                        location="technical_requirements",
                        raw_text="+/-0.01",
                    ),
                },
                {
                    "raw_text": "Ra0.8",
                    "standard_type": "RA_0_8",
                    "confidence": 0.86,
                    "source": source_ref(
                        "pdf",
                        file_id=pdf_file_id,
                        page=1,
                        location="technical_requirements",
                        raw_text="Ra0.8",
                    ),
                },
            ]
            if pdf_result
            else [],
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
            "heat_treatment": requirement_item(False, None, None, 0, system_source),
            "surface_treatment": requirement_item(
                bool(pdf_result and pdf_result["surface_treatment_raw"]),
                pdf_result["surface_treatment_raw"] if pdf_result else None,
                surface_content.get("standard_code")
                if surface_treatment_normalization
                else ("CHEMICAL_NICKEL_PLATING" if pdf_result else None),
                surface_treatment_normalization["confidence"]
                if surface_treatment_normalization
                else (0.82 if pdf_result else 0),
                surface_source,
            ),
            "deburring": requirement_item(True, "Remove burrs.", "DEBURR", 0.75, pdf_source),
            "inspection": requirement_item(True, "Standard inspection.", "STANDARD_INSPECTION", 0.7, system_source),
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
