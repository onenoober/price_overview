from __future__ import annotations

import unittest

from backend.app.pricing_core import build_pricing_core_service
from backend.app.schema_validation import validate_quantity_result


class PricingCoreTests(unittest.TestCase):
    def test_missing_geometry_does_not_generate_fixed_cnc_cutting_or_deburr_amounts(
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
        self.assertIsNone(quantities["deburr"]["value"])
        self.assertIsNone(quote_items["deburr"]["amount"])

        missing_price_operations = {
            risk["evidence"][0]["rule_code"].split(":", 1)[1]
            for risk in result.quote_result["risks"]
            if risk["code"] == "MISSING_PRICE_OR_QUANTITY"
        }
        self.assertIn("deburr", missing_price_operations)

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
        self.assertIsNone(cnc_quantity["value"])
        self.assertTrue(cnc_quantity["requires_review"])
        self.assertIn(
            "QUANTITY_CNC_PARAMETER_MISSING",
            {risk["code"] for risk in result.quantity_result["risks"]},
        )

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
        self.assertIsNone(quantities["surface_grinding_rough"]["value"])
        self.assertIsNone(quantities["finish_grinding"]["value"])
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


if __name__ == "__main__":
    unittest.main()
