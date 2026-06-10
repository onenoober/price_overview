from __future__ import annotations

import unittest
from typing import Any

from backend.app.main import build_parse_ai_outputs


class ParseAiOutputTests(unittest.TestCase):
    def test_parse_ai_outputs_skip_normalization_when_archive_or_rule_matches(self) -> None:
        service = FakeAiAssistanceService()
        pdf_result = {
            "file_id": "file_pdf_001",
            "material_raw": "45",
            "surface_treatment_raw": "化学镀镍",
            "field_evidence": {
                "material_raw": {
                    "source_type": "pdf",
                    "file_id": "file_pdf_001",
                    "raw_text": "材料：45",
                    "rule_code": "PDF_FIELD:material_raw",
                },
                "surface_treatment_raw": {
                    "source_type": "pdf",
                    "file_id": "file_pdf_001",
                    "raw_text": "表面处理：化学镀镍",
                    "rule_code": "PDF_FIELD:surface_treatment_raw",
                },
            },
        }
        risk = {
            "code": "LOW_CONFIDENCE_FIELD",
            "level": "warning",
            "message": "PDF 字段置信度低",
            "requires_review": True,
            "evidence": [],
        }

        outputs = build_parse_ai_outputs(
            ai_service=service,
            task_id="task_001",
            pdf_result=pdf_result,
            risks=[risk],
            material_density=FakeMaterialDensity(),
        )

        self.assertEqual(
            [output["output_type"] for output in outputs],
            ["risk_suggestion"],
        )
        self.assertIsNone(service.material_raw_text)
        self.assertIsNone(service.surface_raw_text)

    def test_parse_ai_outputs_include_normalization_only_for_uncertain_fields(self) -> None:
        service = FakeAiAssistanceService()
        pdf_result = {
            "file_id": "file_pdf_001",
            "material_raw": "未知材料X",
            "surface_treatment_raw": "特殊蓝色处理",
            "field_evidence": {
                "material_raw": {
                    "source_type": "pdf",
                    "file_id": "file_pdf_001",
                    "raw_text": "材料：未知材料X",
                    "rule_code": "PDF_FIELD:material_raw",
                },
                "surface_treatment_raw": {
                    "source_type": "pdf",
                    "file_id": "file_pdf_001",
                    "raw_text": "表面处理：特殊蓝色处理",
                    "rule_code": "PDF_FIELD:surface_treatment_raw",
                },
            },
        }
        risk = {
            "code": "LOW_CONFIDENCE_FIELD",
            "level": "warning",
            "message": "PDF 字段置信度低",
            "requires_review": True,
            "evidence": [],
        }

        outputs = build_parse_ai_outputs(
            ai_service=service,
            task_id="task_001",
            pdf_result=pdf_result,
            risks=[risk],
            material_density=None,
        )

        self.assertEqual(
            [output["output_type"] for output in outputs],
            ["normalization", "normalization", "risk_suggestion"],
        )
        self.assertEqual(service.material_raw_text, "未知材料X")
        self.assertEqual(service.surface_raw_text, "特殊蓝色处理")


class FakeMaterialDensity:
    def source_ref(self) -> dict[str, Any]:
        return {
            "source_type": "price_rule",
            "location": "制造中心材料费档案表.xlsx",
            "raw_text": "45#钢; density=7.85 g/cm3",
            "rule_code": "MATERIAL_DENSITY_ARCHIVE",
        }


class FakeAiAssistanceService:
    material_raw_text: str | None = None
    surface_raw_text: str | None = None
    material_evidence: list[dict[str, Any]]

    def normalize_material(
        self,
        *,
        task_id: str,
        raw_text: str | None,
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.material_raw_text = raw_text
        self.material_evidence = evidence
        return ai_output(
            task_id=task_id,
            output_type="normalization",
            content={
                "raw_text": raw_text,
                "standard_code": "S45C",
                "standard_name": "45#钢",
                "density": 7.85,
                "density_unit": "g/cm3",
                "match_reason": "根据材料档案候选匹配。",
                "confidence": 0.86,
            },
            evidence=evidence,
        )

    def normalize_surface_treatment(
        self,
        *,
        task_id: str,
        raw_text: str | None,
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.surface_raw_text = raw_text
        return ai_output(
            task_id=task_id,
            output_type="normalization",
            content={
                "raw_text": raw_text,
                "standard_code": "CHEMICAL_NICKEL_PLATING",
                "standard_name": "化学镀镍",
                "match_reason": "PDF 表面处理原文包含化学镀镍。",
                "confidence": 0.82,
            },
            evidence=evidence,
        )

    def explain_risk(self, *, task_id: str, risk: dict[str, Any]) -> dict[str, Any]:
        return ai_output(
            task_id=task_id,
            output_type="risk_suggestion",
            content={
                "risk_code": risk["code"],
                "risk_level": risk["level"],
                "original_message": risk["message"],
                "explanation": "字段置信度低，需要复核。",
                "review_suggestion": "请按 PDF 原文确认。",
                "requires_review": True,
                "confidence": 0.7,
            },
            evidence=risk.get("evidence") or [],
            input_type="risk_item",
        )


def ai_output(
    *,
    task_id: str,
    output_type: str,
    content: dict[str, Any],
    evidence: list[dict[str, Any]],
    input_type: str = "field_text",
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "input_type": input_type,
        "output_type": output_type,
        "content": content,
        "confidence": content.get("confidence", 0.7),
        "evidence": evidence,
        "model_name": "fake-ai",
        "prompt_version": "test-v1",
        "created_at": "2026-06-08T10:00:00+08:00",
    }


if __name__ == "__main__":
    unittest.main()
