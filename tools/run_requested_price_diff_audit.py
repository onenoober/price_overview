from __future__ import annotations

import json
import os
import sys
import traceback
from collections import Counter, defaultdict
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
from backend.app.pricing_core import (
    PROCESS_STANDARD_PRICE_RULES,
    SURFACE_TREATMENT_STANDARD_PRICE_RULES,
    build_pricing_core_service,
)


CHINA_TZ = timezone(timedelta(hours=8))
OUTPUT_DIR = REPO_ROOT / "exports" / "requested_price_diff_audit"

SAMPLES = [
    ("机加", r"D:\test\机加\RM-JJ-00083368-01.pdf", r"D:\test\机加\RM-JJ-00083368-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00083679-01.pdf", r"D:\test\机加\RM-JJ-00083679-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00083687-01.pdf", r"D:\test\机加\RM-JJ-00083687-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00083696-01.pdf", r"D:\test\机加\RM-JJ-00083696-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00083706-01.pdf", r"D:\test\机加\RM-JJ-00083706-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00083723-01.pdf", r"D:\test\机加\RM-JJ-00083723-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00083818-01.pdf", r"D:\test\机加\RM-JJ-00083818-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00083845-01.pdf", r"D:\test\机加\RM-JJ-00083845-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00083878-01.pdf", r"D:\test\机加\RM-JJ-00083878-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00083991-01.pdf", r"D:\test\机加\RM-JJ-00083991-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00084184-01.pdf", r"D:\test\机加\RM-JJ-00084184-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00084245-01.pdf", r"D:\test\机加\RM-JJ-00084245-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00084337-01.pdf", r"D:\test\机加\RM-JJ-00084337-01.step"),
    ("轴类", r"D:\test\轴类\轴类\RM-JJ-00083648-01.pdf", r"D:\test\轴类\轴类\RM-JJ-00083648-01.step"),
    ("轴类", r"D:\test\轴类\轴类\RM-JJ-00083692-01.pdf", r"D:\test\轴类\轴类\RM-JJ-00083692-01.step"),
    ("轴类", r"D:\test\轴类\轴类\RM-JJ-00083830-01.pdf", r"D:\test\轴类\轴类\RM-JJ-00083830-01.step"),
    ("轴类", r"D:\test\轴类\轴类\RM-JJ-00083981-01.pdf", r"D:\test\轴类\轴类\RM-JJ-00083981-01.step"),
    ("轴类", r"D:\test\轴类\轴类\RM-JJ-00084313-01.pdf", r"D:\test\轴类\轴类\RM-JJ-00084313-01.step"),
    ("大板", r"D:\test\大板\RM-JJ-00084089-01.pdf", r"D:\test\大板\RM-JJ-00084089-01.step"),
    ("大板", r"D:\test\大板\RM-JJ-00083694-01.pdf", r"D:\test\大板\RM-JJ-00083694-01.step"),
    ("大板", r"D:\test\大板\RM-JJ-00083711-01.pdf", r"D:\test\大板\RM-JJ-00083711-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00083669-01.pdf", r"D:\test\机加\RM-JJ-00083669-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00083681-01.pdf", r"D:\test\机加\RM-JJ-00083681-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00083691-01.pdf", r"D:\test\机加\RM-JJ-00083691-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00083704-01.pdf", r"D:\test\机加\RM-JJ-00083704-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00083725-01.pdf", r"D:\test\机加\RM-JJ-00083725-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00083829-01.pdf", r"D:\test\机加\RM-JJ-00083829-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00083909-01.pdf", r"D:\test\机加\RM-JJ-00083909-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00084099-01.pdf", r"D:\test\机加\RM-JJ-00084099-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00084215-01.pdf", r"D:\test\机加\RM-JJ-00084215-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00084238-01.pdf", r"D:\test\机加\RM-JJ-00084238-01.step"),
    ("机加", r"D:\test\机加\RM-JJ-00084253-01.pdf", r"D:\test\机加\RM-JJ-00084253-01.step"),
]


class NullPriceProvider:
    def find_unit_price(self, **_kwargs: Any) -> None:
        return None


def now_iso() -> str:
    return datetime.now(CHINA_TZ).isoformat(timespec="seconds")


def file_record(path: Path, kind: str) -> dict[str, Any]:
    return {
        "file_id": f"{kind}_{path.stem}",
        "storage_path": str(path),
        "filename": path.name,
        "file_type": kind,
    }


def money(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def optional_money(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def round_up_to_10(value: float) -> float:
    if value <= 0:
        return 0.0
    return float(int((value + 9.99) // 10 * 10))


def calc_line_expected(item: dict[str, Any]) -> float | None:
    item_type = item.get("item_type")
    quantity = optional_money(item.get("quantity"))
    unit_price = optional_money(item.get("unit_price"))
    operation = str(item.get("operation_code") or "")
    if item_type in {"management_fee", "tax"}:
        return optional_money(item.get("amount"))
    if quantity is None or unit_price is None:
        return None
    if item_type == "material":
        return round(quantity * unit_price, 2)
    if item_type == "process":
        rule = PROCESS_STANDARD_PRICE_RULES.get(operation)
        minimum_charge = rule.minimum_charge if rule else 0.0
        return round(max(quantity * unit_price, minimum_charge), 2)
    if item_type == "surface_treatment":
        rule = SURFACE_TREATMENT_STANDARD_PRICE_RULES.get(operation)
        minimum_charge = rule.minimum_charge if rule else 0.0
        return round(max(quantity * unit_price, minimum_charge), 2)
    return optional_money(item.get("amount"))


def audit_lines(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    audited: list[dict[str, Any]] = []
    for item in items:
        if item.get("item_type") not in {
            "material",
            "process",
            "surface_treatment",
            "management_fee",
            "tax",
        }:
            continue
        actual = optional_money(item.get("amount"))
        expected = calc_line_expected(item)
        if actual is None and expected is None:
            status = "missing"
            diff = None
        elif actual is None or expected is None:
            status = "mismatch"
            diff = None
        else:
            diff = round(actual - expected, 2)
            status = "ok" if diff == 0 else "mismatch"
        audited.append(
            {
                "item_id": item.get("item_id"),
                "item_type": item.get("item_type"),
                "operation_code": item.get("operation_code"),
                "quantity": item.get("quantity"),
                "unit": item.get("unit"),
                "unit_price": item.get("unit_price"),
                "actual_amount": actual,
                "expected_amount": expected,
                "diff": diff,
                "status": status,
                "requires_review": bool(item.get("requires_review")),
            }
        )
    return audited


def independent_summary(quote_result: dict[str, Any]) -> dict[str, float]:
    items = quote_result.get("items") or []
    material_amount = sum_expected(items, "material")
    process_amount = sum_expected(items, "process")
    surface_amount = sum_expected(items, "surface_treatment")
    management_fee = round(material_amount * 0.05, 2)
    tax_amount = round((process_amount + surface_amount + management_fee) * 0.13, 2)
    system_calculated_amount = round(
        material_amount + process_amount + surface_amount + management_fee + tax_amount,
        2,
    )
    return {
        "material_amount": material_amount,
        "process_amount": process_amount,
        "surface_treatment_amount": surface_amount,
        "management_fee": management_fee,
        "tax_amount": tax_amount,
        "risk_surcharge_amount": 0.0,
        "system_calculated_amount": system_calculated_amount,
        "system_initial_quote": round_up_to_10(system_calculated_amount),
    }


def sum_expected(items: list[dict[str, Any]], item_type: str) -> float:
    return round(
        sum(
            calc_line_expected(item) or 0.0
            for item in items
            if item.get("item_type") == item_type
        ),
        2,
    )


def final_output_price(summary: dict[str, Any]) -> float:
    confirmed = summary.get("final_confirmed_amount")
    return money(confirmed if confirmed not in (None, "") else summary.get("system_initial_quote"))


def run_one(sample_type: str, pdf_path: Path, step_path: Path) -> dict[str, Any]:
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if not step_path.exists():
        raise FileNotFoundError(f"STEP not found: {step_path}")

    stem = pdf_path.stem
    task = {
        "task_id": f"requested_price_audit_{stem}",
        "part_name": stem,
        "part_no": stem,
        "quantity": 1,
    }
    parser_service = build_parser_service()
    parse_risks: list[dict[str, Any]] = []
    pdf_result, pdf_risks = parser_service.parse_pdf(
        task=task,
        pdf_file=file_record(pdf_path, "pdf"),
    )
    parse_risks.extend(pdf_risks)
    step_result, step_risks = parser_service.parse_step(
        task=task,
        step_file=file_record(step_path, "step"),
    )
    parse_risks.extend(step_risks)
    part_feature = build_part_feature(task, pdf_result, step_result, parse_risks)
    pricing = build_pricing_core_service(
        material_price_provider=NullPriceProvider(),
        material_estimate_provider=NullPriceProvider(),
        surface_treatment_price_provider=NullPriceProvider(),
        surface_treatment_estimate_provider=NullPriceProvider(),
    ).build_quote(
        task_id=task["task_id"],
        quote_id=f"quote_requested_price_audit_{stem}",
        part_feature=part_feature,
        risks=part_feature.get("risks", []),
        priced_at=now_iso(),
        price_version="requested-price-diff-audit-v1",
        use_market_price_search=False,
    )

    quote_result = pricing.quote_result
    quote_summary = quote_result.get("summary") or {}
    expected = independent_summary(quote_result)
    line_audits = audit_lines(quote_result.get("items") or [])
    system_price = final_output_price(quote_summary)
    expected_price = expected["system_initial_quote"]
    geometry = part_feature.get("geometry") or {}
    bbox = geometry.get("bounding_box") or {}
    pdf = pdf_result or {}
    route_codes = [
        op.get("operation_code")
        for op in pricing.process_route.get("operations", [])
        if op.get("operation_code")
    ]
    missing_amount_ops = [
        item.get("operation_code")
        for item in line_audits
        if item["status"] == "missing"
    ]
    return {
        "type": sample_type,
        "stem": stem,
        "pdf": str(pdf_path),
        "step": str(step_path),
        "status": quote_result.get("status"),
        "part_name": pdf.get("part_name"),
        "drawing_no": pdf.get("drawing_no"),
        "material": pdf.get("material_raw"),
        "surface_treatment": pdf.get("surface_treatment_raw"),
        "heat_treatment": pdf.get("heat_treatment_raw"),
        "part_type": geometry.get("part_type"),
        "bounding_box": bbox,
        "step_net_weight": geometry.get("step_net_weight"),
        "operations": route_codes,
        "quote_summary": quote_summary,
        "independent_summary": expected,
        "diff": {
            "final_output_minus_independent_quote": round(system_price - expected_price, 2),
            "system_calculated_minus_independent_calculated": round(
                money(quote_summary.get("system_calculated_amount"))
                - expected["system_calculated_amount"],
                2,
            ),
            "material_amount_diff": round(
                money(quote_summary.get("material_amount")) - expected["material_amount"],
                2,
            ),
            "process_amount_diff": round(
                money(quote_summary.get("process_amount")) - expected["process_amount"],
                2,
            ),
            "surface_treatment_amount_diff": round(
                money(quote_summary.get("surface_treatment_amount"))
                - expected["surface_treatment_amount"],
                2,
            ),
        },
        "final_output_price": system_price,
        "independent_test_price": expected_price,
        "line_audits": line_audits,
        "line_mismatches": [item for item in line_audits if item["status"] == "mismatch"],
        "missing_amount_operations": missing_amount_ops,
        "risk_codes": sorted(
            {
                risk.get("code")
                for risk in quote_result.get("risks", [])
                if risk.get("code")
            }
        ),
        "parse_risk_codes": sorted(
            {
                risk.get("code")
                for risk in parse_risks
                if risk.get("code")
            }
        ),
        "quote_items": quote_result.get("items", []),
        "quantity_items": pricing.quantity_result.get("items", []),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok_rows = [row for row in rows if "error" not in row]
    error_rows = [row for row in rows if "error" in row]
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ok_rows:
        by_type[row["type"]].append(row)

    type_summary: dict[str, dict[str, Any]] = {}
    for sample_type, items in sorted(by_type.items()):
        quote_diffs = [item["diff"]["final_output_minus_independent_quote"] for item in items]
        calc_diffs = [
            item["diff"]["system_calculated_minus_independent_calculated"] for item in items
        ]
        type_summary[sample_type] = {
            "sample_count": len(items),
            "system_total": round(sum(item["final_output_price"] for item in items), 2),
            "independent_total": round(sum(item["independent_test_price"] for item in items), 2),
            "quote_diff_total": round(sum(quote_diffs), 2),
            "quote_diff_average": round(sum(quote_diffs) / len(quote_diffs), 2)
            if quote_diffs
            else 0.0,
            "calculated_diff_total": round(sum(calc_diffs), 2),
            "line_mismatch_count": sum(len(item["line_mismatches"]) for item in items),
            "missing_amount_count": sum(len(item["missing_amount_operations"]) for item in items),
            "status_counts": dict(Counter(str(item.get("status")) for item in items)),
            "risk_codes": sorted({code for item in items for code in item["risk_codes"]}),
        }
    return {
        "sample_count": len(rows),
        "success_count": len(ok_rows),
        "error_count": len(error_rows),
        "system_total": round(sum(item["final_output_price"] for item in ok_rows), 2),
        "independent_total": round(sum(item["independent_test_price"] for item in ok_rows), 2),
        "quote_diff_total": round(
            sum(item["diff"]["final_output_minus_independent_quote"] for item in ok_rows),
            2,
        ),
        "calculated_diff_total": round(
            sum(
                item["diff"]["system_calculated_minus_independent_calculated"]
                for item in ok_rows
            ),
            2,
        ),
        "type_summary": type_summary,
        "top_risks": Counter(
            code for item in ok_rows for code in item["risk_codes"]
        ).most_common(),
        "top_missing_amount_operations": Counter(
            str(code)
            for item in ok_rows
            for code in item["missing_amount_operations"]
        ).most_common(),
    }


def bbox_text(bbox: dict[str, Any]) -> str:
    values = [bbox.get("length"), bbox.get("width"), bbox.get("height")]
    if any(value in (None, "") for value in values):
        return ""
    return f"{values[0]}x{values[1]}x{values[2]} {bbox.get('unit') or 'mm'}"


def render_report(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    ok_rows = [row for row in rows if "error" not in row]
    error_rows = [row for row in rows if "error" in row]
    run_time = now_iso()
    lines = [
        "# 指定 PDF/STEP 样件价格差异自动化测试分析",
        "",
        "## 1. 测试结论",
        "",
        f"- 本次按用户指定清单测试 {summary['sample_count']} 组 PDF/STEP 配套文件，成功 {summary['success_count']} 组，失败 {summary['error_count']} 组。",
        f"- 系统最终输出价合计：{summary['system_total']:.2f} CNY；独立复算测试价合计：{summary['independent_total']:.2f} CNY；最终价差合计：{summary['quote_diff_total']:.2f} CNY。",
        f"- 未取整的系统计算金额与独立复算金额差异合计：{summary['calculated_diff_total']:.2f} CNY。",
        "- 本次独立测试价使用报价明细中的数量、单价和标准最低收费规则重新计算，再按系统同一口径向上取整到 10 元；它主要验证价格汇总和明细公式是否一致，不等同于外部供应商真实报价。",
        "- 本次关闭市场价格搜索和 PDF 视觉补充，使用当前项目规则与本地 PDF 文本/STEP 解析结果，保证可重复。",
        "",
        "## 2. 测试口径",
        "",
        f"- 运行时间：{run_time}",
        "- 系统最终输出价：优先取 `final_confirmed_amount`；当前样件均未人工确认，因此取 `system_initial_quote`。",
        "- 独立复算测试价：材料费 + 加工费 + 表面处理费 + 管理费 + 税费，然后向上取整到 10 元。",
        "- 管理费：材料费 x 5%。",
        "- 税费：(加工费 + 表面处理费 + 管理费) x 13%。",
        "- 加工/表面处理明细：按 `数量 x 单价` 与规则最低收费取较大值；缺失数量或单价的项目按 0 计入汇总，并保留复核风险。",
        "",
        "## 3. 分类汇总",
        "",
        "| 类型 | 数量 | 系统最终价合计 | 独立测试价合计 | 最终价差 | 平均价差 | 未取整价差 | 明细公式不一致 | 缺价项目 | 状态 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for sample_type, item in summary["type_summary"].items():
        statuses = ", ".join(f"{key}:{value}" for key, value in item["status_counts"].items())
        lines.append(
            f"| {sample_type} | {item['sample_count']} | {item['system_total']:.2f} | "
            f"{item['independent_total']:.2f} | {item['quote_diff_total']:.2f} | "
            f"{item['quote_diff_average']:.2f} | {item['calculated_diff_total']:.2f} | "
            f"{item['line_mismatch_count']} | {item['missing_amount_count']} | {statuses} |"
        )

    lines.extend(
        [
            "",
            "## 4. 样件明细",
            "",
            "| 类型 | 文件 | 材料 | 类型 | 尺寸 | 状态 | 系统最终价 | 独立测试价 | 价差 | 未取整价差 | 缺价工序 | 主要风险 |",
            "|---|---|---|---|---|---|---:|---:|---:|---:|---|---|",
        ]
    )
    for row in ok_rows:
        missing_ops = ", ".join(str(code) for code in row["missing_amount_operations"][:6])
        if len(row["missing_amount_operations"]) > 6:
            missing_ops += ", ..."
        risks = ", ".join(row["risk_codes"][:6])
        if len(row["risk_codes"]) > 6:
            risks += ", ..."
        lines.append(
            f"| {row['type']} | {row['stem']} | {row.get('material') or ''} | "
            f"{row.get('part_type') or ''} | {bbox_text(row.get('bounding_box') or {})} | "
            f"{row.get('status') or ''} | {row['final_output_price']:.2f} | "
            f"{row['independent_test_price']:.2f} | "
            f"{row['diff']['final_output_minus_independent_quote']:.2f} | "
            f"{row['diff']['system_calculated_minus_independent_calculated']:.2f} | "
            f"{missing_ops} | {risks} |"
        )

    lines.extend(
        [
            "",
            "## 5. 差异分析",
            "",
        ]
    )
    quote_diff_rows = [
        row
        for row in ok_rows
        if row["diff"]["final_output_minus_independent_quote"] != 0
        or row["diff"]["system_calculated_minus_independent_calculated"] != 0
        or row["line_mismatches"]
    ]
    if quote_diff_rows:
        lines.append("以下样件存在复算差异或明细公式不一致，需要优先检查：")
        lines.append("")
        for row in quote_diff_rows:
            mismatch_text = "; ".join(
                f"{item.get('operation_code')} actual={item.get('actual_amount')} expected={item.get('expected_amount')}"
                for item in row["line_mismatches"][:5]
            )
            lines.append(
                f"- {row['stem']}：最终价差 {row['diff']['final_output_minus_independent_quote']:.2f} CNY，"
                f"未取整价差 {row['diff']['system_calculated_minus_independent_calculated']:.2f} CNY。"
                f"{' 明细：' + mismatch_text if mismatch_text else ''}"
            )
    else:
        lines.append(
            "所有成功样件的系统最终输出价与独立复算测试价一致，未发现汇总公式、最低收费规则或 10 元取整逻辑导致的价格差异。"
        )

    lines.extend(
        [
            "",
            "## 6. 风险和缺价项",
            "",
        ]
    )
    if summary["top_missing_amount_operations"]:
        lines.append("缺失金额的工序统计如下；这些项目按 0 进入本次系统价和复算价，因此不会造成两者差异，但会影响报价完整性：")
        lines.append("")
        for operation, count in summary["top_missing_amount_operations"]:
            lines.append(f"- {operation}: {count}")
    else:
        lines.append("本次未发现金额缺失的报价明细。")

    if summary["top_risks"]:
        lines.extend(["", "主要风险码统计：", ""])
        for code, count in summary["top_risks"][:20]:
            lines.append(f"- {code}: {count}")

    lines.extend(
        [
            "",
            "## 7. 失败样件",
            "",
        ]
    )
    if error_rows:
        for row in error_rows:
            lines.append(f"- {row.get('stem')}: {row.get('error')}")
    else:
        lines.append("无。")

    lines.extend(
        [
            "",
            "## 8. 输出文件",
            "",
            f"- 机器可读结果：`{OUTPUT_DIR / 'requested_price_diff_audit.json'}`",
            f"- 本分析文档：`{OUTPUT_DIR / 'requested_price_diff_audit.md'}`",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for sample_type, pdf_text, step_text in SAMPLES:
        pdf_path = Path(pdf_text)
        step_path = Path(step_text)
        stem = pdf_path.stem
        print(f"RUN {sample_type} {stem}", flush=True)
        try:
            rows.append(run_one(sample_type, pdf_path, step_path))
            print(f"OK {stem}", flush=True)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            rows.append(
                {
                    "type": sample_type,
                    "stem": stem,
                    "pdf": str(pdf_path),
                    "step": str(step_path),
                    "error": repr(exc),
                }
            )
            print(f"ERR {stem}: {exc!r}", flush=True)
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
    (OUTPUT_DIR / "requested_price_diff_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "requested_price_diff_audit.md").write_text(
        render_report(rows, summary),
        encoding="utf-8",
    )
    print(OUTPUT_DIR, flush=True)


if __name__ == "__main__":
    main()
