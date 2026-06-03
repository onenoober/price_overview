from __future__ import annotations

import copy
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from price_overview.pricing_core import PricingCoreService, apply_manual_override, confirm_quote, confirm_risk, run_mock_pricing
from price_overview.pricing_core.contract_validation import validate_a_outputs, validate_contract
from price_overview.pricing_core.price_rules import PRICE_VERSION, PriceRule, find_active_price_rule


def load_mock_part_feature() -> dict:
    return json.loads((REPO_ROOT / "fixtures" / "mock" / "part_feature_plate_skd11.json").read_text(encoding="utf-8"))


class PricingCoreTests(unittest.TestCase):
    def run_pricing_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "pricing_core_cli.py"), *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed

    def test_mock_pipeline_outputs_match_contracts(self) -> None:
        result = run_mock_pricing(load_mock_part_feature())
        validate_contract(result["part_feature"], "part_feature.schema.json")
        validate_a_outputs(result)

        route = result["process_route"]
        quantities = result["quantity_result"]
        quote = result["quote_result"]

        self.assertTrue(route["requires_review"])
        self.assertTrue(all(operation["trigger_reasons"] for operation in route["operations"]))
        self.assertEqual([operation["sequence"] for operation in route["operations"]], list(range(1, len(route["operations"]) + 1)))
        self.assertTrue(all(item["basis"] and item["formula"] for item in quantities["items"]))
        self.assertEqual(quote["currency"], "CNY")
        self.assertEqual(quote["status"], "pending_review")
        self.assertTrue(all(item["formula"] and item["price_source"] for item in quote["items"]))
        self.assertGreater(quote["summary"]["system_initial_quote"], 0)
        self.assertIsNone(quote["summary"]["final_confirmed_amount"])

    def test_unknown_material_generates_missing_price_without_zero_amount(self) -> None:
        part_feature = load_mock_part_feature()
        part_feature["material"]["standard_code"] = "UNKNOWN_MATERIAL"
        part_feature["material"]["standard_name"] = None
        part_feature["risks"].append({"code": "UNKNOWN_MATERIAL", "level": "blocking", "message": "Material is unknown.", "source": "test", "requires_review": True, "evidence": [{"source_type": "manual"}]})

        result = run_mock_pricing(part_feature)
        validate_a_outputs(result)
        quote = result["quote_result"]
        material_items = [item for item in quote["items"] if item["item_type"] == "material"]

        self.assertEqual(quote["status"], "pending_review")
        self.assertTrue(any(risk["code"] == "MISSING_PRICE" for risk in quote["risks"]))
        self.assertIsNone(material_items[0]["amount"])
        self.assertIsNone(material_items[0]["system_amount"])
        self.assertIsNone(material_items[0]["final_amount"])
        self.assertEqual(quote["summary"]["material_amount"], 0)

    def test_unknown_material_keeps_fee_and_tax_items_traceable(self) -> None:
        part_feature = load_mock_part_feature()
        part_feature["material"]["standard_code"] = "UNKNOWN_MATERIAL"

        quote = run_mock_pricing(part_feature)["quote_result"]
        management_fee = next(item for item in quote["items"] if item["item_type"] == "management_fee")
        tax = next(item for item in quote["items"] if item["item_type"] == "tax")

        self.assertTrue(management_fee["formula"])
        self.assertTrue(management_fee["price_source"]["rule_id"])
        self.assertTrue(tax["formula"])
        self.assertTrue(tax["price_source"]["rule_id"])

    def test_missing_size_generates_null_quantity_and_review_risk(self) -> None:
        part_feature = load_mock_part_feature()
        part_feature["geometry"]["bounding_box"]["length"] = None

        result = run_mock_pricing(part_feature)
        validate_a_outputs(result)
        gross_weight = next(item for item in result["quantity_result"]["items"] if item["quantity_type"] == "gross_weight")
        cut_area = next(item for item in result["quantity_result"]["items"] if item["quantity_type"] == "cut_area")
        material_quote = next(item for item in result["quote_result"]["items"] if item["item_type"] == "material")
        wire_quote = next(item for item in result["quote_result"]["items"] if item["operation_code"] == "WIRE_CUTTING")

        self.assertIsNone(gross_weight["value"])
        self.assertIsNone(cut_area["value"])
        self.assertTrue(gross_weight["requires_review"])
        self.assertTrue(cut_area["requires_review"])
        self.assertIsNone(material_quote["amount"])
        self.assertIsNone(wire_quote["amount"])
        self.assertTrue(any(risk["code"] == "MISSING_QUANTITY_BASIS" for risk in result["quantity_result"]["risks"]))

    def test_high_complexity_adds_review_risk(self) -> None:
        part_feature = load_mock_part_feature()
        part_feature["features"]["complexity"]["complexity_score"] = 75

        result = run_mock_pricing(part_feature)
        validate_a_outputs(result)
        route = result["process_route"]

        self.assertTrue(route["requires_review"])
        self.assertTrue(any(risk["code"] == "HIGH_RISK_GEOMETRY" and risk["source"] == "process_recognition" for risk in route["risks"]))
        self.assertEqual(result["quote_result"]["status"], "pending_review")

    def test_complex_part_type_forces_manual_review(self) -> None:
        part_feature = load_mock_part_feature()
        part_feature["geometry"]["part_type"] = "complex"

        result = run_mock_pricing(part_feature)
        validate_a_outputs(result)
        route = result["process_route"]
        manual_review = next(operation for operation in route["operations"] if operation["operation_code"] == "MANUAL_REVIEW")

        self.assertTrue(manual_review["requires_review"])
        self.assertEqual(manual_review["confidence"], 0.5)
        self.assertTrue(any(risk["code"] == "HIGH_RISK_GEOMETRY" and risk["level"] == "blocking" for risk in route["risks"]))

    def test_no_heat_or_surface_treatment_does_not_add_those_operations(self) -> None:
        part_feature = load_mock_part_feature()
        part_feature["manufacturing_requirements"]["heat_treatment"]["required"] = False
        part_feature["manufacturing_requirements"]["surface_treatment"]["required"] = False

        result = run_mock_pricing(part_feature)
        validate_a_outputs(result)
        operation_codes = {operation["operation_code"] for operation in result["process_route"]["operations"]}
        quantity_types = {item["quantity_type"] for item in result["quantity_result"]["items"]}
        quote_operation_codes = {item["operation_code"] for item in result["quote_result"]["items"]}

        self.assertNotIn("HEAT_TREATMENT", operation_codes)
        self.assertNotIn("CHEMICAL_PLATING", operation_codes)
        self.assertNotIn("heat_weight", quantity_types)
        self.assertNotIn("HEAT_TREATMENT", quote_operation_codes)
        self.assertNotIn("CHEMICAL_PLATING", quote_operation_codes)
        self.assertEqual(result["quote_result"]["summary"]["surface_treatment_amount"], 0)

    def test_manual_override_preserves_system_amount(self) -> None:
        quote = run_mock_pricing(load_mock_part_feature())["quote_result"]
        target = next(item for item in quote["items"] if item["amount"] is not None)
        original_system_amount = target["system_amount"]

        updated = apply_manual_override(copy.deepcopy(quote), target_type="quote_item", target_id=target["item_id"], field="final_amount", new_value=999.0, reason="Manual review adjustment", operator_id="user_a")
        validate_contract(updated, "quote_result.schema.json")
        updated_target = next(item for item in updated["items"] if item["item_id"] == target["item_id"])

        self.assertEqual(updated_target["system_amount"], original_system_amount)
        self.assertEqual(updated_target["final_amount"], 999.0)
        self.assertEqual(updated["manual_overrides"][0]["reason"], "Manual review adjustment")

    def test_manual_override_requires_reason(self) -> None:
        quote = run_mock_pricing(load_mock_part_feature())["quote_result"]
        target = next(item for item in quote["items"] if item["amount"] is not None)

        with self.assertRaises(ValueError):
            apply_manual_override(copy.deepcopy(quote), target_type="quote_item", target_id=target["item_id"], field="final_amount", new_value=999.0, reason="", operator_id="user_a")

    def test_manual_override_rejects_unsupported_target_type(self) -> None:
        quote = run_mock_pricing(load_mock_part_feature())["quote_result"]

        with self.assertRaises(ValueError):
            apply_manual_override(copy.deepcopy(quote), target_type="quantity", target_id="qty_001", field="value", new_value=1, reason="Manual quantity adjustment", operator_id="user_a")

    def test_confirm_quote_rejects_unconfirmed_blocking_risk(self) -> None:
        part_feature = load_mock_part_feature()
        part_feature["geometry"]["part_type"] = "complex"
        quote = run_mock_pricing(part_feature)["quote_result"]

        with self.assertRaises(ValueError):
            confirm_quote(copy.deepcopy(quote), confirmed_by="user_a")

    def test_confirm_risk_records_manual_override_and_clears_risk(self) -> None:
        part_feature = load_mock_part_feature()
        part_feature["geometry"]["part_type"] = "complex"
        quote = run_mock_pricing(part_feature)["quote_result"]

        updated = confirm_risk(copy.deepcopy(quote), risk_code="HIGH_RISK_GEOMETRY", reason="Manufacturing engineer reviewed geometry.", operator_id="user_a")
        validate_contract(updated, "quote_result.schema.json")

        self.assertFalse(any(risk["code"] == "HIGH_RISK_GEOMETRY" and risk["level"] == "blocking" and risk["requires_review"] for risk in updated["risks"]))
        self.assertEqual(updated["manual_overrides"][-1]["target_type"], "risk")
        self.assertEqual(updated["manual_overrides"][-1]["target_id"], "HIGH_RISK_GEOMETRY")
        self.assertEqual(updated["manual_overrides"][-1]["reason"], "Manufacturing engineer reviewed geometry.")

    def test_confirm_quote_sets_confirmed_fields_for_clean_quote(self) -> None:
        part_feature = load_mock_part_feature()
        part_feature["risks"] = []
        part_feature["features"]["holes"] = []
        part_feature["features"]["precision_requirements"] = []
        part_feature["manufacturing_requirements"]["heat_treatment"]["required"] = False
        part_feature["manufacturing_requirements"]["surface_treatment"]["required"] = False
        part_feature["manufacturing_requirements"]["deburring"]["required"] = False

        quote = run_mock_pricing(part_feature)["quote_result"]
        self.assertEqual(quote["status"], "priced")

        confirmed = confirm_quote(copy.deepcopy(quote), confirmed_by="user_a", confirm_note="Ready for customer review.")
        validate_contract(confirmed, "quote_result.schema.json")

        self.assertEqual(confirmed["status"], "confirmed")
        self.assertEqual(confirmed["confirmed_by"], "user_a")
        self.assertIsNotNone(confirmed["confirmed_at"])
        self.assertEqual(confirmed["summary"]["final_confirmed_amount"], confirmed["summary"]["system_initial_quote"])
        self.assertEqual(confirmed["manual_overrides"][-1]["reason"], "Ready for customer review.")

    def test_confirm_quote_with_final_amount_records_manual_adjustment(self) -> None:
        part_feature = load_mock_part_feature()
        part_feature["risks"] = []
        part_feature["features"]["holes"] = []
        part_feature["features"]["precision_requirements"] = []
        part_feature["manufacturing_requirements"]["heat_treatment"]["required"] = False
        part_feature["manufacturing_requirements"]["surface_treatment"]["required"] = False
        part_feature["manufacturing_requirements"]["deburring"]["required"] = False
        quote = run_mock_pricing(part_feature)["quote_result"]
        final_amount = quote["summary"]["system_initial_quote"] + 50

        confirmed = confirm_quote(copy.deepcopy(quote), confirmed_by="user_a", confirmed_total_amount=final_amount)
        validate_contract(confirmed, "quote_result.schema.json")

        self.assertEqual(confirmed["status"], "confirmed")
        self.assertEqual(confirmed["summary"]["final_confirmed_amount"], final_amount)
        self.assertEqual(confirmed["summary"]["manual_adjustment_amount"], 50.0)

    def test_price_rule_filters_unapproved_expired_and_prefers_priority(self) -> None:
        rules = [
            PriceRule("draft_skd11", "material", "SKD11", "kg", Decimal("1.00"), "manual", "test", approval_status="draft", priority=1),
            PriceRule("expired_skd11", "material", "SKD11", "kg", Decimal("2.00"), "manual", "test", effective_to=date(2024, 1, 1), priority=1),
            PriceRule("low_priority_skd11", "material", "SKD11", "kg", Decimal("99.00"), "manual", "test", priority=50),
            PriceRule("selected_skd11", "material", "SKD11", "kg", Decimal("45.00"), "manual", "test", effective_from=date(2025, 1, 1), priority=10),
        ]

        rule = find_active_price_rule("material", "SKD11", rules, unit="kg", as_of_date=date(2026, 1, 1), version=PRICE_VERSION)

        self.assertIsNotNone(rule)
        self.assertEqual(rule.rule_id, "selected_skd11")

    def test_custom_empty_price_rules_generate_missing_price(self) -> None:
        result = run_mock_pricing(load_mock_part_feature(), price_rules=[])
        validate_a_outputs(result)
        quote = result["quote_result"]

        self.assertEqual(quote["status"], "pending_review")
        self.assertTrue(any(risk["code"] == "MISSING_PRICE" for risk in quote["risks"]))
        self.assertTrue(any(item["amount"] is None for item in quote["items"]))

    def test_service_price_validates_output_and_does_not_mutate_input(self) -> None:
        part_feature = load_mock_part_feature()
        original = copy.deepcopy(part_feature)

        result = PricingCoreService().price(part_feature)
        validate_a_outputs(result)

        self.assertEqual(part_feature, original)
        self.assertNotEqual(id(result["part_feature"]), id(part_feature))
        self.assertEqual(result["quote_result"]["task_id"], part_feature["task_id"])

    def test_service_confirm_risk_does_not_mutate_original_quote(self) -> None:
        part_feature = load_mock_part_feature()
        part_feature["geometry"]["part_type"] = "complex"
        quote = run_mock_pricing(part_feature)["quote_result"]
        original = copy.deepcopy(quote)

        updated = PricingCoreService().confirm_risk(quote, risk_code="HIGH_RISK_GEOMETRY", reason="Reviewed by engineer.", operator_id="user_a")
        validate_contract(updated, "quote_result.schema.json")

        self.assertEqual(quote, original)
        self.assertFalse(any(risk["code"] == "HIGH_RISK_GEOMETRY" and risk["requires_review"] for risk in updated["risks"]))
        self.assertEqual(updated["manual_overrides"][-1]["operator_id"], "user_a")

    def test_pricing_core_cli_price_writes_pipeline_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "pricing_result.json"

            self.run_pricing_cli("price", "--input", str(REPO_ROOT / "fixtures" / "mock" / "part_feature_plate_skd11.json"), "--output", str(output_path))
            result = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertIn("process_route", result)
        self.assertIn("quantity_result", result)
        self.assertIn("quote_result", result)
        validate_a_outputs(result)

    def test_pricing_core_cli_confirm_risk_accepts_pipeline_payload(self) -> None:
        part_feature = load_mock_part_feature()
        part_feature["geometry"]["part_type"] = "complex"
        pipeline_result = run_mock_pricing(part_feature)

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "pricing_result.json"
            output_path = Path(temp_dir) / "confirmed_risk.json"
            input_path.write_text(json.dumps(pipeline_result, ensure_ascii=False), encoding="utf-8")

            self.run_pricing_cli("confirm-risk", "--quote", str(input_path), "--risk-code", "HIGH_RISK_GEOMETRY", "--reason", "Reviewed by engineer.", "--operator-id", "user_a", "--output", str(output_path))
            result = json.loads(output_path.read_text(encoding="utf-8"))

        validate_a_outputs(result)
        self.assertIn("process_route", result)
        self.assertFalse(any(risk["code"] == "HIGH_RISK_GEOMETRY" and risk["requires_review"] for risk in result["quote_result"]["risks"]))

    def test_pricing_core_cli_confirm_quote_accepts_raw_quote(self) -> None:
        part_feature = load_mock_part_feature()
        part_feature["risks"] = []
        part_feature["features"]["holes"] = []
        part_feature["features"]["precision_requirements"] = []
        part_feature["manufacturing_requirements"]["heat_treatment"]["required"] = False
        part_feature["manufacturing_requirements"]["surface_treatment"]["required"] = False
        part_feature["manufacturing_requirements"]["deburring"]["required"] = False
        quote = run_mock_pricing(part_feature)["quote_result"]

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "quote_result.json"
            output_path = Path(temp_dir) / "confirmed_quote.json"
            input_path.write_text(json.dumps(quote, ensure_ascii=False), encoding="utf-8")

            self.run_pricing_cli("confirm-quote", "--quote", str(input_path), "--confirmed-by", "user_a", "--confirmed-total-amount", "1200.5", "--output", str(output_path))
            confirmed = json.loads(output_path.read_text(encoding="utf-8"))

        validate_contract(confirmed, "quote_result.schema.json")
        self.assertEqual(confirmed["status"], "confirmed")
        self.assertEqual(confirmed["confirmed_by"], "user_a")
        self.assertEqual(confirmed["summary"]["final_confirmed_amount"], 1200.5)


if __name__ == "__main__":
    unittest.main()
