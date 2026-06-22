from __future__ import annotations

import unittest

from backend.app.process_dictionary import (
    PROCESS_DICTIONARY,
    PROCESS_SEQUENCE,
    is_registered_process_code,
)
from backend.app.process_recognition import (
    STAGE_SEQUENCE,
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
                        "operation_code": "氧化发黑",
                        "operation_name_raw": "氧化发黑",
                        "reason": "PDF 技术要求出现氧化发黑，但字典未登记。",
                        "evidence_summary": "technical_requirements contains 氧化发黑",
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
        self.assertEqual(operations[1]["operation_name"], "未登记工序：氧化发黑")
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
                        "operation_code": "氧化发黑",
                        "operation_name_raw": "氧化发黑",
                        "reason": "PDF 技术要求出现氧化发黑。",
                        "evidence_summary": "technical_requirements contains 氧化发黑",
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
        self.assertNotIn("manual_review", codes)
        self.assertIn("INHERITED_REVIEW_RISK", {risk["code"] for risk in route["risks"]})

        for operation in operations:
            definition = PROCESS_DICTIONARY[operation["operation_code"]]
            self.assertEqual(operation["operation_name"], definition.process_name)
            self.assertGreaterEqual(operation["confidence"], 0)
            self.assertLessEqual(operation["confidence"], 1)
            self.assertGreaterEqual(operation["sequence"], 1)
            self.assertTrue(operation["operation_id"].startswith("op_"))
            self.assertTrue(operation["trigger_reasons"])

    def test_route_includes_professional_stage_route_before_operations(self) -> None:
        route = build_process_route(
            task_id="task_stage_route_001",
            route_id="route_stage_route_001",
            part_feature=part_feature_with_process_triggers(),
            inherited_risks=[],
        )

        stage_codes = [stage["stage_code"] for stage in route["stage_route"]]

        self.assertEqual(stage_codes, sorted(stage_codes, key=STAGE_SEQUENCE.index))
        self.assertIn("material_preparation", stage_codes)
        self.assertIn("blanking", stage_codes)
        self.assertIn("rough_machining", stage_codes)
        self.assertIn("hole_machining", stage_codes)
        self.assertIn("heat_and_stabilize", stage_codes)
        self.assertIn("finish_and_precision", stage_codes)
        self.assertIn("surface_treatment", stage_codes)
        self.assertIn("inspection", stage_codes)
        self.assertIn("packaging", stage_codes)
        self.assertLess(stage_codes.index("inspection"), stage_codes.index("packaging"))
        self.assertNotIn("manual_review", stage_codes)
        self.assertEqual(
            [stage["sequence"] for stage in route["stage_route"]],
            list(range(1, len(route["stage_route"]) + 1)),
        )
        self.assertTrue(
            all(stage.get("actual_operation_codes") for stage in route["stage_route"])
        )
        self.assertTrue(
            all(operation.get("stage_code") for operation in route["operations"])
        )

    def test_ai_generated_stage_route_expands_with_part_feature(self) -> None:
        route = build_ai_generated_process_route(
            task_id="task_ai_stage_route_001",
            route_id="route_ai_stage_route_001",
            ai_output=ai_process_stage_route_generation(
                [
                    {
                        "stage_code": "material_preparation",
                        "stage_name_raw": "来料/备料",
                        "reason": "图纸材料为 SKD11。",
                        "evidence_summary": "material=SKD11",
                        "confidence": 0.9,
                        "requires_review": False,
                    },
                    {
                        "stage_code": "blanking",
                        "stage_name_raw": "下料",
                        "reason": "板件需要先开料。",
                        "evidence_summary": "part_type=plate",
                        "confidence": 0.88,
                        "requires_review": False,
                    },
                    {
                        "stage_code": "rough_machining",
                        "stage_name_raw": "主体粗加工",
                        "reason": "板件先粗加工建立基准。",
                        "evidence_summary": "part_type=plate",
                        "confidence": 0.86,
                        "requires_review": False,
                    },
                    {
                        "stage_code": "hole_machining",
                        "stage_name_raw": "孔加工",
                        "reason": "存在孔特征。",
                        "evidence_summary": "holes present",
                        "confidence": 0.86,
                        "requires_review": False,
                    },
                    {
                        "stage_code": "heat_and_stabilize",
                        "stage_name_raw": "热处理",
                        "reason": "图纸要求淬火。",
                        "evidence_summary": "HRC58-62",
                        "confidence": 0.88,
                        "requires_review": False,
                    },
                    {
                        "stage_code": "finish_and_precision",
                        "stage_name_raw": "精加工/精孔",
                        "reason": "热处理后完成精修和精孔。",
                        "evidence_summary": "precision hole",
                        "confidence": 0.84,
                        "requires_review": False,
                    },
                    {
                        "stage_code": "surface_treatment",
                        "stage_name_raw": "表面处理",
                        "reason": "图纸要求化学镍。",
                        "evidence_summary": "chemical nickel",
                        "confidence": 0.84,
                        "requires_review": False,
                    },
                    {
                        "stage_code": "inspection",
                        "stage_name_raw": "终检",
                        "reason": "完工前检验。",
                        "evidence_summary": "inspection",
                        "confidence": 0.82,
                        "requires_review": False,
                    },
                    {
                        "stage_code": "packaging",
                        "stage_name_raw": "包装",
                        "reason": "检验后防护包装。",
                        "evidence_summary": "packaging",
                        "confidence": 0.8,
                        "requires_review": False,
                    },
                ]
            ),
            inherited_risks=[],
            part_feature=part_feature_with_process_triggers(),
        )

        stage_codes = [stage["stage_code"] for stage in route["stage_route"]]
        operation_codes = {operation["operation_code"] for operation in route["operations"]}

        self.assertEqual(stage_codes[0], "material_preparation")
        self.assertLess(stage_codes.index("inspection"), stage_codes.index("packaging"))
        self.assertIn("cnc_rough_milling", operation_codes)
        self.assertIn("drilling", operation_codes)
        self.assertIn("heat_treatment", operation_codes)
        self.assertIn("chemical_nickel", operation_codes)
        self.assertIn("protective_packaging", operation_codes)

    def test_heat_with_precision_hole_expands_to_after_heat_hole_recovery(self) -> None:
        part_feature = part_feature_with_process_triggers()
        part_feature["material"]["raw_text"] = "45#"
        part_feature["material"]["standard_code"] = "S45C"
        part_feature["features"]["precision_requirements"] = []
        part_feature["features"]["holes"] = [
            {
                "hole_type": "precision_candidate",
                "diameter": 8,
                "depth": None,
                "count": 1,
                "confidence": 0.7,
                "evidence": [source("pdf", "hole_precision")],
            }
        ]
        part_feature["manufacturing_requirements"].pop("surface_treatment", None)

        route = build_process_route(
            task_id="task_post_heat_anchor",
            route_id="route_post_heat_anchor",
            part_feature=part_feature,
            inherited_risks=[],
        )

        stage_by_code = {stage["stage_code"]: stage for stage in route["stage_route"]}
        operation_codes = {operation["operation_code"] for operation in route["operations"]}

        self.assertIn("post_heat_correction", stage_by_code)
        self.assertIn("finish_and_precision", stage_by_code)
        self.assertTrue({"precision_hole", "reaming"} & operation_codes)
        self.assertFalse(
            {"straightening", "finish_grinding", "cylindrical_grinding"} & operation_codes
        )
        self.assertTrue(
            {"precision_hole", "reaming", "boring"}
            & set(stage_by_code["post_heat_correction"]["actual_operation_codes"])
        )
        self.assertIn("hardness_inspection", operation_codes)
        self.assertIn("hardness_inspection", stage_by_code["post_heat_correction"]["actual_operation_codes"])

    def test_post_heat_correction_stage_expands_to_straightening_for_thin_plate(self) -> None:
        part_feature = part_feature_with_process_triggers()
        part_feature["material"]["raw_text"] = "45#"
        part_feature["material"]["standard_code"] = "S45C"
        part_feature["geometry"]["part_type"] = "thin_plate"
        part_feature["geometry"]["bounding_box"] = {
            "length": 320,
            "width": 80,
            "height": 4,
            "unit": "mm",
        }
        part_feature["features"]["precision_requirements"] = []
        part_feature["features"]["holes"] = []
        part_feature["manufacturing_requirements"].pop("surface_treatment", None)

        route = build_process_route(
            task_id="task_post_heat_straightening",
            route_id="route_post_heat_straightening",
            part_feature=part_feature,
            inherited_risks=[],
        )

        stage_by_code = {stage["stage_code"]: stage for stage in route["stage_route"]}
        operations = {
            operation["operation_code"]: operation
            for operation in route["operations"]
        }

        self.assertIn("post_heat_correction", stage_by_code)
        self.assertIn("straightening", operations)
        self.assertNotIn("finish_grinding", operations)
        self.assertIn(
            "straightening",
            stage_by_code["post_heat_correction"]["actual_operation_codes"],
        )

    def test_post_heat_correction_stage_expands_to_finish_grinding_for_flatness(self) -> None:
        part_feature = part_feature_with_process_triggers()
        part_feature["material"]["raw_text"] = "45#"
        part_feature["material"]["standard_code"] = "S45C"
        part_feature["features"]["holes"] = []
        part_feature["features"]["precision_requirements"] = [
            {
                "raw_text": "平面度0.02，厚度公差±0.01",
                "standard_type": "flatness",
                "confidence": 0.8,
                "source": source("pdf", "flatness"),
            }
        ]
        part_feature["manufacturing_requirements"].pop("surface_treatment", None)

        route = build_process_route(
            task_id="task_post_heat_finish_grinding",
            route_id="route_post_heat_finish_grinding",
            part_feature=part_feature,
            inherited_risks=[],
        )

        stage_by_code = {stage["stage_code"]: stage for stage in route["stage_route"]}
        operations = {
            operation["operation_code"]: operation
            for operation in route["operations"]
        }

        self.assertIn("post_heat_correction", stage_by_code)
        self.assertIn("finish_grinding", operations)
        self.assertNotIn("straightening", operations)
        self.assertIn(
            "finish_grinding",
            stage_by_code["post_heat_correction"]["actual_operation_codes"],
        )

    def test_post_heat_correction_stage_expands_to_cylindrical_grinding_for_shaft(self) -> None:
        part_feature = part_feature_with_process_triggers()
        part_feature["material"]["raw_text"] = "45#"
        part_feature["material"]["standard_code"] = "S45C"
        part_feature["geometry"]["part_type"] = "shaft"
        part_feature["geometry"]["bounding_box"] = {
            "length": 180,
            "width": 30,
            "height": 30,
            "unit": "mm",
        }
        part_feature["features"]["holes"] = []
        part_feature["features"]["precision_requirements"] = []
        part_feature["manufacturing_requirements"].pop("surface_treatment", None)

        route = build_process_route(
            task_id="task_post_heat_cylindrical_grinding",
            route_id="route_post_heat_cylindrical_grinding",
            part_feature=part_feature,
            inherited_risks=[],
        )

        stage_by_code = {stage["stage_code"]: stage for stage in route["stage_route"]}
        operations = {
            operation["operation_code"]: operation
            for operation in route["operations"]
        }

        self.assertIn("post_heat_correction", stage_by_code)
        self.assertIn("cylindrical_grinding", operations)
        self.assertIn(
            "cylindrical_grinding",
            stage_by_code["post_heat_correction"]["actual_operation_codes"],
        )

    def test_after_heat_recovery_adds_thread_surface_and_hardness_steps(self) -> None:
        part_feature = part_feature_with_process_triggers()
        part_feature["material"]["raw_text"] = "SKD11"
        part_feature["material"]["standard_code"] = "SKD11"
        part_feature["features"]["holes"] = [
            {
                "hole_type": "thread_candidate",
                "diameter": 6,
                "depth": 12,
                "count": 2,
                "confidence": 0.76,
                "evidence": [source("pdf", "thread")],
            }
        ]
        part_feature["features"]["precision_requirements"] = []
        part_feature["manufacturing_requirements"]["technical_requirements"] = [
            "热处理后去氧化皮，硬度HRC58-62"
        ]
        part_feature["manufacturing_requirements"].pop("surface_treatment", None)

        route = build_process_route(
            task_id="task_after_heat_recovery",
            route_id="route_after_heat_recovery",
            part_feature=part_feature,
            inherited_risks=[],
        )

        stage_by_code = {stage["stage_code"]: stage for stage in route["stage_route"]}
        operations = {
            operation["operation_code"]: operation
            for operation in route["operations"]
        }
        actual_codes = stage_by_code["post_heat_correction"]["actual_operation_codes"]

        self.assertIn("thread_chasing", operations)
        self.assertIn("sand_blasting", operations)
        self.assertIn("cleaning", operations)
        self.assertIn("hardness_inspection", operations)
        self.assertIn("thread_chasing", actual_codes)
        self.assertIn("sand_blasting", actual_codes)
        self.assertIn("cleaning", actual_codes)
        self.assertIn("hardness_inspection", actual_codes)
        self.assert_rule_triggered(operations["thread_chasing"], "AFTER_HEAT_THREAD_CHASING")
        self.assert_rule_triggered(operations["sand_blasting"], "AFTER_HEAT_OXIDE_SANDBLASTING")
        self.assert_rule_triggered(operations["hardness_inspection"], "AFTER_HEAT_HARDNESS_INSPECTION")

    def test_stage_without_expanded_operation_is_flagged_for_review(self) -> None:
        route = build_ai_generated_process_route(
            task_id="task_stage_without_operation",
            route_id="route_stage_without_operation",
            ai_output=ai_process_stage_route_generation(
                [
                    {
                        "stage_code": "post_surface",
                        "stage_name_raw": "表处后处理",
                        "reason": "AI 认为需要表处后处理。",
                        "evidence_summary": "post surface",
                        "confidence": 0.8,
                        "requires_review": False,
                    }
                ]
            ),
            inherited_risks=[],
            part_feature={
                "material": {},
                "geometry": {},
                "features": {},
                "manufacturing_requirements": {},
            },
        )

        self.assertEqual(route["stage_route"][0]["stage_code"], "post_surface")
        self.assertEqual(route["stage_route"][0]["actual_operation_codes"], [])
        self.assertTrue(route["stage_route"][0]["requires_review"])
        self.assertIn(
            "STAGE_WITHOUT_OPERATION",
            {risk["code"] for risk in route["risks"]},
        )

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
        self.assertIn("drilling_through", operations)
        self.assertIn("counterbore", operations)
        self.assertIn("blind_tapping", operations)
        self.assertIn("reaming", operations)
        self.assertIn("precision_surface_finish", operations)
        self.assertIn("finish_grinding", operations)
        self.assertIn("heat_treatment", operations)
        self.assertIn("chemical_nickel", operations)
        self.assertIn("deburr", operations)

        self.assert_rule_triggered(operations["drilling"], "HOLE_COUNTER_FEATURE_PREDRILL")
        self.assert_rule_triggered(operations["drilling_through"], "HOLE_THROUGH")
        self.assert_rule_triggered(operations["counterbore"], "HOLE_COUNTERBORE")
        self.assert_rule_triggered(operations["blind_tapping"], "HOLE_THREAD_CANDIDATE")
        self.assert_rule_triggered(operations["reaming"], "HOLE_PRECISION_CANDIDATE")
        self.assert_rule_triggered(operations["precision_surface_finish"], "ROUGHNESS_OR_FLATNESS_REQUIREMENT")
        self.assert_rule_triggered(operations["heat_treatment"], "HEAT_TREATMENT_REQUIRED")
        self.assert_rule_triggered(operations["chemical_nickel"], "SURFACE_TREATMENT_CHEMICAL_NICKEL")
        self.assert_rule_triggered(operations["deburr"], "DEBURRING_REQUIRED")
        self.assertTrue(operations["blind_tapping"]["requires_review"])
        self.assertTrue(operations["reaming"]["requires_review"])

    def test_structured_non_chemical_surface_treatment_maps_to_specific_process(self) -> None:
        part_feature = part_feature_with_process_triggers()
        part_feature["manufacturing_requirements"]["surface_treatment"] = {
            "required": True,
            "raw_text": "硬质阳极氧化",
            "standard_code": "HARD_ANODIZING",
            "confidence": 0.88,
            "source": source("pdf", "surface"),
        }

        route = build_process_route(
            task_id="task_surface_hard_anodizing",
            route_id="route_surface_hard_anodizing",
            part_feature=part_feature,
            inherited_risks=[],
        )

        operations = {
            operation["operation_code"]: operation
            for operation in route["operations"]
        }

        self.assertIn("hard_anodizing", operations)
        self.assertNotIn("chemical_nickel", operations)
        self.assertIn("pre_plating_cleaning", operations)
        self.assertNotIn("post_plating_inspection", operations)
        self.assertIn("coating_thickness_inspection", operations)
        self.assertIn("surface_inspection", operations)
        self.assert_rule_triggered(operations["hard_anodizing"], "SURFACE_TREATMENT_HARD_ANODIZING")

    def test_generic_oxidation_text_does_not_map_to_anodizing(self) -> None:
        part_feature = part_feature_with_process_triggers()
        part_feature["manufacturing_requirements"]["surface_treatment"] = {
            "required": True,
            "raw_text": "氧化发黑",
            "standard_code": None,
            "confidence": 0.72,
            "source": source("pdf", "surface"),
        }

        route = build_process_route(
            task_id="task_surface_black_oxide",
            route_id="route_surface_black_oxide",
            part_feature=part_feature,
            inherited_risks=[],
        )

        codes = {operation["operation_code"] for operation in route["operations"]}

        self.assertNotIn("clear_anodizing", codes)
        self.assertNotIn("review_drawing", codes)
        self.assertIn("SURFACE_TREATMENT_UNKNOWN", {risk["code"] for risk in route["risks"]})
        self.assertTrue(route["requires_review"])

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
        drilling_through = next(
            operation
            for operation in route["operations"]
            if operation["operation_code"] == "drilling_through"
        )
        drilling_blind = next(
            operation
            for operation in route["operations"]
            if operation["operation_code"] == "drilling_blind"
        )

        drilling_rules = [
            reason["rule_code"]
            for reason in drilling["trigger_reasons"]
        ]
        self.assertIn("HOLE_COUNTER_FEATURE_PREDRILL", drilling_rules)
        self.assertIn("HOLE_PRECISION_PREDRILL", drilling_rules)
        self.assert_rule_triggered(drilling_blind, "HOLE_THREAD_PILOT_DRILLING")
        drilling_through_rules = [
            reason["rule_code"]
            for reason in drilling_through["trigger_reasons"]
        ]
        self.assertEqual(drilling_through_rules.count("HOLE_THROUGH"), 2)
        self.assertEqual(drilling_through["confidence"], 0.91)

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
        self.assertNotIn("review_drawing", codes)
        self.assertNotIn("saw_cut", codes)
        self.assertNotIn("cnc_milling", codes)
        self.assertNotIn("wire_cut_profile", codes)
        self.assertIn("PART_TYPE_MISSING", {risk["code"] for risk in route["risks"]})
        self.assertTrue(route["requires_review"])

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
        self.assert_rule_triggered(operations["fixture_setup"], "FIXTURE_SETUP_FROM_PART_TYPE")
        self.assert_rule_triggered(operations["cnc_rough_milling"], "CNC_ROUGH_MILLING_FROM_PART_TYPE")
        self.assert_rule_triggered(operations["cnc_finish_milling"], "CNC_FROM_PART_TYPE")
        self.assert_rule_triggered(operations["profile_milling"], "PROFILE_MILLING_FROM_PART_TYPE")
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

    def test_surface_treatment_precision_hole_risk_mentions_compensation(self) -> None:
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
        self.assertIn("表处前尺寸补偿", risk["message"])
        self.assertIn("表处后孔径复检", risk["message"])

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
        self.assertIn("blind_tapping", codes)
        self.assertIn("turning_rough", codes)
        self.assertIn("turning_finish", codes)
        self.assertNotIn("review_drawing", codes)
        self.assertNotIn("manual_review", codes)
        self.assertNotIn("UNSUPPORTED_PART_REQUIRES_MANUAL_REVIEW", {risk["code"] for risk in route["risks"]})
        operations = {
            operation["operation_code"]: operation
            for operation in route["operations"]
        }
        self.assert_rule_triggered(operations["turning_rough"], "TURNING_ROUGH_FROM_SHAFT_PART_TYPE")
        self.assert_rule_triggered(operations["turning_finish"], "TURNING_FROM_SHAFT_PART_TYPE")

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
        self.assertIn("cnc_rough_milling", operations)
        self.assertIn("cnc_finish_milling", operations)
        self.assertIn("pocket_milling", operations)
        self.assertIn("edm", operations)
        self.assert_rule_triggered(operations["cnc_rough_milling"], "CNC_FROM_COMPLEX_PART_TYPE")
        self.assert_rule_triggered(operations["cnc_finish_milling"], "CNC_FINISH_FROM_COMPLEX_PART_TYPE")
        self.assert_rule_triggered(operations["pocket_milling"], "POCKET_MILLING_COMPLEX_PART_CANDIDATE")
        self.assert_rule_triggered(operations["edm"], "EDM_COMPLEX_PART_CANDIDATE")
        self.assertNotIn("UNSUPPORTED_PART_REQUIRES_MANUAL_REVIEW", {risk["code"] for risk in route["risks"]})

    def test_manufacturing_decision_layer_keeps_planning_out_of_route_and_adds_special_inspections(self) -> None:
        route = build_process_route(
            task_id="task_decision_layer",
            route_id="route_decision_layer",
            part_feature=part_feature_with_process_triggers(),
            inherited_risks=[],
        )

        operations = {
            operation["operation_code"]: operation
            for operation in route["operations"]
        }

        self.assertNotIn("review_drawing", operations)
        self.assertNotIn("process_planning", operations)
        self.assertNotIn(
            "PROCESS_PLANNING_FROM_MANUFACTURING_DECISION_INPUTS",
            {risk["code"] for risk in route["risks"]},
        )
        self.assert_rule_triggered(
            operations["raw_material_check"],
            "RAW_MATERIAL_CHECK_FROM_MATERIAL",
        )
        self.assert_rule_triggered(
            operations["in_process_inspection"],
            "IN_PROCESS_INSPECTION_FROM_ROUTE_RISK",
        )
        self.assert_rule_triggered(
            operations["thread_inspection"],
            "THREAD_INSPECTION_FROM_THREAD_PROCESS",
        )
        self.assert_rule_triggered(
            operations["precision_hole_inspection"],
            "PRECISION_HOLE_INSPECTION_FROM_PRECISION_PROCESS",
        )
        self.assert_rule_triggered(
            operations["coating_thickness_inspection"],
            "SURFACE_TREATMENT_FINAL_COATING_INSPECTION",
        )
        self.assert_rule_triggered(
            operations["surface_inspection"],
            "SURFACE_TREATMENT_FINAL_SURFACE_INSPECTION",
        )

    def test_high_complexity_part_adds_fixture_stress_and_first_article_nodes(self) -> None:
        part_feature = part_feature_with_process_triggers()
        part_feature["part"] = {"quantity": 5}
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
        part_feature["features"]["complexity"]["complexity_score"] = 72
        part_feature["features"]["complexity"]["slot_count"] = 2

        route = build_process_route(
            task_id="task_high_complexity",
            route_id="route_high_complexity",
            part_feature=part_feature,
            inherited_risks=[],
        )

        operations = {
            operation["operation_code"]: operation
            for operation in route["operations"]
        }

        self.assert_rule_triggered(operations["fixture_setup"], "FIXTURE_SETUP_COMPLEX_PART")
        self.assert_rule_triggered(operations["soft_jaw_fixture"], "SOFT_JAW_FIXTURE_FROM_GEOMETRY_RISK")
        self.assert_rule_triggered(operations["stress_relief"], "STRESS_RELIEF_FROM_ROUGHING_RISK")
        self.assert_rule_triggered(operations["first_article_inspection"], "FIRST_ARTICLE_INSPECTION_FROM_BATCH_RISK")
        self.assertTrue(operations["stress_relief"]["requires_review"])

    def test_thin_or_long_plate_adds_anti_deformation_and_flatness_inspection(self) -> None:
        part_feature = part_feature_with_process_triggers()
        part_feature["geometry"]["part_type"] = "plate"
        part_feature["geometry"]["bounding_box"] = {
            "length": 420,
            "width": 36,
            "height": 4,
            "unit": "mm",
        }
        part_feature["features"]["complexity"]["thin_wall_candidate"] = False
        part_feature["features"]["complexity"]["complexity_score"] = 35

        route = build_process_route(
            task_id="task_deformation_risk",
            route_id="route_deformation_risk",
            part_feature=part_feature,
            inherited_risks=[],
        )

        operations = {
            operation["operation_code"]: operation
            for operation in route["operations"]
        }

        self.assert_rule_triggered(operations["support_anti_deformation"], "SUPPORT_ANTI_DEFORMATION_FROM_GEOMETRY")
        self.assert_rule_triggered(operations["stress_relief"], "STRESS_RELIEF_FROM_ROUGHING_RISK")
        self.assert_rule_triggered(operations["flatness_inspection"], "FLATNESS_INSPECTION_FROM_REQUIREMENT_OR_GEOMETRY")

    def test_side_hole_features_add_setup_and_side_processes(self) -> None:
        part_feature = part_feature_with_process_triggers()
        part_feature["features"]["holes"] = [
            {
                "hole_type": "thread_candidate",
                "diameter": 5,
                "depth": 10,
                "count": 2,
                "side": "side",
                "confidence": 0.76,
                "evidence": [source("step", "side_thread")],
            }
        ]

        route = build_process_route(
            task_id="task_side_hole",
            route_id="route_side_hole",
            part_feature=part_feature,
            inherited_risks=[],
        )

        operations = {
            operation["operation_code"]: operation
            for operation in route["operations"]
        }

        self.assert_rule_triggered(operations["second_setup"], "HOLE_SECOND_SETUP_FROM_SIDE_FEATURE")
        self.assert_rule_triggered(operations["side_setup"], "HOLE_SIDE_SETUP_FROM_SIDE_FEATURE")
        self.assert_rule_triggered(operations["side_hole_machining"], "HOLE_SIDE_MACHINING")
        self.assert_rule_triggered(operations["side_tapping"], "HOLE_SIDE_THREAD_CANDIDATE")

    def test_specific_surface_treatments_add_specific_masking_and_post_steps(self) -> None:
        part_feature = part_feature_with_process_triggers()
        part_feature["manufacturing_requirements"]["surface_treatment"] = {
            "required": True,
            "raw_text": "hard chrome",
            "standard_code": "HARD_CHROME",
            "confidence": 0.86,
            "source": source("pdf", "surface_hard_chrome"),
        }

        route = build_process_route(
            task_id="task_hard_chrome",
            route_id="route_hard_chrome",
            part_feature=part_feature,
            inherited_risks=[],
        )

        operations = {
            operation["operation_code"]: operation
            for operation in route["operations"]
        }

        self.assert_rule_triggered(operations["hard_chrome"], "SURFACE_TREATMENT_HARD_CHROME")
        self.assert_rule_triggered(
            operations["hard_chrome_masking"],
            "SURFACE_TREATMENT_HARD_CHROME_MASKING_CANDIDATE",
        )
        self.assert_rule_triggered(operations["dehydrogenation_bake"], "HARD_CHROME_DEHYDROGENATION_CANDIDATE")
        self.assert_rule_triggered(operations["post_chrome_inspection"], "HARD_CHROME_POST_INSPECTION")

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
                        "operation_code": "氧化发黑",
                        "operation_name_raw": "氧化发黑",
                        "reason": "PDF 技术要求出现氧化发黑，当前字典未登记。",
                        "evidence_summary": "technical_requirements contains 氧化发黑",
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
        self.assertEqual(unmapped[0]["operation_name"], "未登记工序：氧化发黑")
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
                        "operation_code": "氧化发黑",
                        "operation_name_raw": "氧化发黑",
                        "reason": "PDF 出现氧化发黑。",
                        "evidence_summary": "氧化发黑",
                        "confidence": 0.9,
                    },
                    {
                        "action": "add",
                        "operation_code": "激光打标",
                        "operation_name_raw": "激光打标",
                        "reason": "PDF 出现激光打标。",
                        "evidence_summary": "激光打标",
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
            ["未登记工序：氧化发黑", "未登记工序：激光打标"],
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


def ai_process_stage_route_generation(stages: list[dict]) -> dict:
    return {
        "task_id": "task_ai_stage_route_001",
        "input_type": "fusion_feature",
        "output_type": "process_route_generation",
        "content": {
            "stages": stages,
            "operations": [],
            "review_required": False,
            "summary": "AI 自主规划工艺阶段路线。",
            "confidence": 0.86,
        },
        "confidence": 0.86,
        "evidence": [],
        "model_name": "fake-ai",
        "prompt_version": "test-v1",
        "created_at": "2026-06-15T10:00:00+08:00",
    }


if __name__ == "__main__":
    unittest.main()
