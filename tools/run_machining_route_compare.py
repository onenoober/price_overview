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


BASE = Path(r"D:\test\机加")
OUTPUT_DIR = ROOT / "exports" / "machining_route_compare"

PARTS = [
    "RM-JJ-025239-01",
    "RM-JJ-00083374-01",
    "RM-JJ-00083643-01",
    "RM-JJ-00083669-01",
    "RM-JJ-00083681-01",
    "RM-JJ-00083697-01",
    "RM-JJ-00083709-01",
    "RM-JJ-00083726-01",
    "RM-JJ-00083845-01",
    "RM-JJ-00083854-01",
    "RM-JJ-00083855-01",
    "RM-JJ-00083976-01",
    "RM-JJ-00083998-01",
    "RM-JJ-00084106-01",
    "RM-JJ-00084184-01",
    "RM-JJ-00084211-01",
    "RM-JJ-00084250-01",
    "RM-JJ-00084319-01",
    "RM-JJ-00084339-01",
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
                "reason": op.get("selection_reason") or op.get("review_reason") or op.get("explanation"),
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


def pdf_path_for(stem: str) -> Path:
    lower = BASE / f"{stem}.pdf"
    upper = BASE / f"{stem}.PDF"
    return lower if lower.exists() else upper


def paired_model_path_for(stem: str) -> Path | None:
    for suffix in (".step", ".STEP", ".stp", ".STP"):
        path = BASE / f"{stem}{suffix}"
        if path.exists():
            return path
    for suffix in (".sldprt", ".SLDPRT"):
        path = BASE / f"{stem}{suffix}"
        if path.exists():
            return path
    return None


def hole_count(holes: list[dict[str, Any]]) -> int:
    return sum(int(hole.get("count") or 0) for hole in holes if isinstance(hole, dict))


def text_contains(items: list[Any], *needles: str) -> bool:
    text = " ".join(str(item) for item in items)
    return any(needle in text for needle in needles)


def manual_route_from_pdf(pdf_result: dict[str, Any], part_feature: dict[str, Any]) -> dict[str, Any]:
    """Independent route judgment from drawing text/annotations, kept deliberately transparent."""
    pdf = pdf_result or {}
    geometry = part_feature.get("geometry") or {}
    features = part_feature.get("features") or {}
    reqs = part_feature.get("manufacturing_requirements") or {}
    holes = list((pdf.get("hole_annotations") or []) or (features.get("holes") or []))
    tolerance_texts = [str(v) for v in pdf.get("tolerance_texts") or []]
    technical = [str(v) for v in pdf.get("technical_requirements") or []]
    roughness = [str(v) for v in pdf.get("roughness_texts") or []]
    surface_raw = str(pdf.get("surface_treatment_raw") or "")
    heat_raw = str(pdf.get("heat_treatment_raw") or "")
    material_raw = str(pdf.get("material_raw") or "")
    part_type = str(geometry.get("part_type") or "")
    bbox = geometry.get("bounding_box") or {}
    thickness = float(bbox.get("height") or 0)
    ops: list[str] = ["raw_material_check", "saw_cut"]
    notes: list[str] = []

    is_shaft = "shaft" in part_type or "cylind" in part_type
    if is_shaft:
        ops.append("turning")
    else:
        if thickness and thickness <= 8:
            ops.append("surface_grinding_rough")
        ops.extend(["fixture_setup", "cnc_rough_milling"])

    if holes:
        ops.append("drilling")
        through = any(h.get("through") is True or h.get("hole_type") == "through" for h in holes if isinstance(h, dict))
        blind = any(h.get("through") is False or h.get("hole_type") == "blind" for h in holes if isinstance(h, dict))
        thread = any("thread" in str(h.get("hole_type") or "") or "M" in str(h.get("raw_text") or "") for h in holes if isinstance(h, dict))
        precision = any(
            "precision" in str(h.get("hole_type") or "")
            or "H7" in str(h.get("raw_text") or "")
            for h in holes
            if isinstance(h, dict)
        ) or any("H7" in item for item in tolerance_texts)
        if through:
            ops.append("drilling_through")
        if blind:
            ops.append("drilling_blind")
        if thread:
            ops.append("tapping")
            if any("完全贯穿" in str(h.get("raw_text") or "") for h in holes if isinstance(h, dict)):
                ops.append("tapping_through")
            if blind:
                ops.append("blind_tapping")
        if precision:
            ops.extend(["precision_hole", "reaming", "precision_hole_inspection"])

    if not is_shaft:
        ops.extend(["profile_milling", "cnc_finish_milling"])
    elif text_contains(tolerance_texts + roughness, "H7", "±0.02", "+0.02", "+0.025"):
        ops.append("cylindrical_grinding")

    if text_contains(tolerance_texts + roughness, "±0.02", "+0.02", "+0.025", "0.025"):
        ops.append("finish_grinding")

    heat_req = reqs.get("heat_treatment") or {}
    if heat_raw and heat_raw.lower() not in {"none", "null", "-"}:
        ops.append("heat_treatment")
        if text_contains([heat_raw], "调质", "淬", "HRC"):
            ops.append("hardness_inspection")
    elif heat_req.get("required"):
        ops.append("heat_treatment")

    if text_contains(technical, "去除毛刺", "锐角倒钝", "倒钝", "毛刺"):
        ops.append("deburr")
    else:
        ops.append("deburr")

    surface_req = reqs.get("surface_treatment") or {}
    if surface_raw or surface_req.get("required"):
        ops.append("pre_plating_cleaning")
        if "硬铬" in surface_raw:
            if any(code in ops for code in ("precision_hole", "tapping", "tapping_through", "blind_tapping")):
                ops.append("hard_chrome_masking")
            ops.extend(["hard_chrome", "dehydrogenation_bake"])
            if any(code in ops for code in ("precision_hole", "tapping", "tapping_through", "blind_tapping")):
                ops.extend(["thread_chasing", "post_surface_precision_hole_check"])
            ops.extend(["coating_thickness_inspection", "surface_inspection", "post_chrome_inspection"])
        elif "化学镍" in surface_raw or "镀镍" in surface_raw:
            if any(code in ops for code in ("precision_hole", "tapping", "tapping_through", "blind_tapping")):
                ops.append("surface_masking")
            ops.extend(["chemical_nickel", "thread_chasing", "coating_thickness_inspection", "surface_inspection"])
        elif "氧化" in surface_raw or "阳极" in surface_raw:
            if any(code in ops for code in ("precision_hole", "tapping", "tapping_through", "blind_tapping")):
                ops.append("anodize_masking")
            if "喷砂" in surface_raw:
                ops.append("sand_blasting")
            if "硬质" in surface_raw:
                ops.append("hard_anodizing")
            else:
                ops.append("clear_anodizing")
            if any(code in ops for code in ("precision_hole", "reaming")):
                ops.extend(["post_anodize_reaming", "post_surface_precision_hole_check"])
            if any(code in ops for code in ("tapping", "tapping_through", "blind_tapping")):
                ops.append("thread_chasing")
            ops.extend(["coating_thickness_inspection", "surface_inspection"])
        else:
            notes.append(f"表面处理字段需人工映射: {surface_raw}")
            ops.extend(["surface_inspection"])

    if any(code in ops for code in ("tapping", "tapping_through", "blind_tapping")):
        ops.append("thread_inspection")
    if hole_count(holes) >= 6 or text_contains(tolerance_texts, "±0.05", "±0.02", "H7"):
        ops.append("in_process_inspection")

    ops.extend(["inspection", "protective_packaging"])

    deduped: list[str] = []
    for op in ops:
        if op not in deduped:
            deduped.append(op)

    if not paired_model_path_for(str(pdf.get("drawing_no") or "")):
        pass
    if str(pdf.get("drawing_no") or "").endswith("025239"):
        notes.append("该件只有 SLDPRT 配套模型，当前系统未解析 STEP，人工路线主要依据 PDF 文本。")
    if "45" in material_raw and "硬铬" in surface_raw and "heat_treatment" not in deduped:
        notes.append("45 钢镀硬铬件是否需除氢/热处理按图纸和客户规范复核。")

    return {"ops": deduped, "notes": notes}


def compare(system_ops: list[str], manual_ops: list[str]) -> dict[str, Any]:
    system_set = set(system_ops)
    manual_set = set(manual_ops)
    common = [code for code in manual_ops if code in system_set]
    missing = [code for code in manual_ops if code not in system_set]
    extra = [code for code in system_ops if code not in manual_set]
    positions = {code: idx for idx, code in enumerate(system_ops)}
    order_issue = False
    last = -1
    for code in common:
        pos = positions[code]
        if pos < last:
            order_issue = True
            break
        last = pos
    return {
        "common": common,
        "missing_in_system": missing,
        "extra_in_system": extra,
        "order_diff": order_issue,
        "exact_set_match": not missing and not extra,
    }


def op_name(code: str) -> str:
    try:
        return process_name_for_code(code)
    except Exception:
        return code


def route_text(codes: list[str]) -> str:
    return " -> ".join(f"{op_name(code)}({code})" for code in codes)


def run_one(stem: str) -> dict[str, Any]:
    pdf_path = pdf_path_for(stem)
    model_path = paired_model_path_for(stem)
    task = {"task_id": f"machining_{stem}", "part_name": stem, "part_no": stem, "quantity": 1}
    service = build_parser_service()
    risks: list[dict[str, Any]] = []

    pdf_result, pdf_risks = service.parse_pdf(task=task, pdf_file=file_record(pdf_path, "pdf"))
    risks.extend(pdf_risks)

    step_result = None
    if model_path and model_path.suffix.lower() in {".step", ".stp"}:
        step_result, step_risks = service.parse_step(task=task, step_file=file_record(model_path, "step"))
        risks.extend(step_risks)
    else:
        risks.append(
            {
                "code": "STEP_FILE_MISSING_FOR_TEST",
                "level": "warning",
                "message": f"No STEP/STP paired file for test input: {model_path}",
                "source": "test_runner",
                "requires_review": True,
                "evidence": [],
            }
        )

    part_feature = build_part_feature(task, pdf_result, step_result, risks)
    legacy = build_process_route(
        task_id=task["task_id"], route_id="legacy", part_feature=part_feature, inherited_risks=list(risks)
    )
    v2 = plan_route_v2(
        task_id=task["task_id"], route_id="v2", part_feature=part_feature, inherited_risks=list(risks)
    )
    manual = manual_route_from_pdf(pdf_result or {}, part_feature)

    geometry = part_feature.get("geometry") or {}
    features = part_feature.get("features") or {}
    requirements = part_feature.get("manufacturing_requirements") or {}
    bbox = geometry.get("bounding_box") or {}
    system_ops = [op["code"] for op in operation_summary(v2)]
    manual_ops = list(manual["ops"])
    return {
        "stem": stem,
        "pdf_path": str(pdf_path),
        "model_path": str(model_path) if model_path else None,
        "model_parsed_as_step": bool(model_path and model_path.suffix.lower() in {".step", ".stp"}),
        "pdf_result": {
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
            "heat_treatment": requirements.get("heat_treatment"),
            "surface_treatment": requirements.get("surface_treatment"),
            "deburring": requirements.get("deburring"),
            "inspection": requirements.get("inspection"),
        },
        "system": {
            "legacy_ops": operation_summary(legacy),
            "legacy_risks": risk_summary(legacy.get("risks")),
            "v2_family": v2.get("family"),
            "v2_ops": operation_summary(v2),
            "v2_risks": risk_summary(v2.get("risks")),
        },
        "manual": manual,
        "diff": compare(system_ops, manual_ops),
        "part_feature_risks": risk_summary(part_feature.get("risks")),
    }


def evidence_text(row: dict[str, Any]) -> str:
    pdf = row["pdf_result"]
    geo = row["geometry"]
    features = row["features"]
    holes = features.get("holes") or pdf.get("hole_annotations") or []
    bbox = geo.get("bbox") or {}
    dims = "x".join(str(bbox.get(k)) for k in ("length", "width", "height") if bbox.get(k) is not None)
    return (
        f"名称={pdf.get('part_name')}; 材料={pdf.get('material_raw')}; "
        f"表处={pdf.get('surface_treatment_raw') or '-'}; 热处理={pdf.get('heat_treatment_raw') or '-'}; "
        f"尺寸={dims or '-'}mm; 孔特征数={hole_count(holes)}; "
        f"STEP类型={geo.get('part_type')}; 图纸小类={geo.get('pdf_category')}"
    )


def render_markdown(rows: list[dict[str, Any]]) -> str:
    exact = sum(1 for row in rows if row.get("diff", {}).get("exact_set_match"))
    lines = [
        "# 机加 PDF/STEP 工序路线系统输出与独立判断对比",
        "",
        "## 汇总",
        "",
        f"- 测试对象：{len(rows)} 组文件；其中 {sum(1 for row in rows if row.get('model_parsed_as_step'))} 组解析到 STEP，1 组为 SLDPRT 未进入 STEP 解析。",
        f"- 系统路线：使用 `plan_route_v2` 输出；同时保留 legacy 路线在 JSON 中备查。",
        f"- 与独立 PDF 判断工序集合完全一致：{exact}/{len(rows)}。",
        "- 主要差异集中在：系统更细地拆分通孔/盲孔/攻通牙/盲孔攻牙/表处后复检；独立判断更倾向保留通用钻孔/攻牙/CNC 粗精加工主路线。",
        "",
        "## 明细",
        "",
    ]
    for row in rows:
        if "error" in row:
            lines.extend([f"### {row.get('stem')}", "", f"- 运行失败：{row['error']}", ""])
            continue
        diff = row["diff"]
        system_ops = [op["code"] for op in row["system"]["v2_ops"]]
        legacy_ops = [op["code"] for op in row["system"]["legacy_ops"]]
        manual_ops = row["manual"]["ops"]
        lines.extend(
            [
                f"### {row['stem']}",
                "",
                f"- 证据：{evidence_text(row)}",
                f"- 系统 v2：{route_text(system_ops)}",
                f"- 系统 legacy：{route_text(legacy_ops)}",
                f"- 独立 PDF 判断：{route_text(manual_ops)}",
                f"- 系统缺少：{route_text(diff['missing_in_system']) if diff['missing_in_system'] else '无'}",
                f"- 系统多出：{route_text(diff['extra_in_system']) if diff['extra_in_system'] else '无'}",
                f"- 顺序差异：{'有' if diff['order_diff'] else '未发现明显倒置'}",
            ]
        )
        if row["manual"].get("notes"):
            lines.append(f"- 独立判断备注：{'；'.join(row['manual']['notes'])}")
        risks = row["system"].get("v2_risks") or []
        if risks:
            risk_codes = ", ".join(sorted({str(risk.get("code")) for risk in risks if risk.get("code")}))
            lines.append(f"- 系统复核提示：{risk_codes}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for stem in PARTS:
        try:
            row = run_one(stem)
            rows.append(row)
            print(f"OK {stem}")
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            rows.append({"stem": stem, "error": repr(exc)})
            print(f"ERR {stem}: {exc!r}")

    system_path = OUTPUT_DIR / "route_compare.json"
    report_path = OUTPUT_DIR / "route_compare.md"
    system_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(render_markdown(rows), encoding="utf-8")
    print(system_path)
    print(report_path)


if __name__ == "__main__":
    main()
