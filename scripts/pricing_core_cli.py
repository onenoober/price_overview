from __future__ import annotations

import argparse
from collections.abc import Callable
from decimal import Decimal
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from price_overview.pricing_core import PricingCoreService


DEFAULT_PART_FEATURE = REPO_ROOT / "fixtures" / "mock" / "part_feature_plate_skd11.json"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    service = PricingCoreService()

    try:
        if args.command == "price":
            payload = service.price(read_json(args.input))
        elif args.command == "override":
            payload = run_quote_command(
                args,
                service.apply_override,
                target_type=args.target_type,
                target_id=args.target_id,
                field=args.field,
                new_value=parse_json_value(args.new_value),
                reason=args.reason,
                operator_id=args.operator_id,
            )
        elif args.command == "confirm-risk":
            payload = run_quote_command(
                args,
                service.confirm_risk,
                risk_code=args.risk_code,
                reason=args.reason,
                operator_id=args.operator_id,
            )
        elif args.command == "confirm-quote":
            payload = run_quote_command(
                args,
                service.confirm_quote,
                confirmed_by=args.confirmed_by,
                confirmed_total_amount=args.confirmed_total_amount,
                confirm_note=args.confirm_note,
            )
        else:
            parser.error(f"Unknown command: {args.command}")
    except Exception as exc:
        error_payload = {
            "success": False,
            "data": None,
            "error": {"code": "PRICING_CORE_ERROR", "message": str(exc), "details": []},
        }
        print(json.dumps(error_payload, ensure_ascii=False), file=sys.stderr)
        return 1

    write_json(payload, args.output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A-side pricing core integration CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    price_parser = subparsers.add_parser(
        "price",
        help="Generate process, quantity, and quote results from part_feature JSON.",
    )
    price_parser.add_argument("--input", default=str(DEFAULT_PART_FEATURE), help="Path to part_feature JSON.")
    add_output_argument(price_parser)

    override_parser = subparsers.add_parser("override", help="Apply a manual quote override.")
    add_quote_argument(override_parser)
    override_parser.add_argument("--target-type", required=True, choices=["quote_item", "quote_summary"])
    override_parser.add_argument("--target-id", required=True)
    override_parser.add_argument("--field", required=True)
    override_parser.add_argument("--new-value", required=True)
    override_parser.add_argument("--reason", required=True)
    override_parser.add_argument("--operator-id", required=True)
    add_output_argument(override_parser)

    risk_parser = subparsers.add_parser("confirm-risk", help="Confirm a reviewable quote risk.")
    add_quote_argument(risk_parser)
    risk_parser.add_argument("--risk-code", required=True)
    risk_parser.add_argument("--reason", required=True)
    risk_parser.add_argument("--operator-id", required=True)
    add_output_argument(risk_parser)

    confirm_parser = subparsers.add_parser("confirm-quote", help="Confirm a clean quote result.")
    add_quote_argument(confirm_parser)
    confirm_parser.add_argument("--confirmed-by", required=True)
    confirm_parser.add_argument("--confirmed-total-amount", type=Decimal)
    confirm_parser.add_argument("--confirm-note", default="")
    add_output_argument(confirm_parser)

    return parser


def add_quote_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--quote", required=True, help="Path to quote_result JSON or full pricing pipeline JSON.")


def add_output_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", help="Path to write JSON output. Defaults to stdout.")


def run_quote_command(args: argparse.Namespace, operation: Callable[..., dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    payload = read_json(args.quote)
    quote_result = extract_quote_result(payload)
    updated_quote = operation(quote_result, **kwargs)
    if isinstance(payload, dict) and isinstance(payload.get("quote_result"), dict):
        payload["quote_result"] = updated_quote
        return payload
    return updated_quote


def extract_quote_result(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("quote_result"), dict):
        return payload["quote_result"]
    return payload


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(payload: dict[str, Any], output: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output:
        Path(output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")


def parse_json_value(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


if __name__ == "__main__":
    raise SystemExit(main())
