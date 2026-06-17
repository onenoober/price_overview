from __future__ import annotations

import unittest

from backend.app.part_feature_builder import build_part_feature


class WeightMismatchRiskTests(unittest.TestCase):
    def test_adds_review_risk_when_pdf_and_step_weight_differ_over_15_percent(
        self,
    ) -> None:
        part_feature = build_part_feature(
            task=task(),
            pdf_result=pdf_result(weight_value=1.3),
            step_result=step_result(net_weight=1.0),
            risks=[],
        )

        risk = risk_by_code(part_feature["risks"], "WEIGHT_MISMATCH")

        self.assertIsNotNone(risk)
        assert risk is not None
        self.assertTrue(risk["requires_review"])
        self.assertEqual(risk["level"], "warning")
        self.assertEqual(len(risk["evidence"]), 2)

    def test_does_not_add_risk_when_weight_difference_is_within_15_percent(
        self,
    ) -> None:
        part_feature = build_part_feature(
            task=task(),
            pdf_result=pdf_result(weight_value=1.15),
            step_result=step_result(net_weight=1.0),
            risks=[],
        )

        self.assertIsNone(risk_by_code(part_feature["risks"], "WEIGHT_MISMATCH"))

    def test_material_normalization_populates_material_name_and_density(self) -> None:
        part_feature = build_part_feature(
            task=task(),
            pdf_result=pdf_result(weight_value=1.0, material_raw="Q235A"),
            step_result=None,
            risks=[],
            material_normalization=material_normalization_output(),
        )

        material = part_feature["material"]
        self.assertEqual(material["raw_text"], "Q235A")
        self.assertEqual(material["standard_code"], "Q235A")
        self.assertEqual(material["standard_name"], "Q235A 碳素结构钢")
        self.assertEqual(material["density"], 7.85)
        self.assertEqual(material["density_unit"], "g/cm3")
        self.assertEqual(material["confidence"], 0.9)
        self.assertEqual(material["source"]["source_type"], "ai")
        self.assertEqual(
            material["source"]["rule_code"],
            "MATERIAL_DENSITY_AI_NORMALIZATION",
        )

    def test_material_normalization_converts_english_name_to_chinese(self) -> None:
        output = material_normalization_output()
        output["content"] = {
            **output["content"],
            "standard_name": "Q235A carbon structural steel",
        }

        part_feature = build_part_feature(
            task=task(),
            pdf_result=pdf_result(weight_value=1.0, material_raw="Q235A"),
            step_result=None,
            risks=[],
            material_normalization=output,
        )

        self.assertEqual(
            part_feature["material"]["standard_name"],
            "Q235A 碳素结构钢",
        )
    def test_material_density_stays_missing_when_ai_unavailable(self) -> None:
        output = material_normalization_output()
        output["content"] = {
            "raw_text": "Q235A",
            "available": False,
            "error_message": "AI request failed with status 429",
            "standard_code": None,
            "standard_name": None,
            "density": None,
            "density_unit": None,
            "match_reason": "AI provider unavailable.",
        }

        part_feature = build_part_feature(
            task=task(),
            pdf_result=pdf_result(weight_value=1.0, material_raw="Q235A"),
            step_result=None,
            risks=[],
            material_normalization=output,
        )

        material = part_feature["material"]
        self.assertEqual(material["raw_text"], "Q235A")
        self.assertIsNone(material["standard_code"])
        self.assertIsNone(material["density"])
        self.assertIsNone(material["density_unit"])
        self.assertEqual(material["source"]["source_type"], "pdf")

    def test_step_net_weight_stays_missing_when_parser_weight_missing(self) -> None:
        output = material_normalization_output()
        output["content"] = {
            "raw_text": "Q235A",
            "available": False,
            "standard_code": None,
            "standard_name": None,
            "density": None,
            "density_unit": None,
        }
        step = step_result(net_weight=None)
        step["volume"] = {"value": 6432.6927, "unit": "mm3", "source": source("step", "STEP_VOLUME")}
        step["net_weight"] = {
            "value": None,
            "unit": None,
            "density": None,
            "density_unit": None,
            "source": source("step", "STEP_NET_WEIGHT"),
        }

        part_feature = build_part_feature(
            task=task(),
            pdf_result=pdf_result(weight_value=0.05, material_raw="Q235A"),
            step_result=step,
            risks=[],
            material_normalization=output,
        )

        net_weight = part_feature["geometry"]["step_net_weight"]
        self.assertIsNone(net_weight["value"])
        self.assertIsNone(net_weight["unit"])
        self.assertEqual(
            net_weight["source"]["rule_code"],
            "STEP_NET_WEIGHT",
        )


def task() -> dict:
    return {
        "task_id": "task_001",
        "part_name": "Part",
        "part_no": "D001",
        "quantity": 1,
    }


def pdf_result(*, weight_value: float, material_raw: str = "45") -> dict:
    field_evidence = {
        "weight_raw": source("pdf", "PDF_TEXT_TITLE_BLOCK:weight_raw"),
        "material_raw": source("pdf", "PDF_TEXT_TITLE_BLOCK:material_raw"),
        "surface_treatment_raw": source(
            "pdf",
            "PDF_FIELD_NOT_FOUND:surface_treatment_raw",
        ),
        "heat_treatment_raw": source("pdf", "PDF_FIELD_NOT_FOUND:heat_treatment_raw"),
        "part_type_raw": source("pdf", "PDF_FIELD_NOT_FOUND:part_type_raw"),
    }
    return {
        "file_id": "file_pdf_001",
        "part_name": "Part",
        "drawing_no": "D001",
        "revision": "A",
        "material_raw": material_raw,
        "weight_raw": f"{weight_value} kg",
        "weight_value": weight_value,
        "weight_unit": "kg",
        "part_type_raw": None,
        "surface_treatment_raw": None,
        "heat_treatment_raw": None,
        "field_evidence": field_evidence,
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
    }


def material_normalization_output() -> dict:
    return {
        "task_id": "task_001",
        "input_type": "field_text",
        "output_type": "normalization",
        "content": {
            "raw_text": "Q235A",
            "standard_code": "Q235A",
            "standard_name": "Q235A 碳素结构钢",
            "density": 7.85,
            "density_unit": "g/cm3",
            "match_reason": "PDF 材料字段为 Q235A。",
            "confidence": 0.9,
        },
        "confidence": 0.9,
        "evidence": [],
        "model_name": "fake-ai",
        "prompt_version": "test-v1",
        "created_at": "2026-06-15T10:00:00+08:00",
    }


def step_result(*, net_weight: float) -> dict:
    return {
        "file_id": "file_step_001",
        "bounding_box": {"length": 10.0, "width": 10.0, "height": 10.0, "unit": "mm"},
        "volume": {"value": 1000.0, "unit": "mm3", "source": source("step", "STEP_VOLUME")},
        "surface_area": {
            "value": 600.0,
            "unit": "mm2",
            "source": source("step", "STEP_SURFACE_AREA"),
        },
        "net_weight": {
            "value": net_weight,
            "unit": "kg",
            "density": 0.00000785,
            "density_unit": "kg/mm3",
            "source": source("step", "STEP_NET_WEIGHT"),
        },
        "part_type_candidates": [],
        "holes": [],
        "geometry_risks": [],
        "complexity": {
            "face_count": None,
            "edge_count": None,
            "small_radius_count": None,
            "slot_count": None,
            "thin_wall_candidate": False,
            "complexity_score": None,
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


def risk_by_code(risks: list[dict], code: str) -> dict | None:
    return next((risk for risk in risks if risk.get("code") == code), None)


if __name__ == "__main__":
    unittest.main()
