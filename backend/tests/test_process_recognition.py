from __future__ import annotations

import unittest

from backend.app.process_dictionary import (
    PROCESS_DICTIONARY,
    PROCESS_SEQUENCE,
    is_registered_process_code,
)
from backend.app.process_recognition import (
    apply_ai_process_route_suggestion,
    build_ai_generated_process_route,
    build_process_route,
)


class ProcessRecognitionTests(unittest.TestCase):
    def test_ai_generated_route_preserves_ai_order_and_unmapped_operations(self) -> None:
        route = build_ai_generated_process_route(
            task_id="task_ai_route_001",
            route_id="route_ai_route_001",
            ai_output=ai_process_route_generation(
                [
                    {
                        "operation_code": "turning",
                        "operation_name_raw": None,
                        "reason": "STEP 显示旋转轴类主体，先车削成形。",
                        "evidence_summary": "step_part_type=shaft",
                        "confidence": 0.88,
                        "requires_review": False,
                    },
                    {
                        "operation_code": "喷砂",
                        "operation_name_raw": "喷砂",
                        "reason": "PDF 技术要求出现喷砂，但字典未登记。",
                        "evidence_summary": "technical_requirements contains 喷砂",
                        "confidence": 0.84,
                        "requires_review": True,
                    },
                    {
                        "operation_code": "inspection",
                        "operation_name_raw": None,
                        "reason": "报价件需要终检。",
                        "evidence_summary": "normal quote practice",
                        "confidence": 0.72,
                        "requires_review": False,
                    },
                ]
            ),
            inherited_risks=[],
            auto_accept=False,
        )

        operations = route["operations"]

        self.assertEqual(
            [operation["operation_code"] for operation in operations],
            ["turning", "unmapped_operation", "inspection"],
        )
        self.assertEqual([operation["sequence"] for operation in operations], [1, 2, 3])
        self.assertEqual(operations[1]["operation_name"], "未登记工序：喷砂")
        self.assertTrue(operations[1]["requires_review"])
        self.assert_rule_triggered(operations[0], "AI_ROUTE_TURNING")
        self.assert_rule_triggered(operations[1], "AI_UNMAPPED_OPERATION")
        self.assertIn(
            "UNMAPPED_OPERATION_REQUIRES_REVIEW",
            {risk["code"] for risk in route["risks"]},
        )

    def test_ai_generated_route_maps_chinese_process_names(self) -> None:
        route = build_ai_generated_process_route(
            task_id="task_ai_route_002",
            route_id="route_ai_route_002",
            ai_output=ai_process_route_generation(
                [
                    {
                        "operation_code": "备料",
                        "operation_name_raw": "备料",
                        "reason": "图纸材料明确，需要先备料。",
                        "evidence_summary": "材料 Q235A。",
                        "confidence": 0.9,
                        "requires_review": False,
                    },
                    {
                        "operation_code": "钻孔",
                        "operation_name_raw": "钻孔",
                        "reason": "图纸可见孔特征。",
                        "evidence_summary": "孔特征。",
                        "confidence": 0.86,
                        "requires_review": False,
                    },
                ]
            ),
            inherited_risks=[],
        )

        self.assertEqual(
            [operation["operation_code"] for operation in route["operations"]],
            ["material_prepare", "drilling"],
        )
        self.assertFalse(any(operation["requires_review"] for operation in route["operations"]))
        self.assertFalse(route["requires_review"])

    def test_ai_generated_route_auto_accepts_common_process_aliases(self) -> None:
        route = build_ai_generated_process_route(
            task_id="task_ai_route_003",
            route_id="route_ai_route_003",
            ai_output=ai_process_route_generation(
                [
                    {
                        "operation_code": "锯床下料",
                        "operation_name_raw": "锯床下料",
                        "reason": "根据外形尺寸先下料。",
                        "evidence_summary": "PDF 外形尺寸。",
                        "confidence": 0.95,
                        "requires_review": True,
                    },
                    {
                        "operation_code": "铣削外形",
                        "operation_name_raw": "铣削外形",
                        "reason": "加工六面体基准及外形。",
                        "evidence_summary": "PDF 外形和 STEP 包络。",
                        "confidence": 0.95,
                        "requires_review": True,
                    },
                    {
                        "operation_code": "钻沉头孔",
                        "operation_name_raw": "钻沉头孔",
                        "reason": "加工通孔及沉头台阶。",
                        "evidence_summary": "PDF 孔标注。",
                        "confidence": 0.98,
                        "requires_review": True,
                    },
                    {
                        "operation_code": "攻螺纹",
                        "operation_name_raw": "攻螺纹",
                        "reason": "加工螺纹孔。",
                        "evidence_summary": "PDF M6 标注。",
                        "confidence": 0.95,
                        "requires_review": True,
                    },
                    {
                        "operation_code": "终检包装",
                        "operation_name_raw": "终检包装",
                        "reason": "完工后检验包装。",
                        "evidence_summary": "常规报价流程。",
                        "confidence": 0.82,
                        "requires_review": True,
                    },
                ]
            ),
            inherited_risks=[{"requires_review": True}],
        )

        self.assertEqual(
            [operation["operation_code"] for operation in route["operations"]],
            ["saw_cut", "cnc_milling", "countersink", "tapping", "inspection"],
        )
        self.assertFalse(any(operation["requires_review"] for operation in route["operations"]))
        self.assertFalse(route["requires_review"])
        self.assertNotIn(
            "PROCESS_ROUTE_REQUIRES_REVIEW",
            {risk["code"] for risk in route["risks"]},
        )

    def test_ai_generated_route_can_auto_accept_unmapped_operations(self) -> None:
        route = build_ai_generated_process_route(
            task_id="task_ai_route_004",
            route_id="route_ai_route_004",
            ai_output=ai_process_route_generation(
                [
                    {
                        "operation_code": "喷砂",
                        "operation_name_raw": "喷砂",
                        "reason": "PDF 技术要求出现喷砂。",
                        "evidence_summary": "technical_requirements contains 喷砂",
                        "confidence": 0.84,
                        "requires_review": True,
                    },
                ]
            ),
            inherited_risks=[],
        )

        operations = route["operations"]
        self.assertEqual([operation["operation_code"] for operation in operations], ["unmapped_operation"])
        self.assertFalse(operations[0]["requires_review"])
        self.assertFalse(route["requires_review"])
        self.assertNotIn(
            "UNMAPPED_OPERATION_REQUIRES_REVIEW",
            {risk["code"] for risk in route["risks"]},
        )

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

    def test_shaft_part_triggers_quotable_turning_route(self) -> None:
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
        self.assertIn("material_prepare", codes)
        self.assertIn("drilling", codes)
        self.assertIn("tapping", codes)
        self.assertIn("turning", codes)
        self.assertNotIn("review_drawing", codes)
        self.assertNotIn("manual_review", codes)
        self.assertNotIn("UNSUPPORTED_PART_REQUIRES_MANUAL_REVIEW", {risk["code"] for risk in route["risks"]})
        operations = {
            operation["operation_code"]: operation
            for operation in route["operations"]
        }
        self.assert_rule_triggered(operations["turning"], "TURNING_FROM_SHAFT_PART_TYPE")

    def test_complex_part_triggers_quotable_cnc_and_edm_candidates(self) -> None:
        part_feature = part_feature_with_process_triggers()
        part_feature["geometry"]["part_type"] = "complex"
        part_feature["geometry"]["part_type_confidence"] = 0.84
        part_feature["geometry"]["part_type_candidates"] = [
            {
                "part_type": "complex",
                "confidence": 0.84,
                "reason": "STEP complex candidate",
                "source": source("step", "part_type_complex"),
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
        self.assertIn("cnc_milling", operations)
        self.assertIn("edm", operations)
        self.assert_rule_triggered(operations["cnc_milling"], "CNC_FROM_COMPLEX_PART_TYPE")
        self.assert_rule_triggered(operations["edm"], "EDM_COMPLEX_PART_CANDIDATE")
        self.assertNotIn("UNSUPPORTED_PART_REQUIRES_MANUAL_REVIEW", {risk["code"] for risk in route["risks"]})

    def test_ai_process_suggestion_can_add_valid_review_operation(self) -> None:
        route = build_process_route(
            task_id="task_001",
            route_id="route_001",
            part_feature=part_feature_with_process_triggers(),
            inherited_risks=[],
        )

        merged = apply_ai_process_route_suggestion(
            route,
            ai_process_suggestion(
                [
                    {
                        "action": "add",
                        "operation_code": "wire_cut_profile",
                        "reason": "STEP 摘要显示存在窄槽/异形轮廓，建议补充线切割候选。",
                        "evidence_summary": "slot_candidate_count > 0",
                        "confidence": 0.82,
                    }
                ]
            ),
        )

        operations = {
            operation["operation_code"]: operation
            for operation in merged["operations"]
        }
        self.assertIn("wire_cut_profile", operations)
        self.assert_rule_triggered(
            operations["wire_cut_profile"],
            "AI_ADD_WIRE_CUT_PROFILE",
        )
        self.assertFalse(operations["wire_cut_profile"]["requires_review"])
        self.assertIn(
            "AI_PROCESS_ROUTE_SUGGESTION_APPLIED",
            {risk["code"] for risk in merged["risks"]},
        )

    def test_ai_process_suggestion_keeps_unknown_operation_as_unmapped_review(self) -> None:
        route = build_process_route(
            task_id="task_001",
            route_id="route_001",
            part_feature=part_feature_with_process_triggers(),
            inherited_risks=[],
        )

        merged = apply_ai_process_route_suggestion(
            route,
            ai_process_suggestion(
                [
                    {
                        "action": "add",
                        "operation_code": "喷砂",
                        "operation_name_raw": "喷砂",
                        "reason": "PDF 技术要求出现喷砂，当前字典未登记。",
                        "evidence_summary": "technical_requirements contains 喷砂",
                        "confidence": 0.9,
                    }
                ]
            ),
        )

        unmapped = [
            operation
            for operation in merged["operations"]
            if operation["operation_code"] == "unmapped_operation"
        ]
        self.assertEqual(len(unmapped), 1)
        self.assertEqual(unmapped[0]["operation_name"], "未登记工序：喷砂")
        self.assertTrue(unmapped[0]["requires_review"])
        self.assert_rule_triggered(unmapped[0], "AI_UNMAPPED_OPERATION")
        self.assertIn(
            "UNMAPPED_OPERATION_REQUIRES_REVIEW",
            {risk["code"] for risk in merged["risks"]},
        )
        self.assertIn(
            "AI_PROCESS_ROUTE_SUGGESTION_APPLIED",
            {risk["code"] for risk in merged["risks"]},
        )

    def test_multiple_unknown_ai_processes_stay_separate(self) -> None:
        route = build_process_route(
            task_id="task_001",
            route_id="route_001",
            part_feature=part_feature_with_process_triggers(),
            inherited_risks=[],
        )

        merged = apply_ai_process_route_suggestion(
            route,
            ai_process_suggestion(
                [
                    {
                        "action": "add",
                        "operation_code": "喷砂",
                        "operation_name_raw": "喷砂",
                        "reason": "PDF 出现喷砂。",
                        "evidence_summary": "喷砂",
                        "confidence": 0.9,
                    },
                    {
                        "action": "add",
                        "operation_code": "氧化发黑",
                        "operation_name_raw": "氧化发黑",
                        "reason": "PDF 出现氧化发黑。",
                        "evidence_summary": "氧化发黑",
                        "confidence": 0.88,
                    },
                ]
            ),
        )

        unmapped = [
            operation
            for operation in merged["operations"]
            if operation["operation_code"] == "unmapped_operation"
        ]

        self.assertEqual(
            [operation["operation_name"] for operation in unmapped],
            ["未登记工序：喷砂", "未登记工序：氧化发黑"],
        )
        self.assertEqual(len({operation["operation_id"] for operation in unmapped}), 2)

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


def ai_process_suggestion(suggestions: list[dict]) -> dict:
    return {
        "task_id": "task_001",
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


def ai_process_route_generation(operations: list[dict]) -> dict:
    return {
        "task_id": "task_ai_route_001",
        "input_type": "fusion_feature",
        "output_type": "process_route_generation",
        "content": {
            "operations": operations,
            "review_required": True,
            "summary": "AI 自主识别工艺路线。",
            "confidence": 0.82,
        },
        "confidence": 0.82,
        "evidence": [],
        "model_name": "fake-ai",
        "prompt_version": "test-v1",
        "created_at": "2026-06-15T10:00:00+08:00",
    }


if __name__ == "__main__":
    unittest.main()
