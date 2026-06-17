from __future__ import annotations

import sqlite3
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "price_overview.sqlite3"

TASK_STATUSES = (
    "draft",
    "uploaded",
    "parsed",
    "priced",
    "pending_review",
    "confirmed",
    "voided",
)
FILE_TYPES = ("pdf", "step", "attachment")
FILE_STATUSES = ("uploaded", "invalid", "deleted")
FILE_PARSE_STATUSES = ("not_parsed", "parsed", "failed", "skipped")

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS quote_task (
        task_id TEXT PRIMARY KEY,
        customer_name TEXT NOT NULL,
        part_name TEXT NOT NULL,
        part_no TEXT NOT NULL DEFAULT '',
        quantity INTEGER NOT NULL CHECK (quantity > 0),
        status TEXT NOT NULL DEFAULT 'draft'
            CHECK (status IN ('draft', 'uploaded', 'parsed', 'priced', 'pending_review', 'confirmed', 'voided')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS part_file (
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
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_part_file_task_id
        ON part_file (task_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_part_file_task_type_version
        ON part_file (task_id, file_type, version)
    """,
    """
    CREATE TABLE IF NOT EXISTS parse_result (
        task_id TEXT PRIMARY KEY,
        parse_job_id TEXT NOT NULL,
        status TEXT NOT NULL
            CHECK (status IN ('completed', 'failed')),
        pdf_extract_result TEXT,
        step_feature_result TEXT,
        part_feature TEXT NOT NULL,
        risks TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (task_id) REFERENCES quote_task(task_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_assistance_result (
        result_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        input_type TEXT NOT NULL
            CHECK (input_type IN ('pdf_text', 'field_text', 'step_geometry', 'fusion_feature', 'rule_result', 'risk_item', 'override_history')),
        output_type TEXT NOT NULL
            CHECK (output_type IN ('field_candidate', 'normalization', 'part_type_classification', 'process_route_suggestion', 'process_route_generation', 'explanation', 'risk_suggestion', 'analysis')),
        content TEXT NOT NULL,
        confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
        evidence TEXT NOT NULL,
        model_name TEXT NOT NULL,
        prompt_version TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (task_id) REFERENCES quote_task(task_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ai_assistance_result_task_id
        ON ai_assistance_result (task_id)
    """,
    """
    CREATE TRIGGER IF NOT EXISTS ignore_pdf_field_candidate_ai
    BEFORE INSERT ON ai_assistance_result
    WHEN NEW.input_type = 'pdf_text' AND NEW.output_type = 'field_candidate'
    BEGIN
        SELECT RAISE(IGNORE);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS dedupe_risk_suggestion_ai
    BEFORE INSERT ON ai_assistance_result
    WHEN NEW.input_type = 'risk_item' AND NEW.output_type = 'risk_suggestion'
    BEGIN
        DELETE FROM ai_assistance_result
        WHERE task_id = NEW.task_id
          AND input_type = NEW.input_type
          AND output_type = NEW.output_type
          AND json_extract(content, '$.risk_code') =
              json_extract(NEW.content, '$.risk_code')
          AND json_extract(content, '$.risk_level') =
              json_extract(NEW.content, '$.risk_level')
          AND json_extract(content, '$.original_message') =
              json_extract(NEW.content, '$.original_message')
          AND evidence = NEW.evidence;
    END
    """,
    """
    CREATE TABLE IF NOT EXISTS quote_result (
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
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_quote_result_task_id
        ON quote_result (task_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS export_record (
        export_id TEXT PRIMARY KEY,
        quote_id TEXT NOT NULL,
        format TEXT NOT NULL CHECK (format IN ('json')),
        storage_path TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (quote_id) REFERENCES quote_result(quote_id) ON DELETE CASCADE
    )
    """,
)


def get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    resolved_path = Path(db_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(resolved_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_database(db_path: Path | str = DEFAULT_DB_PATH) -> Path:
    resolved_path = Path(db_path)

    connection = get_connection(resolved_path)
    try:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        apply_lightweight_migrations(connection)
        connection.commit()
    finally:
        connection.close()

    return resolved_path


def apply_lightweight_migrations(connection: sqlite3.Connection) -> None:
    part_file_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(part_file)").fetchall()
    }
    if "parse_status" not in part_file_columns:
        connection.execute(
            """
            ALTER TABLE part_file
            ADD COLUMN parse_status TEXT NOT NULL DEFAULT 'not_parsed'
            """
        )

    quote_result_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(quote_result)").fetchall()
    }
    if "process_route" not in quote_result_columns:
        connection.execute(
            """
            ALTER TABLE quote_result
            ADD COLUMN process_route TEXT
            """
        )
    if "quantity_result" not in quote_result_columns:
        connection.execute(
            """
            ALTER TABLE quote_result
            ADD COLUMN quantity_result TEXT
            """
        )

    migrate_ai_assistance_result_types(connection)


def migrate_ai_assistance_result_types(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'ai_assistance_result'
        """
    ).fetchone()
    table_sql = str(row["sql"] or "") if row else ""
    if (
        "step_geometry" in table_sql
        and "part_type_classification" in table_sql
        and "fusion_feature" in table_sql
        and "process_route_suggestion" in table_sql
        and "process_route_generation" in table_sql
    ):
        return

    connection.execute("DROP TRIGGER IF EXISTS ignore_pdf_field_candidate_ai")
    connection.execute("DROP TRIGGER IF EXISTS dedupe_risk_suggestion_ai")
    connection.execute("DROP INDEX IF EXISTS idx_ai_assistance_result_task_id")
    connection.execute("ALTER TABLE ai_assistance_result RENAME TO ai_assistance_result_old")
    connection.execute(
        """
        CREATE TABLE ai_assistance_result (
            result_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            input_type TEXT NOT NULL
                CHECK (input_type IN ('pdf_text', 'field_text', 'step_geometry', 'fusion_feature', 'rule_result', 'risk_item', 'override_history')),
            output_type TEXT NOT NULL
                CHECK (output_type IN ('field_candidate', 'normalization', 'part_type_classification', 'process_route_suggestion', 'process_route_generation', 'explanation', 'risk_suggestion', 'analysis')),
            content TEXT NOT NULL,
            confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
            evidence TEXT NOT NULL,
            model_name TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES quote_task(task_id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        INSERT INTO ai_assistance_result (
            result_id, task_id, input_type, output_type, content,
            confidence, evidence, model_name, prompt_version, created_at
        )
        SELECT result_id, task_id, input_type, output_type, content,
               confidence, evidence, model_name, prompt_version, created_at
        FROM ai_assistance_result_old
        """
    )
    connection.execute("DROP TABLE ai_assistance_result_old")
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_assistance_result_task_id
            ON ai_assistance_result (task_id)
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS ignore_pdf_field_candidate_ai
        BEFORE INSERT ON ai_assistance_result
        WHEN NEW.input_type = 'pdf_text' AND NEW.output_type = 'field_candidate'
        BEGIN
            SELECT RAISE(IGNORE);
        END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS dedupe_risk_suggestion_ai
        BEFORE INSERT ON ai_assistance_result
        WHEN NEW.input_type = 'risk_item' AND NEW.output_type = 'risk_suggestion'
        BEGIN
            DELETE FROM ai_assistance_result
            WHERE task_id = NEW.task_id
              AND input_type = NEW.input_type
              AND output_type = NEW.output_type
              AND json_extract(content, '$.risk_code') =
                  json_extract(NEW.content, '$.risk_code')
              AND json_extract(content, '$.risk_level') =
                  json_extract(NEW.content, '$.risk_level')
              AND json_extract(content, '$.original_message') =
                  json_extract(NEW.content, '$.original_message')
              AND evidence = NEW.evidence;
        END
        """
    )


def list_tables(db_path: Path | str = DEFAULT_DB_PATH) -> list[str]:
    connection = get_connection(db_path)
    try:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
            """
        ).fetchall()
    finally:
        connection.close()

    return [row["name"] for row in rows]


if __name__ == "__main__":
    database_path = init_database()
    print(f"Initialized database: {database_path}")
    print(f"Tables: {', '.join(list_tables(database_path))}")
