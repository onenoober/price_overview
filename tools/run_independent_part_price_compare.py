from __future__ import annotations

import json
import os
import sys
import traceback
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("PRICE_PDF_VISION_MODE", "off")
os.environ.setdefault("PRICE_ROUTE_ENGINE_V2", "1")
os.environ.setdefault("PRICE_STEP_PARSER_BACKEND", "auto")

from backend.app.parser_service import build_parser_service
from backend.app.part_feature_builder import build_part_feature
from backend.app.pricing_core import build_pricing_core_service
from tools.run_requested_price_diff_audit import (
    SAMPLES,
    NullPriceProvider,
    file_record,
    final_output_price,
)


CHINA_TZ = timezone(timedelta(hours=8))
OUTPUT_DIR = REPO_ROOT / "exports" / "independent_part_price_compare"

MATERIAL_PRICES = {
    "Q235A": 4.5,
    "Q235": 4.5,
    "45": 12.0,
    "45#": 12.0,
    "S45C": 12.0,
    "40CR": 8.0,
    "40Cr": 8.0,
    "SUS304": 32.0,
    "304": 32.0,
    "6061": 28.0,
    "6061-T6": 28.0,
    "AL6061": 28.0,
}

MATERIAL_DENSITIES = {
    "Q235A": 0.00000785,
    "Q235": 0.00000785,
    "45": 0.00000785,
    "45#": 0.00000785,
    "S45C": 0.00000785,
    "40CR": 0.00000785,
    "40Cr": 0.00000785,
    "SUS304": 0.00000793,
    "304": 0.00000793,
    "6061": 0.00000270,
    "6061-T6": 0.00000270,
    "AL6061": 0.00000270,
}


def now_iso() -> str:
    return datetime.now(CHINA_TZ).isoformat(timespec="seconds")


def money(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def round_up_to_10(value: float) -> float:
    if value <= 0:
        return 0.0
    return float(int((value + 9.99) // 10 * 10))


def number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def norm_text(value: Any) -> str:
    return str(value or "").strip()


def material_key(raw: Any) -> str:
    text = norm_text(raw).upper().replace(" ", "")
    for key in sorted(MATERIAL_PRICES, key=len, reverse=True):
        if key.upper().replace(" ", "") in text:
            return key
    return text or "UNKNOWN"


def material_unit_price(raw: Any) -> float:
    return MATERIAL_PRICES.get(material_key(raw), 12.0)


def material_density(raw: Any) -> float:
    return MATERIAL_DENSITIES.get(material_key(raw), 0.00000785)


def convert_weight_to_kg(value: Any, unit: Any) -> float | None:
    numeric = number(value)
    if numeric is None:
        return None
    text = str(unit or "kg").lower()
    if text == "g":
        return numeric / 1000
    return numeric


def measured_value(measure: dict[str, Any] | None) -> float | None:
    if not isinstance(measure, dict):
        return None
    return number(measure.get("value"))


def bbox_dimensions(bbox: dict[str, Any]) -> tuple[float, float, float] | None:
    dims = [number(bbox.get(key)) for key in ("length", "width", "height")]
    if any(value is None for value in dims):
        return None
    return (float(dims[0]), float(dims[1]), float(dims[2]))


def bbox_text(bbox: dict[str, Any]) -> str:
    dims = bbox_dimensions(bbox)
    if dims is None:
        return "-"
    return f"{dims[0]:g}x{dims[1]:g}x{dims[2]:g} {bbox.get('unit') or 'mm'}"


def estimate_weight_kg(
    *,
    material_raw: Any,
    geometry: dict[str, Any],
    notes: list[str],
) -> float:
    for key, label in (("step_net_weight", "STEP net weight"), ("pdf_weight", "PDF weight")):
        measure = geometry.get(key)
        if isinstance(measure, dict):
            kg = convert_weight_to_kg(measure.get("value"), measure.get("unit"))
            if kg is not None and kg > 0:
                notes.append(f"weight uses {label}: {kg:.4g} kg")
                return kg

    bbox = geometry.get("bounding_box") or {}
    dims = bbox_dimensions(bbox)
    if dims is None:
        notes.append("weight fallback: missing STEP/PDF weight and incomplete bounding box, use 1 kg placeholder")
        return 1.0
    volume = dims[0] * dims[1] * dims[2]
    kg = volume * material_density(material_raw) * 1.15
    notes.append(f"weight estimated from bounding box with 15% stock allowance: {kg:.4g} kg")
    return kg


def surface_area_m2(geometry: dict[str, Any]) -> float:
    measure = geometry.get("surface_area")
    if isinstance(measure, dict):
        value = measured_value(measure)
        unit = str(measure.get("unit") or "mm2").lower()
        if value is not None:
            if unit in {"m2", "m^2"}:
                return value
            if unit in {"cm2", "cm^2"}:
                return value / 10_000
            return value / 1_000_000
    dims = bbox_dimensions(geometry.get("bounding_box") or {})
    if dims is None:
        return 0.01
    l, w, h = dims
    return 2 * (l * w + l * h + w * h) / 1_000_000


def hole_summary(features: dict[str, Any]) -> dict[str, int]:
    holes = features.get("holes") or []
    total = 0
    tapping = 0
    precision = 0
    countersink = 0
    for hole in holes:
        if not isinstance(hole, dict):
            continue
        count = int(number(hole.get("count")) or 1)
        total += count
        text = json.dumps(hole, ensure_ascii=False).lower()
        if "thread" in text or '"m' in text or "tapping" in text:
            tapping += count
        if "h7" in text or "precision" in text or "ream" in text:
            precision += count
        if "counter" in text or "countersink" in text or "counterbore" in text:
            countersink += count
    summary = features.get("hole_summary") or {}
    if total == 0:
        total = int(number(summary.get("total_count")) or 0)
    return {
        "total": total,
        "tapping": tapping,
        "precision": precision,
        "countersink": countersink,
    }


def text_blob(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        if isinstance(value, dict):
            parts.append(json.dumps(value, ensure_ascii=False))
        elif isinstance(value, list):
            parts.extend(str(item) for item in value)
        else:
            parts.append(str(value or ""))
    return " ".join(parts).lower()


def has_surface_treatment(requirements: dict[str, Any], pdf_result: dict[str, Any]) -> tuple[str | None, str]:
    surface = requirements.get("surface_treatment") or {}
    raw = norm_text(surface.get("raw_text") or pdf_result.get("surface_treatment_raw"))
    code = norm_text(surface.get("standard_code"))
    blob = text_blob(raw, code)
    if not raw and not code:
        return None, ""
    if "hard_chrome" in blob or "chrome" in blob or "硬铬" in blob:
        return "hard_chrome", raw or code
    if "chemical_nickel" in blob or "nickel" in blob or "镍" in blob:
        return "chemical_nickel", raw or code
    if "hard_anod" in blob or "硬质" in blob:
        return "hard_anodizing", raw or code
    if "anod" in blob or "氧化" in blob or "阳极" in blob:
        return "anodizing", raw or code
    if "sand" in blob or "喷砂" in blob:
        return "sand_blasting", raw or code
    if "powder" in blob or "喷塑" in blob:
        return "powder_coating", raw or code
    return "surface_review", raw or code


def needs_heat_treatment(requirements: dict[str, Any], pdf_result: dict[str, Any]) -> tuple[bool, str]:
    heat = requirements.get("heat_treatment") or {}
    raw = norm_text(heat.get("raw_text") or pdf_result.get("heat_treatment_raw"))
    required = bool(heat.get("required")) or bool(raw)
    if raw.lower() in {"none", "null", "-", "n/a"}:
        required = False
    return required, raw


def independent_estimate(
    *,
    pdf_result: dict[str, Any],
    part_feature: dict[str, Any],
) -> dict[str, Any]:
    geometry = part_feature.get("geometry") or {}
    features = part_feature.get("features") or {}
    requirements = part_feature.get("manufacturing_requirements") or {}
    material_raw = (
        pdf_result.get("material_raw")
        or (part_feature.get("material") or {}).get("raw_text")
        or "UNKNOWN"
    )
    part_type = norm_text(geometry.get("part_type"))
    bbox = geometry.get("bounding_box") or {}
    dims = bbox_dimensions(bbox)
    ordered_dims = sorted(dims or (0.0, 0.0, 0.0), reverse=True)
    max_dim = ordered_dims[0] if ordered_dims else 0.0
    mid_dim = ordered_dims[1] if len(ordered_dims) > 1 else 0.0
    min_dim = ordered_dims[2] if len(ordered_dims) > 2 else 0.0
    face_area = max_dim * mid_dim
    holes = hole_summary(features)
    complexity = features.get("complexity") or {}
    complexity_score = number(complexity.get("complexity_score"))
    if complexity_score is None:
        complexity_score = 30 + holes["total"] * 1.5
        if max_dim >= 800:
            complexity_score += 20
        if "complex" in part_type:
            complexity_score += 15

    notes: list[str] = []
    weight = estimate_weight_kg(material_raw=material_raw, geometry=geometry, notes=notes)
    material_cost = round(max(weight * material_unit_price(material_raw) * 1.08, 5.0), 2)

    breakdown: list[dict[str, Any]] = [
        {
            "name": "material",
            "amount": material_cost,
            "basis": f"{weight:.4g} kg x {material_unit_price(material_raw):g} CNY/kg x 1.08",
        }
    ]

    saw_cut = 25.0 if max_dim >= 800 or weight >= 10 else 15.0
    breakdown.append({"name": "saw_cut", "amount": saw_cut, "basis": "blank preparation"})

    shaft_like = "shaft" in part_type
    large_plate = max_dim >= 800 or ("large" in part_type and "plate" in part_type)
    surface_m2 = surface_area_m2(geometry)

    process_notes: list[str] = []
    if shaft_like:
        turning_hours = 0.35 + max_dim / 450 + mid_dim / 120 + holes["total"] * 0.025
        turning = max(turning_hours * 120, 80)
        breakdown.append(
            {
                "name": "turning",
                "amount": round(turning, 2),
                "basis": f"{turning_hours:.2f} h x 120 CNY/h, min 80",
            }
        )
        process_notes.append("shaft-like part priced mainly by turning")
    else:
        cnc_hours = 0.45 + face_area / 45_000 + holes["total"] * 0.025 + complexity_score * 0.006
        if min_dim and min_dim <= 12:
            cnc_hours += 0.15
        if large_plate:
            cnc_hours += face_area / 90_000
        cnc_min = 150 if large_plate else (120 if "complex" in part_type else 100)
        cnc = max(cnc_hours * 130, cnc_min)
        breakdown.append(
            {
                "name": "cnc_milling",
                "amount": round(cnc, 2),
                "basis": f"{cnc_hours:.2f} h x 130 CNY/h, min {cnc_min}",
            }
        )
        process_notes.append("non-shaft part priced mainly by CNC milling")

    if holes["total"]:
        drilling = holes["total"] * 5
        breakdown.append({"name": "drilling", "amount": round(drilling, 2), "basis": f"{holes['total']} holes x 5"})
    if holes["countersink"]:
        amount = holes["countersink"] * 12
        breakdown.append({"name": "counterbore/countersink", "amount": amount, "basis": f"{holes['countersink']} x 12"})
    if holes["tapping"]:
        amount = holes["tapping"] * 12
        breakdown.append({"name": "tapping", "amount": amount, "basis": f"{holes['tapping']} x 12"})
    if holes["precision"]:
        amount = holes["precision"] * 35
        breakdown.append({"name": "precision_hole", "amount": amount, "basis": f"{holes['precision']} x 35"})

    precision_blob = text_blob(
        pdf_result.get("tolerance_texts"),
        pdf_result.get("roughness_texts"),
        requirements.get("technical_requirements"),
        part_feature.get("risks"),
    )
    if "h7" in precision_blob or "precision" in precision_blob or "high_precision" in precision_blob:
        grind = max(face_area / 30_000 * 90, 60)
        breakdown.append(
            {
                "name": "finish_grinding_or_precision_finish",
                "amount": round(grind, 2),
                "basis": "precision/tolerance signal from PDF or fusion risks",
            }
        )

    heat_required, heat_raw = needs_heat_treatment(requirements, pdf_result)
    if heat_required:
        heat = max(weight * 18, 45)
        breakdown.append({"name": "heat_treatment", "amount": round(heat, 2), "basis": heat_raw or "heat treatment required"})

    surface_code, surface_raw = has_surface_treatment(requirements, pdf_result)
    if surface_code:
        if surface_code == "chemical_nickel":
            amount = max(surface_m2 * 900, 100)
            basis = f"{surface_m2:.4g} m2 x 900, min 100"
        elif surface_code == "hard_chrome":
            amount = max(surface_m2 * 1000, 120)
            basis = f"{surface_m2:.4g} m2 x 1000, min 120"
        elif surface_code == "hard_anodizing":
            amount = max(surface_m2 * 240, 100)
            basis = f"{surface_m2:.4g} m2 x 240, min 100"
        elif surface_code == "anodizing":
            amount = max(surface_m2 * 150, 80)
            basis = f"{surface_m2:.4g} m2 x 150, min 80"
        elif surface_code == "sand_blasting":
            amount = max(surface_m2 * 90, 40)
            basis = f"{surface_m2:.4g} m2 x 90, min 40"
        elif surface_code == "powder_coating":
            amount = max(surface_m2 * 100, 60)
            basis = f"{surface_m2:.4g} m2 x 100, min 60"
        else:
            amount = 80
            basis = "surface treatment present but type needs review"
        breakdown.append(
            {
                "name": surface_code,
                "amount": round(amount, 2),
                "basis": f"{surface_raw}; {basis}",
            }
        )

    deburr = 25.0 if complexity_score >= 60 or holes["total"] >= 10 else 18.0
    inspection = 35.0 if holes["precision"] or "h7" in precision_blob else 25.0
    packaging = 15.0
    breakdown.extend(
        [
            {"name": "deburr", "amount": deburr, "basis": "manual finishing allowance"},
            {"name": "inspection", "amount": inspection, "basis": "drawing inspection / packaging review"},
            {"name": "packaging", "amount": packaging, "basis": "protective packaging"},
        ]
    )

    material_total = material_cost
    surface_total = sum(
        item["amount"]
        for item in breakdown
        if item["name"]
        in {
            "chemical_nickel",
            "hard_chrome",
            "hard_anodizing",
            "anodizing",
            "sand_blasting",
            "powder_coating",
            "surface_review",
        }
    )
    process_total = round(
        sum(item["amount"] for item in breakdown) - material_total - surface_total,
        2,
    )
    management_fee = round(material_total * 0.05, 2)
    tax = round((process_total + surface_total + management_fee) * 0.13, 2)
    calculated = round(material_total + process_total + surface_total + management_fee + tax, 2)
    quote = round_up_to_10(calculated)

    reasons = []
    reasons.extend(process_notes)
    if holes["total"]:
        reasons.append(f"holes={holes['total']}, tapping={holes['tapping']}, precision={holes['precision']}")
    if surface_code:
        reasons.append(f"surface={surface_code}")
    if heat_required:
        reasons.append("heat treatment included")
    reasons.extend(notes)

    return {
        "quote": quote,
        "calculated": calculated,
        "material_amount": material_total,
        "process_amount": process_total,
        "surface_amount": round(surface_total, 2),
        "management_fee": management_fee,
        "tax": tax,
        "weight_kg": round(weight, 5),
        "surface_area_m2": round(surface_m2, 6),
        "hole_summary": holes,
        "complexity_score": round(complexity_score, 2),
        "breakdown": breakdown,
        "reasons": reasons,
    }


def run_one(sample_type: str, pdf_path: Path, step_path: Path) -> dict[str, Any]:
    task = {
        "task_id": f"independent_price_compare_{pdf_path.stem}",
        "part_name": pdf_path.stem,
        "part_no": pdf_path.stem,
        "quantity": 1,
    }
    parser_service = build_parser_service()
    risks: list[dict[str, Any]] = []
    pdf_result, pdf_risks = parser_service.parse_pdf(task=task, pdf_file=file_record(pdf_path, "pdf"))
    risks.extend(pdf_risks)
    step_result, step_risks = parser_service.parse_step(task=task, step_file=file_record(step_path, "step"))
    risks.extend(step_risks)
    part_feature = build_part_feature(task, pdf_result, step_result, risks)

    pricing = build_pricing_core_service(
        material_price_provider=NullPriceProvider(),
        material_estimate_provider=NullPriceProvider(),
        surface_treatment_price_provider=NullPriceProvider(),
        surface_treatment_estimate_provider=NullPriceProvider(),
    ).build_quote(
        task_id=task["task_id"],
        quote_id=f"quote_independent_price_compare_{pdf_path.stem}",
        part_feature=part_feature,
        risks=part_feature.get("risks", []),
        priced_at=now_iso(),
        price_version="independent-part-price-compare-v1",
        use_market_price_search=False,
    )
    system_summary = pricing.quote_result.get("summary") or {}
    system_price = final_output_price(system_summary)
    independent = independent_estimate(pdf_result=pdf_result or {}, part_feature=part_feature)
    diff = round(system_price - independent["quote"], 2)
    diff_rate = round(diff / independent["quote"] * 100, 2) if independent["quote"] else 0.0
    geometry = part_feature.get("geometry") or {}
    features = part_feature.get("features") or {}
    requirements = part_feature.get("manufacturing_requirements") or {}
    return {
        "type": sample_type,
        "stem": pdf_path.stem,
        "pdf": str(pdf_path),
        "step": str(step_path),
        "system_status": pricing.quote_result.get("status"),
        "system_price": system_price,
        "system_calculated": money(system_summary.get("system_calculated_amount")),
        "independent_price": independent["quote"],
        "independent_calculated": independent["calculated"],
        "diff_system_minus_independent": diff,
        "diff_rate_percent": diff_rate,
        "part_name": (pdf_result or {}).get("part_name"),
        "material": (pdf_result or {}).get("material_raw") or (part_feature.get("material") or {}).get("raw_text"),
        "surface_treatment": (pdf_result or {}).get("surface_treatment_raw"),
        "heat_treatment": (pdf_result or {}).get("heat_treatment_raw"),
        "part_type": geometry.get("part_type"),
        "bounding_box": geometry.get("bounding_box") or {},
        "hole_count": independent["hole_summary"]["total"],
        "precision_hole_count": independent["hole_summary"]["precision"],
        "system_operations": [
            item.get("operation_code")
            for item in pricing.process_route.get("operations", [])
            if item.get("operation_code")
        ],
        "independent_estimate": independent,
        "risk_codes": sorted(
            {
                risk.get("code")
                for risk in pricing.quote_result.get("risks", [])
                if risk.get("code")
            }
        ),
        "pdf_evidence": {
            "technical_requirements": (pdf_result or {}).get("technical_requirements") or [],
            "tolerance_texts": (pdf_result or {}).get("tolerance_texts") or [],
            "roughness_texts": (pdf_result or {}).get("roughness_texts") or [],
            "hole_annotations": (pdf_result or {}).get("hole_annotations") or [],
        },
        "feature_evidence": {
            "complexity": features.get("complexity") or {},
            "manufacturing_requirements": requirements,
        },
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok_rows = [row for row in rows if "error" not in row]
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ok_rows:
        by_type[row["type"]].append(row)
    type_summary = {}
    for sample_type, items in sorted(by_type.items()):
        diffs = [item["diff_system_minus_independent"] for item in items]
        abs_diffs = [abs(item["diff_system_minus_independent"]) for item in items]
        type_summary[sample_type] = {
            "count": len(items),
            "system_total": round(sum(item["system_price"] for item in items), 2),
            "independent_total": round(sum(item["independent_price"] for item in items), 2),
            "diff_total": round(sum(diffs), 2),
            "average_abs_diff": round(sum(abs_diffs) / len(abs_diffs), 2) if abs_diffs else 0,
        }
    return {
        "sample_count": len(rows),
        "success_count": len(ok_rows),
        "error_count": len(rows) - len(ok_rows),
        "system_total": round(sum(item["system_price"] for item in ok_rows), 2),
        "independent_total": round(sum(item["independent_price"] for item in ok_rows), 2),
        "diff_total": round(sum(item["diff_system_minus_independent"] for item in ok_rows), 2),
        "average_abs_diff": round(
            sum(abs(item["diff_system_minus_independent"]) for item in ok_rows) / len(ok_rows),
            2,
        )
        if ok_rows
        else 0,
        "max_abs_diff": max(
            (abs(item["diff_system_minus_independent"]) for item in ok_rows),
            default=0,
        ),
        "type_summary": type_summary,
    }


def difference_label(diff: float, rate: float) -> str:
    if abs(diff) < 0.01:
        return "一致"
    direction = "系统高于独立估价" if diff > 0 else "系统低于独立估价"
    if abs(rate) >= 35:
        return f"{direction}，差异很大"
    if abs(rate) >= 15:
        return f"{direction}，差异中等"
    return f"{direction}，差异较小"


def top_breakdown_text(items: list[dict[str, Any]]) -> str:
    top = sorted(items, key=lambda item: item["amount"], reverse=True)[:5]
    return "; ".join(f"{item['name']}={item['amount']:.2f}" for item in top)


def render_report(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    ok_rows = [row for row in rows if "error" not in row]
    error_rows = [row for row in rows if "error" in row]
    lines = [
        "# 单件系统报价与独立图纸估价对比分析",
        "",
        "## 1. 结论说明",
        "",
        f"- 本次对用户指定的 {summary['sample_count']} 套零件逐件对比，成功 {summary['success_count']} 套，失败 {summary['error_count']} 套。",
        f"- 系统报价合计 {summary['system_total']:.2f} CNY；独立图纸估价合计 {summary['independent_total']:.2f} CNY；系统-独立差额合计 {summary['diff_total']:.2f} CNY。",
        f"- 单件平均绝对差额 {summary['average_abs_diff']:.2f} CNY，最大单件绝对差额 {summary['max_abs_diff']:.2f} CNY。",
        "- 独立图纸估价不读取系统报价明细；它只使用 PDF/STEP 解析出的材料、尺寸/重量、孔特征、精度信号、热处理和表面处理要求，再按下方透明规则估价。",
        "- 该估价是快速核价口径，用于发现系统价偏高/偏低风险，不代表供应商最终报价。",
        "",
        "## 2. 独立估价规则",
        "",
        "- 材料：优先用 STEP/PDF 重量；缺失时用外包络体积 x 材料密度 x 15%备料余量。材料单价：Q235A 4.5、45/S45C 12、40Cr 8、SUS304 32、6061 28 CNY/kg。",
        "- 加工：轴类按车削小时估；非轴类按 CNC 小时估，小时由主平面面积、孔数、复杂度和大板尺寸修正。",
        "- 孔加工：普通孔 5 CNY/孔，沉孔/锪孔 12 CNY/孔，攻牙 12 CNY/孔，精孔 35 CNY/孔。",
        "- 精加工：出现 H7、高精度或融合风险中的 precision 信号时，增加精加工/磨削估价。",
        "- 表面处理：化学镍 900 CNY/m2 起步 100；硬铬 1000 CNY/m2 起步 120；硬质阳极 240 CNY/m2 起步 100；普通阳极 150 CNY/m2 起步 80。",
        "- 税费和管理费：材料管理费 5%；税费按加工费+表处费+管理费的 13%；最终价向上取整到 10 元。",
        "",
        "## 3. 分类汇总",
        "",
        "| 类型 | 数量 | 系统合计 | 独立估价合计 | 系统-独立 | 平均绝对差额 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for sample_type, item in summary["type_summary"].items():
        lines.append(
            f"| {sample_type} | {item['count']} | {item['system_total']:.2f} | "
            f"{item['independent_total']:.2f} | {item['diff_total']:.2f} | "
            f"{item['average_abs_diff']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## 4. 逐件对比",
            "",
            "| 类型 | 零件 | 材料 | 类型/尺寸 | 系统价 | 独立估价 | 差额 | 差异率 | 判断 | 独立估价主要构成 |",
            "|---|---|---|---|---:|---:|---:|---:|---|---|",
        ]
    )
    for row in ok_rows:
        lines.append(
            f"| {row['type']} | {row['stem']} | {row.get('material') or ''} | "
            f"{row.get('part_type') or ''}; {bbox_text(row.get('bounding_box') or {})} | "
            f"{row['system_price']:.2f} | {row['independent_price']:.2f} | "
            f"{row['diff_system_minus_independent']:.2f} | {row['diff_rate_percent']:.2f}% | "
            f"{difference_label(row['diff_system_minus_independent'], row['diff_rate_percent'])} | "
            f"{top_breakdown_text(row['independent_estimate']['breakdown'])} |"
        )

    lines.extend(["", "## 5. 单件分析", ""])
    for row in ok_rows:
        estimate = row["independent_estimate"]
        reasons = "；".join(estimate["reasons"][:6])
        risk_text = ", ".join(row["risk_codes"][:8])
        lines.extend(
            [
                f"### {row['stem']}",
                "",
                f"- 系统价：{row['system_price']:.2f} CNY；独立估价：{row['independent_price']:.2f} CNY；差额：{row['diff_system_minus_independent']:.2f} CNY（{row['diff_rate_percent']:.2f}%）。",
                f"- 判断：{difference_label(row['diff_system_minus_independent'], row['diff_rate_percent'])}。",
                f"- 图纸/模型依据：材料={row.get('material') or '-'}；表处={row.get('surface_treatment') or '-'}；热处理={row.get('heat_treatment') or '-'}；尺寸={bbox_text(row.get('bounding_box') or {})}；孔数={row['hole_count']}；精孔={row['precision_hole_count']}。",
                f"- 独立估价原因：{reasons or '未提取到额外特征，按基础加工估价。'}",
                f"- 独立估价拆分：材料 {estimate['material_amount']:.2f}，加工 {estimate['process_amount']:.2f}，表处 {estimate['surface_amount']:.2f}，管理费 {estimate['management_fee']:.2f}，税费 {estimate['tax']:.2f}，未取整 {estimate['calculated']:.2f}。",
                f"- 系统复核风险：{risk_text or '无'}。",
                "",
            ]
        )

    lines.extend(["## 6. 失败样件", ""])
    if error_rows:
        for row in error_rows:
            lines.append(f"- {row.get('stem')}: {row.get('error')}")
    else:
        lines.append("无。")
    lines.extend(
        [
            "",
            "## 7. 输出文件",
            "",
            f"- JSON 明细：`{OUTPUT_DIR / 'independent_part_price_compare.json'}`",
            f"- 本文档：`{OUTPUT_DIR / 'independent_part_price_compare.md'}`",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for sample_type, pdf_text, step_text in SAMPLES:
        pdf_path = Path(pdf_text)
        step_path = Path(step_text)
        print(f"RUN {sample_type} {pdf_path.stem}", flush=True)
        try:
            rows.append(run_one(sample_type, pdf_path, step_path))
            print(f"OK {pdf_path.stem}", flush=True)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            rows.append(
                {
                    "type": sample_type,
                    "stem": pdf_path.stem,
                    "pdf": str(pdf_path),
                    "step": str(step_path),
                    "error": repr(exc),
                }
            )
            print(f"ERR {pdf_path.stem}: {exc!r}", flush=True)
    summary = summarize(rows)
    payload = {
        "run_at": now_iso(),
        "environment": {
            "PRICE_PDF_VISION_MODE": os.environ.get("PRICE_PDF_VISION_MODE"),
            "PRICE_ROUTE_ENGINE_V2": os.environ.get("PRICE_ROUTE_ENGINE_V2"),
            "PRICE_STEP_PARSER_BACKEND": os.environ.get("PRICE_STEP_PARSER_BACKEND"),
            "market_price_search": False,
        },
        "summary": summary,
        "results": rows,
    }
    (OUTPUT_DIR / "independent_part_price_compare.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "independent_part_price_compare.md").write_text(
        render_report(rows, summary),
        encoding="utf-8",
    )
    print(OUTPUT_DIR, flush=True)


if __name__ == "__main__":
    main()
