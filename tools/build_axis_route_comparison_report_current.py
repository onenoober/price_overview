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


MANUAL: dict[str, dict[str, Any]] = {
    "RM-JJ-00083648-01": {
        "ops": [
            "raw_material_check", "saw_cut", "turning", "drilling", "countersink",
            "heat_treatment", "straightening", "cylindrical_grinding", "deburr",
            "pre_plating_cleaning", "hard_chrome", "dehydrogenation_bake",
            "post_chrome_polishing", "inspection", "post_chrome_inspection",
            "coating_thickness_inspection", "surface_inspection", "protective_packaging",
        ],
        "judgement": "细长滚筒，40Cr 淬火硬铬；L/D 接近 15 且图纸提示合理支撑，人工建议列校直复核和外圆磨。未见局部镀证据，硬铬遮蔽不作为必选。",
    },
    "RM-JJ-00083692-01": {
        "ops": [
            "raw_material_check", "saw_cut", "turning", "drilling", "countersink",
            "stress_relief", "heat_treatment", "straightening", "cylindrical_grinding",
            "deburr", "pre_plating_cleaning", "hard_chrome", "dehydrogenation_bake",
            "post_chrome_polishing", "inspection", "post_chrome_inspection",
            "coating_thickness_inspection", "surface_inspection", "protective_packaging",
        ],
        "judgement": "滚筒更长且淬火，长细热变形风险高；保留去应力/热处理、校直、圆磨和硬铬后处理链。",
    },
    "RM-JJ-00083816-01": {
        "ops": [
            "raw_material_check", "saw_cut", "turning", "finish_grinding", "deburr",
            "pre_plating_cleaning", "hard_chrome", "dehydrogenation_bake",
            "post_chrome_polishing", "inspection", "post_chrome_inspection",
            "coating_thickness_inspection", "surface_inspection", "protective_packaging",
        ],
        "judgement": "薄垫圈类，人工判断以端面/厚度精整为主，不默认圆磨；未见局部镀证据，不默认硬铬遮蔽。",
    },
    "RM-JJ-00083824-01": {
        "ops": [
            "raw_material_check", "saw_cut", "turning", "drilling", "tapping",
            "shaft_milling", "stress_relief", "heat_treatment", "straightening",
            "cylindrical_grinding", "deburr", "pre_plating_cleaning",
            "hard_chrome_masking", "hard_chrome", "dehydrogenation_bake",
            "post_chrome_polishing", "thread_chasing", "inspection",
            "post_chrome_inspection", "coating_thickness_inspection",
            "surface_inspection", "protective_packaging",
        ],
        "judgement": "动力轴存在 M5 内螺纹和复杂轴面迹象，人工建议列轴上铣削复核；螺纹件镀硬铬需遮蔽/镀后清牙。",
    },
    "RM-JJ-00083835-01": {
        "ops": [
            "raw_material_check", "saw_cut", "turning", "drilling", "tapping",
            "heat_treatment", "finish_grinding", "deburr", "pre_plating_cleaning",
            "hard_chrome_masking", "hard_chrome", "dehydrogenation_bake",
            "post_chrome_polishing", "thread_chasing", "inspection",
            "post_chrome_inspection", "coating_thickness_inspection",
            "surface_inspection", "protective_packaging",
        ],
        "judgement": "定位圈为短环件，走精磨而非默认圆磨；带 M4 螺纹，硬铬遮蔽和镀后清牙应保留。",
    },
    "RM-JJ-00083848-01": {
        "ops": [
            "raw_material_check", "saw_cut", "turning", "heat_treatment",
            "finish_grinding", "deburr", "pre_plating_cleaning", "hard_chrome",
            "dehydrogenation_bake", "post_chrome_polishing", "inspection",
            "post_chrome_inspection", "coating_thickness_inspection",
            "surface_inspection", "protective_packaging",
        ],
        "judgement": "定位垫圈为短薄环件，走端面/厚度精磨；无螺纹/局部镀证据，不默认硬铬遮蔽。",
    },
    "RM-JJ-00083853-01": {
        "ops": [
            "raw_material_check", "saw_cut", "turning", "drilling", "tapping",
            "heat_treatment", "finish_grinding", "deburr", "pre_plating_cleaning",
            "hard_chrome_masking", "hard_chrome", "dehydrogenation_bake",
            "post_chrome_polishing", "thread_chasing", "inspection",
            "post_chrome_inspection", "coating_thickness_inspection",
            "surface_inspection", "protective_packaging",
        ],
        "judgement": "进料隔套为短环/隔套件，带 M4 螺纹；走精磨、硬铬遮蔽和镀后清牙。",
    },
    "RM-JJ-00083858-01": {
        "ops": [
            "raw_material_check", "saw_cut", "turning", "heat_treatment",
            "finish_grinding", "deburr", "pre_plating_cleaning", "hard_chrome",
            "dehydrogenation_bake", "post_chrome_polishing", "inspection",
            "post_chrome_inspection", "coating_thickness_inspection",
            "surface_inspection", "protective_packaging",
        ],
        "judgement": "轴承隔套为短薄环件，走精磨；无局部镀或螺纹证据，不默认硬铬遮蔽。",
    },
    "RM-JJ-00083981-01": {
        "ops": [
            "raw_material_check", "saw_cut", "turning", "drilling", "deburr",
            "inspection", "protective_packaging",
        ],
        "judgement": "SUS304 弧形轮未识别有效热处理/表处，仅需车削、孔加工、去毛刺和终检包装。",
    },
    "RM-JJ-00084084-01": {
        "ops": [
            "raw_material_check", "saw_cut", "turning", "drilling", "tapping",
            "straightening", "cylindrical_grinding", "deburr", "pre_plating_cleaning",
            "hard_chrome_masking", "hard_chrome", "dehydrogenation_bake",
            "post_chrome_polishing", "thread_chasing", "inspection",
            "post_chrome_inspection", "coating_thickness_inspection",
            "surface_inspection", "protective_packaging",
        ],
        "judgement": "长推料轴带 M8 盲螺纹并镀硬铬，校直、圆磨、遮蔽和镀后清牙为关键工序。",
    },
    "RM-JJ-00084164-01": {
        "ops": [
            "raw_material_check", "saw_cut", "turning", "drilling", "shaft_milling",
            "heat_treatment", "straightening", "cylindrical_grinding", "deburr",
            "pre_plating_cleaning", "chemical_nickel", "inspection",
            "coating_thickness_inspection", "surface_inspection", "protective_packaging",
        ],
        "judgement": "从动轴长细且多孔，调质后关注校直和外圆精整；无去应力字样，不单列 stress_relief。",
    },
    "RM-JJ-00084248-01": {
        "ops": [
            "raw_material_check", "saw_cut", "turning", "drilling", "shaft_milling",
            "straightening", "deburr", "pre_plating_cleaning", "chemical_nickel",
            "inspection", "coating_thickness_inspection", "surface_inspection",
            "protective_packaging",
        ],
        "judgement": "进料从动轴细长多孔且化学镍，车削、多孔、轴上铣削复核、校直和表处链合理。",
    },
    "RM-JJ-00084311-01": {
        "ops": [
            "raw_material_check", "saw_cut", "turning", "drilling", "boring",
            "deburr", "pre_plating_cleaning", "chemical_nickel", "inspection",
            "coating_thickness_inspection", "surface_inspection", "protective_packaging",
        ],
        "judgement": "滚筒有两个 D37 深盲腔，人工判断应显式列内孔/镗孔；化学镍按表处链计。",
    },
}


def op_name(code: str) -> str:
    try:
        return process_name_for_code(code)
    except Exception:
        return code


def fmt(codes: list[str]) -> str:
    return " -> ".join(f"{op_name(code)}({code})" for code in codes)


def compare(system_ops: list[str], manual_ops: list[str]) -> dict[str, Any]:
    missing = [code for code in manual_ops if code not in system_ops]
    extra = [code for code in system_ops if code not in manual_ops]
    return {
        "missing_in_system": missing,
        "extra_in_system": extra,
        "is_exact_set_match": not missing and not extra,
    }


def evidence(row: dict[str, Any]) -> str:
    pdf = row["pdf_result"]
    geo = row["geometry"]
    bbox = geo.get("bbox") or {}
    holes = sum(int(h.get("count") or 0) for h in row["features"].get("holes") or [])
    return (
        f"名称={pdf.get('part_name')}；材料={pdf.get('material_raw')}；"
        f"表处={pdf.get('surface_treatment_raw') or '-'}；热处理={pdf.get('heat_treatment_raw') or '-'}；"
        f"尺寸={bbox.get('length')} x {bbox.get('width')} x {bbox.get('height')} mm；"
        f"孔数={holes}；STEP类型={geo.get('part_type')}；小类={geo.get('pdf_category')}"
    )


def main() -> None:
    rows = json.loads(SYSTEM_JSON.read_text(encoding="utf-8"))
    comparisons = []
    for row in rows:
        stem = row["stem"]
        system_ops = [op["code"] for op in row["system"]["v2_ops"]]
        manual_ops = MANUAL[stem]["ops"]
        diff = compare(system_ops, manual_ops)
        comparisons.append(
            {
                "stem": stem,
                "evidence": evidence(row),
                "system_family": row["system"].get("v2_family"),
                "system_ops": system_ops,
                "manual_ops": manual_ops,
                "manual_judgement": MANUAL[stem]["judgement"],
                "diff": diff,
                "system_risks": row["system"].get("v2_risks") or [],
            }
        )

    exact = sum(1 for item in comparisons if item["diff"]["is_exact_set_match"])
    lines = [
        "# 轴类 PDF/STEP 工序路线自动化测试与人工比对报告（当前规则版）",
        "",
        "## 结论摘要",
        "",
        "- 测试对象：13 组配套 PDF + STEP。",
        "- 系统路线：使用当前 `plan_route_v2` 规则输出。",
        f"- 系统与人工路线集合完全一致：{exact}/13。",
        f"- 仍有差异或需工艺确认：{len(comparisons) - exact}/13。",
        "- 当前主要差异若存在，集中在硬铬遮蔽、去应力是否单列、短环磨削类型、轴上铣削复核和大内孔镗孔。",
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
                f"- 系统路线：{fmt(item['system_ops'])}",
                f"- 人工路线：{fmt(item['manual_ops'])}",
                f"- 人工判断：{item['manual_judgement']}",
                f"- 系统缺少：{fmt(diff['missing_in_system']) if diff['missing_in_system'] else '无'}",
                f"- 系统多出：{fmt(diff['extra_in_system']) if diff['extra_in_system'] else '无'}",
            ]
        )
        if item["system_risks"]:
            risk_text = "；".join(f"{r.get('code')}: {r.get('message')}" for r in item["system_risks"])
            lines.append(f"- 系统复核提示：{risk_text}")
        lines.append("")

    lines.extend(
        [
            "## 分析结论",
            "",
            "1. 轴类子画像规则已经把长轴/滚筒与短环/垫圈/隔套分开，薄环件不再被默认套圆磨。",
            "2. 大内孔深盲腔已显式输出 `boring`，报价侧按 `precision_hole` 价格路径计数复用。",
            "3. 硬铬遮蔽已从默认必选改为条件触发：螺纹/精孔/局部镀证据明确时入路线，否则仅复核。",
            "4. 调质但无去应力字样的长轴不再单独输出 `stress_relief`，避免热处理与去应力重复。",
            "5. 复杂轴面采用复合证据触发 `shaft_milling`，普通光轴不会因 STEP 面数噪声误加铣削。",
        ]
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "route_comparison_current.json").write_text(
        json.dumps(comparisons, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "analysis_report_current.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    print(OUTPUT_DIR / "analysis_report_current.md")
    print(OUTPUT_DIR / "route_comparison_current.json")


if __name__ == "__main__":
    main()
