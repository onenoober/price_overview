from __future__ import annotations

import unittest

from backend.app.part_feature_builder import build_part_feature, refine_pdf_part_category
from backend.app.parser_service import extract_pdf_fields, looks_like_non_part_name
from backend.app.schema_validation import validate_part_feature


class PdfPartTypeTests(unittest.TestCase):
    def test_extracts_part_type_from_title_block(self) -> None:
        fields = extract_pdf_fields(
            pdf_file={"file_id": "file_pdf_001"},
            blocks=[
                block(1, "零件类型", [980.0, 750.0, 1015.0, 760.0], 1),
                block(1, "方件类", [1020.0, 751.0, 1046.0, 761.0], 2),
            ],
            full_text="零件类型 方件类",
        )

        self.assertEqual(fields["part_type_raw"].value, "方件类")
        self.assertEqual(fields["part_type_raw"].extract_method, "text_layer_title_block")

    def test_pdf_part_type_fills_part_feature_when_step_is_missing(self) -> None:
        part_feature = build_part_feature(
            task=task(),
            pdf_result=pdf_result_with_part_type("方件类"),
            step_result=None,
            risks=[],
        )

        validate_part_feature(part_feature)
        geometry = part_feature["geometry"]
        self.assertIsNone(part_feature["geometry"]["part_type"])
        self.assertEqual(part_feature["geometry"]["part_type_confidence"], 0)
        self.assertIsNone(geometry["step_part_type"])
        self.assertEqual(geometry["step_part_type_confidence"], 0)
        self.assertEqual(geometry["pdf_part_type"], "方件类")
        self.assertEqual(geometry["pdf_part_type_raw"], "方件类")
        self.assertIsNone(geometry["final_quote_type"])
        self.assertEqual(geometry["final_quote_type_confidence"], 0)
        self.assertEqual(
            part_feature["geometry"]["pdf_part_category"]["category_name"],
            "方件类",
        )
        self.assertEqual(
            part_feature["geometry"]["pdf_part_category"]["compatible_part_types"],
            [
                "thin_plate",
                "plate",
                "block",
                "complex_block",
                "precision_block",
                "simple_block",
                "long_bar",
            ],
        )

    def test_pdf_square_category_is_compatible_with_step_plate(
        self,
    ) -> None:
        part_feature = build_part_feature(
            task=task(),
            pdf_result=pdf_result_with_part_type("方件类"),
            step_result=step_result_with_part_type("plate"),
            risks=[],
        )

        validate_part_feature(part_feature)
        geometry = part_feature["geometry"]
        self.assertEqual(geometry["part_type"], "plate")
        self.assertEqual(geometry["part_type_confidence"], 0.76)
        self.assertEqual(geometry["step_part_type"], "plate")
        self.assertEqual(geometry["step_part_type_confidence"], 0.76)
        self.assertEqual(geometry["pdf_part_type"], "方件类")
        self.assertEqual(geometry["final_quote_type"], "plate")
        self.assertEqual(geometry["final_quote_type_confidence"], 0.76)
        self.assertEqual(geometry["profile_summary"]["outer_profile_length"], 495.3137)
        self.assertEqual(geometry["profile_summary"]["outer_line_count"], 4)
        self.assertEqual(geometry["profile_summary"]["inner_arc_count"], 7)
        self.assertEqual(geometry["pdf_part_category"]["category_name"], "方件类")
        self.assertEqual(
            [
                (
                    candidate["part_type"],
                    candidate["source"]["source_type"],
                )
                for candidate in geometry["part_type_candidates"]
            ],
            [("plate", "step")],
        )

        risk = risk_by_code(part_feature["risks"], "PDF_STEP_PART_TYPE_CONFLICT")
        self.assertIsNone(risk)

    def test_new_step_coarse_type_can_be_saved_in_part_feature(self) -> None:
        part_feature = build_part_feature(
            task=task(),
            pdf_result=pdf_result_with_part_type("方件类"),
            step_result=step_result_with_part_type("complex_block"),
            risks=[],
        )

        validate_part_feature(part_feature)
        geometry = part_feature["geometry"]
        self.assertEqual(geometry["part_type"], "complex_block")
        self.assertEqual(geometry["step_part_type"], "complex_block")
        self.assertEqual(geometry["final_quote_type"], "complex_block")

    def test_pdf_round_category_conflicts_with_step_plate(self) -> None:
        part_feature = build_part_feature(
            task=task(),
            pdf_result=pdf_result_with_part_type("圆件类"),
            step_result=step_result_with_part_type("plate"),
            risks=[],
        )

        validate_part_feature(part_feature)
        geometry = part_feature["geometry"]
        self.assertEqual(geometry["part_type"], "plate")
        self.assertEqual(geometry["step_part_type"], "plate")
        self.assertEqual(geometry["pdf_part_type"], "圆件类")
        self.assertEqual(geometry["final_quote_type"], "plate")
        self.assertEqual(geometry["pdf_part_category"]["category_name"], "圆件类")

        risk = risk_by_code(part_feature["risks"], "PDF_STEP_PART_TYPE_CONFLICT")
        self.assertIsNotNone(risk)
        assert risk is not None
        self.assertTrue(risk["requires_review"])
        self.assertIn("PDF类型=圆件类", risk["message"])
        self.assertIn("STEP类型=plate", risk["message"])

    def test_blank_heat_treatment_does_not_capture_weight_label(self) -> None:
        fields = extract_pdf_fields(
            pdf_file={"file_id": "file_pdf_001"},
            blocks=[
                block(1, "热处理\n重量(Kg)\n", [980.6, 807.8, 1084.8, 825.3], 1),
                block(1, "1.47", [1023.1, 815.3, 1043.1, 825.3], 2),
            ],
            full_text="热处理\n重量(Kg)\n1.47",
        )

        self.assertIsNone(fields["heat_treatment_raw"].value)

    def test_surface_treatment_is_not_inferred_as_part_name(self) -> None:
        fields = extract_pdf_fields(
            pdf_file={"file_id": "file_pdf_001"},
            blocks=[
                block(1, "表面处理", [1038.1, 774.5, 1089.1, 784.5], 1),
                block(1, "喷塑小桔纹白色", [1098.4, 774.5, 1168.4, 784.5], 2),
            ],
            full_text="表面处理 喷塑小桔纹白色",
        )

        self.assertIsNone(fields["part_name"].value)
        self.assertEqual(fields["surface_treatment_raw"].value, "喷塑小桔纹白色")


def task() -> dict:
    return {
        "task_id": "task_001",
        "part_name": "Part",
        "part_no": "D001",
        "quantity": 1,
    }


def block(page: int, text: str, bbox: list[float], block_index: int) -> dict:
    return {
        "page": page,
        "text": text,
        "bbox": bbox,
        "block_index": block_index,
    }


def step_result_with_part_type(part_type: str) -> dict:
    return {
        "file_id": "file_step_001",
        "bounding_box": {"length": 80.0, "width": 40.0, "height": 12.0, "unit": "mm"},
        "volume": {"value": 1000.0, "unit": "mm3", "source": step_source("STEP_VOLUME")},
        "surface_area": {
            "value": 600.0,
            "unit": "mm2",
            "source": step_source("STEP_SURFACE_AREA"),
        },
        "profile_summary": {
            "outer_profile_length": 495.3137,
            "outer_line_length": 455.3137,
            "outer_arc_length": 40.0,
            "outer_line_count": 4,
            "outer_arc_count": 2,
            "inner_profile_length": 273.3185,
            "inner_line_length": 100.0,
            "inner_arc_length": 173.3185,
            "inner_line_count": 2,
            "inner_arc_count": 7,
            "top_profile_length": 768.6322,
            "inner_profile_count": 3,
            "circular_inner_profile_count": 2,
            "slot_candidate_count": 1,
            "total_edge_length": 1200.0,
            "line_edge_length": 700.0,
            "circular_edge_length": 500.0,
            "circular_edge_count": 12,
        },
        "net_weight": {
            "value": 0.03,
            "unit": "kg",
            "density": 0.00000785,
            "density_unit": "kg/mm3",
            "source": step_source("STEP_NET_WEIGHT"),
        },
        "part_type_candidates": [
            {
                "part_type": part_type,
                "confidence": 0.76,
                "reason": "Bounding box has plate-like proportions.",
            }
        ],
        "holes": [],
        "geometry_risks": [],
        "complexity": {
            "face_count": 12,
            "edge_count": 48,
            "hole_count": 2,
            "small_radius_count": 0,
            "slot_count": 0,
            "thin_wall_candidate": False,
            "complexity_score": 20,
        },
    }


def step_result_with_part_type_and_bbox(part_type: str, bbox: dict) -> dict:
    result = step_result_with_part_type(part_type)
    result["bounding_box"] = {**bbox, "unit": "mm"}
    result["part_type_candidates"][0]["part_type"] = part_type
    return result


def pdf_result_with_part_type(part_type_raw: str) -> dict:
    field_evidence = {
        "weight_raw": source("weight_raw"),
        "material_raw": source("material_raw"),
        "surface_treatment_raw": source("surface_treatment_raw"),
        "heat_treatment_raw": source("heat_treatment_raw"),
        "part_type_raw": source("part_type_raw"),
    }
    field_confidence = {
        "material_raw": 0.8,
        "surface_treatment_raw": 0,
        "heat_treatment_raw": 0,
        "part_type_raw": 0.78,
    }
    return {
        "file_id": "file_pdf_001",
        "part_name": "Part",
        "drawing_no": "D001",
        "revision": "A",
        "material_raw": "SKD11",
        "weight_value": 0.03,
        "weight_unit": "kg",
        "part_type_raw": part_type_raw,
        "surface_treatment_raw": None,
        "heat_treatment_raw": None,
        "field_evidence": field_evidence,
        "field_confidence": field_confidence,
        "risks": [],
        "tolerance_texts": [],
        "tolerance_evidence": [],
        "roughness_texts": [],
        "roughness_evidence": [],
        "technical_requirements": [],
        "technical_requirement_evidence": [],
    }


def source(rule_code: str) -> dict:
    return {
        "source_type": "pdf",
        "file_id": "file_pdf_001",
        "page": 1,
        "location": "title_block",
        "raw_text": None,
        "rule_code": rule_code,
    }


def step_source(rule_code: str) -> dict:
    return {
        "source_type": "step",
        "file_id": "file_step_001",
        "page": None,
        "location": None,
        "raw_text": None,
        "rule_code": rule_code,
    }


def risk_by_code(risks: list[dict], code: str) -> dict | None:
    return next((risk for risk in risks if risk.get("code") == code), None)


class NonPartNameFilterTests(unittest.TestCase):
    """PR4：标题栏串字段负例过滤。"""

    def test_designer_name_is_not_part_name(self) -> None:
        self.assertTrue(looks_like_non_part_name("郭江峰"))

    def test_heat_treatment_is_not_part_name(self) -> None:
        self.assertTrue(looks_like_non_part_name("调质HB220-280"))

    def test_pantone_color_is_not_part_name(self) -> None:
        self.assertTrue(looks_like_non_part_name("色号:PANTONE427C"))

    def test_h7_hole_callout_is_not_part_name(self) -> None:
        self.assertTrue(looks_like_non_part_name("6 H7 完全贯穿"))

    def test_thread_hole_callout_is_not_part_name(self) -> None:
        self.assertTrue(looks_like_non_part_name("M8 通螺纹"))
        self.assertTrue(looks_like_non_part_name("M6深10"))

    def test_thread_size_inside_real_part_name_is_allowed(self) -> None:
        self.assertFalse(looks_like_non_part_name("M8螺母座"))
        self.assertFalse(looks_like_non_part_name("M10垫片"))
        self.assertFalse(looks_like_non_part_name("销轴M6"))

    def test_projection_label_is_not_part_name(self) -> None:
        self.assertTrue(looks_like_non_part_name("投 影"))


class CategoryRefinementTests(unittest.TestCase):
    """PR4：大板/方件小类纠偏。"""

    def _category(self, name: str) -> dict:
        return {
            "category_name": name,
            "confidence": 0.78,
            "compatible_part_types": ["thin_plate", "plate"],
            "source": {"source_type": "pdf", "file_id": "pdf-1"},
            "raw_text": name,
        }

    def test_prismatic_named_plate_refined_to_prismatic(self) -> None:
        risks: list[dict] = []
        refined = refine_pdf_part_category(
            self._category("大板类"),
            {"part_name": "固定板3"},
            {"bounding_box": {"length": 300, "width": 160, "height": 20}},
            risks,
        )
        self.assertEqual(refined["category_name"], "方件类")
        self.assertIsNotNone(risk_by_code(risks, "CATEGORY_REFINED_PLATE_NAME_SIZE"))

    def test_long_base_plate_refined_to_large_plate(self) -> None:
        risks: list[dict] = []
        refined = refine_pdf_part_category(
            self._category("方件类"),
            {"part_name": "底板21"},
            {"bounding_box": {"length": 1200, "width": 180, "height": 20}},
            risks,
        )
        self.assertEqual(refined["category_name"], "大板类")
        self.assertIsNotNone(risk_by_code(risks, "CATEGORY_REFINED_LARGE_PLATE_SIZE"))

    def test_high_confidence_conflict_produces_review_not_override(self) -> None:
        risks: list[dict] = []
        category = self._category("方件类")
        category["confidence"] = 0.95
        refined = refine_pdf_part_category(
            category,
            {"part_name": "底板21"},
            {"bounding_box": {"length": 1200, "width": 180, "height": 20}},
            risks,
        )
        self.assertEqual(refined["category_name"], "方件类")
        self.assertIsNotNone(risk_by_code(risks, "CATEGORY_REFINEMENT_REVIEW"))

    def test_assembly_support_frame_refined_to_sheet_metal(self) -> None:
        risks: list[dict] = []
        refined = refine_pdf_part_category(
            self._category("方件类"),
            {
                "part_name": "输送支撑架",
                "material_raw": "Q235A",
                "surface_treatment_raw": "喷塑小桔纹白色",
            },
            step_result_with_part_type_and_bbox(
                "assembly_candidate", {"length": 250, "width": 647, "height": 200}
            ),
            risks,
        )
        self.assertEqual(refined["category_name"], "钣金类")
        self.assertIsNotNone(risk_by_code(risks, "ASSEMBLY_SHEET_METAL_CATEGORY_REVIEW"))

    def test_roller_geometry_refined_to_turning(self) -> None:
        risks: list[dict] = []
        refined = refine_pdf_part_category(
            self._category("方件类"),
            {"part_name": "滚筒", "material_raw": "45", "surface_treatment_raw": "镀化学镍"},
            step_result_with_part_type_and_bbox(
                "roller_candidate", {"length": 171, "width": 50, "height": 50}
            ),
            risks,
        )
        self.assertEqual(refined["category_name"], "圆件类")
        self.assertIsNotNone(risk_by_code(risks, "TURNING_GEOMETRY_CATEGORY_REVIEW"))

    def test_short_large_plate_boundary_refined_to_prismatic(self) -> None:
        risks: list[dict] = []
        refined = refine_pdf_part_category(
            self._category("大板类"),
            {"part_name": "底板2", "material_raw": "45", "surface_treatment_raw": "镀硬铬"},
            step_result_with_part_type_and_bbox(
                "unknown", {"length": 480, "width": 40, "height": 16}
            ),
            risks,
        )
        self.assertEqual(refined["category_name"], "方件类")
        self.assertIsNotNone(risk_by_code(risks, "LARGE_PLATE_BOUNDARY_REVIEW"))


if __name__ == "__main__":
    unittest.main()
