from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from price_overview.pricing_core import run_mock_pricing
from price_overview.pricing_core.contract_validation import validate_a_outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the A-side mock pricing pipeline.")
    parser.add_argument("--input", default=str(REPO_ROOT / "fixtures" / "mock" / "part_feature_plate_skd11.json"))
    parser.add_argument("--output")
    args = parser.parse_args()

    part_feature = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = run_mock_pricing(part_feature)
    validate_a_outputs(result)

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

