from __future__ import annotations

import json
import unittest

from backend.app.ai_assistance import (
    align_risk_explanation_content,
    compact_risk_explanation_payload,
    compact_pdf_field_candidate_payload,
    normalize_structured_content,
    pdf_field_candidates_schema,
    validate_structured_content,
)


class AiAssistancePayloadTests(unittest.TestCase):
    def test_pdf_field_candidate_payload_is_compact(self) -> None:
        long_text = "A" * 1000
        evidence = {
            "source_type": "pdf",
            "file_id": "file_pdf_001",
            "page": 1,
            "location": "title_block",
            "raw_text": long_text,
            "rule_code": "PDF_TEXT_FIELD",
        }
        candidate = {
            "field_name": "material_raw",
            "value": "45",
            "raw_text": long_text,
            "confidence": 0.8,
            "extract_method": "text_layer_title_block",
            "evidence": evidence,
            "evidence_detail": {"raw_text": long_text},
        }
        pdf_result = {
            "parser_name": "real_pdf_text_parser",
            "field_details": {
                "material_raw": {
                    "raw_text": long_text,
                    "value": "45",
                    "confidence": 0.8,
                    "extract_method": "text_layer_title_block",
                    "evidence": evidence,
                    "evidence_detail": {"raw_text": long_text},
                    "candidates": [candidate] * 5,
                }
            },
            "field_evidence": {"material_raw": evidence},
            "field_confidence": {"material_raw": 0.8},
            "technical_requirements": [long_text] * 20,
            "text_blocks": [
                {
                    "page": 1,
                    "block_index": index,
                    "bbox": [1.0, 2.0, 3.0, 4.0],
                    "text": long_text,
                }
                for index in range(30)
            ],
        }

        payload = compact_pdf_field_candidate_payload(
            task_id="task_001",
            pdf_result=pdf_result,
        )
        serialized = json.dumps(payload, ensure_ascii=False)

        self.assertNotIn("evidence_detail", serialized)
        self.assertEqual(
            len(payload["field_details"]["material_raw"]["candidates"]),
            3,
        )
        self.assertEqual(len(payload["technical_requirements"]), 8)
        self.assertNotIn("text_blocks_sample", payload)
        self.assertLess(len(serialized), 10000)

    def test_pdf_field_candidate_accepts_list_candidate_value(self) -> None:
        content = {
            "candidates": [
                {
                    "field_name": "technical_requirements",
                    "candidate_value": ["去除毛刺", "锐角倒钝"],
                    "confidence": 0.72,
                    "reason": "技术要求通常是多条文本。",
                    "evidence_summary": "PDF 技术要求栏。",
                }
            ],
            "review_required": True,
            "notes": "需要复核技术要求。",
            "confidence": 0.72,
        }

        normalized = normalize_structured_content("pdf_field_candidates", content)

        validate_structured_content(
            "pdf_field_candidates",
            pdf_field_candidates_schema(),
            normalized,
        )
        self.assertEqual(
            normalized["candidates"][0]["candidate_value"],
            ["去除毛刺", "锐角倒钝"],
        )

    def test_risk_explanation_payload_includes_guidance_for_weight_mismatch(self) -> None:
        risk = {
            "code": "WEIGHT_MISMATCH",
            "level": "warning",
            "message": "PDF=1.3kg，STEP=1.0kg，偏差超过 15%。",
            "requires_review": True,
            "source": "part_feature_fusion",
            "evidence": [
                {
                    "source_type": "pdf",
                    "raw_text": "重量：1.3kg",
                    "rule_code": "WEIGHT_MISMATCH:PDF_WEIGHT",
                },
                {
                    "source_type": "step",
                    "raw_text": "net_weight=1.0kg",
                    "rule_code": "WEIGHT_MISMATCH:STEP_WEIGHT",
                },
            ],
        }

        payload = compact_risk_explanation_payload("task_001", risk)

        self.assertEqual(payload["guidance"]["name"], "PDF 重量与 STEP 理论重量不一致")
        self.assertTrue(payload["constraints"]["explain_only_manual_review_reason"])
        self.assertEqual(payload["constraints"]["must_preserve_risk_level"], "warning")
        self.assertEqual(len(payload["risk"]["evidence"]), 2)

    def test_risk_explanation_alignment_preserves_original_risk_fields(self) -> None:
        risk = {
            "code": "LOW_CONFIDENCE_FIELD",
            "level": "warning",
            "message": "PDF 字段置信度低于阈值：material_raw",
            "requires_review": True,
        }
        ai_content = {
            "risk_code": "OTHER",
            "risk_level": "info",
            "original_message": "changed",
            "explanation": "字段抽取不稳定，需要人工复核。",
            "review_suggestion": "请按 PDF 原文核对材料字段。",
            "requires_review": False,
            "confidence": 1.2,
        }

        aligned = align_risk_explanation_content(ai_content, risk)

        self.assertEqual(aligned["risk_code"], "LOW_CONFIDENCE_FIELD")
        self.assertEqual(aligned["risk_level"], "warning")
        self.assertEqual(
            aligned["original_message"],
            "PDF 字段置信度低于阈值：material_raw",
        )
        self.assertTrue(aligned["requires_review"])
        self.assertEqual(aligned["confidence"], 1.0)


if __name__ == "__main__":
    unittest.main()
