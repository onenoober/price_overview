from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.pricing_core import (
    PROCESS_STANDARD_PRICE_RULES,
    SURFACE_TREATMENT_STANDARD_PRICE_RULES,
)


INPUT = REPO_ROOT / "exports" / "sample_price_audit" / "price_sample_audit.json"
OUTPUT = REPO_ROOT / "exports" / "sample_price_audit" / "price_sample_detail_audit.md"


def money(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def calc_expected_amount(item: dict[str, Any]) -> float | None:
    item_type = item.get("item_type")
    quantity = money(item.get("quantity"))
    unit_price = money(item.get("unit_price"))
    operation = item.get("operation_code")
    if quantity is None or unit_price is None:
        return None
    if item_type == "material":
        return round(quantity * unit_price, 2)
    if item_type == "process":
        rule = PROCESS_STANDARD_PRICE_RULES.get(str(operation))
        minimum = rule.minimum_charge if rule else 0.0
        return round(max(quantity * unit_price, minimum), 2)
    if item_type == "surface_treatment":
        rule = SURFACE_TREATMENT_STANDARD_PRICE_RULES.get(str(operation))
        minimum = rule.minimum_charge if rule else 0.0
        return round(max(quantity * unit_price, minimum), 2)
    return money(item.get("amount"))


def audit_item(item: dict[str, Any]) -> dict[str, Any]:
    actual = money(item.get("amount"))
    expected = calc_expected_amount(item)
    if actual is None and expected is None:
        return {"status": "missing", "operation_code": item.get("operation_code")}
    if actual is None or expected is None:
        return {
            "status": "mismatch",
            "operation_code": item.get("operation_code"),
            "actual": actual,
            "expected": expected,
        }
    diff = round(actual - expected, 2)
    return {
        "status": "ok" if diff == 0 else "mismatch",
        "operation_code": item.get("operation_code"),
        "actual": actual,
        "expected": expected,
        "diff": diff,
    }


def main() -> None:
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    rows = [item for item in data["results"] if "error" not in item]
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_type[row["type"]].append(row)

    lines = [
        "# Price Detail Audit",
        "",
        "This report checks line-item arithmetic independently from the saved quote summary.",
        "",
        "## By Type",
        "",
        "| Type | Items checked | Formula mismatches | Missing amount items | Top missing operations |",
        "|---|---:|---:|---:|---|",
    ]

    details: dict[str, Any] = {}
    for sample_type, items in sorted(by_type.items()):
        audits = [
            audit_item(item)
            for row in items
            for item in row.get("items", [])
            if item.get("item_type") in {"material", "process", "surface_treatment"}
        ]
        mismatches = [item for item in audits if item["status"] == "mismatch"]
        missing = [item for item in audits if item["status"] == "missing"]
        missing_counter = Counter(str(item.get("operation_code")) for item in missing)
        details[sample_type] = {
            "item_count": len(audits),
            "mismatches": mismatches,
            "missing_operations": missing_counter.most_common(),
        }
        top_missing = ", ".join(f"{op} x{count}" for op, count in missing_counter.most_common(8))
        lines.append(
            f"| {sample_type} | {len(audits)} | {len(mismatches)} | {len(missing)} | {top_missing} |"
        )

    lines.extend([
        "",
        "## Per Sample",
        "",
        "| Type | File | Material | System calc | System quote | Missing amount operations |",
        "|---|---|---|---:|---:|---|",
    ])
    for row in rows:
        missing_counter = Counter(
            str(item.get("operation_code"))
            for item in row.get("items", [])
            if item.get("item_type") in {"material", "process", "surface_treatment"}
            and item.get("amount") is None
        )
        missing_text = ", ".join(f"{op} x{count}" for op, count in missing_counter.most_common())
        summary = row["quote_summary"]
        lines.append(
            f"| {row['type']} | {row['stem']} | {row.get('material') or ''} | "
            f"{float(summary.get('system_calculated_amount') or 0):.2f} | "
            f"{float(summary.get('system_initial_quote') or 0):.2f} | {missing_text} |"
        )

    lines.extend([
        "",
        "## Detail JSON",
        "",
        "```json",
        json.dumps(details, ensure_ascii=False, indent=2),
        "```",
    ])
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
