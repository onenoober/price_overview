from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .database import DEFAULT_DB_PATH, get_connection, init_database


CHINA_TZ = timezone(timedelta(hours=8))


def now_iso() -> str:
    return datetime.now(CHINA_TZ).isoformat(timespec="seconds")


def seed_task_001() -> None:
    init_database(DEFAULT_DB_PATH)
    now = now_iso()
    connection = get_connection(DEFAULT_DB_PATH)
    try:
        existing = connection.execute(
            """
            SELECT status, created_at
            FROM quote_task
            WHERE task_id = ?
            """,
            ("task_001",),
        ).fetchone()

        status = existing["status"] if existing else "draft"
        created_at = existing["created_at"] if existing else now
        connection.execute(
            """
            INSERT INTO quote_task (
                task_id, customer_name, part_name, part_no, quantity,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                customer_name = excluded.customer_name,
                part_name = excluded.part_name,
                part_no = excluded.part_no,
                quantity = excluded.quantity,
                updated_at = excluded.updated_at
            """,
            (
                "task_001",
                "测试客户",
                "测试零件",
                "P-001",
                1,
                status,
                created_at,
                now,
            ),
        )
        connection.commit()
    finally:
        connection.close()


if __name__ == "__main__":
    seed_task_001()
    print("Seeded task_001 with UTF-8 Chinese test data.")
