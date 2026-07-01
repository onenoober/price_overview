from __future__ import annotations

import unittest

from backend.app.part_feature_builder import build_part_feature
from backend.app.parser_service import collect_hole_annotation_matches
from backend.app.schema_validation import validate_part_feature


class PdfHoleAnnotationTests(unittest.TestCase):
    def test_extracts_counterbore_hole_annotations_from_pdf_text_blocks(self) -> None:
        annotations = collect_hole_annotation_matches(
            pdf_file={"file_id": "file_pdf_001"},
            blocks=[
                block(1, "4 x Φ9 完全贯穿", [760.0, 220.0, 835.0, 232.0], 1, 10),
                block(1, "⌴ Φ15 深9", [760.0, 234.0, 835.0, 246.0], 2, 10),
                block(1, "3 x Φ9 深19.75", [760.0, 360.0, 835.0, 372.0], 3, 11),
                block(1, "⌴ Φ15 深9", [760.0, 374.0, 835.0, 386.0], 4, 11),
            ],
        )

        self.assertEqual(len(annotations), 2)
        first, second = annotations
        self.assertEqual(first["hole_type"], "counterbore")
        self.assertEqual(first["count"], 4)
        self.assertEqual(first["diameter"], 9.0)
        self.assertTrue(first["through"])
        self.assertEqual(first["counterbore_diameter"], 15.0)
        self.assertEqual(first["counterbore_depth"], 9.0)
        self.assertEqual(second["count"], 3)
        self.assertEqual(second["depth"], 19.75)

    def test_reconstructs_split_hole_callouts_from_text_blocks(self) -> None:
        annotations = collect_hole_annotation_matches(
            pdf_file={"file_id": "file_pdf_001"},
            blocks=[
                block(1, "4 x", [876.86, 260.18, 896.65, 270.08], 18, 8),
                block(1, "9 完全贯穿", [906.05, 260.19, 960.49, 270.08], 19, 8),
                block(1, "15", [912.49, 270.08, 932.28, 279.98], 20, 9),
                block(1, "9", [941.19, 270.08, 951.09, 279.98], 21, 9),
                block(1, "3 x", [876.14, 414.33, 895.93, 424.23], 22, 10),
                block(1, "9", [905.33, 414.33, 920.18, 424.23], 23, 10),
                block(1, "19.75", [929.09, 414.33, 958.78, 424.23], 24, 10),
                block(1, "15", [901.38, 424.23, 921.17, 434.13], 25, 10),
                block(1, "9反面", [930.08, 424.23, 959.77, 434.13], 26, 10),
            ],
        )

        self.assertEqual(len(annotations), 2)
        first, second = annotations
        self.assertEqual(first["hole_type"], "counterbore")
        self.assertEqual(first["count"], 4)
        self.assertEqual(first["diameter"], 9.0)
        self.assertTrue(first["through"])
        self.assertEqual(first["counterbore_diameter"], 15.0)
        self.assertEqual(first["counterbore_depth"], 9.0)
        self.assertEqual(second["count"], 3)
        self.assertEqual(second["diameter"], 9.0)
        self.assertEqual(second["depth"], 19.75)
        self.assertEqual(second["counterbore_diameter"], 15.0)
        self.assertEqual(second["counterbore_depth"], 9.0)

    def test_angle_dimension_does_not_become_count_diameter_hole(self) -> None:
        annotations = collect_hole_annotation_matches(
            pdf_file={"file_id": "file_pdf_001"},
            blocks=[
                block(1, "8.96 X 90°", [760.0, 220.0, 835.0, 232.0], 1, 10),
                block(1, "8.96", [760.0, 234.0, 835.0, 246.0], 2, 10),
                block(1, "0.5", [760.0, 248.0, 835.0, 260.0], 3, 10),
            ],
        )

        self.assertEqual(annotations, [])

    def test_linear_pitch_chain_does_not_become_hole(self) -> None:
        annotations = collect_hole_annotation_matches(
            pdf_file={"file_id": "file_pdf_001"},
            blocks=[
                block(1, "180*7=1260", [584.63, 172.92, 634.12, 182.81], 1, 10),
            ],
        )

        self.assertEqual(annotations, [])

    def test_thread_callout_does_not_infer_counterbore_from_tail_numbers(self) -> None:
        annotations = collect_hole_annotation_matches(
            pdf_file={"file_id": "file_pdf_001"},
            blocks=[
                block(1, "2 x M6 - 6H; 12; 171; 5; 15两端", [760.0, 220.0, 900.0, 232.0], 1, 10),
            ],
        )

        self.assertEqual(len(annotations), 1)
        annotation = annotations[0]
        self.assertEqual(annotation["hole_type"], "thread_candidate")
        self.assertNotIn("counterbore_diameter", annotation)
        self.assertNotIn("counterbore_depth", annotation)

    def test_pdf_annotations_split_matching_step_hole_group(self) -> None:
        part_feature = build_part_feature(
            task=task(),
            pdf_result=pdf_result_with_hole_annotations(),
            step_result=step_result_with_seven_holes(),
            risks=[],
        )

        validate_part_feature(part_feature)
        holes = part_feature["features"]["holes"]
        self.assertEqual([hole["count"] for hole in holes], [4, 3])
        self.assertEqual([hole["hole_type"] for hole in holes], ["counterbore", "counterbore"])
        self.assertTrue(holes[0]["through"])
        self.assertEqual(holes[0]["counterbore_diameter"], 15.0)
        self.assertFalse(holes[1]["through"])
        self.assertEqual(holes[1]["depth"], 19.75)
        self.assertGreaterEqual(len(holes[0]["evidence"]), 2)
        self.assertIn(
            "PDF_STEP_HOLE_DEPTH_CONFLICT",
            {risk["code"] for risk in part_feature["risks"]},
        )
        self.assertNotIn(
            "PDF_STEP_HOLE_DIMENSION_MISMATCH",
            {risk["code"] for risk in part_feature["risks"]},
        )

    def test_step_bbox_fallback_depth_does_not_trigger_dimension_mismatch(
        self,
    ) -> None:
        part_feature = build_part_feature(
            task=task(),
            pdf_result=pdf_result_with_hole_annotations(
                [
                    {
                        "hole_type": "counterbore",
                        "diameter": 9.0,
                        "depth": 19.75,
                        "count": 3,
                        "through": False,
                        "counterbore_diameter": 15.0,
                        "counterbore_depth": 9.0,
                        "confidence": 0.9,
                        "raw_text": "3 x Φ9 深19.75; ⌴ Φ15 深9",
                        "evidence": [source("pdf", "PDF_TEXT_HOLE_ANNOTATION")],
                    }
                ]
            ),
            step_result=step_result_with_hole(
                {
                    "hole_type": "counterbore",
                    "diameter": 9.0,
                    "depth": 16.0,
                    "count": 3,
                    "counterbore_diameter": 15.0,
                    "counterbore_depth": 9.0,
                    "confidence": 0.72,
                    "evidence": [source("step", "STEP_HOLE_CANDIDATE")],
                }
            ),
            risks=[],
        )

        validate_part_feature(part_feature)
        risk_codes = {risk["code"] for risk in part_feature["risks"]}
        self.assertIn("PDF_STEP_HOLE_DEPTH_CONFLICT", risk_codes)
        self.assertNotIn("PDF_STEP_HOLE_DIMENSION_MISMATCH", risk_codes)

    def test_implausible_step_counterbore_is_downgraded_during_fusion(self) -> None:
        part_feature = build_part_feature(
            task=task(),
            pdf_result=pdf_result_with_hole_annotations(
                [
                    {
                        "hole_type": "thread_candidate",
                        "diameter": 6.0,
                        "depth": 6.0,
                        "count": 2,
                        "through": False,
                        "confidence": 0.82,
                        "raw_text": "2 x M6 - 6H; 12; 171; 5; 15两端",
                        "evidence": [source("pdf", "PDF_TEXT_HOLE_ANNOTATION")],
                    }
                ]
            ),
            step_result={
                **step_result_with_hole(
                    {
                        "hole_type": "counterbore",
                        "diameter": 5.0,
                        "depth": 12.0,
                        "count": 1,
                        "counterbore_diameter": 12.0,
                        "counterbore_depth": 274.0,
                        "confidence": 0.72,
                        "evidence": [source("step", "STEP_HOLE_CANDIDATE")],
                    }
                ),
                "bounding_box": {"length": 12.0, "width": 12.0, "height": 275.0, "unit": "mm"},
                "part_type_candidates": [{"part_type": "shaft_candidate", "confidence": 0.9}],
            },
            risks=[],
        )

        validate_part_feature(part_feature)
        holes = part_feature["features"]["holes"]
        self.assertEqual(holes[1]["hole_type"], "blind")
        self.assertNotIn("counterbore_diameter", holes[1])
        self.assertNotIn("counterbore_depth", holes[1])

    def test_pdf_step_hole_dimension_mismatch_adds_review_risk(self) -> None:
        part_feature = build_part_feature(
            task=task(),
            pdf_result=pdf_result_with_hole_annotations(
                [
                    {
                        "hole_type": "through",
                        "diameter": 9.0,
                        "depth": None,
                        "count": 1,
                        "through": True,
                        "confidence": 0.9,
                        "raw_text": "1 x Φ9 完全贯穿",
                        "evidence": [source("pdf", "PDF_TEXT_HOLE_ANNOTATION")],
                    }
                ]
            ),
            step_result=step_result_with_hole(
                {
                    "hole_type": "through",
                    "diameter": 10.0,
                    "depth": 16.0,
                    "count": 1,
                    "confidence": 0.62,
                    "evidence": [source("step", "STEP_HOLE_CANDIDATE")],
                }
            ),
            risks=[],
        )

        validate_part_feature(part_feature)
        risk_codes = {risk["code"] for risk in part_feature["risks"]}
        self.assertIn("PDF_STEP_HOLE_DIMENSION_MISMATCH", risk_codes)
        self.assertIn("PDF_STEP_HOLE_ANNOTATION_MISMATCH", risk_codes)
        dimension_risk = risk_by_code(
            part_feature["risks"],
            "PDF_STEP_HOLE_DIMENSION_MISMATCH",
        )
        self.assertIsNotNone(dimension_risk)
        assert dimension_risk is not None
        self.assertTrue(dimension_risk["requires_review"])
        self.assertIn("直径 PDF=9", dimension_risk["message"])
        self.assertIn("STEP=10", dimension_risk["message"])


def block(
    page: int,
    text: str,
    bbox: list[float],
    block_index: int,
    parent_block_index: int,
) -> dict:
    return {
        "page": page,
        "text": text,
        "bbox": bbox,
        "block_index": block_index,
        "parent_block_index": parent_block_index,
    }


class CompositePrecisionSplitTests(unittest.TestCase):
    """大板P2：复合孔标注(螺纹+H7)拆分为独立 precision_candidate。"""

    def test_thread_plus_h7_splits_precision_candidate(self) -> None:
        annotations = collect_hole_annotation_matches(
            pdf_file={"file_id": "file_pdf_h7"},
            blocks=[
                block(1, "M6 - 6H 完全贯穿", [400.0, 200.0, 470.0, 212.0], 1, 20),
                block(1, "5 H7 完全贯穿", [400.0, 214.0, 470.0, 226.0], 2, 20),
            ],
        )
        types = [a.get("hole_type") for a in annotations]
        self.assertIn("thread_candidate", types)
        self.assertIn("precision_candidate", types)
        precision = next(a for a in annotations if a.get("hole_type") == "precision_candidate")
        self.assertEqual(precision.get("count"), 5)

    def test_plain_tolerance_not_split_into_precision(self) -> None:
        annotations = collect_hole_annotation_matches(
            pdf_file={"file_id": "file_pdf_tol"},
            blocks=[
                block(1, "M6 - 6H 完全贯穿", [400.0, 200.0, 470.0, 212.0], 1, 21),
                block(1, "4 x Φ9 ±0.1", [400.0, 214.0, 470.0, 226.0], 2, 21),
            ],
        )
        self.assertNotIn(
            "precision_candidate", [a.get("hole_type") for a in annotations]
        )


def task() -> dict:
    return {
        "task_id": "task_001",
        "part_name": "Part",
        "part_no": "D001",
        "quantity": 1,
    }


def pdf_result_with_hole_annotations(
    hole_annotations: list[dict] | None = None,
) -> dict:
    return {
        "file_id": "file_pdf_001",
        "part_name": "Part",
        "drawing_no": "D001",
        "revision": "A",
        "material_raw": "45",
        "weight_raw": "1.47 kg",
        "weight_value": 1.47,
        "weight_unit": "kg",
        "part_type_raw": None,
        "surface_treatment_raw": None,
        "heat_treatment_raw": None,
        "field_evidence": {
            "material_raw": source("pdf", "PDF_FIELD:material_raw"),
            "weight_raw": source("pdf", "PDF_FIELD:weight_raw"),
            "surface_treatment_raw": source("pdf", "PDF_FIELD:surface_treatment_raw"),
            "heat_treatment_raw": source("pdf", "PDF_FIELD:heat_treatment_raw"),
            "part_type_raw": source("pdf", "PDF_FIELD:part_type_raw"),
        },
        "field_confidence": {
            "material_raw": 0.8,
            "weight_raw": 0.8,
            "surface_treatment_raw": 0,
            "heat_treatment_raw": 0,
            "part_type_raw": 0,
        },
        "risks": [],
        "tolerance_texts": [],
        "tolerance_evidence": [],
        "roughness_texts": [],
        "roughness_evidence": [],
        "technical_requirements": [],
        "technical_requirement_evidence": [],
        "hole_annotations": hole_annotations if hole_annotations is not None else [
            {
                "hole_type": "counterbore",
                "diameter": 9.0,
                "depth": None,
                "count": 4,
                "through": True,
                "counterbore_diameter": 15.0,
                "counterbore_depth": 9.0,
                "confidence": 0.9,
                "raw_text": "4 x Φ9 完全贯穿; ⌴ Φ15 深9",
                "evidence": [source("pdf", "PDF_TEXT_HOLE_ANNOTATION")],
            },
            {
                "hole_type": "counterbore",
                "diameter": 9.0,
                "depth": 19.75,
                "count": 3,
                "through": False,
                "counterbore_diameter": 15.0,
                "counterbore_depth": 9.0,
                "confidence": 0.9,
                "raw_text": "3 x Φ9 深19.75; ⌴ Φ15 深9",
                "evidence": [source("pdf", "PDF_TEXT_HOLE_ANNOTATION")],
            },
        ],
    }


def step_result_with_seven_holes() -> dict:
    return step_result_with_hole(
        {
            "hole_type": "through",
            "diameter": 9.0,
            "depth": 16.0,
            "count": 7,
            "confidence": 0.62,
            "evidence": [source("step", "STEP_HOLE_CANDIDATE")],
        }
    )


def step_result_with_hole(hole: dict) -> dict:
    return {
        "file_id": "file_step_001",
        "bounding_box": {"length": 180.0, "width": 70.0, "height": 16.0, "unit": "mm"},
        "volume": {"value": 1000.0, "unit": "mm3", "source": source("step", "STEP_VOLUME")},
        "surface_area": {
            "value": 600.0,
            "unit": "mm2",
            "source": source("step", "STEP_SURFACE_AREA"),
        },
        "net_weight": {
            "value": 1.0,
            "unit": "kg",
            "density": 0.00000785,
            "density_unit": "kg/mm3",
            "source": source("step", "STEP_NET_WEIGHT"),
        },
        "part_type_candidates": [{"part_type": "plate", "confidence": 0.76}],
        "holes": [hole],
        "geometry_risks": [],
        "complexity": {
            "face_count": 12,
            "edge_count": 48,
            "small_radius_count": 0,
            "slot_count": 0,
            "thin_wall_candidate": False,
            "complexity_score": 20,
        },
    }


def risk_by_code(risks: list[dict], code: str) -> dict | None:
    return next((risk for risk in risks if risk.get("code") == code), None)


def source(source_type: str, rule_code: str) -> dict:
    return {
        "source_type": source_type,
        "file_id": f"file_{source_type}_001",
        "page": 1 if source_type == "pdf" else None,
        "location": "annotation" if source_type == "pdf" else None,
        "raw_text": None,
        "rule_code": rule_code,
    }


if __name__ == "__main__":
    unittest.main()
