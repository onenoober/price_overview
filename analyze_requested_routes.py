from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

os.environ.setdefault("PRICE_PDF_VISION_MODE", "off")
os.environ.setdefault("PRICE_STEP_PARSER_BACKEND", "auto")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backend.app.parser_service import build_parser_service
from backend.app.part_feature_builder import build_part_feature
from backend.app.process_dictionary import process_name_for_code
from backend.app.process_recognition import build_process_route
from backend.app.domain_v2.route_engine import plan_route_v2


PARTS = [
    ("钣金", "RM-JJ-00083381-01"),
    ("钣金", "RM-JJ-00083917-01"),
    ("钣金", "RM-JJ-00083980-01"),
    ("钣金", "RM-JJ-00084158-01"),
    ("钣金", "RM-JJ-00084346-01"),
    ("大板", "RM-JJ-00083694-01"),
    ("大板", "RM-JJ-00083711-01"),
    ("大板", "RM-JJ-00083722-01"),
    ("大板", "RM-JJ-00084089-01"),
    ("机加", "RM-JJ-00083669-01"),
    ("机加", "RM-JJ-00083683-01"),
    ("机加", "RM-JJ-00083695-01"),
    ("机加", "RM-JJ-00083826-01"),
    (r"轴类\轴类", "RM-JJ-00083820-01"),
    (r"轴类\轴类", "RM-JJ-00083835-01"),
    (r"轴类\轴类", "RM-JJ-00083857-01"),
    (r"轴类\轴类", "RM-JJ-00084313-01"),
]


def file_record(path: Path, kind: str) -> dict[str, Any]:
    return {
        "file_id": f"{kind}_{path.name}",
        "storage_path": str(path),
        "filename": path.name,
        "file_type": kind,
    }


def op_summary(route: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for op in route.get("operations") or []:
        code = op.get("operation_code")
        try:
            name = process_name_for_code(code)
        except Exception:
            name = op.get("operation_name") or code
        result.append(
            {
                "code": code,
                "name": op.get("operation_name") or name,
                "requires_review": bool(op.get("requires_review")),
                "reason": op.get("selection_reason") or op.get("review_reason"),
            }
        )
    return result


def risks_summary(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "code": item.get("code"),
            "level": item.get("level"),
            "message": item.get("message"),
            "requires_review": item.get("requires_review"),
        }
        for item in risks
    ]


def run_one(base: Path, folder: str, stem: str) -> dict[str, Any]:
    pdf_path = base / folder / f"{stem}.pdf"
    step_path = base / folder / f"{stem}.step"
    task = {
        "task_id": f"task_{stem}",
        "part_name": stem,
        "part_no": stem,
        "quantity": 1,
    }
    service = build_parser_service()
    risks: list[dict[str, Any]] = []

    pdf_result, pdf_risks = service.parse_pdf(task=task, pdf_file=file_record(pdf_path, "pdf"))
    risks.extend(pdf_risks)

    step_result = None
    if step_path.exists():
        step_result, step_risks = service.parse_step(task=task, step_file=file_record(step_path, "step"))
        risks.extend(step_risks)
    else:
        risks.append(
            {
                "code": "STEP_FILE_MISSING_FOR_TEST",
                "level": "warning",
                "message": f"Test input has no paired STEP file: {step_path}",
                "source": "test_runner",
                "requires_review": True,
                "evidence": [],
            }
        )

    part_feature = build_part_feature(task, pdf_result, step_result, risks)
    legacy = build_process_route(
        task_id=task["task_id"],
        route_id="r_legacy",
        part_feature=part_feature,
        inherited_risks=list(risks),
    )
    v2 = plan_route_v2(
        task_id=task["task_id"],
        route_id="r_v2",
        part_feature=part_feature,
        inherited_risks=list(risks),
    )

    geometry = part_feature.get("geometry") or {}
    features = part_feature.get("features") or {}
    reqs = part_feature.get("manufacturing_requirements") or {}
    bbox = geometry.get("bounding_box") or {}
    return {
        "folder": folder,
        "stem": stem,
        "pdf_exists": pdf_path.exists(),
        "step_exists": step_path.exists(),
        "pdf_path": str(pdf_path),
        "step_path": str(step_path) if step_path.exists() else None,
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
            "legacy_ops": op_summary(legacy),
            "v2_family": v2.get("family"),
            "v2_ops": op_summary(v2),
            "legacy_risks": risks_summary(legacy.get("risks") or []),
            "v2_risks": risks_summary(v2.get("risks") or []),
        },
        "part_feature_risks": risks_summary(part_feature.get("risks") or []),
    }


def main() -> None:
    base = Path(r"D:\test")
    output_dir = ROOT / "exports" / "route_analysis_requested"
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for folder, stem in PARTS:
        try:
            rows.append(run_one(base, folder, stem))
            print(f"OK {folder} {stem}")
        except Exception as exc:
            traceback.print_exc()
            rows.append({"folder": folder, "stem": stem, "error": repr(exc)})
            print(f"ERR {folder} {stem}: {exc!r}")

    output_path = output_dir / "system_routes.json"
    output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
