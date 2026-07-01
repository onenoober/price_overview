from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SYSTEM_INPUT = REPO_ROOT / "exports" / "requested_price_diff_audit" / "requested_price_diff_audit.json"
INDEPENDENT_INPUT = (
    REPO_ROOT / "exports" / "independent_part_price_compare" / "independent_part_price_compare.json"
)
OUTPUT_DIR = REPO_ROOT / "exports" / "price_component_issue_analysis"

SURFACE_WEIGHT_RATES = {
    "chemical_nickel": 22.0,
    "hard_chrome": 28.0,
    "hard_anodizing": 18.0,
    "clear_anodizing": 14.0,
    "color_anodizing": 16.0,
    "sand_blasting": 4.0,
    "powder_coating": 8.0,
    "white_powder_coating": 8.0,
    "powder_coating_texture": 10.0,
}


def money(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def round_up_to_10(value: float) -> float:
    if value <= 0:
        return 0.0
    return float(int((value + 9.99) // 10 * 10))


def component_sum(items: list[dict[str, Any]], item_type: str) -> float:
    return round(sum(money(item.get("amount")) for item in items if item.get("item_type") == item_type), 2)


def process_item_amounts(items: list[dict[str, Any]]) -> dict[str, float]:
    amounts: dict[str, float] = defaultdict(float)
    for item in items:
        if item.get("item_type") != "process":
            continue
        code = str(item.get("operation_code") or "unknown")
        amounts[code] += money(item.get("amount"))
    return {key: round(value, 2) for key, value in amounts.items()}


def independent_process_amounts(breakdown: list[dict[str, Any]]) -> dict[str, float]:
    excluded = {
        "material",
        "chemical_nickel",
        "hard_chrome",
        "hard_anodizing",
        "anodizing",
        "sand_blasting",
        "powder_coating",
        "surface_review",
    }
    amounts: dict[str, float] = defaultdict(float)
    for item in breakdown:
        name = str(item.get("name") or "unknown")
        if name in excluded:
            continue
        amounts[name] += money(item.get("amount"))
    return {key: round(value, 2) for key, value in amounts.items()}


def surface_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if item.get("item_type") == "surface_treatment"]


def expected_surface_by_weight(
    surface_quote_items: list[dict[str, Any]],
    independent: dict[str, Any],
) -> tuple[float, list[str]]:
    weight = money(independent.get("weight_kg"))
    notes = []
    total = 0.0
    for item in surface_quote_items:
        code = str(item.get("operation_code") or "")
        rate = SURFACE_WEIGHT_RATES.get(code)
        if rate is None:
            rate = 12.0
            notes.append(f"{code}: no configured kg rate, use review fallback 12 CNY/kg")
        amount = weight * rate
        minimum = 50.0 if code not in {"hard_chrome", "chemical_nickel", "hard_anodizing"} else 80.0
        amount = max(amount, minimum)
        total += amount
        notes.append(f"{code}: {weight:.4g} kg x {rate:g} CNY/kg, min {minimum:g}")
    return round(total, 2), notes


def total_from_components(material: float, process: float, surface: float) -> dict[str, float]:
    management = round(material * 0.05, 2)
    tax = round((process + surface + management) * 0.13, 2)
    calculated = round(material + process + surface + management + tax, 2)
    return {
        "material_amount": round(material, 2),
        "process_amount": round(process, 2),
        "surface_treatment_amount": round(surface, 2),
        "management_fee": management,
        "tax_amount": tax,
        "calculated_total": calculated,
        "rounded_quote": round_up_to_10(calculated),
    }


def join_top_diffs(diffs: list[tuple[str, float]], limit: int = 5) -> str:
    if not diffs:
        return ""
    top = sorted(diffs, key=lambda item: abs(item[1]), reverse=True)[:limit]
    return "; ".join(f"{name}:{diff:+.2f}" for name, diff in top)


def analyze_row(system_row: dict[str, Any], independent_row: dict[str, Any]) -> dict[str, Any]:
    summary = system_row["quote_summary"]
    items = system_row["quote_items"]
    independent = independent_row["independent_estimate"]
    system_components = {
        "material_amount": money(summary.get("material_amount")),
        "process_amount": money(summary.get("process_amount")),
        "surface_treatment_amount": money(summary.get("surface_treatment_amount")),
        "management_fee": money(summary.get("management_fee")),
        "tax_amount": money(summary.get("tax_amount")),
        "calculated_total": money(summary.get("system_calculated_amount")),
        "rounded_quote": money(summary.get("system_initial_quote")),
    }
    independent_area_components = {
        "material_amount": money(independent.get("material_amount")),
        "process_amount": money(independent.get("process_amount")),
        "surface_treatment_amount": money(independent.get("surface_amount")),
    }
    surface_by_weight, surface_notes = expected_surface_by_weight(surface_items(items), independent)
    target_components = total_from_components(
        independent_area_components["material_amount"],
        independent_area_components["process_amount"],
        surface_by_weight,
    )
    component_diffs = {
        key: round(system_components[key] - target_components[key], 2)
        for key in target_components
    }

    system_process = process_item_amounts(items)
    independent_process = independent_process_amounts(independent.get("breakdown") or [])
    process_codes = sorted(set(system_process) | set(independent_process))
    process_diffs = [
        (code, round(system_process.get(code, 0.0) - independent_process.get(code, 0.0), 2))
        for code in process_codes
        if round(system_process.get(code, 0.0) - independent_process.get(code, 0.0), 2) != 0
    ]

    issues: list[str] = []
    if abs(component_diffs["material_amount"]) > 5:
        direction = "偏低" if component_diffs["material_amount"] < 0 else "偏高"
        issues.append(
            f"材料费{direction}: system {system_components['material_amount']:.2f} vs independent {target_components['material_amount']:.2f}"
        )
    if surface_items(items):
        surface_units = sorted({str(item.get("unit") or "") for item in surface_items(items)})
        if any(unit.lower() in {"m2", "m^2"} for unit in surface_units):
            issues.append(
                "表面处理计量口径不符合目标公式: system uses area unit "
                f"{','.join(surface_units)}, target uses net/gross weight kg"
            )
    if abs(component_diffs["surface_treatment_amount"]) > 5:
        direction = "偏低" if component_diffs["surface_treatment_amount"] < 0 else "偏高"
        issues.append(
            f"表面处理费{direction}: system {system_components['surface_treatment_amount']:.2f} vs kg-formula {target_components['surface_treatment_amount']:.2f}"
        )
    if abs(component_diffs["process_amount"]) > 20:
        direction = "偏低" if component_diffs["process_amount"] < 0 else "偏高"
        issues.append(
            f"加工费{direction}: system {system_components['process_amount']:.2f} vs independent {target_components['process_amount']:.2f}; top ops {join_top_diffs(process_diffs)}"
        )
    management_expected_from_system_material = round(system_components["material_amount"] * 0.05, 2)
    if abs(system_components["management_fee"] - management_expected_from_system_material) > 0.01:
        issues.append("管理费公式错误: not equal to system material fee x 5%")
    tax_expected_from_system = round(
        (
            system_components["process_amount"]
            + system_components["surface_treatment_amount"]
            + system_components["management_fee"]
        )
        * 0.13,
        2,
    )
    if abs(system_components["tax_amount"] - tax_expected_from_system) > 0.01:
        issues.append("税金公式错误: not equal to (process + surface + management) x 13%")
    if not issues:
        issues.append("未发现公式级小项问题，差异主要来自独立估价参数假设")

    return {
        "type": system_row["type"],
        "stem": system_row["stem"],
        "material": system_row.get("material"),
        "part_type": system_row.get("part_type"),
        "system_components": system_components,
        "target_components": target_components,
        "component_diffs_system_minus_target": component_diffs,
        "system_process_amounts": system_process,
        "independent_process_amounts": independent_process,
        "process_diffs_system_minus_independent": dict(process_diffs),
        "surface_system_items": [
            {
                "operation_code": item.get("operation_code"),
                "quantity": item.get("quantity"),
                "unit": item.get("unit"),
                "unit_price": item.get("unit_price"),
                "amount": item.get("amount"),
            }
            for item in surface_items(items)
        ],
        "surface_weight_formula_notes": surface_notes,
        "weight_kg": independent.get("weight_kg"),
        "issues": issues,
        "main_issue": issues[0],
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    component_keys = [
        "material_amount",
        "process_amount",
        "surface_treatment_amount",
        "management_fee",
        "tax_amount",
        "calculated_total",
        "rounded_quote",
    ]
    totals = {
        key: round(sum(row["component_diffs_system_minus_target"][key] for row in rows), 2)
        for key in component_keys
    }
    issue_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        for issue in row["issues"]:
            if issue.startswith("材料费"):
                issue_counts["材料费问题"] += 1
            elif issue.startswith("加工费"):
                issue_counts["加工费问题"] += 1
            elif issue.startswith("表面处理计量"):
                issue_counts["表处计量口径问题"] += 1
            elif issue.startswith("表面处理费"):
                issue_counts["表处金额问题"] += 1
            elif issue.startswith("管理费"):
                issue_counts["管理费公式问题"] += 1
            elif issue.startswith("税金"):
                issue_counts["税金公式问题"] += 1
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_type[row["type"]].append(row)
    type_summary = {}
    for sample_type, items in sorted(by_type.items()):
        type_summary[sample_type] = {
            "count": len(items),
            **{
                key: round(sum(row["component_diffs_system_minus_target"][key] for row in items), 2)
                for key in component_keys
            },
        }
    return {
        "sample_count": len(rows),
        "component_diff_totals_system_minus_target": totals,
        "issue_counts": dict(sorted(issue_counts.items())),
        "type_summary": type_summary,
    }


def render_report(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    totals = summary["component_diff_totals_system_minus_target"]
    lines = [
        "# 系统价格小项问题分析",
        "",
        "## 1. 结论",
        "",
        f"- 本报告逐件对比 {summary['sample_count']} 套 PDF/STEP 配套零件的系统小项价格和独立小项价格。",
        "- 目标公式按用户指定：材料费=毛重*材料单价；加工费=加工工艺*工艺单价；表面处理=不同表面处理*单价*净重；管理费=材料费*5%；税金=(加工费+表面处理+管理费)*13%。",
        f"- 小项差异合计（系统-目标）：材料 {totals['material_amount']:.2f}，加工 {totals['process_amount']:.2f}，表处 {totals['surface_treatment_amount']:.2f}，管理费 {totals['management_fee']:.2f}，税金 {totals['tax_amount']:.2f}，未取整总价 {totals['calculated_total']:.2f}。",
        "- 管理费和税金本身未发现公式错误；它们的差异主要由材料费、加工费、表面处理费变化传导产生。",
        "- 最关键的系统问题是表面处理当前多按面积 m2 计价，而目标公式要求按净重 kg 计价；加工费主要偏低在 CNC、精加工/磨削、孔加工、包装检验等工序。",
        "",
        "## 2. 问题计数",
        "",
        "| 问题类型 | 件数 |",
        "|---|---:|",
    ]
    for name, count in summary["issue_counts"].items():
        lines.append(f"| {name} | {count} |")

    lines.extend(
        [
            "",
            "## 3. 分类小项差异汇总",
            "",
            "| 类型 | 件数 | 材料差异 | 加工差异 | 表处差异 | 管理费差异 | 税金差异 | 未取整总价差异 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for sample_type, item in summary["type_summary"].items():
        lines.append(
            f"| {sample_type} | {item['count']} | {item['material_amount']:.2f} | "
            f"{item['process_amount']:.2f} | {item['surface_treatment_amount']:.2f} | "
            f"{item['management_fee']:.2f} | {item['tax_amount']:.2f} | {item['calculated_total']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## 4. 逐件小项差异",
            "",
            "| 类型 | 零件 | 材料 | 系统价 | 目标价 | 总差异 | 材料 | 加工 | 表处 | 管理费 | 税金 | 主要问题 |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in rows:
        s = row["system_components"]
        t = row["target_components"]
        d = row["component_diffs_system_minus_target"]
        lines.append(
            f"| {row['type']} | {row['stem']} | {row.get('material') or ''} | "
            f"{s['rounded_quote']:.2f} | {t['rounded_quote']:.2f} | {d['rounded_quote']:.2f} | "
            f"{d['material_amount']:.2f} | {d['process_amount']:.2f} | "
            f"{d['surface_treatment_amount']:.2f} | {d['management_fee']:.2f} | "
            f"{d['tax_amount']:.2f} | {row['main_issue']} |"
        )

    lines.extend(["", "## 5. 单件原因明细", ""])
    for row in rows:
        s = row["system_components"]
        t = row["target_components"]
        d = row["component_diffs_system_minus_target"]
        surface_items_text = "; ".join(
            f"{item['operation_code']} {item['quantity']} {item['unit']} x {item['unit_price']} = {item['amount']}"
            for item in row["surface_system_items"]
        )
        process_top = join_top_diffs(list(row["process_diffs_system_minus_independent"].items()), 8)
        lines.extend(
            [
                f"### {row['stem']}",
                "",
                f"- 系统/目标未取整总价：{s['calculated_total']:.2f} / {t['calculated_total']:.2f}，差异 {d['calculated_total']:.2f}；取整后：{s['rounded_quote']:.2f} / {t['rounded_quote']:.2f}。",
                f"- 材料费：系统 {s['material_amount']:.2f}，目标 {t['material_amount']:.2f}，差异 {d['material_amount']:.2f}。目标按独立估算重量 {row['weight_kg']} kg 计算。",
                f"- 加工费：系统 {s['process_amount']:.2f}，目标 {t['process_amount']:.2f}，差异 {d['process_amount']:.2f}。主要工序差异：{process_top or '无明显工序差异'}。",
                f"- 表面处理费：系统 {s['surface_treatment_amount']:.2f}，目标 {t['surface_treatment_amount']:.2f}，差异 {d['surface_treatment_amount']:.2f}。",
                f"- 系统表处明细：{surface_items_text or '无表面处理项目'}。",
                f"- 目标表处按重量公式：{'; '.join(row['surface_weight_formula_notes']) or '无表面处理项目'}。",
                f"- 管理费：系统 {s['management_fee']:.2f}，目标 {t['management_fee']:.2f}，差异 {d['management_fee']:.2f}；税金：系统 {s['tax_amount']:.2f}，目标 {t['tax_amount']:.2f}，差异 {d['tax_amount']:.2f}。",
                f"- 结论：{'；'.join(row['issues'])}",
                "",
            ]
        )

    lines.extend(
        [
            "## 6. 输出文件",
            "",
            f"- JSON 明细：`{OUTPUT_DIR / 'price_component_issue_analysis.json'}`",
            f"- 本文档：`{OUTPUT_DIR / 'price_component_issue_analysis.md'}`",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    system_data = json.loads(SYSTEM_INPUT.read_text(encoding="utf-8"))
    independent_data = json.loads(INDEPENDENT_INPUT.read_text(encoding="utf-8"))
    independent_by_stem = {row["stem"]: row for row in independent_data["results"]}
    rows = [
        analyze_row(row, independent_by_stem[row["stem"]])
        for row in system_data["results"]
        if "error" not in row and row["stem"] in independent_by_stem
    ]
    summary = summarize(rows)
    payload = {"summary": summary, "results": rows}
    (OUTPUT_DIR / "price_component_issue_analysis.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "price_component_issue_analysis.md").write_text(
        render_report(rows, summary),
        encoding="utf-8",
    )
    print(OUTPUT_DIR)


if __name__ == "__main__":
    main()
