from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from .storage import StoredFile


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def get_quote_task(
    connection: sqlite3.Connection,
    task_id: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT task_id, customer_name, part_name, part_no, quantity, status,
               created_at, updated_at
        FROM quote_task
        WHERE task_id = ?
        """,
        (task_id,),
    ).fetchone()
    return row_to_dict(row)


def list_quote_tasks(
    connection: sqlite3.Connection,
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT task_id, customer_name, part_name, part_no, quantity, status,
               created_at, updated_at
        FROM quote_task
        ORDER BY updated_at DESC, created_at DESC, task_id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def insert_quote_task(
    connection: sqlite3.Connection,
    *,
    task_id: str,
    customer_name: str,
    part_name: str,
    part_no: str,
    quantity: int,
    now: str,
) -> dict[str, Any]:
    connection.execute(
        """
        INSERT INTO quote_task (
            task_id, customer_name, part_name, part_no, quantity,
            status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'draft', ?, ?)
        """,
        (
            task_id,
            customer_name,
            part_name,
            part_no,
            quantity,
            now,
            now,
        ),
    )
    task = get_quote_task(connection, task_id)
    if task is None:
        raise sqlite3.IntegrityError("quote_task insert did not return a row")
    return task


def get_next_file_version(
    connection: sqlite3.Connection,
    task_id: str,
    file_type: str,
) -> int:
    row = connection.execute(
        """
        SELECT COALESCE(MAX(version), 0) + 1 AS next_version
        FROM part_file
        WHERE task_id = ?
          AND file_type = ?
        """,
        (task_id, file_type),
    ).fetchone()
    return int(row["next_version"])


def insert_part_file(
    connection: sqlite3.Connection,
    stored_file: StoredFile,
    *,
    uploaded_by: str,
    uploaded_at: str,
) -> dict[str, Any]:
    connection.execute(
        """
        INSERT INTO part_file (
            file_id, task_id, file_type, filename, storage_path, version,
            size_bytes, checksum, status, parse_status, uploaded_by, uploaded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stored_file.file_id,
            stored_file.task_id,
            stored_file.file_type,
            stored_file.filename,
            stored_file.storage_path,
            stored_file.version,
            stored_file.size_bytes,
            stored_file.checksum,
            "uploaded",
            "not_parsed",
            uploaded_by,
            uploaded_at,
        ),
    )

    row = connection.execute(
        """
        SELECT file_id, task_id, file_type, filename, storage_path, version,
               size_bytes, checksum, status, parse_status, uploaded_by, uploaded_at
        FROM part_file
        WHERE file_id = ?
        """,
        (stored_file.file_id,),
    ).fetchone()
    return dict(row)


def mark_task_uploaded(
    connection: sqlite3.Connection,
    task_id: str,
    updated_at: str,
) -> None:
    connection.execute(
        """
        UPDATE quote_task
        SET status = CASE
                WHEN status = 'draft' THEN 'uploaded'
                ELSE status
            END,
            updated_at = ?
        WHERE task_id = ?
        """,
        (updated_at, task_id),
    )


def mark_task_parsed(
    connection: sqlite3.Connection,
    task_id: str,
    updated_at: str,
) -> None:
    connection.execute(
        """
        UPDATE quote_task
        SET status = CASE
                WHEN status IN ('draft', 'uploaded') THEN 'parsed'
                ELSE status
            END,
            updated_at = ?
        WHERE task_id = ?
        """,
        (updated_at, task_id),
    )


def get_latest_part_file(
    connection: sqlite3.Connection,
    task_id: str,
    file_type: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT file_id, task_id, file_type, filename, storage_path, version,
               size_bytes, checksum, status, parse_status, uploaded_by, uploaded_at
        FROM part_file
        WHERE task_id = ?
          AND file_type = ?
          AND status = 'uploaded'
        ORDER BY version DESC
        LIMIT 1
        """,
        (task_id, file_type),
    ).fetchone()
    return row_to_dict(row)


def list_part_files(
    connection: sqlite3.Connection,
    task_id: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT file_id, task_id, file_type, filename, storage_path, version,
               size_bytes, checksum, status, parse_status, uploaded_by, uploaded_at
        FROM part_file
        WHERE task_id = ?
        ORDER BY file_type, version
        """,
        (task_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_part_file(
    connection: sqlite3.Connection,
    task_id: str,
    file_id: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT file_id, task_id, file_type, filename, storage_path, version,
               size_bytes, checksum, status, parse_status, uploaded_by, uploaded_at
        FROM part_file
        WHERE task_id = ?
          AND file_id = ?
        """,
        (task_id, file_id),
    ).fetchone()
    return row_to_dict(row)


def update_part_file_status(
    connection: sqlite3.Connection,
    *,
    task_id: str,
    file_id: str,
    status: str,
    parse_status: str | None = None,
) -> dict[str, Any] | None:
    if parse_status is None:
        connection.execute(
            """
            UPDATE part_file
            SET status = ?
            WHERE task_id = ?
              AND file_id = ?
            """,
            (status, task_id, file_id),
        )
    else:
        connection.execute(
            """
            UPDATE part_file
            SET status = ?,
                parse_status = ?
            WHERE task_id = ?
              AND file_id = ?
            """,
            (status, parse_status, task_id, file_id),
        )
    return get_part_file(connection, task_id, file_id)


def update_part_file_parse_status(
    connection: sqlite3.Connection,
    *,
    file_id: str,
    parse_status: str,
) -> None:
    connection.execute(
        """
        UPDATE part_file
        SET parse_status = ?
        WHERE file_id = ?
        """,
        (parse_status, file_id),
    )


def upsert_parse_result(
    connection: sqlite3.Connection,
    *,
    task_id: str,
    parse_job_id: str,
    status: str,
    pdf_extract_result: dict[str, Any] | None,
    step_feature_result: dict[str, Any] | None,
    part_feature: dict[str, Any],
    risks: list[dict[str, Any]],
    now: str,
) -> None:
    connection.execute(
        """
        INSERT INTO parse_result (
            task_id, parse_job_id, status, pdf_extract_result,
            step_feature_result, part_feature, risks, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(task_id) DO UPDATE SET
            parse_job_id = excluded.parse_job_id,
            status = excluded.status,
            pdf_extract_result = excluded.pdf_extract_result,
            step_feature_result = excluded.step_feature_result,
            part_feature = excluded.part_feature,
            risks = excluded.risks,
            updated_at = excluded.updated_at
        """,
        (
            task_id,
            parse_job_id,
            status,
            json.dumps(pdf_extract_result, ensure_ascii=False)
            if pdf_extract_result
            else None,
            json.dumps(step_feature_result, ensure_ascii=False)
            if step_feature_result
            else None,
            json.dumps(part_feature, ensure_ascii=False),
            json.dumps(risks, ensure_ascii=False),
            now,
            now,
        ),
    )


def get_parse_result(
    connection: sqlite3.Connection,
    task_id: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT task_id, parse_job_id, status, pdf_extract_result,
               step_feature_result, part_feature, risks, created_at, updated_at
        FROM parse_result
        WHERE task_id = ?
        """,
        (task_id,),
    ).fetchone()

    if row is None:
        return None

    result = dict(row)
    result["pdf_extract_result"] = (
        json.loads(result["pdf_extract_result"])
        if result["pdf_extract_result"]
        else None
    )
    result["step_feature_result"] = (
        json.loads(result["step_feature_result"])
        if result["step_feature_result"]
        else None
    )
    result["part_feature"] = json.loads(result["part_feature"])
    result["risks"] = json.loads(result["risks"])
    return result


def insert_ai_outputs(
    connection: sqlite3.Connection,
    outputs: list[dict[str, Any]],
) -> None:
    for output in outputs:
        delete_duplicate_ai_outputs(connection, output)
        connection.execute(
            """
            INSERT INTO ai_assistance_result (
                result_id, task_id, input_type, output_type, content,
                confidence, evidence, model_name, prompt_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"ai_{uuid.uuid4().hex[:12]}",
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


def delete_ai_outputs_for_task(
    connection: sqlite3.Connection,
    task_id: str,
) -> None:
    connection.execute(
        "DELETE FROM ai_assistance_result WHERE task_id = ?",
        (task_id,),
    )


def list_ai_outputs(
    connection: sqlite3.Connection,
    task_id: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT result_id, task_id, input_type, output_type, content,
               confidence, evidence, model_name, prompt_version, created_at
        FROM ai_assistance_result
        WHERE task_id = ?
          AND NOT (input_type = 'pdf_text' AND output_type = 'field_candidate')
        ORDER BY created_at DESC, result_id DESC
        """,
        (task_id,),
    ).fetchall()

    outputs = []
    for row in rows:
        item = dict(row)
        item["content"] = json.loads(item["content"])
        item["evidence"] = json.loads(item["evidence"])
        if is_duplicate_ai_output(item, outputs):
            continue
        outputs.append(item)
    return outputs


def delete_duplicate_ai_outputs(
    connection: sqlite3.Connection,
    output: dict[str, Any],
) -> None:
    dedupe_key = ai_output_dedupe_key(output)
    if dedupe_key is None:
        return

    rows = connection.execute(
        """
        SELECT result_id, task_id, input_type, output_type, content, evidence
        FROM ai_assistance_result
        WHERE task_id = ?
          AND input_type = ?
          AND output_type = ?
        """,
        (output["task_id"], output["input_type"], output["output_type"]),
    ).fetchall()
    duplicate_ids = []
    for row in rows:
        existing = dict(row)
        existing["content"] = json.loads(existing["content"])
        existing["evidence"] = json.loads(existing["evidence"])
        if ai_output_dedupe_key(existing) == dedupe_key:
            duplicate_ids.append(existing["result_id"])

    if duplicate_ids:
        connection.executemany(
            "DELETE FROM ai_assistance_result WHERE result_id = ?",
            [(result_id,) for result_id in duplicate_ids],
        )


def is_duplicate_ai_output(
    output: dict[str, Any],
    existing_outputs: list[dict[str, Any]],
) -> bool:
    dedupe_key = ai_output_dedupe_key(output)
    if dedupe_key is None:
        return False
    return any(ai_output_dedupe_key(existing) == dedupe_key for existing in existing_outputs)


def ai_output_dedupe_key(output: dict[str, Any]) -> tuple[Any, ...] | None:
    if (
        output.get("input_type") == "risk_item"
        and output.get("output_type") == "risk_suggestion"
    ):
        content = output.get("content") or {}
        return (
            "risk_suggestion",
            output.get("task_id"),
            content.get("risk_code"),
            content.get("risk_level"),
            content.get("original_message"),
            evidence_dedupe_key(output.get("evidence") or []),
        )
    return None


def evidence_dedupe_key(evidence: list[dict[str, Any]]) -> str:
    parts = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        parts.append(
            {
                "source_type": item.get("source_type"),
                "file_id": item.get("file_id"),
                "page": item.get("page"),
                "location": item.get("location"),
                "raw_text": item.get("raw_text"),
                "rule_code": item.get("rule_code"),
            }
        )
    return json.dumps(parts, ensure_ascii=False, sort_keys=True)


def insert_quote_result(
    connection: sqlite3.Connection,
    *,
    quote_result: dict[str, Any],
    process_route: dict[str, Any] | None = None,
    quantity_result: dict[str, Any] | None = None,
    now: str,
) -> None:
    connection.execute(
        """
        INSERT INTO quote_result (
            quote_id, task_id, status, process_route, quantity_result,
            quote_result, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            quote_result["quote_id"],
            quote_result["task_id"],
            quote_result["status"],
            json.dumps(process_route, ensure_ascii=False)
            if process_route is not None
            else None,
            json.dumps(quantity_result, ensure_ascii=False)
            if quantity_result is not None
            else None,
            json.dumps(quote_result, ensure_ascii=False),
            now,
            now,
        ),
    )


def get_quote_result(
    connection: sqlite3.Connection,
    quote_id: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT quote_id, task_id, status, process_route, quantity_result,
               quote_result, created_at, updated_at
        FROM quote_result
        WHERE quote_id = ?
        """,
        (quote_id,),
    ).fetchone()

    if row is None:
        return None

    result = dict(row)
    result["process_route"] = parse_optional_json(result["process_route"])
    result["quantity_result"] = parse_optional_json(result["quantity_result"])
    result["quote_result"] = json.loads(result["quote_result"])
    return result


def get_latest_quote_result_by_task(
    connection: sqlite3.Connection,
    task_id: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT quote_id, task_id, status, process_route, quantity_result,
               quote_result, created_at, updated_at
        FROM quote_result
        WHERE task_id = ?
        ORDER BY updated_at DESC, created_at DESC, quote_id DESC
        LIMIT 1
        """,
        (task_id,),
    ).fetchone()

    if row is None:
        return None

    result = dict(row)
    result["process_route"] = parse_optional_json(result["process_route"])
    result["quantity_result"] = parse_optional_json(result["quantity_result"])
    result["quote_result"] = json.loads(result["quote_result"])
    return result


def update_quote_result(
    connection: sqlite3.Connection,
    *,
    quote_result: dict[str, Any],
    process_route: dict[str, Any] | None = None,
    quantity_result: dict[str, Any] | None = None,
    now: str,
) -> None:
    if process_route is not None or quantity_result is not None:
        connection.execute(
            """
            UPDATE quote_result
            SET status = ?,
                process_route = ?,
                quantity_result = ?,
                quote_result = ?,
                updated_at = ?
            WHERE quote_id = ?
            """,
            (
                quote_result["status"],
                json.dumps(process_route, ensure_ascii=False)
                if process_route is not None
                else None,
                json.dumps(quantity_result, ensure_ascii=False)
                if quantity_result is not None
                else None,
                json.dumps(quote_result, ensure_ascii=False),
                now,
                quote_result["quote_id"],
            ),
        )
        return

    connection.execute(
        """
        UPDATE quote_result
        SET status = ?,
            quote_result = ?,
            updated_at = ?
        WHERE quote_id = ?
        """,
        (
            quote_result["status"],
            json.dumps(quote_result, ensure_ascii=False),
            now,
            quote_result["quote_id"],
        ),
    )


def parse_optional_json(value: str | None) -> Any:
    return json.loads(value) if value else None


def mark_task_priced(
    connection: sqlite3.Connection,
    task_id: str,
    status: str,
    updated_at: str,
) -> None:
    task_status = "pending_review" if status == "pending_review" else "priced"
    connection.execute(
        """
        UPDATE quote_task
        SET status = CASE
                WHEN status IN ('draft', 'uploaded', 'parsed', 'priced', 'pending_review')
                THEN ?
                ELSE status
            END,
            updated_at = ?
        WHERE task_id = ?
        """,
        (task_status, updated_at, task_id),
    )


def mark_task_confirmed(
    connection: sqlite3.Connection,
    task_id: str,
    updated_at: str,
) -> None:
    connection.execute(
        """
        UPDATE quote_task
        SET status = CASE
                WHEN status IN ('priced', 'pending_review') THEN 'confirmed'
                ELSE status
            END,
            updated_at = ?
        WHERE task_id = ?
        """,
        (updated_at, task_id),
    )


def insert_export_record(
    connection: sqlite3.Connection,
    *,
    export_id: str,
    quote_id: str,
    export_format: str,
    storage_path: str,
    created_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO export_record (
            export_id, quote_id, format, storage_path, created_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (export_id, quote_id, export_format, storage_path, created_at),
    )


def get_export_record(
    connection: sqlite3.Connection,
    export_id: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT export_id, quote_id, format, storage_path, created_at
        FROM export_record
        WHERE export_id = ?
        """,
        (export_id,),
    ).fetchone()
    return row_to_dict(row)
