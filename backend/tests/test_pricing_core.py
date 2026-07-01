from __future__ import annotations

import os
import unittest

from backend.app.market_material_pricing import (
    MaterialMarketPrice,
    SurfaceTreatmentMarketPrice,
)
from backend.app.domain_v2.route_engine.config import ROUTE_ENGINE_ENV
from backend.app.pricing_core import build_pricing_core_service
from backend.app.schema_validation import validate_process_route, validate_quantity_result


class PricingCoreTests(unittest.TestCase):
    """这些用例校验旧追加链路线 → 数量/报价的耦合契约，固定走 legacy 引擎；
    新分层引擎的路线契约由 ``test_route_*`` 套件覆盖。"""

    def setUp(self) -> None:
        self._prev_route_engine = os.environ.get(ROUTE_ENGINE_ENV)
        os.environ[ROUTE_ENGINE_ENV] = "legacy"

    def tearDown(self) -> None:
        if self._prev_route_engine is None:
            os.environ.pop(ROUTE_ENGINE_ENV, None)
        else:
            os.environ[ROUTE_ENGINE_ENV] = self._prev_route_engine
    def test_missing_geometry_does_not_generate_fixed_cnc_or_cutting_amounts(
        self,
    ) -> None:
        result = build_pricing_core_service().build_quote(
            task_id="task_001",
            quote_id="quote_001",
            part_feature=part_feature_without_step_complexity(),
            risks=[],
            priced_at="2026-06-08T10:00:00+08:00",
            price_version="a-basic-v1",
        )

        quote_items = {
            item["operation_code"]: item
            for item in result.quote_result["items"]
            if item.get("operation_code")
        }
        quantities = {
            item["operation_code"]: item
            for item in result.quantity_result["items"]
            if item.get("operation_code")
        }

        self.assertNotIn("cnc_milling", quantities)
        self.assertNotIn("cnc_milling", quote_items)
        self.assertNotIn("saw_cut", quantities)
        self.assertNotIn("saw_cut", quote_items)
        self.assertEqual(quantities["deburr"]["value"], 1)
        self.assertEqual(quantities["deburr"]["unit"], "pcs")
        self.assertEqual(quote_items["deburr"]["unit_price"], 12.5)
        self.assertEqual(quote_items["deburr"]["amount"], 12.5)
        self.assertTrue(quote_items["deburr"]["requires_review"])

        missing_price_operations = {
            risk["evidence"][0]["rule_code"].split(":", 1)[1]
            for risk in result.quote_result["risks"]
            if risk["code"] == "MISSING_PRICE_OR_QUANTITY"
        }
        self.assertNotIn("deburr", missing_price_operations)
        self.assertIn(
            "QUANTITY_DEBURR_COMPLEXITY_MISSING",
            {risk["code"] for risk in result.quantity_result["risks"]},
        )

    def test_material_gross_weight_uses_bbox_and_density(self) -> None:
        result = build_pricing_core_service().build_quote(
            task_id="task_002",
            quote_id="quote_002",
            part_feature=part_feature_with_quantity_inputs(),
            risks=[],
            priced_at="2026-06-08T10:00:00+08:00",
            price_version="a-basic-v1",
        )
        validate_quantity_result(result.quantity_result)

        quantities = {
            item["quantity_type"]: item
            for item in result.quantity_result["items"]
        }

        self.assertEqual(quantities["gross_weight"]["value"], 0.0785)
        self.assertEqual(quantities["gross_weight"]["unit"], "kg")
        self.assertFalse(quantities["gross_weight"]["requires_review"])
        self.assertEqual(quantities["inspection_count"]["value"], 3)
        self.assertEqual(quantities["manual_quantity"]["value"], 3)

        cnc_quantity = next(
            item
            for item in result.quantity_result["items"]
            if item["operation_code"] == "cnc_milling"
        )
        self.assertEqual(cnc_quantity["value"], 0.0987)
        self.assertTrue(cnc_quantity["requires_review"])
        self.assertIn("装夹分钟", cnc_quantity["formula"])
        self.assertIn("上下表面面积", cnc_quantity["formula"])
        self.assertIn("CNC 工时按默认装夹", cnc_quantity["review_reason"])
        cnc_basis = {
            item["name"]: item["value"]
            for item in cnc_quantity["basis"]
        }
        self.assertEqual(cnc_basis["top_bottom_face_area"], 2000)
        self.assertEqual(cnc_basis["outer_profile_length"], 140)
        self.assertEqual(cnc_basis["setup_minutes"], 5.0)
        self.assertEqual(cnc_basis["contour_passes"], 2.0)
        self.assertIn(
            "QUANTITY_CNC_ESTIMATE_REQUIRES_REVIEW",
            {risk["code"] for risk in result.quantity_result["risks"]},
        )

    def test_material_price_uses_review_weight_when_density_missing(self) -> None:
        part_feature = part_feature_with_quantity_inputs()
        part_feature["part"]["quantity"] = 1
        part_feature["material"].update(
            {
                "raw_text": "Q235A",
                "standard_code": None,
                "standard_name": None,
                "density": None,
                "density_unit": None,
            }
        )
        part_feature["geometry"]["bounding_box"] = {
            "length": 40,
            "width": 15,
            "height": 15,
            "unit": "mm",
        }
        part_feature["geometry"]["pdf_weight"] = {
            "value": 0.05,
            "unit": "kg",
            "source": source("pdf_weight"),
        }

        result = build_pricing_core_service(
            material_price_provider=NullMaterialPriceProvider(),
            material_estimate_provider=NullMaterialPriceProvider(),
            surface_treatment_price_provider=NullSurfaceTreatmentPriceProvider(),
            surface_treatment_estimate_provider=NullSurfaceTreatmentPriceProvider(),
        ).build_quote(
            task_id="task_missing_density",
            quote_id="quote_missing_density",
            part_feature=part_feature,
            risks=[],
            priced_at="2026-06-17T10:00:00+08:00",
            price_version="a-basic-v1",
        )
        quantities = {
            item["quantity_type"]: item
            for item in result.quantity_result["items"]
        }
        material_item = next(
            item
            for item in result.quote_result["items"]
            if item["item_type"] == "material"
        )

        self.assertIsNone(quantities["gross_weight"]["value"])
        self.assertTrue(quantities["gross_weight"]["requires_review"])
        self.assertEqual(quantities["material_weight"]["value"], 0.05)
        self.assertTrue(quantities["material_weight"]["requires_review"])
        self.assertEqual(material_item["quantity"], 0.05)
        self.assertEqual(material_item["unit_price"], 4.5)
        self.assertEqual(material_item["amount"], 0.23)
        self.assertTrue(material_item["requires_review"])
        self.assertIn(
            "MATERIAL_DENSITY_MISSING",
            {risk["code"] for risk in result.quantity_result["risks"]},
        )
        self.assertIn(
            "MATERIAL_WEIGHT_REQUIRES_REVIEW",
            {risk["code"] for risk in result.quote_result["risks"]},
        )
        self.assertEqual(result.quote_result["status"], "pending_review")

    def test_material_price_can_use_realtime_market_search(self) -> None:
        result = build_pricing_core_service(
            material_price_provider=FakeMaterialPriceProvider(),
            surface_treatment_price_provider=NullSurfaceTreatmentPriceProvider(),
            surface_treatment_estimate_provider=NullSurfaceTreatmentPriceProvider(),
        ).build_quote(
            task_id="task_market_001",
            quote_id="quote_market_001",
            part_feature=part_feature_with_quantity_inputs(),
            risks=[],
            priced_at="2026-06-11T10:00:00+08:00",
            price_version="market-test-v1",
        )

        material_item = next(
            item
            for item in result.quote_result["items"]
            if item["item_type"] == "material"
        )

        self.assertEqual(material_item["unit_price"], 3.76)
        self.assertEqual(material_item["amount"], 0.3)
        self.assertTrue(material_item["requires_review"])
        self.assertEqual(
            material_item["price_source"]["source_type"],
            "market_search",
        )
        self.assertIn(
            "MARKET_PRICE_REQUIRES_REVIEW",
            {risk["code"] for risk in result.quote_result["risks"]},
        )
        self.assertEqual(result.quote_result["status"], "pending_review")

    def test_known_material_price_falls_back_to_builtin_table(self) -> None:
        part_feature = part_feature_with_quantity_inputs()
        part_feature["material"]["raw_text"] = "Q235A"
        part_feature["material"]["standard_code"] = "Q235A"

        result = build_pricing_core_service(
            material_price_provider=NullMaterialPriceProvider(),
            material_estimate_provider=NullMaterialPriceProvider(),
            surface_treatment_price_provider=NullSurfaceTreatmentPriceProvider(),
            surface_treatment_estimate_provider=NullSurfaceTreatmentPriceProvider(),
        ).build_quote(
            task_id="task_material_fallback",
            quote_id="quote_material_fallback",
            part_feature=part_feature,
            risks=[],
            priced_at="2026-06-11T10:00:00+08:00",
            price_version="fallback-test-v1",
        )

        material_item = next(
            item
            for item in result.quote_result["items"]
            if item["item_type"] == "material"
        )
        risks = {
            risk["code"]
            for risk in result.quote_result["risks"]
        }

        self.assertEqual(material_item["unit_price"], 4.5)
        self.assertEqual(material_item["amount"], 0.35)
        self.assertEqual(
            material_item["price_source"]["source_id"],
            "a_basic_material_price_table",
        )
        self.assertTrue(material_item["requires_review"])
        self.assertIn("MATERIAL_FALLBACK_PRICE_REQUIRES_REVIEW", risks)
        self.assertNotIn("MISSING_PRICE_OR_QUANTITY", risks)

    def test_material_price_falls_back_to_gpt_only_estimate(self) -> None:
        result = build_pricing_core_service(
            material_price_provider=NullMaterialPriceProvider(),
            material_estimate_provider=FakeMaterialEstimateProvider(),
            surface_treatment_price_provider=NullSurfaceTreatmentPriceProvider(),
            surface_treatment_estimate_provider=NullSurfaceTreatmentPriceProvider(),
        ).build_quote(
            task_id="task_material_estimate",
            quote_id="quote_material_estimate",
            part_feature=part_feature_with_quantity_inputs(),
            risks=[],
            priced_at="2026-06-11T10:00:00+08:00",
            price_version="estimate-test-v1",
        )

        material_item = next(
            item
            for item in result.quote_result["items"]
            if item["item_type"] == "material"
        )

        self.assertEqual(material_item["unit_price"], 5.25)
        self.assertEqual(material_item["amount"], 0.41)
        self.assertEqual(material_item["price_source"]["source_type"], "ai_estimate")
        self.assertTrue(material_item["requires_review"])
        self.assertIn("GPT-only 估算", material_item["explanation"])
        self.assertIn(
            "MATERIAL_AI_ESTIMATE_REQUIRES_REVIEW",
            {risk["code"] for risk in result.quote_result["risks"]},
        )

    def test_3d_review_constraint_is_risk_only_not_route_quantity_or_quote_item(self) -> None:
        part_feature = part_feature_with_quantity_inputs()
        part_feature["manufacturing_requirements"]["technical_requirements"] = [
            "未标注尺寸参见3D。"
        ]

        result = build_pricing_core_service(
            material_price_provider=FakeMaterialPriceProvider(),
            surface_treatment_price_provider=NullSurfaceTreatmentPriceProvider(),
            surface_treatment_estimate_provider=NullSurfaceTreatmentPriceProvider(),
        ).build_quote(
            task_id="task_review_only",
            quote_id="quote_review_only",
            part_feature=part_feature,
            risks=[],
            priced_at="2026-06-11T10:00:00+08:00",
            price_version="a-basic-v1",
        )

        route_codes = {
            item["operation_code"]
            for item in result.process_route["operations"]
        }
        quantity_codes = {
            item["operation_code"]
            for item in result.quantity_result["items"]
        }
        quote_codes = {
            item["operation_code"]
            for item in result.quote_result["items"]
            if item.get("operation_code")
        }
        missing_price_operations = {
            risk["evidence"][0]["rule_code"].split(":", 1)[1]
            for risk in result.quote_result["risks"]
            if risk["code"] == "MISSING_PRICE_OR_QUANTITY"
        }

        self.assertNotIn("review_drawing", route_codes)
        self.assertNotIn("review_drawing", quantity_codes)
        self.assertNotIn("review_drawing", quote_codes)
        self.assertNotIn("review_drawing", missing_price_operations)
        self.assertIn(
            "TECH_REQ_REVIEW_3D",
            {risk["code"] for risk in result.process_route["risks"]},
        )

    def test_plating_auxiliary_steps_are_route_only(self) -> None:
        part_feature = part_feature_with_quantity_inputs()
        part_feature["manufacturing_requirements"]["surface_treatment"] = {
            "required": True,
            "raw_text": "化学镍",
            "standard_code": "CHEMICAL_NICKEL",
            "confidence": 0.9,
            "source": source("surface"),
        }

        result = build_pricing_core_service(
            material_price_provider=FakeMaterialPriceProvider(),
            surface_treatment_price_provider=NullSurfaceTreatmentPriceProvider(),
            surface_treatment_estimate_provider=NullSurfaceTreatmentPriceProvider(),
        ).build_quote(
            task_id="task_plating_route_only",
            quote_id="quote_plating_route_only",
            part_feature=part_feature,
            risks=[],
            priced_at="2026-06-11T10:00:00+08:00",
            price_version="a-basic-v1",
        )

        route_codes = {
            item["operation_code"]
            for item in result.process_route["operations"]
        }
        quantity_codes = {
            item["operation_code"]
            for item in result.quantity_result["items"]
        }
        quote_codes = {
            item["operation_code"]
            for item in result.quote_result["items"]
            if item.get("operation_code")
        }
        missing_price_operations = {
            risk["evidence"][0]["rule_code"].split(":", 1)[1]
            for risk in result.quote_result["risks"]
            if risk["code"] == "MISSING_PRICE_OR_QUANTITY"
        }

        self.assertIn("pre_plating_cleaning", route_codes)
        self.assertNotIn("post_plating_inspection", route_codes)
        self.assertIn("chemical_nickel", route_codes)
        self.assertIn("coating_thickness_inspection", route_codes)
        self.assertIn("surface_inspection", route_codes)
        self.assertNotIn("pre_plating_cleaning", quantity_codes)
        self.assertNotIn("pre_plating_cleaning", quote_codes)
        self.assertIn("chemical_nickel", quote_codes)
        self.assertNotIn("pre_plating_cleaning", missing_price_operations)
        self.assertNotIn("chemical_nickel", missing_price_operations)

        chemical_nickel_item = next(
            item
            for item in result.quote_result["items"]
            if item.get("operation_code") == "chemical_nickel"
        )
        self.assertEqual(chemical_nickel_item["unit_price"], 900.0)
        self.assertEqual(chemical_nickel_item["amount"], 80.0)
        self.assertEqual(
            chemical_nickel_item["price_source"]["source_id"],
            "surface_treatment_price_standard",
        )
        self.assertTrue(chemical_nickel_item["requires_review"])

    def test_surface_treatment_price_can_use_tavily_gpt_candidate(self) -> None:
        part_feature = part_feature_with_quantity_inputs()
        part_feature["manufacturing_requirements"]["surface_treatment"] = {
            "required": True,
            "raw_text": "化学镍",
            "standard_code": "CHEMICAL_NICKEL",
            "confidence": 0.9,
            "source": source("surface"),
        }

        result = build_pricing_core_service(
            material_price_provider=FakeMaterialPriceProvider(),
            surface_treatment_price_provider=FakeSurfaceTreatmentPriceProvider(),
        ).build_quote(
            task_id="task_surface_market",
            quote_id="quote_surface_market",
            part_feature=part_feature,
            risks=[],
            priced_at="2026-06-11T10:00:00+08:00",
            price_version="market-test-v1",
        )

        chemical_nickel_item = next(
            item
            for item in result.quote_result["items"]
            if item.get("operation_code") == "chemical_nickel"
        )

        self.assertEqual(chemical_nickel_item["quantity"], 0.0022)
        self.assertEqual(chemical_nickel_item["unit"], "m2")
        self.assertEqual(chemical_nickel_item["unit_price"], 1200.0)
        self.assertEqual(chemical_nickel_item["amount"], 2.64)
        self.assertEqual(chemical_nickel_item["price_source"]["source_type"], "market_search")
        self.assertTrue(chemical_nickel_item["requires_review"])
        self.assertIn(
            "SURFACE_TREATMENT_MARKET_PRICE_REQUIRES_REVIEW",
            {risk["code"] for risk in result.quote_result["risks"]},
        )

    def test_surface_treatment_price_falls_back_to_gpt_only_estimate(self) -> None:
        part_feature = part_feature_with_quantity_inputs()
        part_feature["manufacturing_requirements"]["surface_treatment"] = {
            "required": True,
            "raw_text": "化学镍",
            "standard_code": "CHEMICAL_NICKEL",
            "confidence": 0.9,
            "source": source("surface"),
        }

        result = build_pricing_core_service(
            material_price_provider=FakeMaterialPriceProvider(),
            surface_treatment_price_provider=NullSurfaceTreatmentPriceProvider(),
            surface_treatment_estimate_provider=FakeSurfaceTreatmentEstimateProvider(),
        ).build_quote(
            task_id="task_surface_estimate",
            quote_id="quote_surface_estimate",
            part_feature=part_feature,
            risks=[],
            priced_at="2026-06-11T10:00:00+08:00",
            price_version="estimate-test-v1",
        )

        chemical_nickel_item = next(
            item
            for item in result.quote_result["items"]
            if item.get("operation_code") == "chemical_nickel"
        )

        self.assertEqual(chemical_nickel_item["quantity"], 0.0022)
        self.assertEqual(chemical_nickel_item["unit"], "m2")
        self.assertEqual(chemical_nickel_item["unit_price"], 1300.0)
        self.assertEqual(chemical_nickel_item["amount"], 2.86)
        self.assertEqual(chemical_nickel_item["price_source"]["source_type"], "ai_estimate")
        self.assertIn("AI估算价", chemical_nickel_item["formula"])
        self.assertIn(
            "SURFACE_TREATMENT_AI_ESTIMATE_REQUIRES_REVIEW",
            {risk["code"] for risk in result.quote_result["risks"]},
        )

    def test_non_chemical_surface_treatment_can_be_priced_independently(self) -> None:
        part_feature = part_feature_with_quantity_inputs()
        part_feature["manufacturing_requirements"]["surface_treatment"] = {
            "required": True,
            "raw_text": "喷塑",
            "standard_code": "POWDER_COATING",
            "confidence": 0.91,
            "source": source("surface"),
        }

        result = build_pricing_core_service(
            material_price_provider=FakeMaterialPriceProvider(),
            surface_treatment_price_provider=FakeSurfaceTreatmentPriceProvider(),
        ).build_quote(
            task_id="task_surface_powder",
            quote_id="quote_surface_powder",
            part_feature=part_feature,
            risks=[],
            priced_at="2026-06-11T10:00:00+08:00",
            price_version="market-test-v1",
        )

        surface_item = next(
            item
            for item in result.quote_result["items"]
            if item.get("item_type") == "surface_treatment"
        )

        self.assertEqual(surface_item["operation_code"], "powder_coating")
        self.assertEqual(surface_item["quantity"], 0.0022)
        self.assertEqual(surface_item["unit"], "m2")
        self.assertEqual(surface_item["unit_price"], 1200.0)
        self.assertEqual(surface_item["amount"], 2.64)
        self.assertEqual(surface_item["price_source"]["source_type"], "market_search")
        self.assertTrue(surface_item["requires_review"])

    def test_management_fee_is_always_five_percent_of_material_amount(self) -> None:
        result = build_pricing_core_service(
            material_price_provider=FakeMaterialPriceProvider()
        ).build_quote(
            task_id="task_management_fee",
            quote_id="quote_management_fee",
            part_feature=part_feature_with_quantity_inputs(),
            risks=[],
            priced_at="2026-06-11T10:00:00+08:00",
            price_version="a-basic-v1",
        )

        summary = result.quote_result["summary"]
        management_item = next(
            item
            for item in result.quote_result["items"]
            if item["item_type"] == "management_fee"
        )
        expected_management_fee = round(summary["material_amount"] * 0.05, 2)

        self.assertEqual(summary["management_fee"], expected_management_fee)
        self.assertEqual(management_item["amount"], expected_management_fee)

    def test_tax_excludes_material_amount_from_tax_base(self) -> None:
        result = build_pricing_core_service(
            material_price_provider=FakeMaterialPriceProvider(),
        ).build_quote(
            task_id="task_tax_base",
            quote_id="quote_tax_base",
            part_feature=part_feature_with_quantity_inputs(),
            risks=[],
            priced_at="2026-06-11T10:00:00+08:00",
            price_version="a-basic-v1",
        )

        summary = result.quote_result["summary"]
        tax_item = next(
            item
            for item in result.quote_result["items"]
            if item["item_type"] == "tax"
        )
        expected_tax = round(
            (
                summary["process_amount"]
                + summary["surface_treatment_amount"]
                + summary["management_fee"]
            )
            * 0.13,
            2,
        )

        self.assertEqual(summary["tax_amount"], expected_tax)
        self.assertEqual(tax_item["amount"], expected_tax)

    def test_process_price_uses_south_china_standard_table(self) -> None:
        result = build_pricing_core_service(
            material_price_provider=FakeMaterialPriceProvider(),
        ).build_quote(
            task_id="task_process_market",
            quote_id="quote_process_market",
            part_feature=part_feature_with_quantity_inputs(),
            risks=[],
            priced_at="2026-06-11T10:00:00+08:00",
            price_version="market-test-v1",
        )

        cnc_item = next(
            item
            for item in result.quote_result["items"]
            if item.get("operation_code") == "cnc_milling"
        )

        self.assertEqual(cnc_item["unit_price"], 115.0)
        self.assertEqual(cnc_item["amount"], 80.0)
        self.assertEqual(cnc_item["price_source"]["source_type"], "manual")
        self.assertTrue(cnc_item["price_source"]["rule_id"].startswith("SOUTH_CHINA_CNC_MILLING"))
        self.assertEqual(cnc_item["formula"], "按华南工序标准：max(工程量 × 单价，起步价)")
        self.assertTrue(cnc_item["requires_review"])
        self.assertNotIn(
            "PROCESS_MARKET_PRICE_REQUIRES_REVIEW",
            {risk["code"] for risk in result.quote_result["risks"]},
        )

    def test_process_route_override_bypasses_rule_route_for_quote(self) -> None:
        part_feature = part_feature_with_quantity_inputs()
        process_route_override = {
            "schema_version": "1.0",
            "task_id": "task_ai_override",
            "route_id": "route_ai_override",
            "stage_route": [],
            "operations": [
                route_operation("material_prepare", 1),
                route_operation("turning", 2),
                route_operation(
                    "unmapped_operation",
                    3,
                    operation_name="未登记工序：氧化发黑",
                    requires_review=True,
                ),
                route_operation("inspection", 4),
            ],
            "requires_review": True,
            "risks": [],
        }

        result = build_pricing_core_service().build_quote(
            task_id="task_ai_override",
            quote_id="quote_ai_override",
            part_feature=part_feature,
            risks=[],
            priced_at="2026-06-08T10:00:00+08:00",
            price_version="a-basic-v1",
            process_route_override=process_route_override,
        )

        route_codes = [
            operation["operation_code"]
            for operation in result.process_route["operations"]
        ]
        quote_items = {
            item["operation_code"]: item
            for item in result.quote_result["items"]
            if item.get("operation_code")
        }

        self.assertEqual(
            route_codes,
            ["material_prepare", "turning", "unmapped_operation", "inspection"],
        )
        self.assertIn("turning", quote_items)
        self.assertIn("inspection", quote_items)
        self.assertNotIn("cnc_milling", quote_items)
        self.assertNotIn("unmapped_operation", quote_items)

    def test_low_confidence_hole_quantity_requires_review(self) -> None:
        part_feature = part_feature_with_quantity_inputs()
        part_feature["features"]["holes"] = [
            {
                "hole_type": "through",
                "diameter": 6,
                "depth": None,
                "count": 2,
                "confidence": 0.42,
                "evidence": [source("low_confidence_hole")],
            }
        ]

        result = build_pricing_core_service().build_quote(
            task_id="task_003",
            quote_id="quote_003",
            part_feature=part_feature,
            risks=[],
            priced_at="2026-06-08T10:00:00+08:00",
            price_version="a-basic-v1",
        )

        drilling_quantity = next(
            item
            for item in result.quantity_result["items"]
            if item["operation_code"] == "drilling"
        )
        self.assertEqual(drilling_quantity["value"], 2)
        self.assertTrue(drilling_quantity["requires_review"])
        self.assertIn(
            "QUANTITY_LOW_CONFIDENCE_HOLE_COUNT",
            {risk["code"] for risk in result.quantity_result["risks"]},
        )

    def test_boring_route_uses_large_bore_count_for_precision_hole_quote(self) -> None:
        part_feature = part_feature_with_quantity_inputs()
        part_feature["geometry"]["part_type"] = "shaft"
        part_feature["geometry"]["bounding_box"] = {
            "length": 120,
            "width": 60,
            "height": 60,
            "unit": "mm",
        }
        part_feature["features"]["holes"] = [
            {
                "hole_type": "blind",
                "diameter": 37,
                "depth": 45,
                "count": 2,
                "confidence": 0.82,
                "feature_role": "large_coaxial_bore",
                "evidence": [source("large_coaxial_bore")],
            }
        ]
        process_route_override = {
            "schema_version": "1.0",
            "task_id": "task_boring_quote",
            "route_id": "route_boring_quote",
            "stage_route": [],
            "operations": [
                route_operation("material_prepare", 1),
                route_operation("turning", 2),
                route_operation("boring", 3, requires_review=True),
                route_operation("inspection", 4),
            ],
            "requires_review": True,
            "risks": [],
        }

        result = build_pricing_core_service().build_quote(
            task_id="task_boring_quote",
            quote_id="quote_boring_quote",
            part_feature=part_feature,
            risks=[],
            priced_at="2026-06-08T10:00:00+08:00",
            price_version="a-basic-v1",
            process_route_override=process_route_override,
        )

        quantities = {
            item["operation_code"]: item
            for item in result.quantity_result["items"]
        }
        quote_items = {
            item["operation_code"]: item
            for item in result.quote_result["items"]
            if item.get("operation_code")
        }
        missing_price_operations = {
            risk["evidence"][0]["rule_code"].split(":", 1)[1]
            for risk in result.quote_result["risks"]
            if risk["code"] == "MISSING_PRICE_OR_QUANTITY"
        }

        self.assertIn("precision_hole", quantities)
        self.assertEqual(quantities["precision_hole"]["value"], 2)
        self.assertEqual(quantities["precision_hole"]["unit"], "pcs")
        self.assertTrue(quantities["precision_hole"]["requires_review"])
        self.assertIn("precision_hole", quote_items)
        self.assertNotIn("boring", quote_items)
        self.assertEqual(quote_items["precision_hole"]["quantity"], 2)
        self.assertEqual(quote_items["precision_hole"]["unit_price"], 27.5)
        self.assertEqual(quote_items["precision_hole"]["amount"], 55.0)
        self.assertTrue(quote_items["precision_hole"]["requires_review"])
        self.assertNotIn("precision_hole", missing_price_operations)

    def test_wire_cut_and_grinding_do_not_emit_fake_quantities(self) -> None:
        part_feature = part_feature_with_quantity_inputs()
        part_feature["geometry"]["part_type"] = "thin_plate"
        part_feature["geometry"]["bounding_box"] = {
            "length": 100,
            "width": 50,
            "height": 2,
            "unit": "mm",
        }
        part_feature["features"]["complexity"]["thin_wall_candidate"] = True
        part_feature["features"]["precision_requirements"] = [
            {
                "raw_text": "Ra0.8，平面度0.02",
                "standard_type": "flatness",
                "confidence": 0.8,
                "source": source("flatness"),
            }
        ]
        part_feature["manufacturing_requirements"]["heat_treatment"] = {
            "required": True,
            "raw_text": "淬火",
            "standard_code": "QUENCH",
            "confidence": 0.8,
            "source": source("heat"),
        }

        result = build_pricing_core_service().build_quote(
            task_id="task_004",
            quote_id="quote_004",
            part_feature=part_feature,
            risks=[],
            priced_at="2026-06-08T10:00:00+08:00",
            price_version="a-basic-v1",
        )

        quantities = {
            item["operation_code"]: item
            for item in result.quantity_result["items"]
        }
        self.assertIsNone(quantities["wire_cut_profile"]["value"])
        self.assertEqual(quantities["surface_grinding_rough"]["value"], 3)
        self.assertEqual(quantities["surface_grinding_rough"]["unit"], "pcs")
        self.assertTrue(quantities["surface_grinding_rough"]["requires_review"])
        self.assertEqual(quantities["finish_grinding"]["value"], 3)
        self.assertEqual(quantities["finish_grinding"]["unit"], "pcs")
        self.assertTrue(quantities["finish_grinding"]["requires_review"])
        self.assertIn(
            "QUANTITY_WIRE_CUT_LENGTH_MISSING",
            {risk["code"] for risk in result.quantity_result["risks"]},
        )
        self.assertIn(
            "QUANTITY_GRINDING_FACE_COUNT_MISSING",
            {risk["code"] for risk in result.quantity_result["risks"]},
        )

    def test_wire_cut_profile_uses_step_outer_profile_length(self) -> None:
        part_feature = part_feature_with_quantity_inputs()
        part_feature["geometry"]["part_type"] = "plate"
        part_feature["geometry"]["bounding_box"] = {
            "length": 180,
            "width": 70,
            "height": 16,
            "unit": "mm",
        }
        part_feature["geometry"]["profile_summary"] = {
            "outer_profile_length": 495.3137,
            "inner_profile_length": 273.3185,
            "top_profile_length": 768.6322,
        }
        part_feature["manufacturing_requirements"]["technical_requirements"] = [
            "外形线切割加工"
        ]

        result = build_pricing_core_service().build_quote(
            task_id="task_005",
            quote_id="quote_005",
            part_feature=part_feature,
            risks=[],
            priced_at="2026-06-08T10:00:00+08:00",
            price_version="a-basic-v1",
        )

        wire_quantity = next(
            item
            for item in result.quantity_result["items"]
            if item["operation_code"] == "wire_cut_profile"
        )
        self.assertEqual(wire_quantity["value"], 7925.0192)
        self.assertEqual(wire_quantity["unit"], "mm2")
        self.assertFalse(wire_quantity["requires_review"])
        self.assertNotIn(
            "QUANTITY_WIRE_CUT_LENGTH_MISSING",
            {risk["code"] for risk in result.quantity_result["risks"]},
        )

    def test_ai_process_suggestion_rebuilds_quantities_for_added_operation(self) -> None:
        part_feature = part_feature_with_quantity_inputs()
        part_feature["geometry"]["part_type"] = "plate"
        part_feature["geometry"]["profile_summary"] = {
            "outer_profile_length": 120.0,
        }

        result = build_pricing_core_service().build_quote(
            task_id="task_ai_001",
            quote_id="quote_ai_001",
            part_feature=part_feature,
            risks=[],
            priced_at="2026-06-08T10:00:00+08:00",
            price_version="a-basic-v1",
            process_route_ai_suggestion=ai_process_suggestion(
                [
                    {
                        "action": "add",
                        "operation_code": "wire_cut_profile",
                        "reason": "AI 根据 STEP 轮廓摘要建议补充线切割外形。",
                        "evidence_summary": "outer_profile_length=120",
                        "confidence": 0.82,
                    }
                ]
            ),
        )

        operation_codes = {
            operation["operation_code"]
            for operation in result.process_route["operations"]
        }
        quantities = {
            item["operation_code"]: item
            for item in result.quantity_result["items"]
        }
        self.assertIn("wire_cut_profile", operation_codes)
        self.assertEqual(quantities["wire_cut_profile"]["value"], 1200.0)
        self.assertIn(
            "AI_PROCESS_ROUTE_SUGGESTION_APPLIED",
            {risk["code"] for risk in result.process_route["risks"]},
        )

    def test_unknown_ai_process_enters_route_without_auto_quote_item(self) -> None:
        part_feature = part_feature_with_quantity_inputs()

        result = build_pricing_core_service().build_quote(
            task_id="task_ai_002",
            quote_id="quote_ai_002",
            part_feature=part_feature,
            risks=[],
            priced_at="2026-06-08T10:00:00+08:00",
            price_version="a-basic-v1",
            process_route_ai_suggestion=ai_process_suggestion(
                [
                    {
                        "action": "add",
                        "operation_code": "氧化发黑",
                        "operation_name_raw": "氧化发黑",
                        "reason": "PDF 技术要求出现氧化发黑，当前字典未登记。",
                        "evidence_summary": "technical_requirements contains 氧化发黑",
                        "confidence": 0.9,
                    }
                ]
            ),
        )

        validate_process_route(result.process_route)
        unmapped = [
            operation
            for operation in result.process_route["operations"]
            if operation["operation_code"] == "unmapped_operation"
        ]
        quote_operation_codes = {
            item.get("operation_code")
            for item in result.quote_result["items"]
            if item.get("operation_code")
        }

        self.assertEqual(len(unmapped), 1)
        self.assertEqual(unmapped[0]["operation_name"], "未登记工序：氧化发黑")
        self.assertTrue(unmapped[0]["requires_review"])
        self.assertNotIn("unmapped_operation", quote_operation_codes)
        self.assertEqual(result.quote_result["status"], "pending_review")
        self.assertIn(
            "UNMAPPED_OPERATION_REQUIRES_REVIEW",
            {risk["code"] for risk in result.process_route["risks"]},
        )

    def test_shaft_part_generates_turning_quote_item(self) -> None:
        part_feature = part_feature_with_quantity_inputs()
        part_feature["geometry"]["part_type"] = "shaft"
        part_feature["geometry"]["part_type_candidates"] = [
            {
                "part_type": "shaft",
                "confidence": 0.88,
                "reason": "test shaft",
                "source": source("part_type"),
            }
        ]

        result = build_pricing_core_service().build_quote(
            task_id="task_shaft_001",
            quote_id="quote_shaft_001",
            part_feature=part_feature,
            risks=[],
            priced_at="2026-06-08T10:00:00+08:00",
            price_version="a-basic-v1",
        )

        quote_items = {
            item["operation_code"]: item
            for item in result.quote_result["items"]
            if item.get("operation_code")
        }
        quantities = {
            item["operation_code"]: item
            for item in result.quantity_result["items"]
        }

        self.assertIn("turning", quote_items)
        self.assertIn("turning", quantities)
        self.assertIsNotNone(quote_items["turning"]["amount"])
        self.assertTrue(quote_items["turning"]["requires_review"])
        self.assertEqual(result.quote_result["status"], "pending_review")

    def test_complex_part_generates_cnc_and_edm_quote_items(self) -> None:
        part_feature = part_feature_with_quantity_inputs()
        part_feature["geometry"]["part_type"] = "complex"
        part_feature["geometry"]["part_type_candidates"] = [
            {
                "part_type": "complex",
                "confidence": 0.82,
                "reason": "test complex",
                "source": source("part_type"),
            }
        ]
        part_feature["features"]["complexity"]["slot_count"] = 2
        part_feature["features"]["complexity"]["small_radius_count"] = 4
        part_feature["features"]["complexity"]["complexity_score"] = 68

        result = build_pricing_core_service().build_quote(
            task_id="task_complex_001",
            quote_id="quote_complex_001",
            part_feature=part_feature,
            risks=[],
            priced_at="2026-06-08T10:00:00+08:00",
            price_version="a-basic-v1",
        )

        quote_items = {
            item["operation_code"]: item
            for item in result.quote_result["items"]
            if item.get("operation_code")
        }
        quantities = {
            item["operation_code"]: item
            for item in result.quantity_result["items"]
        }

        self.assertIn("cnc_milling", quote_items)
        self.assertIn("edm", quote_items)
        self.assertIn("edm", quantities)
        self.assertIsNotNone(quote_items["edm"]["amount"])
        self.assertTrue(quote_items["edm"]["requires_review"])

    def test_missing_part_quantity_marks_inspection_and_packaging_for_review(self) -> None:
        part_feature = part_feature_with_quantity_inputs()
        part_feature["part"]["quantity"] = None

        result = build_pricing_core_service().build_quote(
            task_id="task_005",
            quote_id="quote_005",
            part_feature=part_feature,
            risks=[],
            priced_at="2026-06-08T10:00:00+08:00",
            price_version="a-basic-v1",
        )

        quantities = {
            item["operation_code"]: item
            for item in result.quantity_result["items"]
        }
        self.assertIsNone(quantities["inspection"]["value"])
        self.assertTrue(quantities["inspection"]["requires_review"])
        self.assertIsNone(quantities["protective_packaging"]["value"])
        self.assertTrue(quantities["protective_packaging"]["requires_review"])
        self.assertIn(
            "QUANTITY_PART_COUNT_MISSING",
            {risk["code"] for risk in result.quantity_result["risks"]},
        )


def part_feature_without_step_complexity() -> dict:
    return {
        "schema_version": "1.0",
        "task_id": "task_001",
        "part": {
            "part_name": "Part",
            "drawing_no": "D001",
            "revision": "A",
            "quantity": 1,
        },
        "material": {
            "raw_text": "SKD11",
            "standard_code": None,
            "standard_name": None,
            "density": None,
            "density_unit": None,
            "confidence": 0.8,
            "source": source("material"),
        },
        "geometry": {
            "bounding_box": {
                "length": None,
                "width": None,
                "height": None,
                "unit": "mm",
            },
            "volume": {"value": None, "unit": "mm3", "source": source("volume")},
            "surface_area": {
                "value": None,
                "unit": "mm2",
                "source": source("surface_area"),
            },
            "pdf_weight": {"value": 0.03, "unit": "kg", "source": source("weight")},
            "step_net_weight": {
                "value": None,
                "unit": None,
                "source": source("step_weight"),
            },
            "part_type": None,
            "part_type_confidence": 0,
        },
        "features": {
            "holes": [],
            "hole_summary": {"total_count": 0, "by_type": {}, "by_diameter": {}},
            "precision_requirements": [],
            "complexity": {},
        },
        "manufacturing_requirements": {
            "heat_treatment": {
                "required": False,
                "raw_text": None,
                "standard_code": None,
                "confidence": 0,
                "source": source("heat"),
            },
            "surface_treatment": {
                "required": False,
                "raw_text": None,
                "standard_code": None,
                "confidence": 0,
                "source": source("surface"),
            },
            "deburring": {
                "required": True,
                "raw_text": "Remove burrs",
                "standard_code": "DEBURR",
                "confidence": 0.75,
                "source": source("deburr"),
            },
            "inspection": {
                "required": True,
                "raw_text": "Standard inspection",
                "standard_code": "STANDARD_INSPECTION",
                "confidence": 0.7,
                "source": source("inspection"),
            },
            "packaging": {
                "required": False,
                "raw_text": None,
                "standard_code": None,
                "confidence": 0,
                "source": source("packaging"),
            },
        },
        "risks": [],
    }


def part_feature_with_quantity_inputs() -> dict:
    return {
        "schema_version": "1.0",
        "task_id": "task_002",
        "part": {
            "part_name": "Block",
            "drawing_no": "D002",
            "revision": "A",
            "quantity": 3,
        },
        "material": {
            "raw_text": "S45C",
            "standard_code": "S45C",
            "standard_name": None,
            "density": 0.00000785,
            "density_unit": "kg/mm3",
            "confidence": 0.9,
            "source": source("material"),
        },
        "geometry": {
            "bounding_box": {
                "length": 10,
                "width": 20,
                "height": 50,
                "unit": "mm",
            },
            "volume": {"value": 8000, "unit": "mm3", "source": source("volume")},
            "surface_area": {
                "value": 2200,
                "unit": "mm2",
                "source": source("surface_area"),
            },
            "pdf_weight": {"value": None, "unit": None, "source": source("weight")},
            "step_net_weight": {
                "value": None,
                "unit": None,
                "source": source("step_weight"),
            },
            "part_type": "block",
            "part_type_confidence": 0.86,
            "part_type_candidates": [
                {
                    "part_type": "block",
                    "confidence": 0.86,
                    "reason": "test",
                    "source": source("part_type"),
                }
            ],
        },
        "features": {
            "holes": [],
            "hole_summary": {"total_count": 0, "by_type": {}, "by_diameter": {}},
            "precision_requirements": [],
            "complexity": {
                "face_count": 12,
                "edge_count": 24,
                "small_radius_count": 0,
                "slot_count": 0,
                "thin_wall_candidate": False,
                "complexity_score": 30,
            },
        },
        "manufacturing_requirements": {
            "heat_treatment": {
                "required": False,
                "raw_text": None,
                "standard_code": None,
                "confidence": 0,
                "source": source("heat"),
            },
            "surface_treatment": {
                "required": False,
                "raw_text": None,
                "standard_code": None,
                "confidence": 0,
                "source": source("surface"),
            },
            "deburring": {
                "required": False,
                "raw_text": None,
                "standard_code": None,
                "confidence": 0,
                "source": source("deburr"),
            },
            "inspection": {
                "required": True,
                "raw_text": "Standard inspection",
                "standard_code": "STANDARD_INSPECTION",
                "confidence": 0.7,
                "source": source("inspection"),
            },
            "packaging": {
                "required": True,
                "raw_text": "Protective packaging",
                "standard_code": "PROTECTIVE_PACKAGING",
                "confidence": 0.7,
                "source": source("packaging"),
            },
        },
        "risks": [],
    }


def source(rule_code: str) -> dict:
    return {
        "source_type": "system",
        "file_id": None,
        "page": None,
        "location": None,
        "raw_text": None,
        "rule_code": rule_code,
    }


def ai_process_suggestion(suggestions: list[dict]) -> dict:
    return {
        "task_id": "task_ai_001",
        "input_type": "fusion_feature",
        "output_type": "process_route_suggestion",
        "content": {
            "suggestions": suggestions,
            "review_required": True,
            "summary": "AI 建议复核工艺路线。",
            "confidence": 0.82,
        },
        "confidence": 0.82,
        "evidence": [],
        "model_name": "fake-ai",
        "prompt_version": "test-v1",
        "created_at": "2026-06-15T10:00:00+08:00",
    }


def route_operation(
    operation_code: str,
    sequence: int,
    *,
    operation_name: str | None = None,
    requires_review: bool = False,
) -> dict:
    return {
        "operation_id": f"op_{sequence:03d}_{operation_code}",
        "operation_code": operation_code,
        "operation_name": operation_name or operation_code,
        "sequence": sequence,
        "trigger_reasons": [
            {
                "rule_code": f"TEST_{operation_code.upper()}",
                "message": "test route override",
                "source": source(f"TEST_{operation_code.upper()}"),
            }
        ],
        "confidence": 0.8,
        "requires_review": requires_review,
        "review_reason": "test review" if requires_review else None,
        "explanation": "test route override",
    }


class FakeMaterialPriceProvider:
    def find_unit_price(self, **_kwargs) -> MaterialMarketPrice:
        return MaterialMarketPrice(
            material_code="S45C",
            unit_price=3.76,
            unit="CNY/kg",
            region="south_china",
            query="S45C 广东 价格 元/kg",
            title="广州45#碳结圆钢20mm",
            url="https://example.test/material-price",
            snippet="广州45#碳结圆钢20mm 3760元/吨",
            source_domain="example.test",
            searched_at="2026-06-11T10:00:00+08:00",
            confidence=0.84,
        )


class NullMaterialPriceProvider:
    def find_unit_price(self, **_kwargs) -> None:
        return None


class FakeMaterialEstimateProvider:
    def find_unit_price(self, **kwargs) -> MaterialMarketPrice:
        return MaterialMarketPrice(
            material_code="S45C",
            unit_price=5.25,
            unit="CNY/kg",
            region=kwargs.get("region") or "south_china",
            query="按华南45号钢首版核价区间估算，规格和含税口径需复核。",
            title="AI 材料估算价",
            url="ai://material-price-estimate/s45c",
            snippet="按华南45号钢首版核价区间估算，规格和含税口径需复核。",
            source_domain="ai_estimate",
            searched_at="2026-06-11T10:00:00+08:00",
            confidence=0.55,
            provider="gpt_estimate",
            rule_id="GPT_MATERIAL_PRICE_ESTIMATE",
            source_type="ai_estimate",
        )


class FakeSurfaceTreatmentPriceProvider:
    def find_unit_price(self, **kwargs) -> SurfaceTreatmentMarketPrice:
        return SurfaceTreatmentMarketPrice(
            treatment_code=kwargs["treatment_code"],
            treatment_name=kwargs["treatment_name"],
            unit_price=1200.0,
            unit="CNY/m2",
            minimum_charge=None,
            region=kwargs.get("region") or "south_china",
            region_match="exact",
            query="化学镍 广东 加工费 元/m2",
            title="广东化学镀镍加工报价",
            url="https://example.test/surface-treatment-price",
            snippet="化学镀镍加工报价 1200元/m2",
            source_domain="example.test",
            searched_at="2026-06-11T10:00:00+08:00",
            confidence=0.78,
        )


class NullSurfaceTreatmentPriceProvider:
    def find_unit_price(self, **_kwargs) -> None:
        return None


class FakeSurfaceTreatmentEstimateProvider:
    def find_unit_price(self, **kwargs) -> SurfaceTreatmentMarketPrice:
        return SurfaceTreatmentMarketPrice(
            treatment_code=kwargs["treatment_code"],
            treatment_name=kwargs["treatment_name"],
            unit_price=1300.0,
            unit="CNY/m2",
            minimum_charge=None,
            region=kwargs.get("region") or "south_china",
            region_match="estimate",
            query="按华南化学镍小批量表面积计价估算，膜厚未知需复核。",
            title="AI 表面处理估算价",
            url="ai://surface-treatment-estimate",
            snippet="按华南化学镍小批量表面积计价估算，膜厚未知需复核。",
            source_domain="ai_estimate",
            searched_at="2026-06-11T10:00:00+08:00",
            confidence=0.55,
            provider="gpt_estimate",
            rule_id="GPT_SURFACE_TREATMENT_PRICE_ESTIMATE",
            source_type="ai_estimate",
        )


if __name__ == "__main__":
    unittest.main()
