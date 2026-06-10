from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


PARSER_ROOT = Path(__file__).resolve().parent
if str(PARSER_ROOT) not in sys.path:
    sys.path.insert(0, str(PARSER_ROOT))

from step_parser import build_part_feature_stub, parse_step_file


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    result = parse_step_file(
        args.input,
        task_id=args.task_id,
        file_id=args.file_id,
        density=args.density,
        density_unit=args.density_unit,
        backend=args.backend,
    )
    write_json(result, args.output)

    if args.part_feature_output:
        part_feature = build_part_feature_stub(
            result,
            part_name=args.part_name,
            drawing_no=args.drawing_no,
            revision=args.revision,
            quantity=args.quantity,
            material_code=args.material_code,
            material_name=args.material_name,
            density=args.density,
            density_unit=args.density_unit if args.density is not None else None,
        )
        write_json(part_feature, args.part_feature_output)

    has_blocking_risk = any(risk.get("level") == "blocking" for risk in result.get("geometry_risks", []))
    return 2 if has_blocking_risk else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Standalone STEP geometry parser.")
    parser.add_argument("input", help="Path to .step or .stp file.")
    parser.add_argument("--output", help="Write step_feature_result JSON to this path. Defaults to stdout.")
    parser.add_argument("--task-id", help="Quote task id.")
    parser.add_argument("--file-id", help="STEP file id. Defaults to input file stem.")
    parser.add_argument("--backend", choices=["auto", "pythonocc", "cadquery"], default="auto")
    parser.add_argument("--density", type=float, help="Optional material density.")
    parser.add_argument("--density-unit", choices=["kg/mm3", "g/cm3"], default="kg/mm3")

    parser.add_argument("--part-feature-output", help="Optional path for an A-side part_feature-like JSON stub.")
    parser.add_argument("--part-name")
    parser.add_argument("--drawing-no")
    parser.add_argument("--revision")
    parser.add_argument("--quantity", type=float, default=1)
    parser.add_argument("--material-code")
    parser.add_argument("--material-name")
    return parser


def write_json(payload: dict[str, Any], output: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    raise SystemExit(main())
