from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.app.database import get_connection, init_database
from backend.app.repository import (
    delete_ai_outputs_for_task,
    get_parse_result,
    insert_ai_outputs,
    list_ai_outputs,
    upsert_parse_result,
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
                self.assertEqual(outputs[0]["content"]["standard_name"], "45号钢")
            finally:
                connection.close()

    def test_list_ai_outputs_normalizes_english_material_name_to_chinese(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            init_database(db_path)
            connection = get_connection(db_path)
            try:
                insert_task(connection)
                output = normalization_output()
                output["content"] = {
                    **output["content"],
                    "raw_text": "Q235A",
                    "standard_code": "Q235A",
                    "standard_name": "Q235A carbon structural steel",
                }
                insert_ai_outputs(connection, [output])
                connection.commit()

                outputs = list_ai_outputs(connection, "task_001")

                self.assertEqual(
                    outputs[0]["content"]["standard_name"],
                    "Q235A 碳素结构钢",
                )
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

    def test_step_part_type_classification_output_can_be_saved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            init_database(db_path)
            connection = get_connection(db_path)
            try:
                insert_task(connection)
                insert_ai_outputs(connection, [step_part_type_output()])
                connection.commit()

                outputs = list_ai_outputs(connection, "task_001")

                self.assertEqual(len(outputs), 1)
                self.assertEqual(outputs[0]["input_type"], "step_geometry")
                self.assertEqual(outputs[0]["output_type"], "part_type_classification")
                self.assertEqual(outputs[0]["content"]["part_type"], "plate")
            finally:
                connection.close()

    def test_process_route_suggestion_output_can_be_saved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            init_database(db_path)
            connection = get_connection(db_path)
            try:
                insert_task(connection)
                insert_ai_outputs(connection, [process_route_suggestion_output()])
                connection.commit()

                outputs = list_ai_outputs(connection, "task_001")

                self.assertEqual(len(outputs), 1)
                self.assertEqual(outputs[0]["input_type"], "fusion_feature")
                self.assertEqual(outputs[0]["output_type"], "process_route_suggestion")
                self.assertEqual(
                    outputs[0]["content"]["suggestions"][0]["operation_code"],
                    "wire_cut_profile",
                )
            finally:
                connection.close()

    def test_process_route_generation_output_can_be_saved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            init_database(db_path)
            connection = get_connection(db_path)
            try:
                insert_task(connection)
                insert_ai_outputs(connection, [process_route_generation_output()])
                connection.commit()

                outputs = list_ai_outputs(connection, "task_001")

                self.assertEqual(len(outputs), 1)
                self.assertEqual(outputs[0]["input_type"], "fusion_feature")
                self.assertEqual(outputs[0]["output_type"], "process_route_generation")
                self.assertEqual(
                    outputs[0]["content"]["operations"][0]["operation_code"],
                    "turning",
                )
            finally:
                connection.close()

    def test_get_parse_result_normalizes_historical_english_material_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            init_database(db_path)
            connection = get_connection(db_path)
            try:
                insert_task(connection)
                upsert_parse_result(
                    connection,
                    task_id="task_001",
                    parse_job_id="parse_001",
                    status="completed",
                    pdf_extract_result=None,
                    step_feature_result=None,
                    part_feature=part_feature_with_material(
                        raw_text="SKD11",
                        standard_code="SKD11",
                        standard_name="JIS SKD11 cold work tool steel",
                    ),
                    risks=[],
                    now="2026-06-08T10:00:00+08:00",
                )
                connection.commit()

                parse_result = get_parse_result(connection, "task_001")

                assert parse_result is not None
                self.assertEqual(
                    parse_result["part_feature"]["material"]["standard_name"],
                    "SKD11 冷作模具钢",
                )
            finally:
                connection.close()

    def test_get_parse_result_removes_legacy_builtin_density(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            init_database(db_path)
            connection = get_connection(db_path)
            try:
                insert_task(connection)
                upsert_parse_result(
                    connection,
                    task_id="task_001",
                    parse_job_id="parse_001",
                    status="completed",
                    pdf_extract_result=pdf_result_with_material("Q235A"),
                    step_feature_result=step_result_with_legacy_builtin_density(),
                    part_feature=part_feature_with_legacy_builtin_density(),
                    risks=[],
                    now="2026-06-17T10:00:00+08:00",
                )
                connection.commit()

                parse_result = get_parse_result(connection, "task_001")

                assert parse_result is not None
                material = parse_result["part_feature"]["material"]
                net_weight = parse_result["part_feature"]["geometry"]["step_net_weight"]
                step_net_weight = parse_result["step_feature_result"]["net_weight"]
                self.assertEqual(material["raw_text"], "Q235A")
                self.assertIsNone(material["standard_code"])
                self.assertIsNone(material["density"])
                self.assertIsNone(material["density_unit"])
                self.assertEqual(material["source"]["source_type"], "pdf")
                self.assertIsNone(net_weight["value"])
                self.assertIsNone(net_weight["unit"])
                self.assertIsNone(net_weight["density_source"])
                self.assertIsNone(step_net_weight["value"])
                self.assertIsNone(step_net_weight["density_source"])
            finally:
                connection.close()

    def test_init_database_migrates_old_ai_output_type_constraints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            create_old_ai_output_schema(db_path)

            init_database(db_path)
            connection = get_connection(db_path)
            try:
                insert_ai_outputs(
                    connection,
                    [
                        step_part_type_output(),
                        process_route_suggestion_output(),
                        process_route_generation_output(),
                    ],
                )
                connection.commit()

                outputs = list_ai_outputs(connection, "task_001")

                self.assertEqual(len(outputs), 4)
                self.assertIn(
                    "process_route_suggestion",
                    [output["output_type"] for output in outputs],
                )
                self.assertIn(
                    "process_route_generation",
                    [output["output_type"] for output in outputs],
                )
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


def part_feature_with_material(
    *,
    raw_text: str,
    standard_code: str,
    standard_name: str,
) -> dict:
    return {
        "schema_version": "1.0",
        "task_id": "task_001",
        "part": {
            "part_name": "Part",
            "drawing_no": "D001",
            "revision": None,
            "quantity": 1,
        },
        "material": {
            "raw_text": raw_text,
            "standard_code": standard_code,
            "standard_name": standard_name,
            "density": 7.7,
            "density_unit": "g/cm3",
            "confidence": 0.9,
            "source": {"source_type": "ai", "rule_code": "MATERIAL_DENSITY_AI_NORMALIZATION"},
        },
        "geometry": {},
        "features": {},
        "manufacturing_requirements": {},
        "risks": [],
    }


def pdf_result_with_material(raw_text: str) -> dict:
    return {
        "file_id": "file_pdf_001",
        "material_raw": raw_text,
        "field_evidence": {
            "material_raw": {
                "source_type": "pdf",
                "file_id": "file_pdf_001",
                "page": 1,
                "location": "title_block",
                "raw_text": raw_text,
                "rule_code": "PDF_TEXT_TITLE_BLOCK:material_raw",
            }
        },
    }


def part_feature_with_legacy_builtin_density() -> dict:
    source = {
        "source_type": "price_rule",
        "raw_text": "Q235A; density=7.85 g/cm3",
        "rule_code": "MATERIAL_DENSITY_BUILTIN:Q235A",
    }
    return {
        "schema_version": "1.0",
        "task_id": "task_001",
        "part": {
            "part_name": "Part",
            "drawing_no": "D001",
            "revision": None,
            "quantity": 1,
        },
        "material": {
            "raw_text": "Q235A",
            "standard_code": "Q235A",
            "standard_name": "Q235A carbon structural steel",
            "density": 7.85,
            "density_unit": "g/cm3",
            "confidence": 0.78,
            "source": source,
        },
        "geometry": {
            "step_net_weight": {
                "value": 0.050497,
                "unit": "kg",
                "source": {"source_type": "step", "file_id": "file_step_001"},
            }
        },
        "features": {},
        "manufacturing_requirements": {},
        "risks": [],
    }


def step_result_with_legacy_builtin_density() -> dict:
    source = {
        "source_type": "price_rule",
        "raw_text": "Q235A; density=7.85 g/cm3",
        "rule_code": "MATERIAL_DENSITY_BUILTIN:Q235A",
    }
    return {
        "file_id": "file_step_001",
        "net_weight": {
            "value": 0.050497,
            "unit": "kg",
            "density": 0.00000785,
            "density_unit": "kg/mm3",
            "source": {"source_type": "step", "file_id": "file_step_001"},
            "density_source": source,
        },
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


def step_part_type_output() -> dict:
    return {
        "task_id": "task_001",
        "input_type": "step_geometry",
        "output_type": "part_type_classification",
        "content": {
            "part_type": "plate",
            "specific_type": "板件",
            "reason": "AI 根据 STEP 几何摘要判断为板件。",
            "requires_review": False,
            "confidence": 0.88,
        },
        "confidence": 0.88,
        "evidence": [
            {
                "source_type": "step",
                "file_id": "file_step_001",
                "rule_code": "STEP_GEOMETRY_SUMMARY",
            }
        ],
        "model_name": "qwen3.5-omni-plus",
        "prompt_version": "b4-openai-v1",
        "created_at": "2026-06-08T10:00:00+08:00",
    }


def process_route_suggestion_output() -> dict:
    return {
        "task_id": "task_001",
        "input_type": "fusion_feature",
        "output_type": "process_route_suggestion",
        "content": {
            "suggestions": [
                {
                    "action": "add",
                    "operation_code": "wire_cut_profile",
                    "reason": "STEP 几何摘要显示存在窄槽，建议补充线切割候选。",
                    "evidence_summary": "slot_candidate_count > 0",
                    "confidence": 0.82,
                }
            ],
            "review_required": True,
            "summary": "AI 建议复核工艺路线。",
            "confidence": 0.82,
        },
        "confidence": 0.82,
        "evidence": [
            {
                "source_type": "system",
                "file_id": None,
                "rule_code": "PROCESS_ROUTE_RULE_BASELINE",
            }
        ],
        "model_name": "qwen3.5-omni-plus",
        "prompt_version": "b4-openai-v1",
        "created_at": "2026-06-08T10:00:00+08:00",
    }


def process_route_generation_output() -> dict:
    return {
        "task_id": "task_001",
        "input_type": "fusion_feature",
        "output_type": "process_route_generation",
        "content": {
            "operations": [
                {
                    "operation_code": "turning",
                    "operation_name_raw": None,
                    "reason": "STEP 显示轴类主体，AI 自主识别车削。",
                    "evidence_summary": "step_part_type=shaft",
                    "confidence": 0.86,
                    "requires_review": False,
                }
            ],
            "review_required": False,
            "summary": "AI 自主生成工艺路线。",
            "confidence": 0.86,
        },
        "confidence": 0.86,
        "evidence": [
            {
                "source_type": "system",
                "file_id": None,
                "rule_code": "AI_PROCESS_ROUTE_GENERATION_INPUT",
            }
        ],
        "model_name": "qwen3.5-omni-plus",
        "prompt_version": "b4-openai-v1",
        "created_at": "2026-06-08T10:00:00+08:00",
    }


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


def create_old_ai_output_schema(db_path: Path) -> None:
    connection = get_connection(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE quote_task (
                task_id TEXT PRIMARY KEY,
                customer_name TEXT NOT NULL,
                part_name TEXT NOT NULL,
                part_no TEXT NOT NULL DEFAULT '',
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                status TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'uploaded', 'parsed', 'priced', 'pending_review', 'confirmed', 'voided')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE part_file (
                file_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                file_type TEXT NOT NULL
                    CHECK (file_type IN ('pdf', 'step', 'attachment')),
                filename TEXT NOT NULL,
                storage_path TEXT NOT NULL,
                version INTEGER NOT NULL CHECK (version > 0),
                size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
                checksum TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'uploaded'
                    CHECK (status IN ('uploaded', 'invalid', 'deleted')),
                parse_status TEXT NOT NULL DEFAULT 'not_parsed'
                    CHECK (parse_status IN ('not_parsed', 'parsed', 'failed', 'skipped')),
                uploaded_by TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES quote_task(task_id) ON DELETE CASCADE,
                UNIQUE (task_id, file_type, version)
            );
            CREATE TABLE quote_result (
                quote_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                status TEXT NOT NULL
                    CHECK (status IN ('priced', 'pending_review', 'confirmed', 'voided')),
                process_route TEXT,
                quantity_result TEXT,
                quote_result TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES quote_task(task_id) ON DELETE CASCADE
            );
            CREATE TABLE ai_assistance_result (
                result_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                input_type TEXT NOT NULL
                    CHECK (input_type IN ('pdf_text', 'field_text', 'rule_result', 'risk_item', 'override_history')),
                output_type TEXT NOT NULL
                    CHECK (output_type IN ('field_candidate', 'normalization', 'explanation', 'risk_suggestion', 'analysis')),
                content TEXT NOT NULL,
                confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
                evidence TEXT NOT NULL,
                model_name TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES quote_task(task_id) ON DELETE CASCADE
            );
            """
        )
        insert_task(connection)
        direct_insert_ai_output(
            connection,
            result_id="ai_old",
            output=normalization_output(),
        )
        connection.commit()
    finally:
        connection.close()


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
