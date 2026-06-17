from __future__ import annotations

import unittest

from backend.app.part_feature_builder import build_part_feature
from backend.app.parser_service import extract_pdf_fields
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
            ["thin_plate", "plate", "block"],
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

    def test_ai_step_part_type_becomes_primary_type(self) -> None:
        part_feature = build_part_feature(
            task=task(),
            pdf_result=pdf_result_with_part_type("方件类"),
            step_result=step_result_with_part_type("plate"),
            risks=[],
            step_part_type_classification=ai_step_part_type("block"),
        )

        validate_part_feature(part_feature)
        geometry = part_feature["geometry"]
        self.assertEqual(geometry["part_type"], "block")
        self.assertEqual(geometry["part_type_confidence"], 0.91)
        self.assertEqual(geometry["step_part_type"], "block")
        self.assertEqual(geometry["step_part_type_specific"], "焊接钢结构支架")
        self.assertEqual(geometry["final_quote_type"], "block")
        self.assertEqual(
            geometry["part_type_candidates"][0]["source"]["rule_code"],
            "STEP_AI_PART_TYPE_CLASSIFICATION",
        )
        self.assertEqual(
            geometry["part_type_candidates"][0]["source"]["source_type"],
            "step",
        )

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
            "small_radius_count": 0,
            "slot_count": 0,
            "thin_wall_candidate": False,
            "complexity_score": 20,
        },
    }


def ai_step_part_type(part_type: str) -> dict:
    return {
        "task_id": "task_001",
        "input_type": "step_geometry",
        "output_type": "part_type_classification",
        "content": {
            "part_type": part_type,
            "specific_type": "焊接钢结构支架",
            "reason": "AI 根据 STEP 几何摘要判断。",
            "requires_review": False,
            "confidence": 0.91,
        },
        "confidence": 0.91,
        "evidence": [],
        "model_name": "fake-ai",
        "prompt_version": "test-v1",
        "created_at": "2026-06-15T10:00:00+08:00",
    }


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


if __name__ == "__main__":
    unittest.main()
