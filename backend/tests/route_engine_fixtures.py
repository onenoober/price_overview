"""分层路线引擎测试用的 part_feature 合成夹具。"""

from __future__ import annotations

from typing import Any


def make_part_feature(
    *,
    category_name: str | None,
    part_type: str,
    compatible_part_types: tuple[str, ...],
    confidence: float = 0.95,
    holes: list[dict[str, Any]] | None = None,
    slots: list[dict[str, Any]] | None = None,
    complexity: dict[str, Any] | None = None,
    surface_treatment: dict[str, Any] | None = None,
    heat_treatment: dict[str, Any] | None = None,
    technical_requirements: list[dict[str, Any]] | None = None,
    material: dict[str, Any] | None = None,
    bounding_box: dict[str, Any] | None = None,
    part_name: str = "Part",
) -> dict[str, Any]:
    pdf_part_category: dict[str, Any] | None
    if category_name is None:
        pdf_part_category = None
    else:
        pdf_part_category = {
            "category_name": category_name,
            "confidence": confidence,
            "compatible_part_types": list(compatible_part_types),
            "source": {"source_type": "pdf", "file_id": "pdf-1"},
            "raw_text": category_name,
        }
    return {
        "geometry": {
            "part_type": part_type,
            "bounding_box": bounding_box or {"length": 100, "width": 80, "height": 20},
            "pdf_part_category": pdf_part_category,
        },
        "part": {"part_name": part_name},
        "features": {
            "holes": holes or [],
            "slots": slots or [],
            "precision_requirements": [],
            "complexity": complexity or {},
        },
        "manufacturing_requirements": {
            "heat_treatment": heat_treatment or {"required": False, "source": None},
            "surface_treatment": surface_treatment or {"required": False, "source": None},
            "deburring": {"required": False},
            "technical_requirements": technical_requirements or [],
            "technical_requirement_details": technical_requirements or [],
            "inspection": {"required": True},
            "packaging": {"required": False},
        },
        "material": material or {},
    }


def operation_codes(route: dict[str, Any]) -> list[str]:
    return [str(op.get("operation_code")) for op in route.get("operations", [])]


def review_codes(route: dict[str, Any]) -> list[str]:
    return [str(risk.get("code")) for risk in route.get("risks", [])]


def risk_codes(route: dict[str, Any]) -> set[str]:
    return {str(risk.get("code")) for risk in route.get("risks", []) if risk.get("code")}
