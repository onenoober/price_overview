from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from price_overview.pricing_core import PricingCoreService
from price_overview.pricing_core.contract_validation import validate_a_outputs, validate_contract


DEFAULT_SAMPLE = {
    "sample_id": "mock_plate_skd11",
    "part_feature_file": "fixtures/mock/part_feature_plate_skd11.json",
    "expected_required_operations": [
        "MATERIAL_PREP",
        "CUTTING",
        "WIRE_CUTTING",
        "DRILLING",
        "COUNTERBORE",
        "TAPPING",
        "HEAT_TREATMENT",
        "GRINDING",
        "PRECISION_HOLE",
        "DEBURRING",
        "CHEMICAL_PLATING",
        "INSPECTION",
        "PACKAGING",
    ],
    "expected_risk_codes": ["WEIGHT_MISMATCH", "HIGH_PRECISION_REQUIREMENT"],
    "reference_quote_amount": 1199.0,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    service = PricingCoreService()
    samples = load_samples(args.manifest)
    results = [run_sample(sample, service, amount_tolerance=args.amount_tolerance) for sample in samples]
    payload = {
        "success": all(sample["passed"] for sample in results),
        "sample_count": len(results),
        "passed": sum(1 for sample in results if sample["passed"]),
        "failed": sum(1 for sample in results if not sample["passed"]),
        "samples": results,
    }
    write_json(payload, args.output)
    return 0 if payload["success"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run A-side pricing regression samples.")
    parser.add_argument("--manifest", help="Optional JSON manifest with regression samples.")
    parser.add_argument("--amount-tolerance", type=float, default=1.0)
    parser.add_argument("--output", help="Path to write JSON report. Defaults to stdout.")
    return parser


def load_samples(manifest: str | None) -> list[dict[str, Any]]:
    if not manifest:
        return [DEFAULT_SAMPLE]
    payload = json.loads(Path(manifest).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        samples = payload.get("samples")
    else:
        samples = payload
    if not isinstance(samples, list):
        raise ValueError("Regression manifest must be a list or an object with samples.")
    return samples


def run_sample(sample: dict[str, Any], service: PricingCoreService, *, amount_tolerance: float) -> dict[str, Any]:
    errors: list[str] = []
    sample_id = sample.get("sample_id") or Path(sample["part_feature_file"]).stem
    try:
        part_feature_path = resolve_path(sample["part_feature_file"])
        part_feature = json.loads(part_feature_path.read_text(encoding="utf-8"))
        validate_contract(part_feature, "part_feature.schema.json")
        result = service.price(part_feature)
        validate_a_outputs(result)
        operation_codes = {operation["operation_code"] for operation in result["process_route"]["operations"]}
        risk_codes = {risk["code"] for risk in result["quote_result"]["risks"]}
        expected_operations = set(sample.get("expected_required_operations", []))
        expected_risks = set(sample.get("expected_risk_codes", []))
        missing_operations = sorted(expected_operations - operation_codes)
        missing_risks = sorted(expected_risks - risk_codes)
        if missing_operations:
            errors.append(f"Missing required operations: {', '.join(missing_operations)}")
        if missing_risks:
            errors.append(f"Missing expected risks: {', '.join(missing_risks)}")

        quote_amount = result["quote_result"]["summary"]["system_initial_quote"]
        reference_quote_amount = sample.get("reference_quote_amount")
        amount_delta = None
        if reference_quote_amount is not None:
            amount_delta = round(float(quote_amount) - float(reference_quote_amount), 4)
            if abs(amount_delta) > amount_tolerance:
                errors.append(f"Quote amount delta {amount_delta} exceeds tolerance {amount_tolerance}.")

        return {
            "sample_id": sample_id,
            "passed": not errors,
            "quote_status": result["quote_result"]["status"],
            "quote_amount": quote_amount,
            "missing_operations": missing_operations,
            "missing_risks": missing_risks,
            "amount_delta": amount_delta,
            "errors": errors,
        }
    except Exception as exc:
        return {
            "sample_id": sample_id,
            "passed": False,
            "quote_status": None,
            "quote_amount": None,
            "missing_operations": [],
            "missing_risks": [],
            "amount_delta": None,
            "errors": [str(exc)],
        }


def resolve_path(path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def write_json(payload: dict[str, Any], output: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output:
        Path(output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    raise SystemExit(main())
