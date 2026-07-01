"""12 样本路线快照回归（方案 §5 回归基线）。

用 ``_samples`` 中冻结的 ``part_feature_summary`` 作为输入（不重跑重解析），对新引擎输出的
operation_code 序列做快照断言。每次改规则都对比 diff；新增/删除工序必须能解释来源，否则此测试
拦截。样本目录不存在时自动跳过（CI 无样本环境）。
"""

from __future__ import annotations

import glob
import json
import os
import unittest

from backend.app.domain_v2.route_engine import plan_route_v2
from backend.app.schema_validation import validate_process_route

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SAMPLE_GLOB = os.path.join(_REPO_ROOT, "_samples", "*", "run_outputs", "RM-*.json")
_SNAPSHOT_PATH = os.path.join(os.path.dirname(__file__), "data", "route_engine_snapshot.json")


def _load_samples() -> dict[str, dict]:
    samples: dict[str, dict] = {}
    for path in sorted(glob.glob(_SAMPLE_GLOB)):
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        part_feature = payload.get("part_feature_summary")
        if isinstance(part_feature, dict):
            samples[os.path.splitext(os.path.basename(path))[0]] = part_feature
    return samples


class RouteSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.samples = _load_samples()
        if not self.samples:
            self.skipTest("no _samples present")
        with open(_SNAPSHOT_PATH, encoding="utf-8") as handle:
            self.snapshot = json.load(handle)

    def test_engine_output_matches_committed_snapshot(self) -> None:
        for stem, part_feature in self.samples.items():
            with self.subTest(sample=stem):
                route = plan_route_v2(
                    task_id="t", route_id="r", part_feature=part_feature, inherited_risks=[]
                )
                validate_process_route(route)
                actual = {
                    "family": route["family"],
                    "operations": [op["operation_code"] for op in route["operations"]],
                }
                expected = self.snapshot.get(stem)
                self.assertIsNotNone(expected, f"missing snapshot for {stem}")
                self.assertEqual(actual, expected, stem)

    def test_no_non_evidence_machining_explosion(self) -> None:
        # 量级控制：任一样本主路线工序数远小于旧链 20–38。
        for stem, part_feature in self.samples.items():
            with self.subTest(sample=stem):
                route = plan_route_v2(
                    task_id="t", route_id="r", part_feature=part_feature, inherited_risks=[]
                )
                self.assertLessEqual(len(route["operations"]), 20, stem)


if __name__ == "__main__":
    unittest.main()
