from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.app.database import get_connection, init_database
from backend.app.repository import (
    delete_ai_outputs_for_task,
    insert_ai_outputs,
    list_ai_outputs,
)


class AiOutputRepositoryTests(unittest.TestCase):
    def test_risk_suggestions_are_deduplicated_by_risk_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            init_database(db_path)
            connection = get_connection(db_path)
            try:
                connection.execute(
                    """
                    INSERT INTO quote_task (
                        task_id, customer_name, part_name, part_no,
                        quantity, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "task_001",
                        "Customer",
                        "Part",
                        "D001",
                        1,
                        "draft",
                        "2026-06-08T10:00:00+08:00",
                        "2026-06-08T10:00:00+08:00",
                    ),
                )
                insert_ai_outputs(
                    connection,
                    [
                        risk_output("old explanation", "2026-06-08T10:00:00+08:00"),
                        risk_output("new explanation", "2026-06-08T11:00:00+08:00"),
                    ],
                )
                connection.commit()

                outputs = list_ai_outputs(connection, "task_001")

                self.assertEqual(len(outputs), 1)
                self.assertEqual(
                    outputs[0]["content"]["explanation"],
                    "new explanation",
                )
            finally:
                connection.close()

    def test_database_trigger_deduplicates_direct_risk_suggestion_inserts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            init_database(db_path)
            connection = get_connection(db_path)
            try:
                insert_task(connection)
                direct_insert_ai_output(
                    connection,
                    result_id="ai_old",
                    output=risk_output("old explanation", "2026-06-08T10:00:00+08:00"),
                )
                direct_insert_ai_output(
                    connection,
                    result_id="ai_new",
                    output=risk_output("new explanation", "2026-06-08T11:00:00+08:00"),
                )
                connection.commit()

                rows = connection.execute(
                    """
                    SELECT result_id, content FROM ai_assistance_result
                    WHERE input_type='risk_item' AND output_type='risk_suggestion'
                    """
                ).fetchall()

                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["result_id"], "ai_new")
                self.assertEqual(
                    json.loads(rows[0]["content"])["explanation"],
                    "new explanation",
                )
            finally:
                connection.close()

    def test_ai_outputs_can_be_cleared_for_new_parse(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            init_database(db_path)
            connection = get_connection(db_path)
            try:
                insert_task(connection)
                insert_ai_outputs(
                    connection,
                    [risk_output("old explanation", "2026-06-08T10:00:00+08:00")],
                )
                connection.commit()

                delete_ai_outputs_for_task(connection, "task_001")
                connection.commit()

                self.assertEqual(list_ai_outputs(connection, "task_001"), [])
            finally:
                connection.close()

    def test_list_ai_outputs_keeps_normalization_but_hides_pdf_field_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            init_database(db_path)
            connection = get_connection(db_path)
            try:
                insert_task(connection)
                insert_ai_outputs(
                    connection,
                    [
                        normalization_output(),
                        pdf_field_candidate_output(),
                    ],
                )
                connection.commit()

                outputs = list_ai_outputs(connection, "task_001")

                self.assertEqual(len(outputs), 1)
                self.assertEqual(outputs[0]["output_type"], "normalization")
                self.assertEqual(outputs[0]["content"]["standard_code"], "S45C")
            finally:
                connection.close()

    def test_list_ai_outputs_keeps_unavailable_status_records_for_ui_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            init_database(db_path)
            connection = get_connection(db_path)
            try:
                insert_task(connection)
                insert_ai_outputs(
                    connection,
                    [unavailable_risk_output()],
                )
                connection.commit()

                outputs = list_ai_outputs(connection, "task_001")

                self.assertEqual(len(outputs), 1)
                self.assertFalse(outputs[0]["content"]["available"])
            finally:
                connection.close()


def risk_output(explanation: str, created_at: str) -> dict:
    return {
        "task_id": "task_001",
        "input_type": "risk_item",
        "output_type": "risk_suggestion",
        "content": {
            "risk_code": "LOW_CONFIDENCE_FIELD",
            "risk_level": "warning",
            "original_message": "PDF 字段置信度低于阈值：part_name",
            "explanation": explanation,
            "review_suggestion": "请复核。",
            "requires_review": True,
            "confidence": 0.62,
        },
        "confidence": 0.62,
        "evidence": [
            {
                "source_type": "pdf",
                "file_id": "file_pdf_001",
                "page": 1,
                "location": "title_block",
                "raw_text": "气缸顶升板",
                "rule_code": "PDF_TEXT_TITLE_BLOCK:part_name",
            }
        ],
        "model_name": "qwen3.5-omni-plus",
        "prompt_version": "b4-openai-v1",
        "created_at": created_at,
    }


def normalization_output() -> dict:
    return {
        "task_id": "task_001",
        "input_type": "field_text",
        "output_type": "normalization",
        "content": {
            "raw_text": "45",
            "standard_code": "S45C",
            "standard_name": "45#钢",
            "density": 7.85,
            "density_unit": "g/cm3",
            "match_reason": "材料档案候选匹配。",
            "confidence": 0.86,
        },
        "confidence": 0.86,
        "evidence": [],
        "model_name": "qwen3.5-omni-plus",
        "prompt_version": "b4-openai-v1",
        "created_at": "2026-06-08T10:00:00+08:00",
    }


def pdf_field_candidate_output() -> dict:
    return {
        "task_id": "task_001",
        "input_type": "pdf_text",
        "output_type": "field_candidate",
        "content": {
            "candidates": [],
            "review_required": True,
            "notes": "hidden",
            "confidence": 0.0,
        },
        "confidence": 0.0,
        "evidence": [],
        "model_name": "qwen3.5-omni-plus",
        "prompt_version": "b4-openai-v1",
        "created_at": "2026-06-08T10:00:01+08:00",
    }


def unavailable_risk_output() -> dict:
    output = risk_output("不可用", "2026-06-08T10:00:00+08:00")
    output["content"] = {
        **output["content"],
        "available": False,
        "error_message": "AI provider is not configured",
        "review_suggestion": "AI 当前不可用，请直接按结构化风险证据进行人工复核。",
    }
    output["confidence"] = 0.0
    output["model_name"] = "ai-unavailable"
    output["prompt_version"] = "b4-ai-unavailable-v1"
    return output


def insert_task(connection) -> None:
    connection.execute(
        """
        INSERT INTO quote_task (
            task_id, customer_name, part_name, part_no,
            quantity, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "task_001",
            "Customer",
            "Part",
            "D001",
            1,
            "draft",
            "2026-06-08T10:00:00+08:00",
            "2026-06-08T10:00:00+08:00",
        ),
    )


def direct_insert_ai_output(connection, *, result_id: str, output: dict) -> None:
    connection.execute(
        """
        INSERT INTO ai_assistance_result (
            result_id, task_id, input_type, output_type, content,
            confidence, evidence, model_name, prompt_version, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result_id,
            output["task_id"],
            output["input_type"],
            output["output_type"],
            json.dumps(output["content"], ensure_ascii=False),
            output["confidence"],
            json.dumps(output["evidence"], ensure_ascii=False),
            output["model_name"],
            output["prompt_version"],
            output["created_at"],
        ),
    )


if __name__ == "__main__":
    unittest.main()
