from __future__ import annotations

import unittest
from typing import Any

from backend.app.domain_v2.route_engine import plan_route_v2
from backend.tests.route_engine_fixtures import make_part_feature, operation_codes


CAT_TURNING = "\u5706\u4ef6\u7c7b"


def _plan(part_feature: dict[str, Any]) -> dict[str, Any]:
    return plan_route_v2(
        task_id="axis-profile",
        route_id="axis-profile-route",
        part_feature=part_feature,
        inherited_risks=[],
    )


def _operation(route: dict[str, Any], code: str) -> dict[str, Any] | None:
    return next(
        (
            operation
            for operation in route.get("operations", [])
            if operation.get("operation_code") == code
        ),
        None,
    )


class AxisRouteProfileTests(unittest.TestCase):
    def test_short_ring_does_not_default_to_cylindrical_grinding(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_TURNING,
                part_type="ring",
                compatible_part_types=("ring", "shaft"),
                bounding_box={"length": 8, "width": 80, "height": 80},
                surface_treatment={
                    "required": True,
                    "raw_text": "\u9540\u786c\u94ec",
                    "standard_code": "HARD_CHROME",
                    "source": {"source_type": "pdf", "file_id": "pdf-1"},
                },
            )
        )

        self.assertNotIn("cylindrical_grinding", set(operation_codes(route)))

    def test_ld_14_72_shaft_with_avoid_bending_text_adds_review_straightening(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_TURNING,
                part_type="shaft",
                compatible_part_types=("shaft",),
                bounding_box={"length": 368, "width": 25, "height": 25},
                technical_requirements=[
                    {
                        "raw_text": (
                            "\u88c5\u5939\u65f6\u5e94\u5408\u7406\u652f\u6491\uff0c"
                            "\u907f\u514d\u5f2f\u66f2"
                        )
                    }
                ],
            )
        )

        straightening = _operation(route, "straightening")
        self.assertIsNotNone(straightening)
        self.assertTrue(straightening.get("requires_review"))

    def test_ordinary_short_shaft_does_not_add_straightening(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_TURNING,
                part_type="shaft",
                compatible_part_types=("shaft",),
                bounding_box={"length": 120, "width": 12, "height": 12},
            )
        )

        self.assertNotIn("straightening", set(operation_codes(route)))

    def test_plain_smooth_shaft_does_not_add_shaft_milling(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_TURNING,
                part_type="complex_surface_candidate",
                compatible_part_types=("shaft", "shaft_candidate"),
                bounding_box={"length": 122, "width": 8, "height": 8},
                complexity={"complexity_score": 85, "face_count": 120, "edge_count": 220},
            )
        )

        self.assertNotIn("shaft_milling", set(operation_codes(route)))

    def test_large_deep_blind_bore_triggers_boring(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_TURNING,
                part_type="shaft",
                compatible_part_types=("shaft",),
                bounding_box={"length": 120, "width": 60, "height": 60},
                holes=[
                    {
                        "count": 2,
                        "hole_type": "blind",
                        "diameter": 37,
                        "depth": 95,
                        "raw_text": "2xD37 deep blind coaxial bore",
                    }
                ],
            )
        )

        self.assertIn("boring", set(operation_codes(route)))

    def test_tempering_without_stress_relief_text_does_not_add_stress_relief(self) -> None:
        route = _plan(
            make_part_feature(
                category_name=CAT_TURNING,
                part_type="shaft",
                compatible_part_types=("shaft",),
                material={"raw_text": "40Cr"},
                heat_treatment={
                    "required": True,
                    "raw_text": "\u8c03\u8d28 HRC28-32",
                    "source": {"source_type": "pdf", "file_id": "pdf-1"},
                },
                bounding_box={"length": 180, "width": 30, "height": 30},
            )
        )

        codes = set(operation_codes(route))
        self.assertIn("heat_treatment", codes)
        self.assertNotIn("stress_relief", codes)


if __name__ == "__main__":
    unittest.main()
