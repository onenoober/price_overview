"""L1 硬路由层测试：业务小类当家，几何不换族。"""

from __future__ import annotations

import unittest

from backend.app.domain_v2.route_engine.families import (
    LARGE_PLATE,
    MACHINING,
    SHEET_METAL,
    TURNING,
)
from backend.app.domain_v2.route_engine.parsed_part import parse_part_feature
from backend.app.domain_v2.route_engine.reviews import (
    CATEGORY_GEOMETRY_CONFLICT_REVIEW,
    LOW_CONFIDENCE_CATEGORY_REVIEW,
)
from backend.app.domain_v2.route_engine.router import route_family

from backend.tests.route_engine_fixtures import make_part_feature


def _decision(**kwargs):
    return route_family(parse_part_feature(make_part_feature(**kwargs)))


class RouterTests(unittest.TestCase):
    def test_sheet_metal_category_routes_to_sheet_metal(self) -> None:
        decision = _decision(
            category_name="钣金类",
            part_type="thin_plate",
            compatible_part_types=("thin_plate", "plate", "complex"),
        )
        self.assertEqual(decision.family, SHEET_METAL)
        self.assertFalse(decision.blocking)

    def test_round_part_routes_to_turning(self) -> None:
        decision = _decision(
            category_name="圆件类",
            part_type="shaft",
            compatible_part_types=("shaft", "shaft_candidate"),
        )
        self.assertEqual(decision.family, TURNING)

    def test_large_plate_and_prismatic(self) -> None:
        self.assertEqual(
            _decision(
                category_name="大板类",
                part_type="plate",
                compatible_part_types=("thin_plate", "plate", "long_bar"),
            ).family,
            LARGE_PLATE,
        )
        self.assertEqual(
            _decision(
                category_name="方件类",
                part_type="block",
                compatible_part_types=("block", "plate"),
            ).family,
            MACHINING,
        )

    def test_geometry_conflict_keeps_family_but_flags_review(self) -> None:
        # 小类=钣金，但几何 part_type=shaft（不在兼容集）→ 仍走钣金，挂复核。
        decision = _decision(
            category_name="钣金类",
            part_type="shaft",
            compatible_part_types=("thin_plate", "plate", "complex"),
        )
        self.assertEqual(decision.family, SHEET_METAL)
        self.assertIn(
            CATEGORY_GEOMETRY_CONFLICT_REVIEW,
            [review.code for review in decision.reviews],
        )
        self.assertFalse(decision.blocking)

    def test_low_confidence_category_falls_back_to_machining_and_blocks(self) -> None:
        decision = _decision(
            category_name="钣金类",
            part_type="thin_plate",
            compatible_part_types=("thin_plate",),
            confidence=0.3,
        )
        self.assertEqual(decision.family, MACHINING)
        self.assertTrue(decision.blocking)
        self.assertIn(
            LOW_CONFIDENCE_CATEGORY_REVIEW,
            [review.code for review in decision.reviews],
        )

    def test_missing_category_falls_back_to_machining_and_blocks(self) -> None:
        decision = _decision(
            category_name=None,
            part_type="block",
            compatible_part_types=(),
        )
        self.assertEqual(decision.family, MACHINING)
        self.assertTrue(decision.blocking)

    def test_unmapped_category_falls_back_to_machining(self) -> None:
        decision = _decision(
            category_name="型材类",
            part_type="complex",
            compatible_part_types=("complex",),
        )
        self.assertEqual(decision.family, MACHINING)
        self.assertTrue(decision.blocking)


if __name__ == "__main__":
    unittest.main()
