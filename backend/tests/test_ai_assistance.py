from __future__ import annotations

import asyncio
import json
import os
import time
import unittest

from backend.app.ai_assistance import (
    align_risk_explanation_content,
    build_ai_output,
    collect_openai_stream_text,
    compact_process_route_generation_payload,
    compact_risk_explanation_payload,
    compact_pdf_field_candidate_payload,
    normalize_structured_content,
    parse_ai_json_object,
    pdf_field_candidates_schema,
    validate_structured_content,
)
from backend.app.main import generate_process_route_with_timeout


class AiAssistancePayloadTests(unittest.TestCase):
    def test_process_route_generation_timeout_returns_unavailable_output(self) -> None:
        previous = os.environ.get("PRICE_AI_PROCESS_ROUTE_TIMEOUT_SECONDS")
        os.environ["PRICE_AI_PROCESS_ROUTE_TIMEOUT_SECONDS"] = "0.05"
        try:
            output = asyncio.run(
                generate_process_route_with_timeout(
                    ai_service=SlowProcessRouteAiService(),
                    task_id="task_timeout",
                    part_feature={
                        "part": {},
                        "material": {},
                        "geometry": {},
                        "features": {},
                        "manufacturing_requirements": {},
                    },
                    pdf_result=None,
                    step_result=None,
                    inherited_risks=[],
                )
            )
        finally:
            if previous is None:
                os.environ.pop("PRICE_AI_PROCESS_ROUTE_TIMEOUT_SECONDS", None)
            else:
                os.environ["PRICE_AI_PROCESS_ROUTE_TIMEOUT_SECONDS"] = previous

        self.assertEqual(output["output_type"], "process_route_generation")
        self.assertFalse(output["content"]["available"])
        self.assertEqual(output["model_name"], "ai-timeout")

    def test_process_route_generation_payload_includes_decision_framework(self) -> None:
        payload = compact_process_route_generation_payload(
            task_id="task_001",
            part_feature={
                "part": {"quantity": 2},
                "material": {"raw_text": "Q235A"},
                "geometry": {
                    "part_type": "shaft",
                    "bounding_box": {"length": 120, "width": 20, "height": 20},
                },
                "features": {"holes": [], "complexity": {"complexity_score": 24}},
                "manufacturing_requirements": {
                    "technical_requirements": ["M6-6H", "发黑"],
                    "surface_treatment": {"required": True, "raw_text": "发黑"},
                },
            },
            pdf_result={
                "file_id": "file_pdf_001",
                "material_raw": "Q235A",
                "technical_requirements": ["M6-6H", "发黑"],
            },
            step_result={
                "file_id": "file_step_001",
                "bounding_box": {"length": 120, "width": 20, "height": 20},
                "topology": {"solid_count": 1},
            },
            inherited_risks=[],
        )

        self.assertIn("decision_framework", payload)
        self.assertIn("evidence_priority", payload["decision_framework"])
        self.assertGreaterEqual(len(payload["decision_framework"]["analysis_steps"]), 12)
        self.assertEqual(payload["pdf_drawing_summary"]["file_id"], "file_pdf_001")
        self.assertEqual(payload["step_geometry_summary"]["file_id"], "file_step_001")
        self.assertIn("machining before surface treatment", payload["decision_framework"]["principle"])
        self.assertNotIn("allowed_operation_codes", payload)
        self.assertNotIn("inherited_risks", payload)

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

    def test_material_normalization_uses_chinese_standard_name(self) -> None:
        content = {
            "raw_text": "Q235A",
            "standard_code": "Q235A",
            "standard_name": "Q235A carbon structural steel",
            "density": 7.85,
            "density_unit": "g/cm3",
            "match_reason": "PDF 材料字段为 Q235A。",
            "confidence": 0.92,
        }

        normalized = normalize_structured_content("material_normalization", content)

        self.assertEqual(normalized["standard_name"], "Q235A 碳素结构钢")

    def test_material_normalization_maps_tool_steel_name_to_chinese(self) -> None:
        content = {
            "raw_text": "SKD11",
            "standard_code": "SKD11",
            "standard_name": "JIS SKD11 cold work tool steel",
            "density": 7.7,
            "density_unit": "g/cm3",
            "match_reason": "PDF 材料字段为 SKD11。",
            "confidence": 0.9,
        }

        normalized = normalize_structured_content("material_normalization", content)

        self.assertEqual(normalized["standard_name"], "SKD11 冷作模具钢")

    def test_collect_chat_completion_stream_text(self) -> None:
        lines = [
            'data: {"choices":[{"delta":{"content":"{\\"ok\\":"}}]}',
            'data: {"choices":[{"delta":{"content":"true}"}}]}',
            "data: [DONE]",
        ]

        self.assertEqual(collect_openai_stream_text(lines), '{"ok":true}')

    def test_collect_responses_stream_text(self) -> None:
        lines = [
            'data: {"type":"response.output_text.delta","delta":"{\\"ok\\":"}',
            'data: {"type":"response.output_text.delta","delta":"true}"}',
            "data: [DONE]",
        ]

        self.assertEqual(collect_openai_stream_text(lines), '{"ok":true}')

    def test_parse_ai_json_object_accepts_markdown_wrapped_json(self) -> None:
        response_text = """
        下面是结果：

        ```json
        {"available": true, "summary": "已生成", "confidence": 0.91}
        ```
        """

        self.assertEqual(
            parse_ai_json_object(response_text),
            {"available": True, "summary": "已生成", "confidence": 0.91},
        )

    def test_parse_ai_json_object_extracts_first_json_object(self) -> None:
        response_text = (
            '好的，{"summary": "包含 { 内部文本 }", "confidence": 0.8} '
            "以上为 JSON。"
        )

        self.assertEqual(
            parse_ai_json_object(response_text),
            {"summary": "包含 { 内部文本 }", "confidence": 0.8},
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


class SlowProcessRouteAiService:
    def generate_process_route(self, **kwargs):
        time.sleep(1)
        return build_ai_output(
            task_id=kwargs["task_id"],
            input_type="fusion_feature",
            output_type="process_route_generation",
            content={
                "available": True,
                "operations": [],
                "review_required": False,
                "summary": "",
                "confidence": 1.0,
            },
            confidence=1.0,
            evidence=[],
            model_name="slow-test",
            prompt_version="test",
        )


if __name__ == "__main__":
    unittest.main()
