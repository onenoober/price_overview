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
    classify_part_type,
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

    def test_coarse_part_type_classifies_simple_block_as_block_subtype(self) -> None:
        candidates = classify_part_type(
            test_metrics(
                bbox=BoundingBox(length=40.0, width=15.0, height=15.0),
                face_counts={"PLANE": 12, "CYLINDER": 10},
                edge_counts={"LINE": 34, "CIRCLE": 20},
            ),
            {},
        )

        self.assertEqual(candidates[0]["part_type"], "block")
        self.assertEqual(candidates[0]["specific_type"], "simple_block")

    def test_coarse_part_type_classifies_hole_rich_prismatic_part_as_complex_block(self) -> None:
        candidates = classify_part_type(
            test_metrics(
                bbox=BoundingBox(length=180.0, width=70.0, height=16.0),
                face_counts={"PLANE": 17, "CYLINDER": 28},
                edge_counts={"LINE": 52, "CIRCLE": 56},
                cylindrical_area_ratio=0.1191,
                counterbore_count=7,
            ),
            {
                "hole_count": 7,
                "small_radius_count": 28,
                "slot_count": 0,
                "complexity_score": 100,
            },
        )

        self.assertEqual(candidates[0]["part_type"], "complex_block")
        self.assertGreaterEqual(candidates[0]["confidence"], 0.9)

    def test_coarse_part_type_classifies_long_bar(self) -> None:
        candidates = classify_part_type(
            test_metrics(
                bbox=BoundingBox(length=180.0, width=30.0, height=20.0),
                face_counts={"PLANE": 10, "CYLINDER": 2},
                edge_counts={"LINE": 28, "CIRCLE": 4},
            ),
            {},
        )

        self.assertEqual(candidates[0]["part_type"], "long_bar")

    def test_coarse_part_type_classifies_thin_plate(self) -> None:
        candidates = classify_part_type(
            test_metrics(
                bbox=BoundingBox(length=120.0, width=80.0, height=2.0),
                face_counts={"PLANE": 8, "CYLINDER": 2},
                edge_counts={"LINE": 20, "CIRCLE": 4},
            ),
            {},
        )

        self.assertEqual(candidates[0]["part_type"], "thin_plate")

    def test_coarse_part_type_classifies_assembly_candidate(self) -> None:
        candidates = classify_part_type(
            test_metrics(
                bbox=BoundingBox(length=120.0, width=80.0, height=30.0),
                face_counts={"PLANE": 18, "CYLINDER": 4},
                edge_counts={"LINE": 60, "CIRCLE": 8},
                solid_count=3,
            ),
            {},
        )

        self.assertEqual(candidates[0]["part_type"], "assembly_candidate")

def test_metrics(
    *,
    bbox: BoundingBox,
    face_counts: dict[str, int],
    edge_counts: dict[str, int],
    cylindrical_area_ratio: float = 0.0,
    counterbore_count: int = 0,
    solid_count: int = 1,
) -> ShapeMetrics:
    return ShapeMetrics(
        backend="test",
        bounding_box=bbox,
        volume=None,
        surface_area=None,
        face_count=sum(face_counts.values()),
        edge_count=sum(edge_counts.values()),
        face_type_counts=face_counts,
        edge_type_counts=edge_counts,
        cylindrical_area_ratio=cylindrical_area_ratio,
        circular_edge_ratio=0.0,
        cylindrical_faces=[],
        circular_edges=[],
        edge_records=[],
        profile_wires=[],
        counterbore_candidates=[
            {"count": counterbore_count}
        ]
        if counterbore_count
        else [],
        countersink_candidates=[],
        solid_count=solid_count,
        shell_count=0,
        compound_count=0,
    )


if __name__ == "__main__":
    unittest.main()
