from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_DIR = REPO_ROOT / "docs" / "contracts"


def validate_contract(instance: dict[str, Any], schema_name: str) -> None:
    schema = json.loads((CONTRACT_DIR / schema_name).read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(instance)


def validate_a_outputs(result: dict[str, Any]) -> None:
    validate_contract(result["process_route"], "process_route.schema.json")
    validate_contract(result["quantity_result"], "quantity_result.schema.json")
    validate_contract(result["quote_result"], "quote_result.schema.json")

