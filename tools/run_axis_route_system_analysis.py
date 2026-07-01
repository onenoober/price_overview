from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

os.environ.setdefault("PRICE_PDF_VISION_MODE", "off")
os.environ.setdefault("PRICE_STEP_PARSER_BACKEND", "auto")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.domain_v2.route_engine import plan_route_v2
from backend.app.parser_service import build_parser_service
from backend.app.part_feature_builder import build_part_feature
from backend.app.process_dictionary import process_name_for_code
from backend.app.process_recognition import build_process_route


BASE = Path(r"D:\test\轴类\轴类")
OUTPUT_DIR = ROOT / "exports" / "axis_route_analysis"
PARTS = [
    "RM-JJ-00083648-01",
    "RM-JJ-00083692-01",
    "RM-JJ-00083816-01",
    "RM-JJ-00083824-01",
    "RM-JJ-00083835-01",
    "RM-JJ-00083848-01",
    "RM-JJ-00083853-01",
    "RM-JJ-00083858-01",
    "RM-JJ-00083981-01",
    "RM-JJ-00084084-01",
    "RM-JJ-00084164-01",
    "RM-JJ-00084248-01",
    "RM-JJ-00084311-01",
]


def file_record(path: Path, kind: str) -> dict[str, Any]:
    return {
        "file_id": f"{kind}_{path.name}",
        "storage_path": str(path),
        "filename": path.name,
        "file_type": kind,
    }


def operation_summary(route: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for op in route.get("operations") or []:
        code = str(op.get("operation_code") or "")
        try:
            name = process_name_for_code(code)
        except Exception:
            name = str(op.get("operation_name") or code)
        rows.append(
            {
                "code": code,
                "name": op.get("operation_name") or name,
                "requires_review": bool(op.get("requires_review")),
                "reason": op.get("selection_reason") or op.get("review_reason"),
                "confidence": op.get("confidence"),
            }
        )
    return rows


def risk_summary(risks: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [
        {
            "code": item.get("code"),
            "level": item.get("level"),
            "message": item.get("message"),
            "requires_review": item.get("requires_review"),
        }
        for item in (risks or [])
    ]


def run_one(stem: str) -> dict[str, Any]:
    pdf_path = BASE / f"{stem}.pdf"
    step_path = BASE / f"{stem}.step"
    task = {
        "task_id": f"axis_{stem}",
        "part_name": stem,
        "part_no": stem,
        "quantity": 1,
    }
    service = build_parser_service()
    risks: list[dict[str, Any]] = []

    pdf_result, pdf_risks = service.parse_pdf(task=task, pdf_file=file_record(pdf_path, "pdf"))
    risks.extend(pdf_risks)
    step_result, step_risks = service.parse_step(task=task, step_file=file_record(step_path, "step"))
    risks.extend(step_risks)

    part_feature = build_part_feature(task, pdf_result, step_result, risks)
    legacy = build_process_route(
        task_id=task["task_id"],
        route_id="legacy",
        part_feature=part_feature,
        inherited_risks=list(risks),
    )
    v2 = plan_route_v2(
        task_id=task["task_id"],
        route_id="v2",
        part_feature=part_feature,
        inherited_risks=list(risks),
    )

    geometry = part_feature.get("geometry") or {}
    features = part_feature.get("features") or {}
    reqs = part_feature.get("manufacturing_requirements") or {}
    bbox = geometry.get("bounding_box") or {}

    return {
        "stem": stem,
        "pdf_path": str(pdf_path),
        "step_path": str(step_path),
        "pdf_exists": pdf_path.exists(),
        "step_exists": step_path.exists(),
        "pdf_result": {
            "parser": (pdf_result or {}).get("parser_name"),
            "drawing_no": (pdf_result or {}).get("drawing_no"),
            "part_name": (pdf_result or {}).get("part_name"),
            "material_raw": (pdf_result or {}).get("material_raw"),
            "surface_treatment_raw": (pdf_result or {}).get("surface_treatment_raw"),
            "heat_treatment_raw": (pdf_result or {}).get("heat_treatment_raw"),
            "weight_raw": (pdf_result or {}).get("weight_raw"),
            "technical_requirements": (pdf_result or {}).get("technical_requirements") or [],
            "tolerance_texts": (pdf_result or {}).get("tolerance_texts") or [],
            "roughness_texts": (pdf_result or {}).get("roughness_texts") or [],
            "hole_annotations": (pdf_result or {}).get("hole_annotations") or [],
        },
        "geometry": {
            "part_type": geometry.get("part_type"),
            "step_part_type": geometry.get("step_part_type"),
            "pdf_part_type": geometry.get("pdf_part_type"),
            "pdf_category": (geometry.get("pdf_part_category") or {}).get("category_name"),
            "pdf_category_confidence": (geometry.get("pdf_part_category") or {}).get("confidence"),
            "bbox": bbox,
            "step_net_weight": geometry.get("step_net_weight"),
            "pdf_weight": geometry.get("pdf_weight"),
        },
        "features": {
            "holes": features.get("holes") or [],
            "slots": features.get("slots") or [],
            "complexity": features.get("complexity") or {},
        },
        "requirements": {
            "heat_treatment": reqs.get("heat_treatment"),
            "surface_treatment": reqs.get("surface_treatment"),
            "deburring": reqs.get("deburring"),
            "inspection": reqs.get("inspection"),
        },
        "system": {
            "legacy_ops": operation_summary(legacy),
            "legacy_risks": risk_summary(legacy.get("risks")),
            "v2_family": v2.get("family"),
            "v2_business_category": v2.get("business_category"),
            "v2_ops": operation_summary(v2),
            "v2_risks": risk_summary(v2.get("risks")),
        },
        "part_feature_risks": risk_summary(part_feature.get("risks")),
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for stem in PARTS:
        try:
            row = run_one(stem)
            rows.append(row)
            print(f"OK {stem}")
        except Exception as exc:
            traceback.print_exc()
            rows.append({"stem": stem, "error": repr(exc)})
            print(f"ERR {stem}: {exc!r}")

    output_path = OUTPUT_DIR / "system_routes.json"
    output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
