from __future__ import annotations

import unittest

from backend.app.process_dictionary import (
    PROCESS_DICTIONARY,
    PROCESS_SEQUENCE,
    is_registered_process_code,
)
from backend.app.process_recognition import build_process_route


class ProcessRecognitionTests(unittest.TestCase):
    def test_route_uses_registered_process_codes_in_dictionary_order(self) -> None:
        route = build_process_route(
            task_id="task_001",
            route_id="route_001",
            part_feature=part_feature_with_process_triggers(),
            inherited_risks=[{"requires_review": True}],
        )

        operations = route["operations"]
        codes = [operation["operation_code"] for operation in operations]

        self.assertEqual(codes, sorted(codes, key=PROCESS_SEQUENCE.index))
        self.assertTrue(all(is_registered_process_code(code) for code in codes))
        self.assertTrue(all(code == code.lower() for code in codes))
        self.assertIn("manual_review", codes)

        for operation in operations:
            definition = PROCESS_DICTIONARY[operation["operation_code"]]
            self.assertEqual(operation["operation_name"], definition.process_name)
            self.assertGreaterEqual(operation["confidence"], 0)
            self.assertLessEqual(operation["confidence"], 1)
            self.assertGreaterEqual(operation["sequence"], 1)
            self.assertTrue(operation["operation_id"].startswith("op_"))
            self.assertTrue(operation["trigger_reasons"])

    def test_hole_and_requirement_rules_are_triggered_from_part_feature(self) -> None:
        route = build_process_route(
            task_id="task_001",
            route_id="route_001",
            part_feature=part_feature_with_process_triggers(),
            inherited_risks=[],
        )

        operations = {
            operation["operation_code"]: operation
            for operation in route["operations"]
        }

        self.assertIn("drilling", operations)
        self.assertIn("countersink", operations)
        self.assertIn("tapping", operations)
        self.assertIn("precision_hole", operations)
        self.assertIn("finish_grinding", operations)
        self.assertIn("heat_treatment", operations)
        self.assertIn("chemical_nickel", operations)
        self.assertIn("deburr", operations)

        self.assert_rule_triggered(operations["drilling"], "HOLE_THROUGH")
        self.assert_rule_triggered(operations["countersink"], "HOLE_COUNTERBORE")
        self.assert_rule_triggered(operations["tapping"], "HOLE_THREAD_CANDIDATE")
        self.assert_rule_triggered(operations["precision_hole"], "HOLE_PRECISION_CANDIDATE")
        self.assert_rule_triggered(operations["finish_grinding"], "ROUGHNESS_OR_FLATNESS_REQUIREMENT")
        self.assert_rule_triggered(operations["heat_treatment"], "HEAT_TREATMENT_REQUIRED")
        self.assert_rule_triggered(operations["chemical_nickel"], "SURFACE_TREATMENT_CHEMICAL_NICKEL")
        self.assert_rule_triggered(operations["deburr"], "DEBURRING_REQUIRED")
        self.assertTrue(operations["tapping"]["requires_review"])
        self.assertTrue(operations["precision_hole"]["requires_review"])

    def test_duplicate_process_triggers_merge_into_one_operation(self) -> None:
        part_feature = part_feature_with_process_triggers()
        part_feature["features"]["holes"].append(
            {
                "hole_type": "through",
                "diameter": 5,
                "depth": None,
                "count": 2,
                "confidence": 0.91,
                "evidence": [source("pdf", "hole_through_extra")],
            }
        )

        route = build_process_route(
            task_id="task_001",
            route_id="route_001",
            part_feature=part_feature,
            inherited_risks=[],
        )

        drilling = next(
            operation
            for operation in route["operations"]
            if operation["operation_code"] == "drilling"
        )

        drilling_rules = [
            reason["rule_code"]
            for reason in drilling["trigger_reasons"]
        ]
        self.assertEqual(drilling_rules.count("HOLE_THROUGH"), 2)
        self.assertIn("HOLE_COUNTER_FEATURE_PREDRILL", drilling_rules)
        self.assertIn("HOLE_THREAD_PILOT_DRILLING", drilling_rules)
        self.assertIn("HOLE_PRECISION_PREDRILL", drilling_rules)
        self.assertEqual(drilling["confidence"], 0.91)

    def test_missing_geometry_does_not_default_to_cnc_or_cutting(self) -> None:
        part_feature = part_feature_with_process_triggers()
        part_feature["geometry"] = {
            "bounding_box": {
                "length": None,
                "width": None,
                "height": None,
                "unit": "mm",
            },
            "part_type": None,
            "part_type_confidence": 0,
            "part_type_candidates": [],
        }
        part_feature["features"]["holes"] = []

        route = build_process_route(
            task_id="task_001",
            route_id="route_001",
            part_feature=part_feature,
            inherited_risks=[],
        )

        codes = {operation["operation_code"] for operation in route["operations"]}
        self.assertIn("review_drawing", codes)
        self.assertNotIn("saw_cut", codes)
        self.assertNotIn("cnc_milling", codes)
        self.assertNotIn("wire_cut_profile", codes)

    def test_plate_geometry_triggers_cutting_and_cnc_without_wire_candidate(self) -> None:
        route = build_process_route(
            task_id="task_001",
            route_id="route_001",
            part_feature=part_feature_with_process_triggers(),
            inherited_risks=[],
        )

        operations = {
            operation["operation_code"]: operation
            for operation in route["operations"]
        }
        self.assert_rule_triggered(operations["saw_cut"], "BLANK_SAW_CUT_FROM_PART_TYPE")
        self.assert_rule_triggered(operations["cnc_milling"], "CNC_FROM_PART_TYPE")
        self.assertNotIn("wire_cut_profile", operations)
        self.assertNotIn("CNC_WIRE_CUT_CONFLICT", {risk["code"] for risk in route["risks"]})

    def test_technical_m_thread_callout_triggers_drilling_and_tapping(self) -> None:
        part_feature = part_feature_with_process_triggers()
        part_feature["features"]["holes"] = []
        part_feature["features"]["precision_requirements"] = []
        part_feature["manufacturing_requirements"]["technical_requirements"] = [
            "4-M6 螺纹孔，深10"
        ]

        route = build_process_route(
            task_id="task_001",
            route_id="route_001",
            part_feature=part_feature,
            inherited_risks=[],
        )

        operations = {
            operation["operation_code"]: operation
            for operation in route["operations"]
        }
        self.assert_rule_triggered(operations["drilling"], "TECH_REQ_THREAD_PILOT_DRILLING")
        self.assert_rule_triggered(operations["tapping"], "TECH_REQ_THREAD_TAPPING")
        self.assertTrue(operations["tapping"]["requires_review"])

    def test_h8_precision_requirement_triggers_precision_hole(self) -> None:
        part_feature = part_feature_with_process_triggers()
        part_feature["features"]["holes"] = []
        part_feature["features"]["precision_requirements"] = [
            {
                "raw_text": "Φ8 H8",
                "standard_type": "H8",
                "confidence": 0.78,
                "source": source("pdf", "precision_h8"),
            }
        ]

        route = build_process_route(
            task_id="task_001",
            route_id="route_001",
            part_feature=part_feature,
            inherited_risks=[],
        )

        operations = {
            operation["operation_code"]: operation
            for operation in route["operations"]
        }
        self.assert_rule_triggered(operations["drilling"], "PRECISION_REQUIREMENT_PREDRILL")
        self.assert_rule_triggered(operations["precision_hole"], "PRECISION_REQUIREMENT")
        self.assertTrue(operations["precision_hole"]["requires_review"])

    def test_tool_steel_material_adds_lightweight_process_candidates(self) -> None:
        part_feature = part_feature_with_process_triggers()
        part_feature["features"]["complexity"]["small_radius_count"] = 3
        part_feature["geometry"]["profile_summary"] = {
            "outer_arc_count": 2,
            "outer_arc_length": 12.5,
        }

        route = build_process_route(
            task_id="task_001",
            route_id="route_001",
            part_feature=part_feature,
            inherited_risks=[],
        )

        operations = {
            operation["operation_code"]: operation
            for operation in route["operations"]
        }
        self.assert_rule_triggered(operations["wire_cut_profile"], "MATERIAL_TOOL_STEEL_WIRE_CUT")
        self.assert_rule_triggered(operations["surface_grinding_rough"], "MATERIAL_TOOL_STEEL_REFERENCE_GRINDING")
        self.assert_rule_triggered(operations["finish_grinding"], "MATERIAL_TOOL_STEEL_FINISH_GRINDING")
        self.assertIn(
            "MATERIAL_PROCESS_RISK",
            {risk["code"] for risk in route["risks"]},
        )

    def test_thin_plate_adds_straightening_candidate_without_heat(self) -> None:
        part_feature = part_feature_with_process_triggers()
        part_feature["geometry"]["part_type"] = "thin_plate"
        part_feature["geometry"]["bounding_box"] = {
            "length": 100,
            "width": 20,
            "height": 2,
            "unit": "mm",
        }
        part_feature["features"]["complexity"]["thin_wall_candidate"] = False
        part_feature["manufacturing_requirements"]["heat_treatment"] = {
            "required": False,
            "raw_text": None,
            "standard_code": None,
            "confidence": 0.7,
            "source": source("pdf", "heat_not_required"),
        }

        route = build_process_route(
            task_id="task_001",
            route_id="route_001",
            part_feature=part_feature,
            inherited_risks=[],
        )

        operations = {
            operation["operation_code"]: operation
            for operation in route["operations"]
        }
        self.assert_rule_triggered(operations["straightening"], "THIN_PART_STRAIGHTENING_CANDIDATE")
        self.assertTrue(operations["straightening"]["requires_review"])

    def test_support_against_bending_does_not_trigger_straightening(self) -> None:
        part_feature = part_feature_with_process_triggers()
        part_feature["manufacturing_requirements"]["technical_requirements"] = [
            "加工后合理支撑避免弯曲"
        ]

        route = build_process_route(
            task_id="task_001",
            route_id="route_001",
            part_feature=part_feature,
            inherited_risks=[],
        )

        operations = {
            operation["operation_code"]: operation
            for operation in route["operations"]
        }
        self.assertNotIn("straightening", operations)
        self.assert_rule_triggered(
            operations["protective_packaging"],
            "TECH_REQ_SUPPORT_PACKAGING",
        )

    def test_chemical_nickel_precision_hole_risk_mentions_compensation(self) -> None:
        route = build_process_route(
            task_id="task_001",
            route_id="route_001",
            part_feature=part_feature_with_process_triggers(),
            inherited_risks=[],
        )

        risk = next(
            item
            for item in route["risks"]
            if item["code"] == "SURFACE_TREATMENT_PRECISION_HOLE_RISK"
        )
        self.assertIn("镀前尺寸补偿", risk["message"])
        self.assertIn("镀后孔径复检", risk["message"])

    def test_unsupported_shaft_outputs_manual_route_only(self) -> None:
        part_feature = part_feature_with_process_triggers()
        part_feature["geometry"]["part_type"] = "shaft"
        part_feature["geometry"]["part_type_confidence"] = 0.9
        part_feature["geometry"]["part_type_candidates"] = [
            {
                "part_type": "shaft",
                "confidence": 0.9,
                "reason": "STEP shaft candidate",
                "source": source("step", "part_type_shaft"),
            }
        ]

        route = build_process_route(
            task_id="task_001",
            route_id="route_001",
            part_feature=part_feature,
            inherited_risks=[],
        )

        codes = [operation["operation_code"] for operation in route["operations"]]
        self.assertEqual(codes, ["review_drawing", "turning", "manual_review"])
        self.assertIn(
            "UNSUPPORTED_PART_REQUIRES_MANUAL_REVIEW",
            {risk["code"] for risk in route["risks"]},
        )

    def assert_rule_triggered(self, operation: dict, rule_code: str) -> None:
        self.assertIn(
            rule_code,
            {reason["rule_code"] for reason in operation["trigger_reasons"]},
        )


def part_feature_with_process_triggers() -> dict:
    return {
        "schema_version": "1.0",
        "task_id": "task_001",
        "material": {
            "raw_text": "SKD11",
            "standard_code": None,
            "source": source("pdf", "material"),
        },
        "geometry": {
            "bounding_box": {
                "length": 120,
                "width": 80,
                "height": 16,
                "unit": "mm",
            },
            "part_type": "plate",
            "part_type_confidence": 0.86,
            "part_type_candidates": [
                {
                    "part_type": "plate",
                    "confidence": 0.86,
                    "reason": "STEP plate candidate",
                    "source": source("step", "part_type_plate"),
                }
            ],
        },
        "features": {
            "holes": [
                {
                    "hole_type": "through",
                    "diameter": 9,
                    "depth": None,
                    "count": 4,
                    "confidence": 0.82,
                    "evidence": [source("step", "hole_through")],
                },
                {
                    "hole_type": "counterbore",
                    "diameter": 9,
                    "depth": None,
                    "count": 4,
                    "confidence": 0.86,
                    "evidence": [source("pdf", "hole_counterbore")],
                },
                {
                    "hole_type": "thread_candidate",
                    "diameter": 6,
                    "depth": 12,
                    "count": 2,
                    "confidence": 0.72,
                    "evidence": [source("pdf", "hole_thread")],
                },
                {
                    "hole_type": "precision_candidate",
                    "diameter": 8,
                    "depth": None,
                    "count": 1,
                    "confidence": 0.7,
                    "evidence": [source("pdf", "hole_precision")],
                },
            ],
            "precision_requirements": [
                {
                    "raw_text": "Ra0.8",
                    "standard_type": "Ra",
                    "confidence": 0.74,
                    "source": source("pdf", "roughness"),
                }
            ],
            "complexity": {
                "face_count": 42,
                "edge_count": 96,
                "small_radius_count": 0,
                "slot_count": 0,
                "thin_wall_candidate": False,
                "complexity_score": 32,
            },
        },
        "manufacturing_requirements": {
            "heat_treatment": {
                "required": True,
                "raw_text": "淬火 HRC58-62",
                "standard_code": "QUENCH",
                "confidence": 0.84,
                "source": source("pdf", "heat"),
            },
            "surface_treatment": {
                "required": True,
                "raw_text": "化学镍",
                "standard_code": "CHEMICAL_NICKEL",
                "confidence": 0.83,
                "source": source("pdf", "surface"),
            },
            "deburring": {
                "required": True,
                "raw_text": "去毛刺锐角倒钝",
                "standard_code": "DEBURR",
                "confidence": 0.78,
                "source": source("pdf", "deburr"),
            },
            "inspection": {
                "required": True,
                "raw_text": "全检",
                "standard_code": "INSPECTION",
                "confidence": 0.76,
                "source": source("pdf", "inspection"),
            },
            "packaging": {
                "required": True,
                "raw_text": "防划伤包装",
                "standard_code": "PROTECTIVE_PACKAGING",
                "confidence": 0.74,
                "source": source("pdf", "packaging"),
            },
        },
    }


def source(source_type: str, rule_code: str) -> dict:
    return {
        "source_type": source_type,
        "file_id": None,
        "page": None,
        "location": None,
        "raw_text": None,
        "rule_code": rule_code,
    }


if __name__ == "__main__":
    unittest.main()
