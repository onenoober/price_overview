from __future__ import annotations

import unittest

from backend.app.part_feature_builder import build_part_feature
from backend.app.schema_validation import validate_part_feature


class TechnicalRequirementsFusionTests(unittest.TestCase):
    def test_pdf_technical_requirements_are_preserved_in_part_feature(self) -> None:
        pdf_result = pdf_result_with_technical_requirements()
        part_feature = build_part_feature(
            task=task(),
            pdf_result=pdf_result,
            step_result=None,
            risks=[],
        )

        validate_part_feature(part_feature)
        manufacturing = part_feature["manufacturing_requirements"]
        requirements = manufacturing["technical_requirements"]
        details = manufacturing["technical_requirement_details"]

        self.assertEqual(requirements, pdf_result["technical_requirements"])
        self.assertEqual([item["raw_text"] for item in details], requirements)
        self.assertEqual(
            [item["requirement_type"] for item in details],
            ["deburring", "surface_treatment", "precision"],
        )
        self.assertEqual([item["confidence"] for item in details], [0.81, 0.79, 0.76])
        self.assertTrue(all(item["source"]["source_type"] == "pdf" for item in details))
        self.assertEqual(details[0]["source"]["raw_text"], requirements[0])
        self.assertTrue(manufacturing["deburring"]["required"])


def task() -> dict:
    return {
        "task_id": "task_001",
        "part_name": "Part",
        "part_no": "D001",
        "quantity": 1,
    }


def pdf_result_with_technical_requirements() -> dict:
    technical_requirements = [
        "Remove burrs and break sharp edges",
        "Surface treatment: black oxide",
        "Unspecified tolerance per GB/T 1804-m",
    ]
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
            "material_raw": source("PDF_FIELD:material_raw"),
            "weight_raw": source("PDF_FIELD:weight_raw"),
            "surface_treatment_raw": source("PDF_FIELD:surface_treatment_raw"),
            "heat_treatment_raw": source("PDF_FIELD:heat_treatment_raw"),
            "part_type_raw": source("PDF_FIELD:part_type_raw"),
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
        "technical_requirements": technical_requirements,
        "technical_requirement_evidence": [
            source("PDF_TEXT_TECHNICAL_REQUIREMENT", raw_text=text)
            for text in technical_requirements
        ],
        "field_details": {
            "technical_requirements": {
                "candidates": [
                    {"confidence": 0.81},
                    {"confidence": 0.79},
                    {"confidence": 0.76},
                ]
            }
        },
    }


def source(rule_code: str, raw_text: str | None = None) -> dict:
    return {
        "source_type": "pdf",
        "file_id": "file_pdf_001",
        "page": 1,
        "location": "technical_requirements",
        "raw_text": raw_text,
        "rule_code": rule_code,
    }


if __name__ == "__main__":
    unittest.main()
