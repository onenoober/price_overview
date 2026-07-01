from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.process_dictionary import process_name_for_code


OUTPUT_DIR = ROOT / "exports" / "axis_route_analysis"
SYSTEM_JSON = OUTPUT_DIR / "system_routes.json"


MANUAL_ROUTES: dict[str, dict[str, Any]] = {
    "RM-JJ-00083648-01": {
        "ops": [
            "raw_material_check",
            "saw_cut",
            "turning",
            "drilling",
            "countersink",
            "stress_relief",
            "heat_treatment",
            "straightening",
            "cylindrical_grinding",
            "deburr",
            "pre_plating_cleaning",
            "hard_chrome_masking",
            "hard_chrome",
            "dehydrogenation_bake",
            "post_chrome_polishing",
            "inspection",
            "post_chrome_inspection",
            "coating_thickness_inspection",
            "surface_inspection",
            "protective_packaging",
        ],
        "judgement": "细长滚筒，40Cr 淬硬后镀硬铬；长径比接近 15，建议把校直/跳动复核列入路线。",
    },
    "RM-JJ-00083692-01": {
        "ops": [
            "raw_material_check",
            "saw_cut",
            "turning",
            "drilling",
            "countersink",
            "stress_relief",
            "heat_treatment",
            "straightening",
            "cylindrical_grinding",
            "deburr",
            "pre_plating_cleaning",
            "hard_chrome_masking",
            "hard_chrome",
            "dehydrogenation_bake",
            "post_chrome_polishing",
            "inspection",
            "post_chrome_inspection",
            "coating_thickness_inspection",
            "surface_inspection",
            "protective_packaging",
        ],
        "judgement": "比 83648 更长的滚筒，同样按车削、孔加工、热处理校直、外圆磨、硬铬链处理。",
    },
    "RM-JJ-00083816-01": {
        "ops": [
            "raw_material_check",
            "saw_cut",
            "turning",
            "finish_grinding",
            "deburr",
            "pre_plating_cleaning",
            "hard_chrome",
            "dehydrogenation_bake",
            "post_chrome_polishing",
            "inspection",
            "coating_thickness_inspection",
            "surface_inspection",
            "protective_packaging",
        ],
        "judgement": "薄垫圈类零件，人工判断更偏端面/厚度精整；遮蔽是否需要取决于图纸是否要求局部镀。",
    },
    "RM-JJ-00083824-01": {
        "ops": [
            "raw_material_check",
            "saw_cut",
            "turning",
            "drilling",
            "tapping",
            "shaft_milling",
            "stress_relief",
            "heat_treatment",
            "straightening",
            "cylindrical_grinding",
            "deburr",
            "pre_plating_cleaning",
            "hard_chrome_masking",
            "hard_chrome",
            "dehydrogenation_bake",
            "post_chrome_polishing",
            "thread_chasing",
            "inspection",
            "post_chrome_inspection",
            "coating_thickness_inspection",
            "surface_inspection",
            "protective_packaging",
        ],
        "judgement": "动力轴存在 M5 螺纹和复杂轴面迹象，建议把轴上铣削/侧面特征作为复核工序列出。",
    },
    "RM-JJ-00083835-01": {
        "ops": [
            "raw_material_check",
            "saw_cut",
            "turning",
            "drilling",
            "tapping",
            "stress_relief",
            "heat_treatment",
            "cylindrical_grinding",
            "deburr",
            "pre_plating_cleaning",
            "hard_chrome_masking",
            "hard_chrome",
            "dehydrogenation_bake",
            "post_chrome_polishing",
            "thread_chasing",
            "inspection",
            "post_chrome_inspection",
            "coating_thickness_inspection",
            "surface_inspection",
            "protective_packaging",
        ],
        "judgement": "定位圈带 M4 与多孔，短件无需常规校直；孔和螺纹应在镀后复检/清牙。",
    },
    "RM-JJ-00083848-01": {
        "ops": [
            "raw_material_check",
            "saw_cut",
            "turning",
            "stress_relief",
            "heat_treatment",
            "finish_grinding",
            "deburr",
            "pre_plating_cleaning",
            "hard_chrome",
            "dehydrogenation_bake",
            "post_chrome_polishing",
            "inspection",
            "post_chrome_inspection",
            "coating_thickness_inspection",
            "surface_inspection",
            "protective_packaging",
        ],
        "judgement": "定位垫圈为薄环件，人工路线更倾向精磨端面/厚度；硬铬遮蔽需按局部镀要求确认。",
    },
    "RM-JJ-00083853-01": {
        "ops": [
            "raw_material_check",
            "saw_cut",
            "turning",
            "drilling",
            "tapping",
            "stress_relief",
            "heat_treatment",
            "cylindrical_grinding",
            "deburr",
            "pre_plating_cleaning",
            "hard_chrome_masking",
            "hard_chrome",
            "dehydrogenation_bake",
            "post_chrome_polishing",
            "thread_chasing",
            "inspection",
            "post_chrome_inspection",
            "coating_thickness_inspection",
            "surface_inspection",
            "protective_packaging",
        ],
        "judgement": "隔套带 M4 与多个浅孔，按车削件加孔/螺纹、热处理、硬铬链处理。",
    },
    "RM-JJ-00083858-01": {
        "ops": [
            "raw_material_check",
            "saw_cut",
            "turning",
            "stress_relief",
            "heat_treatment",
            "finish_grinding",
            "deburr",
            "pre_plating_cleaning",
            "hard_chrome",
            "dehydrogenation_bake",
            "post_chrome_polishing",
            "inspection",
            "post_chrome_inspection",
            "coating_thickness_inspection",
            "surface_inspection",
            "protective_packaging",
        ],
        "judgement": "轴承隔套为短薄环件，建议精磨端面/厚度；遮蔽是否需要按镀层范围复核。",
    },
    "RM-JJ-00083981-01": {
        "ops": [
            "raw_material_check",
            "saw_cut",
            "turning",
            "drilling",
            "deburr",
            "inspection",
            "protective_packaging",
        ],
        "judgement": "SUS304 弧形轮未识别有效热处理/表处，仅需车削、孔加工、去毛刺与终检。",
    },
    "RM-JJ-00084084-01": {
        "ops": [
            "raw_material_check",
            "saw_cut",
            "turning",
            "drilling",
            "tapping",
            "straightening",
            "cylindrical_grinding",
            "deburr",
            "pre_plating_cleaning",
            "hard_chrome_masking",
            "hard_chrome",
            "dehydrogenation_bake",
            "post_chrome_polishing",
            "thread_chasing",
            "inspection",
            "post_chrome_inspection",
            "coating_thickness_inspection",
            "surface_inspection",
            "protective_packaging",
        ],
        "judgement": "长推料轴带 M8 盲螺纹且镀硬铬，长细比高，校直、磨削和镀后清牙是关键。",
    },
    "RM-JJ-00084164-01": {
        "ops": [
            "raw_material_check",
            "saw_cut",
            "turning",
            "drilling",
            "shaft_milling",
            "heat_treatment",
            "straightening",
            "cylindrical_grinding",
            "deburr",
            "pre_plating_cleaning",
            "chemical_nickel",
            "inspection",
            "coating_thickness_inspection",
            "surface_inspection",
            "protective_packaging",
        ],
        "judgement": "从动轴长细且多孔，调质后应关注校直与外圆精整；轴上铣削/多面加工需结合 3D 复核。",
    },
    "RM-JJ-00084248-01": {
        "ops": [
            "raw_material_check",
            "saw_cut",
            "turning",
            "drilling",
            "shaft_milling",
            "straightening",
            "deburr",
            "pre_plating_cleaning",
            "chemical_nickel",
            "inspection",
            "coating_thickness_inspection",
            "surface_inspection",
            "protective_packaging",
        ],
        "judgement": "进料从动轴细长多孔且化学镍，系统的车削+多孔+轴上铣削+表处路线基本合理。",
    },
    "RM-JJ-00084311-01": {
        "ops": [
            "raw_material_check",
            "saw_cut",
            "turning",
            "boring",
            "deburr",
            "pre_plating_cleaning",
            "chemical_nickel",
            "inspection",
            "coating_thickness_inspection",
            "surface_inspection",
            "protective_packaging",
        ],
        "judgement": "滚筒有两个 D37 深盲腔，更像车削中镗孔/内孔加工，不宜完全省略孔/镗孔工序。",
    },
}


def op_name(code: str) -> str:
    try:
        return process_name_for_code(code)
    except Exception:
        return code


def format_ops(codes: list[str]) -> str:
    return " -> ".join(f"{op_name(code)}({code})" for code in codes)


def compare(system_ops: list[str], manual_ops: list[str]) -> dict[str, Any]:
    system_set = set(system_ops)
    manual_set = set(manual_ops)
    common = [code for code in manual_ops if code in system_set]
    missing = [code for code in manual_ops if code not in system_set]
    extra = [code for code in system_ops if code not in manual_set]
    order_notes: list[str] = []
    positions = {code: idx for idx, code in enumerate(system_ops)}
    last_pos = -1
    for code in common:
        pos = positions[code]
        if pos < last_pos:
            order_notes.append(f"{op_name(code)}({code}) order differs")
            break
        last_pos = pos
    return {
        "common": common,
        "missing_in_system": missing,
        "extra_in_system": extra,
        "order_notes": order_notes,
        "is_exact_set_match": not missing and not extra,
    }


def summarize_evidence(row: dict[str, Any]) -> str:
    pdf = row.get("pdf_result") or {}
    geo = row.get("geometry") or {}
    features = row.get("features") or {}
    holes = features.get("holes") or []
    hole_count = sum(int(hole.get("count") or 0) for hole in holes if isinstance(hole, dict))
    bbox = geo.get("bbox") or {}
    return (
        f"名称={pdf.get('part_name')}; 材料={pdf.get('material_raw')}; "
        f"表处={pdf.get('surface_treatment_raw') or '-'}; 热处理={pdf.get('heat_treatment_raw') or '-'}; "
        f"尺寸={bbox.get('length')} x {bbox.get('width')} x {bbox.get('height')}mm; "
        f"孔数={hole_count}; STEP类型={geo.get('part_type')}; 小类={geo.get('pdf_category')}"
    )


def build() -> tuple[list[dict[str, Any]], str]:
    rows = json.loads(SYSTEM_JSON.read_text(encoding="utf-8"))
    comparisons: list[dict[str, Any]] = []
    for row in rows:
        stem = row["stem"]
        manual = MANUAL_ROUTES[stem]
        system_ops = [op["code"] for op in row["system"]["v2_ops"]]
        manual_ops = list(manual["ops"])
        diff = compare(system_ops, manual_ops)
        comparisons.append(
            {
                "stem": stem,
                "evidence": summarize_evidence(row),
                "system_family": row["system"].get("v2_family"),
                "system_ops": system_ops,
                "manual_ops": manual_ops,
                "manual_judgement": manual["judgement"],
                "diff": diff,
                "system_risks": row["system"].get("v2_risks") or [],
            }
        )
    return comparisons, render_markdown(comparisons)


def render_markdown(comparisons: list[dict[str, Any]]) -> str:
    exact = sum(1 for item in comparisons if item["diff"]["is_exact_set_match"])
    lines = [
        "# 轴类 PDF/STEP 工序路线自动化测试与人工比对报告",
        "",
        "## 结论摘要",
        "",
        f"- 测试对象：13 组配套 PDF + STEP。",
        f"- 系统路线：使用 `plan_route_v2` 输出；测试前首次运行暴露 `evidence.py` 缺失 `_is_fit_precision_hole` 的运行时错误，已做最小修复后复测通过。",
        f"- 完全一致：{exact}/13；存在差异或需工艺确认：{len(comparisons) - exact}/13。",
        "- 主要差异集中在：长细轴校直阈值、薄环/垫圈的磨削类型、复杂轴面是否显式列入轴上铣削、内孔/镗孔是否单列、以及硬铬遮蔽是否按默认工序加入。",
        "",
        "## 明细对比",
        "",
    ]
    for item in comparisons:
        diff = item["diff"]
        lines.extend(
            [
                f"### {item['stem']}",
                "",
                f"- 证据：{item['evidence']}",
                f"- 系统路线：{format_ops(item['system_ops'])}",
                f"- 人工路线：{format_ops(item['manual_ops'])}",
                f"- 人工判断：{item['manual_judgement']}",
                f"- 系统缺少：{format_ops(diff['missing_in_system']) if diff['missing_in_system'] else '无'}",
                f"- 系统多出：{format_ops(diff['extra_in_system']) if diff['extra_in_system'] else '无'}",
                f"- 顺序差异：{'; '.join(diff['order_notes']) if diff['order_notes'] else '未发现明显顺序倒置'}",
            ]
        )
        risks = item.get("system_risks") or []
        if risks:
            risk_text = "；".join(
                f"{risk.get('code')}: {risk.get('message')}" for risk in risks
            )
            lines.append(f"- 系统复核提示：{risk_text}")
        lines.append("")
    lines.extend(
        [
            "## 改进建议",
            "",
            "1. 长细轴校直规则建议引入图纸技术要求“合理支撑，避免弯曲”和长径比边界复核，83648 这类接近阈值的件不应静默跳过。",
            "2. 对垫圈/隔套类短薄环件，建议区分 `cylindrical_grinding` 与 `finish_grinding`/端面精磨，避免把所有圆件硬铬前精整都归成圆磨。",
            "3. 对 `complex_surface_candidate` 或多孔长轴，系统当前用风险提示和 `shaft_milling` 混合表达；建议统一为“轴上铣削/侧面特征复核”工序或复核风险。",
            "4. 对大内孔/深盲腔，建议把车削可完成的内孔加工显式映射到 `boring` 或同类工序，84311 目前系统路线过简。",
            "5. 硬铬遮蔽默认加入较保守；若 PDF 未标局部镀层，可把 `hard_chrome_masking` 标为需确认而非固定必选。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    comparisons, markdown = build()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "route_comparison.json").write_text(
        json.dumps(comparisons, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "analysis_report.md").write_text(markdown, encoding="utf-8")
    print(OUTPUT_DIR / "analysis_report.md")
    print(OUTPUT_DIR / "route_comparison.json")


if __name__ == "__main__":
    main()
