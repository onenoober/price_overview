"""临时脚本：对 D:\\test 下的 PDF+STEP 跑全链路，输出 legacy 与 v2 路线对比。"""

from __future__ import annotations

import os
import sys
import traceback

os.environ.setdefault("PRICE_PDF_VISION_MODE", "off")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.app.parser_service import build_parser_service
from backend.app.part_feature_builder import build_part_feature
from backend.app.process_recognition import build_process_route
from backend.app.domain_v2.route_engine import plan_route_v2

BASE = r"D:\test"
PARTS = [
    ("钣金", "RM-JJ-00083980-01"),
    ("钣金", "RM-JJ-00084332-01"),
    ("钣金", "RM-JJ-00083867-01"),
    ("大板", "RM-JJ-00083702-01"),
    ("大板", "RM-JJ-00083711-01"),
    ("大板", "RM-JJ-00083722-01"),
    ("大板", "RM-JJ-00084089-01"),
    ("机加", "RM-JJ-00083377-01"),
    ("机加", "RM-JJ-00083695-01"),
    ("机加", "RM-JJ-00083691-01"),
    ("机加", "RM-JJ-00083706-01"),
    (r"轴类\轴类", "RM-JJ-00083820-01"),
    (r"轴类\轴类", "RM-JJ-00083830-01"),
    (r"轴类\轴类", "RM-JJ-00083979-01"),
    (r"轴类\轴类", "RM-JJ-00083860-01"),
    (r"轴类\轴类", "RM-JJ-00083849-01"),
]


def file_record(path: str, kind: str) -> dict:
    return {
        "file_id": f"{kind}_{os.path.basename(path)}",
        "storage_path": path,
        "filename": os.path.basename(path),
        "file_type": kind,
    }


def run_one(folder: str, stem: str) -> dict:
    pdf_path = os.path.join(BASE, folder, stem + ".pdf")
    step_path = os.path.join(BASE, folder, stem + ".step")
    task = {
        "task_id": f"task_{stem}",
        "part_name": stem,
        "part_no": stem,
        "quantity": 1,
    }
    service = build_parser_service()

    out: dict = {"stem": stem, "folder": folder}
    risks: list = []

    pdf_result, pdf_risks = service.parse_pdf(task=task, pdf_file=file_record(pdf_path, "pdf"))
    risks.extend(pdf_risks)
    step_result, step_risks = service.parse_step(task=task, step_file=file_record(step_path, "step"))
    risks.extend(step_risks)

    part_feature = build_part_feature(task, pdf_result, step_result, risks)

    geom = part_feature.get("geometry") or {}
    cat = (geom.get("pdf_part_category") or {})
    out["pdf_category"] = cat.get("category_name")
    out["pdf_category_conf"] = cat.get("confidence")
    out["part_type"] = geom.get("part_type")
    out["part_name"] = (pdf_result or {}).get("part_name")
    out["material"] = (pdf_result or {}).get("material_raw")
    out["surface_raw"] = (pdf_result or {}).get("surface_treatment_raw")
    out["heat_raw"] = (pdf_result or {}).get("heat_treatment_raw")
    holes = (part_feature.get("features") or {}).get("holes") or []
    out["hole_count"] = sum(int(h.get("count") or 0) for h in holes)

    legacy = build_process_route(
        task_id=task["task_id"], route_id="r_legacy", part_feature=part_feature, inherited_risks=list(risks)
    )
    out["legacy_ops"] = [o["operation_code"] for o in legacy["operations"]]

    v2 = plan_route_v2(
        task_id=task["task_id"], route_id="r_v2", part_feature=part_feature, inherited_risks=list(risks)
    )
    out["v2_family"] = v2.get("family")
    out["v2_ops"] = [o["operation_code"] for o in v2["operations"]]
    out["v2_reviews"] = sorted({r["code"] for r in v2.get("risks", [])})
    return out


def main() -> None:
    for folder, stem in PARTS:
        print("=" * 100)
        try:
            out = run_one(folder, stem)
        except Exception as exc:  # noqa: BLE001
            print(f"[{folder}] {stem}  ERROR: {exc!r}")
            traceback.print_exc()
            continue
        print(f"[{folder}] {stem}  | 业务小类={out['pdf_category']}({out['pdf_category_conf']}) "
              f"| STEP part_type={out['part_type']} | 名称={out['part_name']} | 材料={out['material']}")
        print(f"   表处字段={out['surface_raw']} | 热处理字段={out['heat_raw']} | 孔数={out['hole_count']}")
        print(f"   [LEGACY n={len(out['legacy_ops'])}] {' / '.join(out['legacy_ops'])}")
        print(f"   [V2 {out['v2_family']} n={len(out['v2_ops'])}] {' / '.join(out['v2_ops'])}")
        print(f"   [V2 复核] {', '.join(out['v2_reviews'])}")


if __name__ == "__main__":
    main()
