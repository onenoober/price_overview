from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]
PART_FEATURE_SCHEMA_PATH = REPO_ROOT / "docs" / "contracts" / "part_feature.schema.json"
PROCESS_ROUTE_SCHEMA_PATH = REPO_ROOT / "docs" / "contracts" / "process_route.schema.json"
QUANTITY_RESULT_SCHEMA_PATH = REPO_ROOT / "docs" / "contracts" / "quantity_result.schema.json"
QUOTE_RESULT_SCHEMA_PATH = REPO_ROOT / "docs" / "contracts" / "quote_result.schema.json"


class ContractValidationError(Exception):
    def __init__(self, details: list[dict[str, Any]]) -> None:
        self.details = details
        super().__init__("contract validation failed")


@lru_cache(maxsize=1)
def get_part_feature_validator() -> Draft202012Validator:
    schema = json.loads(PART_FEATURE_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_part_feature(part_feature: dict[str, Any]) -> None:
    validate_with(get_part_feature_validator(), part_feature)


@lru_cache(maxsize=1)
def get_process_route_validator() -> Draft202012Validator:
    schema = json.loads(PROCESS_ROUTE_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_process_route(process_route: dict[str, Any]) -> None:
    validate_with(get_process_route_validator(), process_route)


@lru_cache(maxsize=1)
def get_quantity_result_validator() -> Draft202012Validator:
    schema = json.loads(QUANTITY_RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_quantity_result(quantity_result: dict[str, Any]) -> None:
    validate_with(get_quantity_result_validator(), quantity_result)


@lru_cache(maxsize=1)
def get_quote_result_validator() -> Draft202012Validator:
    schema = json.loads(QUOTE_RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_quote_result(quote_result: dict[str, Any]) -> None:
    validate_with(get_quote_result_validator(), quote_result)


def validate_with(
    validator: Draft202012Validator,
    payload: dict[str, Any],
) -> None:
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: list(error.path),
    )

    if not errors:
        return

    details = []
    for error in errors:
        path = ".".join(str(item) for item in error.path) or "$"
        details.append(
            {
                "path": path,
                "message": error.message,
            }
        )

    raise ContractValidationError(details)
