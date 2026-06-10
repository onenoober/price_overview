from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from typing import Any
import zipfile


PARSER_ROOT = Path(__file__).resolve().parent
if str(PARSER_ROOT) not in sys.path:
    sys.path.insert(0, str(PARSER_ROOT))

from step_parser import parse_step_file


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = parse_zip(
        Path(args.zip),
        prefix=args.prefix,
        backend=args.backend,
        output=Path(args.output) if args.output else None,
        keep_extracted=args.keep_extracted,
    )
    print(json.dumps(summary_payload(report), ensure_ascii=False, indent=2))
    return 0 if report["failed_count"] == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch parse STEP/STP files from a ZIP archive.")
    parser.add_argument("--zip", required=True, help="ZIP file path.")
    parser.add_argument("--prefix", default="", help="Only parse ZIP members under this prefix.")
    parser.add_argument("--backend", choices=["auto", "cadquery", "pythonocc"], default="cadquery")
    parser.add_argument("--output", help="Write full JSON report to this path.")
    parser.add_argument("--keep-extracted", action="store_true", help="Keep temporary extracted STEP files.")
    return parser


def parse_zip(zip_path: Path, *, prefix: str, backend: str, output: Path | None, keep_extracted: bool) -> dict[str, Any]:
    if not zip_path.exists():
        raise FileNotFoundError(zip_path)
    extract_dir = Path(tempfile.mkdtemp(prefix="step_parser_batch_"))
    results: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = sorted(
                name
                for name in zf.namelist()
                if name.startswith(prefix) and name.lower().endswith((".step", ".stp"))
            )
            for index, name in enumerate(names, start=1):
                results.append(parse_member(zf, name, index, extract_dir, backend))
    finally:
        if not keep_extracted and extract_dir.exists():
            shutil.rmtree(extract_dir)

    report = build_report(zip_path, prefix, results)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def parse_member(zf: zipfile.ZipFile, name: str, index: int, extract_dir: Path, backend: str) -> dict[str, Any]:
    parts = name.split("/")
    category = parts[-2] if len(parts) >= 2 else ""
    local_path = extract_dir / str(index) / Path(name).name
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(zf.read(name))

    start = time.time()
    try:
        parsed = parse_step_file(local_path, task_id=f"batch_{index}", file_id=Path(name).stem, backend=backend)
        elapsed = round(time.time() - start, 3)
        risks = [risk["code"] for risk in parsed.get("geometry_risks", [])]
        bbox = parsed["bounding_box"]
        profile = parsed.get("profile_summary", {})
        return {
            "index": index,
            "category": category,
            "file": Path(name).name,
            "zip_member": name,
            "file_size": zf.getinfo(name).file_size,
            "success": "STEP_PARSE_FAILED" not in risks and "MISSING_STEP" not in risks,
            "elapsed_sec": elapsed,
            "bbox": {"length": bbox.get("length"), "width": bbox.get("width"), "height": bbox.get("height")},
            "part_type": parsed["part_type_candidates"][0]["part_type"] if parsed.get("part_type_candidates") else None,
            "part_type_candidates": parsed.get("part_type_candidates", [])[:3],
            "hole_count": parsed["hole_summary"]["total_count"],
            "hole_by_diameter": parsed["hole_summary"]["by_diameter"],
            "hole_group_count": len(parsed.get("hole_groups", [])),
            "counterbore_count": sum(item.get("count", 0) for item in parsed.get("counterbore_candidates", [])),
            "slot_candidate_count": sum(item.get("count", 0) for item in parsed.get("slot_candidates", [])),
            "inner_profile_count": profile.get("inner_profile_count"),
            "outer_profile_length": profile.get("outer_profile_length"),
            "inner_profile_length": profile.get("inner_profile_length"),
            "top_profile_length": profile.get("top_profile_length"),
            "complexity_score": parsed["complexity"].get("complexity_score"),
            "risk_codes": risks,
        }
    except Exception as exc:
        return {
            "index": index,
            "category": category,
            "file": Path(name).name,
            "zip_member": name,
            "file_size": zf.getinfo(name).file_size,
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def build_report(zip_path: Path, prefix: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    category_summary: dict[str, Any] = {}
    for category in sorted({item["category"] for item in results}):
        items = [item for item in results if item["category"] == category]
        success_items = [item for item in items if item.get("success")]
        category_summary[category] = {
            "count": len(items),
            "success": len(success_items),
            "failed": len(items) - len(success_items),
            "part_types": dict(Counter(item.get("part_type") for item in success_items)),
            "avg_complexity": round(sum((item.get("complexity_score") or 0) for item in success_items) / max(1, len(success_items)), 2),
            "total_holes": sum(item.get("hole_count") or 0 for item in success_items),
            "total_slots": sum(item.get("slot_candidate_count") or 0 for item in success_items),
            "total_counterbores": sum(item.get("counterbore_count") or 0 for item in success_items),
            "risk_count": sum(1 for item in success_items if item.get("risk_codes")),
        }
    return {
        "zip_path": str(zip_path),
        "prefix": prefix,
        "sample_count": len(results),
        "success_count": sum(1 for item in results if item.get("success")),
        "failed_count": sum(1 for item in results if not item.get("success")),
        "category_summary": category_summary,
        "failures": [item for item in results if not item.get("success")],
        "results": results,
    }


def summary_payload(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_count": report["sample_count"],
        "success_count": report["success_count"],
        "failed_count": report["failed_count"],
        "category_summary": report["category_summary"],
        "failures": report["failures"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
