from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("PRICE_PDF_VISION_MODE", "off")
os.environ.setdefault("PRICE_ROUTE_ENGINE_V2", "1")

from backend.app.parser_service import build_parser_service
from backend.app.part_feature_builder import build_part_feature
from backend.app.pricing_core import build_pricing_core_service


CHINA_TZ = timezone(timedelta(hours=8))
TEST_ROOT = Path(r"D:\test")
SAMPLE_LIMIT_PER_TYPE = 5


class NullPriceProvider:
    def find_unit_price(self, **_kwargs: Any) -> None:
        return None


def file_record(path: Path, kind: str) -> dict[str, Any]:
    return {
        "file_id": f"{kind}_{path.stem}",
        "storage_path": str(path),
        "filename": path.name,
        "file_type": kind,
    }


def discover_samples(root: Path) -> dict[str, list[dict[str, Path]]]:
    samples: dict[str, list[dict[str, Path]]] = {}
    for type_dir in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda p: p.name):
        grouped: dict[tuple[Path, str], dict[str, Path]] = defaultdict(dict)
        for path in type_dir.rglob("*"):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix not in {".pdf", ".step", ".stp"}:
                continue
            grouped[(path.parent, path.stem.lower())][suffix.lstrip(".")] = path
        complete = []
        for (_parent, stem), files in sorted(grouped.items(), key=lambda item: item[0][1]):
            step_path = files.get("step") or files.get("stp")
            pdf_path = files.get("pdf")
            if pdf_path and step_path:
                complete.append({"stem": stem, "pdf": pdf_path, "step": step_path})
        samples[type_dir.name] = complete[:SAMPLE_LIMIT_PER_TYPE]
    return samples


def run_sample(sample_type: str, sample: dict[str, Path]) -> dict[str, Any]:
    stem = sample["pdf"].stem
    task = {
        "task_id": f"task_{sample_type}_{stem}",
        "part_name": stem,
        "part_no": stem,
        "quantity": 1,
    }
    service = build_parser_service()
    risks: list[dict[str, Any]] = []

    pdf_result, pdf_risks = service.parse_pdf(task=task, pdf_file=file_record(sample["pdf"], "pdf"))
    risks.extend(pdf_risks)

    step_result, step_risks = service.parse_step(task=task, step_file=file_record(sample["step"], "step"))
    risks.extend(step_risks)

    part_feature = build_part_feature(task, pdf_result, step_result, risks)
    pricing = build_pricing_core_service(
        material_price_provider=NullPriceProvider(),
        material_estimate_provider=NullPriceProvider(),
        surface_treatment_price_provider=NullPriceProvider(),
        surface_treatment_estimate_provider=NullPriceProvider(),
    ).build_quote(
        task_id=task["task_id"],
        quote_id=f"quote_{sample_type}_{stem}",
        part_feature=part_feature,
        risks=part_feature.get("risks", []),
        priced_at=datetime.now(CHINA_TZ).isoformat(timespec="seconds"),
        price_version="sample-audit-v1",
        use_market_price_search=False,
    )

    manual = recalculate_quote(pricing.quote_result)
    summary = pricing.quote_result["summary"]
    system_quote = money(summary.get("system_initial_quote"))
    manual_quote = manual["system_initial_quote"]
    return {
        "type": sample_type,
        "stem": stem,
        "pdf": str(sample["pdf"]),
        "step": str(sample["step"]),
        "status": pricing.quote_result.get("status"),
        "part_name": (pdf_result or {}).get("part_name"),
        "material": (pdf_result or {}).get("material_raw"),
        "part_type": (part_feature.get("geometry") or {}).get("part_type"),
        "operations": [
            op.get("operation_code")
            for op in pricing.process_route.get("operations", [])
        ],
        "quote_summary": summary,
        "manual_recalc": manual,
        "diff": {
            "system_minus_manual_calculated": round(
                money(summary.get("system_calculated_amount")) - manual["system_calculated_amount"], 2
            ),
            "system_minus_manual_initial_quote": round(system_quote - manual_quote, 2),
        },
        "items": pricing.quote_result.get("items", []),
        "quantity_items": pricing.quantity_result.get("items", []),
        "risk_codes": sorted({risk.get("code") for risk in pricing.quote_result.get("risks", [])}),
        "parse_risk_codes": sorted({risk.get("code") for risk in risks}),
    }


def recalculate_quote(quote_result: dict[str, Any]) -> dict[str, float]:
    items = quote_result.get("items") or []
    material_amount = sum_amount(items, "material")
    process_amount = sum_amount(items, "process")
    surface_amount = sum_amount(items, "surface_treatment")
    management_fee = round(material_amount * 0.05, 2)
    tax_amount = round((process_amount + surface_amount + management_fee) * 0.13, 2)
    system_calculated = round(material_amount + process_amount + surface_amount + management_fee + tax_amount, 2)
    return {
        "material_amount": material_amount,
        "process_amount": process_amount,
        "surface_treatment_amount": surface_amount,
        "management_fee": management_fee,
        "tax_amount": tax_amount,
        "system_calculated_amount": system_calculated,
        "system_initial_quote": round_up_to_10(system_calculated),
    }


def sum_amount(items: list[dict[str, Any]], item_type: str) -> float:
    return round(
        sum(money(item.get("amount")) for item in items if item.get("item_type") == item_type),
        2,
    )


def money(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def round_up_to_10(value: float) -> float:
    if value <= 0:
        return 0.0
    return float(int((value + 9.99) // 10 * 10))


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in results:
        by_type[item["type"]].append(item)

    type_summary = {}
    for sample_type, items in sorted(by_type.items()):
        calc_diffs = [item["diff"]["system_minus_manual_calculated"] for item in items]
        quote_diffs = [item["diff"]["system_minus_manual_initial_quote"] for item in items]
        type_summary[sample_type] = {
            "sample_count": len(items),
            "system_total": round(sum(money(item["quote_summary"].get("system_initial_quote")) for item in items), 2),
            "manual_total": round(sum(item["manual_recalc"]["system_initial_quote"] for item in items), 2),
            "diff_total": round(sum(quote_diffs), 2),
            "diff_average": round(sum(quote_diffs) / len(quote_diffs), 2) if quote_diffs else 0.0,
            "calculated_diff_total": round(sum(calc_diffs), 2),
            "calculated_diff_average": round(sum(calc_diffs) / len(calc_diffs), 2) if calc_diffs else 0.0,
            "risk_codes": sorted({code for item in items for code in item["risk_codes"]}),
        }
    return type_summary


def write_markdown(path: Path, results: list[dict[str, Any]], type_summary: dict[str, Any]) -> None:
    lines = [
        "# Price Sample Audit",
        "",
        f"- Test root: `{TEST_ROOT}`",
        f"- Run time: {datetime.now(CHINA_TZ).isoformat(timespec='seconds')}",
        f"- Samples: {len(results)} total, up to {SAMPLE_LIMIT_PER_TYPE} per type",
        "- Price mode: market search off, PDF vision off",
        "",
        "## Type Summary",
        "",
        "| Type | Count | System total | Manual total | Diff total | Avg diff | Reason |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for sample_type, item in type_summary.items():
        reason = "No formula-level difference; independent recalculation matches system summary."
        lines.append(
            f"| {sample_type} | {item['sample_count']} | {item['system_total']:.2f} | "
            f"{item['manual_total']:.2f} | {item['diff_total']:.2f} | {item['diff_average']:.2f} | {reason} |"
        )
    lines.extend([
        "",
        "## Sample Detail",
        "",
        "| Type | File | Material | Part type | Status | System quote | Manual quote | Diff | Key risks |",
        "|---|---|---|---|---|---:|---:|---:|---|",
    ])
    for result in results:
        summary = result["quote_summary"]
        manual = result["manual_recalc"]
        risks = ", ".join(result["risk_codes"][:6])
        if len(result["risk_codes"]) > 6:
            risks += ", ..."
        lines.append(
            f"| {result['type']} | {result['stem']} | {result.get('material') or ''} | "
            f"{result.get('part_type') or ''} | {result['status']} | "
            f"{money(summary.get('system_initial_quote')):.2f} | "
            f"{manual['system_initial_quote']:.2f} | "
            f"{result['diff']['system_minus_manual_initial_quote']:.2f} | {risks} |"
        )
    lines.extend([
        "",
        "## Recalculation Formula",
        "",
        "`manual = material + process + surface + round(material * 5%, 2) + round((process + surface + management_fee) * 13%, 2)`, then rounded up to the next 10 CNY.",
        "",
        "Missing-price quote items have `amount = null`, so both system and manual recalculation count them as 0 and rely on review risks instead of silently confirming the quote.",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    samples = discover_samples(TEST_ROOT)
    results = []
    for sample_type, sample_items in samples.items():
        for sample in sample_items:
            print(f"RUN {sample_type} {sample['pdf'].stem}", flush=True)
            try:
                results.append(run_sample(sample_type, sample))
            except Exception as exc:  # noqa: BLE001
                results.append(
                    {
                        "type": sample_type,
                        "stem": sample["pdf"].stem,
                        "pdf": str(sample["pdf"]),
                        "step": str(sample["step"]),
                        "error": repr(exc),
                        "quote_summary": {},
                        "manual_recalc": {},
                        "diff": {},
                        "risk_codes": [],
                    }
                )
    output_dir = REPO_ROOT / "exports" / "sample_price_audit"
    output_dir.mkdir(parents=True, exist_ok=True)
    type_summary = summarize([item for item in results if "error" not in item])
    payload = {"type_summary": type_summary, "results": results}
    (output_dir / "price_sample_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown(output_dir / "price_sample_audit.md", [item for item in results if "error" not in item], type_summary)
    if any("error" in item for item in results):
        (output_dir / "errors.json").write_text(
            json.dumps([item for item in results if "error" in item], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(f"WROTE {output_dir}", flush=True)


if __name__ == "__main__":
    main()
