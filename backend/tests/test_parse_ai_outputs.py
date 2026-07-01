from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.app.database import get_connection, init_database
from backend.app.main import (
    build_parse_ai_outputs,
    create_app,
    material_normalization_to_step_density,
    normalize_pdf_material_with_ai,
)
from backend.app.repository import get_parse_result, insert_part_file, insert_quote_task
from backend.app.storage import StoredFile


class ParseAiOutputTests(unittest.TestCase):
    def test_parse_endpoint_does_not_call_ai_when_use_ai_false(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            init_database(db_path)
            app = create_app(
                db_path=db_path,
                upload_root=Path(temp_dir) / "uploads",
                export_root=Path(temp_dir) / "exports",
                parser_service=FakeParserService(),
                ai_service=FailingAiAssistanceService(),
            )
            with TestClient(app) as client:
                connection = get_connection(db_path)
                try:
                    insert_quote_task(
                        connection,
                        task_id="task_parse_no_ai",
                        customer_name="Customer",
                        part_name="Bracket",
                        part_no="RM-JJ-00083254",
                        quantity=100,
                        now="2026-06-22T10:00:00+08:00",
                    )
                    insert_part_file(
                        connection,
                        StoredFile(
                            file_id="file_pdf_001",
                            task_id="task_parse_no_ai",
                            file_type="pdf",
                            filename="drawing.pdf",
                            storage_path="uploads/task_parse_no_ai/pdf/drawing.pdf",
                            version=1,
                            size_bytes=10,
                            checksum="sha256",
                        ),
                        uploaded_by="tester",
                        uploaded_at="2026-06-22T10:00:00+08:00",
                    )
                    connection.commit()
                finally:
                    connection.close()

                response = client.post(
                    "/api/quote-tasks/task_parse_no_ai/parse",
                    json={"parse_pdf": True, "parse_step": False, "use_ai": False},
                )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["success"])
            connection = get_connection(db_path)
            try:
                parse_result = get_parse_result(connection, "task_parse_no_ai")
            finally:
                connection.close()
            self.assertIsNotNone(parse_result)
            assert parse_result is not None
            material = parse_result["part_feature"]["material"]
            self.assertEqual(material["raw_text"], "SUS304")
            self.assertIsNone(material["standard_code"])
            self.assertEqual(material["source"]["source_type"], "pdf")

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


class FailingAiAssistanceService:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"AI service should not be called when use_ai=False: {name}")


class FakeParserService:
    def parse_pdf(
        self,
        *,
        task: dict[str, Any],
        pdf_file: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        return (
            {
                "file_id": pdf_file["file_id"],
                "drawing_no": "RM-JJ-00083254",
                "part_name": "光电支架",
                "revision": "01",
                "part_type_raw": "钣金类",
                "material_raw": "SUS304",
                "weight_raw": "0.06 kg",
                "weight_value": 0.06,
                "weight_unit": "kg",
                "surface_treatment_raw": None,
                "heat_treatment_raw": None,
                "technical_requirements": [],
                "field_evidence": {
                    "drawing_no": source("pdf", "PDF_FIELD:drawing_no"),
                    "part_name": source("pdf", "PDF_FIELD:part_name"),
                    "revision": source("pdf", "PDF_FIELD:revision"),
                    "part_type_raw": source("pdf", "PDF_FIELD:part_type_raw"),
                    "material_raw": source("pdf", "PDF_FIELD:material_raw"),
                    "weight_raw": source("pdf", "PDF_FIELD:weight_raw"),
                },
                "field_confidence": {
                    "drawing_no": 0.9,
                    "part_name": 0.9,
                    "revision": 0.9,
                    "part_type_raw": 0.9,
                    "material_raw": 0.9,
                    "weight_raw": 0.9,
                },
            },
            [],
        )

    def parse_step(
        self,
        *,
        task: dict[str, Any],
        step_file: dict[str, Any],
        material_density: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        raise AssertionError("STEP parser should not be called in this test")


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


def source(source_type: str, rule_code: str) -> dict[str, Any]:
    return {
        "source_type": source_type,
        "file_id": "file_pdf_001" if source_type == "pdf" else None,
        "raw_text": rule_code,
        "rule_code": rule_code,
    }


if __name__ == "__main__":
    unittest.main()
