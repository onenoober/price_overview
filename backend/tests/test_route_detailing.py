from __future__ import annotations

import os
import unittest

from backend.app.domain_v2.route_engine import plan_route_v2
from backend.tests.route_engine_fixtures import make_part_feature, operation_codes, risk_codes


CAT_LARGE_PLATE = "\u5927\u677f\u7c7b"
CAT_SHEET_METAL = "\u94a3\u91d1\u7c7b"
CAT_TURNING = "\u5706\u4ef6\u7c7b"
CAT_MACHINING = "\u65b9\u4ef6\u7c7b"


def _plan(part_feature):
    return plan_route_v2(
        task_id="t",
        route_id="r",
        part_feature=part_feature,
        inherited_risks=[],
    )


class RouteDetailingTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("PRICE_AGENT_ROUTE_DETAILING", None)

    def test_detailing_can_be_disabled(self) -> None:
        os.environ["PRICE_AGENT_ROUTE_DETAILING"] = "off"
        route = _plan(
            make_part_feature(
                category_name=CAT_LARGE_PLATE,
                part_type="plate",
                compatible_part_types=("plate", "long_bar"),
                material={"raw_text": "45"},
                surface_treatment={
                    "required": True,
                    "raw_text": "hard chrome",
                    "standard_code": "HARD_CHROME",
                    "source": {"source_type": "pdf", "file_id": "pdf-1"},
                },
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("hard_chrome", codes)
        self.assertNotIn("dehydrogenation_bake", codes)
        self.assertNotIn("post_chrome_inspection", codes)

    def test_template_conditional_welding_is_review_only_on_single_sheet(self) -> None:
        """P1 修复：标准模板条件句（"对于尺寸较大的钣金件…进行焊接加固…焊后打磨"）
        在单片钣金件上不得提级为必焊，只产 WELDING_CONDITIONAL_TEXT 复核。"""

        route = _plan(
            make_part_feature(
                category_name="钣金类",
                part_type="plate",
                compatible_part_types=("plate", "long_bar"),
                technical_requirements=[
                    {"raw_text": "对于尺寸较大的钣金件，对接合处进行焊接加固，焊后打磨"}
                ],
            )
        )
        self.assertNotIn("sheet_metal_welding", set(operation_codes(route)))
        self.assertIn("WELDING_CONDITIONAL_TEXT", risk_codes(route))

    def test_hard_chrome_detail_chain_added(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_LARGE_PLATE,
                part_type="plate",
                compatible_part_types=("plate", "long_bar"),
                material={"raw_text": "45"},
                surface_treatment={
                    "required": True,
                    "raw_text": "hard chrome",
                    "standard_code": "HARD_CHROME",
                    "source": {"source_type": "pdf", "file_id": "pdf-1"},
                },
                holes=[{"count": 2, "hole_type": "precision_candidate", "raw_text": "H7"}],
            )
        )
        codes = set(operation_codes(route))
        for code in {
            "hard_chrome",
            "hard_chrome_masking",
            "dehydrogenation_bake",
            "post_chrome_polishing",
            "post_surface_precision_hole_check",
            "coating_thickness_inspection",
            "post_chrome_inspection",
        }:
            self.assertIn(code, codes)

    def test_heat_treatment_hardness_inspection_added(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_TURNING,
                part_type="shaft",
                compatible_part_types=("shaft",),
                heat_treatment={
                    "required": True,
                    "raw_text": "HRC45-50",
                    "source": {"source_type": "pdf", "file_id": "pdf-1"},
                },
            )
        )
        self.assertIn("hardness_inspection", set(operation_codes(route)))

    def test_heat_treatment_section_heading_alone_does_not_add_heat_treatment(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_MACHINING,
                part_type="block",
                compatible_part_types=("block",),
                material={"raw_text": "6061"},
                technical_requirements=[{"raw_text": "热处理"}],
            )
        )
        self.assertNotIn("heat_treatment", set(operation_codes(route)))

    def test_anodize_precision_hole_post_reaming_added(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_MACHINING,
                part_type="block",
                compatible_part_types=("block",),
                material={"raw_text": "6061"},
                surface_treatment={
                    "required": True,
                    "raw_text": "clear anodizing",
                    "standard_code": "ANODIZING",
                    "source": {"source_type": "pdf", "file_id": "pdf-1"},
                },
                holes=[{"count": 1, "hole_type": "precision_candidate", "raw_text": "H7"}],
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("clear_anodizing", codes)
        self.assertIn("post_anodize_reaming", codes)
        self.assertIn("post_surface_precision_hole_check", codes)

    def test_machining_complex_block_adds_family_local_detailing(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_MACHINING,
                part_type="complex_block",
                compatible_part_types=("block", "complex_block"),
                holes=[
                    {"count": 2, "hole_type": "through", "through": True, "diameter": 5.0},
                    {"count": 2, "hole_type": "blind", "through": False, "diameter": 4.2, "depth": 12.0},
                    {
                        "count": 1,
                        "hole_type": "thread_candidate",
                        "through": True,
                        "raw_text": "M6 - 6H \u5b8c\u5168\u8d2f\u7a7f",
                    },
                    {
                        "count": 1,
                        "hole_type": "thread_candidate",
                        "through": False,
                        "raw_text": "M4 - 6H; 8",
                    },
                    {"count": 1, "hole_type": "precision_candidate", "raw_text": "H7"},
                ],
                complexity={"complexity_score": 80, "face_count": 24, "edge_count": 64},
            )
        )

        self.assertEqual(route["family"], "MACHINING")
        codes = operation_codes(route)
        for code in {
            "fixture_setup",
            "cnc_rough_milling",
            "drilling",
            "drilling_through",
            "drilling_blind",
            "tapping",
            "tapping_through",
            "blind_tapping",
            "profile_milling",
            "cnc_finish_milling",
            "precision_hole",
            "thread_inspection",
            "in_process_inspection",
            "inspection",
        }:
            self.assertIn(code, codes)
        self.assertLess(codes.index("fixture_setup"), codes.index("cnc_rough_milling"))
        self.assertLess(codes.index("cnc_rough_milling"), codes.index("drilling"))
        self.assertLess(codes.index("drilling"), codes.index("tapping"))
        self.assertLess(codes.index("tapping"), codes.index("profile_milling"))
        self.assertLess(codes.index("profile_milling"), codes.index("cnc_finish_milling"))
        self.assertLess(codes.index("thread_inspection"), codes.index("inspection"))
        self.assertLess(codes.index("in_process_inspection"), codes.index("inspection"))
        for operation in route["operations"]:
            self.assertTrue(operation.get("trigger_reasons"), operation)
            self.assertIsNotNone(operation.get("confidence"), operation)
            self.assertTrue(operation.get("stage_code"), operation)

    def test_machining_weak_counterbore_and_slot_require_review(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_MACHINING,
                part_type="complex_block",
                compatible_part_types=("block", "complex_block"),
                holes=[
                    {
                        "count": 2,
                        "hole_type": "counterbore",
                        "diameter": 5.0,
                    }
                ],
                complexity={"complexity_score": 70, "slot_count": 1},
            )
        )
        codes = set(operation_codes(route))
        self.assertNotIn("counterbore", codes)
        self.assertNotIn("slot_milling", codes)
        risks = risk_codes(route)
        self.assertIn("WEAK_MACHINING_COUNTERBORE_REVIEW", risks)
        self.assertIn("WEAK_MACHINING_SLOT_REVIEW", risks)

    def test_counterbore_does_not_spawn_countersink(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_LARGE_PLATE,
                part_type="plate",
                compatible_part_types=("plate", "long_bar"),
                holes=[
                    {
                        "count": 4,
                        "hole_type": "counterbore",
                        "diameter": 4.5,
                        "counterbore_diameter": 8.0,
                        "counterbore_depth": 2.5,
                    }
                ],
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("counterbore", codes)
        self.assertNotIn("countersink", codes)

    def test_sheet_metal_redundant_countersink_is_suppressed(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_SHEET_METAL,
                part_type="plate",
                compatible_part_types=("plate", "complex"),
                holes=[
                    {
                        "count": 4,
                        "hole_type": "counterbore",
                        "diameter": 4.5,
                        "counterbore_diameter": 8.0,
                        "counterbore_depth": 2.5,
                    },
                    {
                        "count": 4,
                        "hole_type": "countersink",
                        "diameter": 4.5,
                        "countersink_diameter": 8.0,
                        "countersink_depth": 1.7,
                        "countersink_angle": 90.0,
                    },
                ],
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("counterbore", codes)
        self.assertNotIn("countersink", codes)

    def test_implausible_shaft_counterbore_is_not_routed(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_TURNING,
                part_type="shaft",
                compatible_part_types=("shaft",),
                holes=[
                    {
                        "count": 2,
                        "hole_type": "thread_candidate",
                        "diameter": 6.0,
                        "depth": 6.0,
                    },
                    {
                        "count": 1,
                        "hole_type": "counterbore",
                        "diameter": 5.0,
                        "depth": 12.0,
                        "counterbore_diameter": 12.0,
                        "counterbore_depth": 274.0,
                    },
                ],
                bounding_box={"length": 275, "width": 12, "height": 12},
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("drilling", codes)
        self.assertIn("tapping", codes)
        self.assertNotIn("counterbore", codes)

    def test_slender_shaft_adds_straightening_candidate(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_TURNING,
                part_type="shaft",
                compatible_part_types=("shaft",),
                heat_treatment={
                    "required": True,
                    "raw_text": "HRC45-50",
                    "source": {"source_type": "pdf", "file_id": "pdf-1"},
                },
                bounding_box={"length": 275, "width": 12, "height": 12},
            )
        )
        codes = operation_codes(route)
        self.assertIn("straightening", codes)
        self.assertIn("cylindrical_grinding", codes)
        self.assertLess(codes.index("straightening"), codes.index("cylindrical_grinding"))

    def test_short_shaft_does_not_add_straightening(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_TURNING,
                part_type="shaft",
                compatible_part_types=("shaft",),
                bounding_box={"length": 40, "width": 20, "height": 20},
            )
        )
        self.assertNotIn("straightening", set(operation_codes(route)))


if __name__ == "__main__":
    unittest.main()
