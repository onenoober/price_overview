from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.parser_service import ParserError, ParserService, RealStepParser


class StepParserIntegrationTests(unittest.TestCase):
    def test_real_step_parser_calls_standalone_parser(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            step_path = Path(temp_dir) / "part.step"
            step_path.write_text("ISO-10303-21;", encoding="utf-8")
            task = {"task_id": "task_001"}
            step_file = {
                "file_id": "file_step_001",
                "file_type": "step",
                "filename": "part.step",
                "storage_path": str(step_path),
            }
            parser_result = {
                "schema_version": "1.0",
                "task_id": "task_001",
                "file_id": "file_step_001",
                "backend": "cadquery",
                "bounding_box": {
                    "length": 1.0,
                    "width": 1.0,
                    "height": 1.0,
                    "unit": "mm",
                },
                "volume": {"value": 1.0, "unit": "mm3", "source": {}},
                "surface_area": {"value": 6.0, "unit": "mm2", "source": {}},
                "net_weight": {"value": None, "unit": None, "source": {}},
                "part_type_candidates": [],
                "holes": [],
                "hole_summary": {"total_count": 0, "by_type": {}, "by_diameter": {}},
                "hole_groups": [],
                "counterbore_candidates": [],
                "slot_candidates": [],
                "profile_summary": {},
                "complexity": {"complexity_score": 0},
                "geometry_risks": [],
            }

            with patch(
                "backend.app.parser_service.load_standalone_step_parser",
                return_value=lambda *args, **kwargs: parser_result,
            ) as load_parser:
                result = RealStepParser().parse(task=task, step_file=step_file)

        load_parser.assert_called_once()
        self.assertEqual(result["parser_name"], "real_step_geometry_parser")
        self.assertEqual(result["backend"], "cadquery")
        self.assertEqual(result["file_id"], "file_step_001")

    def test_real_step_parser_passes_material_density(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            step_path = Path(temp_dir) / "part.step"
            step_path.write_text("ISO-10303-21;", encoding="utf-8")
            task = {"task_id": "task_001"}
            step_file = {
                "file_id": "file_step_001",
                "file_type": "step",
                "filename": "part.step",
                "storage_path": str(step_path),
            }
            parser_result = {
                "schema_version": "1.0",
                "task_id": "task_001",
                "file_id": "file_step_001",
                "backend": "cadquery",
                "bounding_box": {
                    "length": 1.0,
                    "width": 1.0,
                    "height": 1.0,
                    "unit": "mm",
                },
                "volume": {"value": 187221.7357, "unit": "mm3", "source": {}},
                "surface_area": {"value": 6.0, "unit": "mm2", "source": {}},
                "net_weight": {
                    "value": 1.469690625245,
                    "unit": "kg",
                    "density": 0.00000785,
                    "density_unit": "kg/mm3",
                    "source": {},
                },
                "part_type_candidates": [],
                "holes": [],
                "hole_summary": {"total_count": 0, "by_type": {}, "by_diameter": {}},
                "hole_groups": [],
                "counterbore_candidates": [],
                "slot_candidates": [],
                "profile_summary": {},
                "complexity": {"complexity_score": 0},
                "geometry_risks": [],
            }
            calls = []

            def fake_parse_step_file(*args, **kwargs):
                calls.append(kwargs)
                return parser_result

            with patch(
                "backend.app.parser_service.load_standalone_step_parser",
                return_value=fake_parse_step_file,
            ):
                result = RealStepParser().parse(
                    task=task,
                    step_file=step_file,
                    material_density={
                        "density_kg_mm3": 0.00000785,
                        "source": {
                            "source_type": "price_rule",
                            "rule_code": "MATERIAL_DENSITY_ARCHIVE",
                        },
                    },
                )

        self.assertEqual(calls[0]["density"], 0.00000785)
        self.assertEqual(calls[0]["density_unit"], "kg/mm3")
        self.assertEqual(
            result["net_weight"]["density_source"]["rule_code"],
            "MATERIAL_DENSITY_ARCHIVE",
        )

    def test_auto_step_parse_failure_returns_structured_risk(self) -> None:
        class FailingStepParser:
            parser_name = "real_step_geometry_parser"

            def parse(self, *, task, step_file):
                raise ParserError("STEP_PARSE_FAILED", "bad step")

        service = ParserService(
            mode="auto",
            pdf_parser=FailingStepParser(),
            step_parser=FailingStepParser(),
        )
        step_result, risks = service.parse_step(
            task={"task_id": "task_001"},
            step_file={
                "file_id": "file_step_001",
                "file_type": "step",
                "filename": "part.step",
                "storage_path": "part.step",
            },
        )

        self.assertIsNone(step_result)
        self.assertEqual([risk["code"] for risk in risks], ["STEP_PARSE_FAILED"])
        self.assertIn("未生成替代解析结果", risks[0]["message"])


if __name__ == "__main__":
    unittest.main()
