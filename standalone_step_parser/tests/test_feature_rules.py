from __future__ import annotations

from pathlib import Path
import sys
import unittest


PARSER_ROOT = Path(__file__).resolve().parents[1]
if str(PARSER_ROOT) not in sys.path:
    sys.path.insert(0, str(PARSER_ROOT))

from step_parser.models import BoundingBox, HoleCandidate, SourceRef
from step_parser.parser import (
    build_hole_candidates,
    countersink_included_angle,
    is_deep_hole,
    is_long_cantilever_candidate,
    is_narrow_slot,
    ShapeMetrics,
)


class FeatureRuleTests(unittest.TestCase):
    def test_counterbore_candidates_replace_matching_simple_holes(self) -> None:
        source = SourceRef(file_id="file_step_001")
        holes = build_hole_candidates(
            hole_instances=[
                {"diameter": 9.0, "center_x": 0.0, "center_y": 0.0},
                {"diameter": 9.0, "center_x": 50.0, "center_y": 0.0},
            ],
            counterbore_candidates=[
                {
                    "center_x": 0.0,
                    "center_y": 0.0,
                    "base_diameter": 9.0,
                    "counterbore_diameter": 15.0,
                    "counterbore_depth": 5.0,
                }
            ],
            countersink_candidates=[],
            bbox=BoundingBox(length=80.0, width=40.0, height=12.0),
            source=source,
        )

        self.assertEqual([hole.hole_type for hole in holes], ["counterbore", "through"])
        self.assertEqual(holes[0].counterbore_diameter, 15.0)
        self.assertEqual(holes[0].depth, 12.0)
        self.assertEqual(holes[1].count, 1)

    def test_countersink_angle_is_calculated_from_diameter_delta_and_depth(self) -> None:
        angle = countersink_included_angle(6.0, 12.0, 3.0)

        self.assertAlmostEqual(angle, 90.0)

    def test_risk_helpers_detect_deep_holes_narrow_slots_and_long_thin_parts(self) -> None:
        self.assertTrue(
            is_deep_hole(
                HoleCandidate(
                    hole_type="through",
                    diameter=3.0,
                    depth=20.0,
                    count=1,
                    confidence=0.8,
                    evidence=[SourceRef(file_id="file_step_001")],
                )
            )
        )
        self.assertTrue(
            is_narrow_slot(
                {
                    "avg_width": 2.5,
                    "avg_length": 30.0,
                }
            )
        )
        self.assertTrue(
            is_long_cantilever_candidate(
                ShapeMetrics(
                    backend="test",
                    bounding_box=BoundingBox(length=180.0, width=20.0, height=4.0),
                    volume=None,
                    surface_area=None,
                    face_count=0,
                    edge_count=0,
                    face_type_counts={},
                    edge_type_counts={},
                    cylindrical_area_ratio=0,
                    circular_edge_ratio=0,
                    cylindrical_faces=[],
                    circular_edges=[],
                    edge_records=[],
                    profile_wires=[],
                    counterbore_candidates=[],
                    countersink_candidates=[],
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
