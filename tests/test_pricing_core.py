from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from price_overview.pricing_core import apply_manual_override, run_mock_pricing
from price_overview.pricing_core.contract_validation import validate_a_outputs, validate_contract


def load_mock_part_feature() -> dict:
    return json.loads((REPO_ROOT / "fixtures" / "mock" / "part_feature_plate_skd11.json").read_text(encoding="utf-8"))


class PricingCoreTests(unittest.TestCase):
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

    def test_missing_size_generates_null_quantity_and_review_risk(self) -> None:
        part_feature = load_mock_part_feature()
        part_feature["geometry"]["bounding_box"]["length"] = None

        result = run_mock_pricing(part_feature)
        validate_a_outputs(result)
        gross_weight = next(item for item in result["quantity_result"]["items"] if item["quantity_type"] == "gross_weight")

        self.assertIsNone(gross_weight["value"])
        self.assertTrue(gross_weight["requires_review"])
        self.assertTrue(any(risk["code"] == "MISSING_QUANTITY_BASIS" for risk in result["quantity_result"]["risks"]))

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


if __name__ == "__main__":
    unittest.main()

