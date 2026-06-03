from __future__ import annotations

from collections.abc import Iterable
from datetime import date
import json
from pathlib import Path
import sqlite3
from typing import Any

from .contract_validation import validate_a_outputs, validate_contract
from .history import validate_quote_history_sample
from .price_rules import PriceRule, validate_price_rules


SCHEMA_VERSION = 1


class PricingStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS quote_task (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    latest_quote_id TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS part_feature (
                    task_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS process_route (
                    route_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS engineering_quantity (
                    route_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS quote_result (
                    quote_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    price_version TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS quote_item (
                    quote_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    item_type TEXT NOT NULL,
                    operation_code TEXT,
                    system_amount REAL,
                    final_amount REAL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (quote_id, item_id)
                );

                CREATE TABLE IF NOT EXISTS quote_summary (
                    quote_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS human_override (
                    quote_id TEXT NOT NULL,
                    override_id TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    field TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    operator_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (quote_id, override_id)
                );

                CREATE TABLE IF NOT EXISTS quote_history_sample (
                    sample_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    quote_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS price_rule (
                    rule_id TEXT PRIMARY KEY,
                    price_type TEXT NOT NULL,
                    target_code TEXT NOT NULL,
                    unit TEXT,
                    unit_price TEXT NOT NULL,
                    min_amount TEXT,
                    setup_fee TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    effective_from TEXT,
                    effective_to TEXT,
                    approval_status TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS price_source_record (
                    source_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    latest_rule_count INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (?)", (SCHEMA_VERSION,))

    def save_pricing_result(self, pricing_result: dict[str, Any]) -> None:
        validate_contract(pricing_result["part_feature"], "part_feature.schema.json")
        validate_a_outputs(pricing_result)
        part_feature = pricing_result["part_feature"]
        process_route = pricing_result["process_route"]
        quantity_result = pricing_result["quantity_result"]
        quote_result = pricing_result["quote_result"]
        task_id = quote_result["task_id"]
        quote_id = quote_result["quote_id"]

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO quote_task (task_id, status, latest_quote_id)
                VALUES (?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET status = excluded.status, latest_quote_id = excluded.latest_quote_id, updated_at = CURRENT_TIMESTAMP
                """,
                (task_id, quote_result["status"], quote_id),
            )
            conn.execute(
                """
                INSERT INTO part_feature (task_id, payload)
                VALUES (?, ?)
                ON CONFLICT(task_id) DO UPDATE SET payload = excluded.payload, updated_at = CURRENT_TIMESTAMP
                """,
                (task_id, dumps(part_feature)),
            )
            conn.execute(
                "INSERT OR REPLACE INTO process_route (route_id, task_id, payload) VALUES (?, ?, ?)",
                (process_route["route_id"], task_id, dumps(process_route)),
            )
            conn.execute(
                "INSERT OR REPLACE INTO engineering_quantity (route_id, task_id, payload) VALUES (?, ?, ?)",
                (quantity_result["route_id"], task_id, dumps(quantity_result)),
            )
            conn.execute(
                """
                INSERT INTO quote_result (quote_id, task_id, status, price_version, payload)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(quote_id) DO UPDATE SET status = excluded.status, price_version = excluded.price_version, payload = excluded.payload, updated_at = CURRENT_TIMESTAMP
                """,
                (quote_id, task_id, quote_result["status"], quote_result["price_version"], dumps(quote_result)),
            )
            conn.execute("DELETE FROM quote_item WHERE quote_id = ?", (quote_id,))
            conn.executemany(
                "INSERT INTO quote_item (quote_id, item_id, item_type, operation_code, system_amount, final_amount, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        quote_id,
                        item["item_id"],
                        item["item_type"],
                        item.get("operation_code"),
                        item.get("system_amount"),
                        item.get("final_amount"),
                        dumps(item),
                    )
                    for item in quote_result["items"]
                ],
            )
            conn.execute(
                "INSERT OR REPLACE INTO quote_summary (quote_id, payload) VALUES (?, ?)",
                (quote_id, dumps(quote_result["summary"])),
            )
            conn.execute("DELETE FROM human_override WHERE quote_id = ?", (quote_id,))
            conn.executemany(
                "INSERT INTO human_override (quote_id, override_id, target_type, target_id, field, reason, operator_id, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        quote_id,
                        override["override_id"],
                        override["target_type"],
                        override["target_id"],
                        override["field"],
                        override["reason"],
                        override["operator_id"],
                        dumps(override),
                    )
                    for override in quote_result["manual_overrides"]
                ],
            )

    def get_quote_result(self, quote_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT payload FROM quote_result WHERE quote_id = ?", (quote_id,)).fetchone()
        return loads(row["payload"]) if row else None

    def save_history_sample(self, sample: dict[str, Any]) -> None:
        validate_quote_history_sample(sample)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO quote_history_sample (sample_id, task_id, quote_id, created_at, payload)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(sample_id) DO UPDATE SET payload = excluded.payload
                """,
                (sample["sample_id"], sample["task_id"], sample["quote_id"], sample["created_at"], dumps(sample)),
            )

    def list_history_samples(self, task_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT payload FROM quote_history_sample"
        params: tuple[str, ...] = ()
        if task_id is not None:
            query += " WHERE task_id = ?"
            params = (task_id,)
        query += " ORDER BY created_at, sample_id"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [loads(row["payload"]) for row in rows]

    def save_price_rules(self, rules: Iterable[PriceRule]) -> None:
        rule_list = list(rules)
        errors = validate_price_rules(rule_list)
        if errors:
            raise ValueError("; ".join(errors))
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO price_rule (
                    rule_id, price_type, target_code, unit, unit_price, min_amount, setup_fee,
                    source_type, source_id, version, effective_from, effective_to,
                    approval_status, priority, payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rule_id) DO UPDATE SET
                    price_type = excluded.price_type,
                    target_code = excluded.target_code,
                    unit = excluded.unit,
                    unit_price = excluded.unit_price,
                    min_amount = excluded.min_amount,
                    setup_fee = excluded.setup_fee,
                    source_type = excluded.source_type,
                    source_id = excluded.source_id,
                    version = excluded.version,
                    effective_from = excluded.effective_from,
                    effective_to = excluded.effective_to,
                    approval_status = excluded.approval_status,
                    priority = excluded.priority,
                    payload = excluded.payload
                """,
                [price_rule_row(rule) for rule in rule_list],
            )
            for source_key, source_rules in group_by_source(rule_list).items():
                source_type, source_id = source_key
                conn.execute(
                    """
                    INSERT INTO price_source_record (source_id, source_type, latest_rule_count)
                    VALUES (?, ?, ?)
                    ON CONFLICT(source_id) DO UPDATE SET source_type = excluded.source_type, latest_rule_count = excluded.latest_rule_count, updated_at = CURRENT_TIMESTAMP
                    """,
                    (source_id, source_type, len(source_rules)),
                )

    def load_price_rules(self, *, active_only: bool = False, as_of_date: date | None = None, version: str | None = None) -> list[PriceRule]:
        with self.connect() as conn:
            rows = conn.execute("SELECT payload FROM price_rule ORDER BY price_type, target_code, priority, rule_id").fetchall()
        rules = [PriceRule.from_dict(loads(row["payload"])) for row in rows]
        if not active_only:
            return rules
        match_date = as_of_date or date.today()
        match_version = version or (rules[0].version if rules else "")
        return [rule for rule in rules if rule.is_active(as_of_date=match_date, version=match_version)]

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


def price_rule_row(rule: PriceRule) -> tuple[Any, ...]:
    payload = rule.to_dict()
    return (
        rule.rule_id,
        rule.price_type,
        rule.target_code,
        rule.unit,
        str(rule.unit_price),
        str(rule.min_amount) if rule.min_amount is not None else None,
        str(rule.setup_fee),
        rule.source_type,
        rule.source_id,
        rule.version,
        rule.effective_from.isoformat() if rule.effective_from else None,
        rule.effective_to.isoformat() if rule.effective_to else None,
        rule.approval_status,
        rule.priority,
        dumps(payload),
    )


def group_by_source(rules: list[PriceRule]) -> dict[tuple[str, str], list[PriceRule]]:
    result: dict[tuple[str, str], list[PriceRule]] = {}
    for rule in rules:
        result.setdefault((rule.source_type, rule.source_id), []).append(rule)
    return result


def dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def loads(payload: str) -> dict[str, Any]:
    return json.loads(payload)
