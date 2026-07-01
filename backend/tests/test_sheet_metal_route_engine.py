from __future__ import annotations

import unittest

from backend.app.domain_v2.route_engine import plan_route_v2
from backend.tests.route_engine_fixtures import make_part_feature, operation_codes


CAT_SHEET_METAL = "\u94a3\u91d1\u7c7b"
CAT_MACHINING = "\u65b9\u4ef6\u7c7b"
CAT_TURNING = "\u5706\u4ef6\u7c7b"


def _plan(part_feature):
    return plan_route_v2(
        task_id="t",
        route_id="r",
        part_feature=part_feature,
        inherited_risks=[],
    )


class SheetMetalRouteEngineTests(unittest.TestCase):
    def test_sheet_metal_counterbore_survives_shallow_sheet_suppression(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_SHEET_METAL,
                part_type="thin_plate",
                compatible_part_types=("thin_plate", "plate", "complex_block"),
                holes=[
                    {
                        "count": 8,
                        "hole_type": "counterbore",
                        "diameter": 4.5,
                        "through": True,
                        "counterbore_diameter": 8.96,
                        "counterbore_depth": 0.5,
                        "evidence": [
                            {
                                "source_type": "pdf",
                                "raw_text": "8 x \u03c64.5 \u901a\u5b54; \u03c68.96; 0.5",
                                "rule_code": "PDF_TEXT_HOLE_ANNOTATION",
                            }
                        ],
                    }
                ],
                bounding_box={"length": 650, "width": 275, "height": 3, "thickness": 3},
            )
        )

        codes = set(operation_codes(route))
        self.assertIn("counterbore", codes)
        self.assertNotIn("cnc_rough_milling", codes)
        self.assertNotIn("edm", codes)

    def test_sheet_metal_countersink_is_added_for_explicit_90_degree_callout(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_SHEET_METAL,
                part_type="thin_plate",
                compatible_part_types=("thin_plate", "plate", "complex_block"),
                holes=[
                    {
                        "count": 12,
                        "hole_type": "countersink",
                        "diameter": 4.5,
                        "countersink_diameter": 9.0,
                        "countersink_depth": 2.2,
                        "countersink_angle": 90.0,
                        "evidence": [
                            {
                                "source_type": "pdf",
                                "raw_text": "12 x \u03c64.5; \u03c69.0 X 90\u00b0",
                                "rule_code": "PDF_TEXT_HOLE_ANNOTATION",
                            }
                        ],
                    }
                ],
                bounding_box={"length": 324, "width": 235, "height": 3, "thickness": 3},
            )
        )

        self.assertIn("countersink", set(operation_codes(route)))

    def test_sheet_metal_obround_dimensions_do_not_suppress_explicit_counterbore(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_SHEET_METAL,
                part_type="thin_plate",
                compatible_part_types=("thin_plate", "plate"),
                holes=[
                    {
                        "count": 5,
                        "hole_type": "through",
                        "diameter": 8.5,
                        "raw_text": "5 x 8.5 X 30 \u957f\u5706\u5b54",
                    },
                    {
                        "count": 6,
                        "hole_type": "counterbore",
                        "diameter": 4.5,
                        "through": True,
                        "counterbore_diameter": 8.96,
                        "counterbore_depth": 0.5,
                        "evidence": [
                            {
                                "source_type": "pdf",
                                "raw_text": "6 x \u03c64.5 \u901a\u5b54; \u03c68.96; 0.5",
                                "rule_code": "PDF_TEXT_HOLE_ANNOTATION",
                            }
                        ],
                    },
                ],
            )
        )

        self.assertIn("counterbore", set(operation_codes(route)))

    def test_sheet_metal_small_formed_part_gets_bending_from_name_and_envelope(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_SHEET_METAL,
                part_type="unknown",
                compatible_part_types=("unknown", "thin_plate", "formed_sheet"),
                part_name="\u5206\u6d41\u5230\u4f4d\u68c0\u6d4b\u652f\u67b6",
                bounding_box={"length": 122, "width": 15, "height": 30, "thickness": 3},
                holes=[{"count": 2, "hole_type": "counterbore", "diameter": 4.5}],
            )
        )

        self.assertIn("bending", set(operation_codes(route)))

    def test_sheet_metal_weldment_adds_welding_support_chain(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_SHEET_METAL,
                part_type="assembly_candidate",
                compatible_part_types=("assembly_candidate", "formed_sheet"),
                part_name="\u8f93\u9001\u652f\u6491\u67b6",
                surface_treatment={
                    "required": True,
                    "raw_text": "\u55b7\u5851\u5c0f\u6854\u7eb9\u767d\u8272",
                    "standard_code": "POWDER_COATING_TEXTURE",
                    "source": {"source_type": "pdf", "file_id": "pdf-1"},
                },
                technical_requirements=[
                    {"raw_text": "\u710a\u63a5\u524d\u5fc5\u987b\u5c06\u7f3a\u9677\u5f7b\u5e95\u6e05\u9664"},
                    {"raw_text": "\u710a\u63a5\u65f6\u710a\u7f1d\u8981\u6c42\u5e73\u6ed1\uff0c\u4e0d\u5f97\u6709\u6c14\u5b54\u5939\u6e23"},
                ],
                holes=[{"count": 4, "hole_type": "thread_candidate", "diameter": 16.0}],
            )
        )

        codes = operation_codes(route)
        for code in (
            "welding_prepare",
            "fit_up",
            "sheet_metal_welding",
            "weld_grinding",
            "weld_inspection",
        ):
            self.assertIn(code, codes)
        self.assertLess(codes.index("welding_prepare"), codes.index("sheet_metal_welding"))
        self.assertLess(codes.index("sheet_metal_welding"), codes.index("weld_grinding"))

    def test_non_sheet_metal_routes_do_not_receive_sheet_metal_welding_chain(self) -> None:
        for category, part_type, compatible in (
            (CAT_MACHINING, "block", ("block",)),
            (CAT_TURNING, "shaft", ("shaft",)),
        ):
            route = _plan(
                make_part_feature(
                    category_name=category,
                    part_type=part_type,
                    compatible_part_types=compatible,
                    technical_requirements=[
                        {"raw_text": "\u710a\u63a5\u524d\u5fc5\u987b\u5c06\u7f3a\u9677\u5f7b\u5e95\u6e05\u9664"}
                    ],
                )
            )
            codes = set(operation_codes(route))
            self.assertNotIn("welding_prepare", codes)
            self.assertNotIn("fit_up", codes)
            self.assertNotIn("sheet_metal_welding", codes)
            self.assertNotIn("weld_grinding", codes)


if __name__ == "__main__":
    unittest.main()
