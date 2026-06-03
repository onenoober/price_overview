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

from price_overview.pricing_core import PricingCoreService, PricingStore


DEFAULT_PART_FEATURE = REPO_ROOT / "fixtures" / "mock" / "part_feature_plate_skd11.json"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    service = PricingCoreService()

    try:
        if args.command == "price":
            load_rule_input_if_present(service, args)
            payload = service.price(read_json(args.input))
            if args.db:
                service.save_pricing_result(payload, args.db)
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
        elif args.command == "dictionary":
            payload = {"kind": args.kind, "items": service.dictionary(args.kind)}
        elif args.command == "price-rules":
            load_rule_input_if_present(service, args)
            payload = {"price_rules": service.list_price_rules(active_only=args.active_only, price_type=args.price_type, target_code=args.target_code)}
            if args.db:
                service.save_price_rules(None, args.db)
        elif args.command == "history-sample":
            pricing_result = read_json(args.pricing_result)
            final_quote = extract_quote_result(read_json(args.final_quote)) if args.final_quote else None
            history_sample = service.history_sample(
                pricing_result,
                final_quote_result=final_quote,
                deal_amount=args.deal_amount,
                deal_status=args.deal_status,
                sample_id=args.sample_id,
            )
            if args.db:
                service.save_history_sample(history_sample, args.db)
            payload = {"history_sample": history_sample}
            if args.include_summary:
                payload["summary"] = service.history_summary(history_sample)
        elif args.command == "store-init":
            PricingStore(args.db).initialize()
            payload = {"db": args.db, "initialized": True}
        elif args.command == "store-save-result":
            pricing_result = read_json(args.pricing_result)
            service.save_pricing_result(pricing_result, args.db)
            payload = {"db": args.db, "task_id": pricing_result["quote_result"]["task_id"], "quote_id": pricing_result["quote_result"]["quote_id"], "saved": True}
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
    add_price_rules_argument(price_parser)
    price_parser.add_argument("--db", help="Optional SQLite database path for saving the pricing result.")
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

    dictionary_parser = subparsers.add_parser("dictionary", help="List a stable A-side base dictionary.")
    dictionary_parser.add_argument("--kind", required=True, choices=["materials", "operations", "surface_treatments", "risk_tags", "units"])
    add_output_argument(dictionary_parser)

    rules_parser = subparsers.add_parser("price-rules", help="List or import price rules.")
    add_price_rules_argument(rules_parser)
    rules_parser.add_argument("--active-only", action="store_true")
    rules_parser.add_argument("--price-type", choices=["material", "process", "surface_treatment", "risk_surcharge"])
    rules_parser.add_argument("--target-code")
    rules_parser.add_argument("--db", help="Optional SQLite database path for saving imported price rules.")
    add_output_argument(rules_parser)

    history_parser = subparsers.add_parser("history-sample", help="Build a quote history sample from a pricing result.")
    history_parser.add_argument("--pricing-result", required=True, help="Path to full pricing pipeline JSON.")
    history_parser.add_argument("--final-quote", help="Path to final quote_result JSON or full pricing pipeline JSON.")
    history_parser.add_argument("--deal-amount", type=Decimal)
    history_parser.add_argument("--deal-status")
    history_parser.add_argument("--sample-id")
    history_parser.add_argument("--include-summary", action="store_true")
    history_parser.add_argument("--db", help="Optional SQLite database path for saving the history sample.")
    add_output_argument(history_parser)

    store_init_parser = subparsers.add_parser("store-init", help="Initialize the A-side SQLite persistence store.")
    store_init_parser.add_argument("--db", required=True)
    add_output_argument(store_init_parser)

    store_save_parser = subparsers.add_parser("store-save-result", help="Save a full pricing result into the A-side SQLite store.")
    store_save_parser.add_argument("--pricing-result", required=True)
    store_save_parser.add_argument("--db", required=True)
    add_output_argument(store_save_parser)

    return parser


def add_quote_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--quote", required=True, help="Path to quote_result JSON or full pricing pipeline JSON.")


def add_output_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", help="Path to write JSON output. Defaults to stdout.")


def add_price_rules_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--price-rules", help="Optional price_rules JSON file.")
    parser.add_argument("--default-approval-status", default="draft", choices=["draft", "approved", "disabled"])


def load_rule_input_if_present(service: PricingCoreService, args: argparse.Namespace) -> None:
    if getattr(args, "price_rules", None):
        service.load_price_rules(args.price_rules, default_approval_status=args.default_approval_status)


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
