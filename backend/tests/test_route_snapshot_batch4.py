"""16 件 PDF+STEP 黄金样件回归。

本测试会在本机存在 ``D:\test`` 样件目录时重跑 PDF/STEP 解析和 v2 路线引擎，
用于锁定 route_engine_v2_root_fix_plan.md 中的关键验收点。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from backend.app.domain_v2.route_engine import plan_route_v2
from backend.app.parser_service import build_parser_service
from backend.app.part_feature_builder import build_part_feature

SAMPLE_ROOT = Path(r"D:\test")
SNAPSHOT_PATH = Path(__file__).with_name("data") / "route_engine_snapshot_batch4.json"


def _file_record(path: Path, kind: str) -> dict[str, Any]:
    return {
        "file_id": f"{kind}_{path.name}",
        "storage_path": str(path),
        "filename": path.name,
        "file_type": kind,
    }


def _find_file(stem: str, suffix: str) -> Path | None:
    matches = sorted(SAMPLE_ROOT.rglob(stem + suffix))
    return matches[0] if matches else None


class RouteSnapshotBatch4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with SNAPSHOT_PATH.open(encoding="utf-8") as handle:
            cls.snapshot = json.load(handle)

    def setUp(self) -> None:
        if not SAMPLE_ROOT.exists():
            self.skipTest(r"D:\test sample directory is not available")
        missing = [
            stem
            for stem in self.snapshot
            if _find_file(stem, ".pdf") is None or _find_file(stem, ".step") is None
        ]
        if missing:
            self.skipTest("missing batch4 sample files: " + ", ".join(missing))

    def test_batch4_routes_match_snapshot(self) -> None:
        service = build_parser_service()
        for stem, expected in self.snapshot.items():
            with self.subTest(sample=stem):
                pdf_path = _find_file(stem, ".pdf")
                step_path = _find_file(stem, ".step")
                assert pdf_path is not None and step_path is not None
                task = {
                    "task_id": f"task_{stem}",
                    "part_name": stem,
                    "part_no": stem,
                    "quantity": 1,
                }
                risks: list[dict[str, Any]] = []
                pdf_result, pdf_risks = service.parse_pdf(
                    task=task, pdf_file=_file_record(pdf_path, "pdf")
                )
                step_result, step_risks = service.parse_step(
                    task=task, step_file=_file_record(step_path, "step")
                )
                risks.extend(pdf_risks)
                risks.extend(step_risks)
                part_feature = build_part_feature(task, pdf_result, step_result, risks)
                route = plan_route_v2(
                    task_id=task["task_id"],
                    route_id="route_v2",
                    part_feature=part_feature,
                    inherited_risks=list(risks),
                )

                geometry = part_feature.get("geometry") or {}
                category = geometry.get("pdf_part_category") or {}
                actual = {
                    "part_name": (pdf_result or {}).get("part_name"),
                    "pdf_category": category.get("category_name"),
                    "step_part_type": geometry.get("part_type"),
                    "family": route.get("family"),
                    "operations": [
                        operation.get("operation_code")
                        for operation in route.get("operations", [])
                    ],
                }
                self.assertEqual(actual, {key: expected[key] for key in actual})

    def test_batch4_critical_acceptance_assertions(self) -> None:
        for stem, expected in self.snapshot.items():
            operations = set(expected.get("operations") or [])
            with self.subTest(sample=stem):
                for op_code in expected.get("must_include") or []:
                    self.assertIn(op_code, operations, stem)
                for op_code in expected.get("forbidden_operations") or []:
                    self.assertNotIn(op_code, operations, stem)


if __name__ == "__main__":
    unittest.main()
