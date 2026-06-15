from __future__ import annotations

import unittest
from typing import Any

from backend.app.main import (
    build_parse_ai_outputs,
    material_normalization_to_step_density,
    normalize_pdf_material_with_ai,
)


class ParseAiOutputTests(unittest.TestCase):
    def test_parse_ai_outputs_skip_duplicate_material_normalization(self) -> None:
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
            material_normalization=ai_output(
                task_id="task_001",
                output_type="normalization",
                content={
                    "raw_text": "45",
                    "standard_code": "S45C",
                    "standard_name": "45#钢",
                    "density": 7.85,
                    "density_unit": "g/cm3",
                    "match_reason": "材料已归一。",
                    "confidence": 0.86,
                },
                evidence=[],
            ),
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
            material_normalization=None,
        )

        self.assertEqual(
            [output["output_type"] for output in outputs],
            ["normalization", "normalization", "risk_suggestion"],
        )
        self.assertEqual(service.material_raw_text, "未知材料X")
        self.assertEqual(service.surface_raw_text, "特殊蓝色处理")

    def test_normalize_pdf_material_with_ai_uses_extracted_pdf_material(self) -> None:
        service = FakeAiAssistanceService()
        pdf_result = {
            "file_id": "file_pdf_001",
            "material_raw": "Q235A",
            "field_evidence": {
                "material_raw": {
                    "source_type": "pdf",
                    "file_id": "file_pdf_001",
                    "raw_text": "材料：Q235A",
                    "rule_code": "PDF_FIELD:material_raw",
                }
            },
        }

        output = normalize_pdf_material_with_ai(
            ai_service=service,
            task_id="task_001",
            pdf_result=pdf_result,
        )

        self.assertEqual(service.material_raw_text, "Q235A")
        self.assertEqual(output["content"]["standard_code"], "Q235A")

    def test_material_normalization_to_step_density_converts_ai_density(self) -> None:
        output = ai_output(
            task_id="task_001",
            output_type="normalization",
            content={
                "raw_text": "Q235A",
                "standard_code": "Q235A",
                "standard_name": "Q235A 碳素结构钢",
                "density": 7.85,
                "density_unit": "g/cm3",
                "match_reason": "PDF 材料字段为 Q235A。",
                "confidence": 0.9,
            },
            evidence=[],
        )

        density = material_normalization_to_step_density(output)

        self.assertIsNotNone(density)
        assert density is not None
        self.assertEqual(density["material_name"], "Q235A 碳素结构钢")
        self.assertEqual(density["standard_code"], "Q235A")
        self.assertEqual(density["density_kg_mm3"], 0.00000785)
        self.assertEqual(density["source"]["source_type"], "ai")
        self.assertEqual(
            density["source"]["rule_code"],
            "MATERIAL_DENSITY_AI_NORMALIZATION",
        )


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
        standard_code = "Q235A" if raw_text == "Q235A" else "S45C"
        standard_name = "Q235A 碳素结构钢" if raw_text == "Q235A" else "45#钢"
        return ai_output(
            task_id=task_id,
            output_type="normalization",
            content={
                "raw_text": raw_text,
                "standard_code": standard_code,
                "standard_name": standard_name,
                "density": 7.85,
                "density_unit": "g/cm3",
                "match_reason": "根据 PDF 材料字段归一。",
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
