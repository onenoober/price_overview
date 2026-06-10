from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import unittest


PARSER_ROOT = Path(__file__).resolve().parents[1]
if str(PARSER_ROOT) not in sys.path:
    sys.path.insert(0, str(PARSER_ROOT))

from step_parser import parse_step_file


DEFAULT_STEP_FILE = Path(
    "C:/Users/Administrator/Desktop/"
    "\u56fe\u7247\u5206\u9009/\u56fe\u7247\u5206\u9009/result/"
    "\u5927\u677f/RM-JJ-00083694-01.step"
)


def cad_backend_available() -> bool:
    return importlib.util.find_spec("OCC") is not None or importlib.util.find_spec("cadquery") is not None


@unittest.skipUnless(DEFAULT_STEP_FILE.exists(), f"STEP file not found: {DEFAULT_STEP_FILE}")
@unittest.skipUnless(cad_backend_available(), "cadquery or pythonocc-core is required to parse STEP files.")
class RealStepReadTests(unittest.TestCase):
    def test_parse_rm_jj_00083694_01_step_extracts_geometry(self) -> None:
        step_file = Path(os.environ.get("STEP_PARSER_REAL_STEP", DEFAULT_STEP_FILE))
        result = parse_step_file(
            step_file,
            task_id="task_real_step_rm_jj_00083694_01",
            file_id="file_rm_jj_00083694_01",
            backend=os.environ.get("STEP_PARSER_BACKEND", "auto"),
        )

        risk_codes = {risk["code"] for risk in result["geometry_risks"]}
        self.assertNotIn("MISSING_STEP", risk_codes)
        self.assertNotIn("STEP_PARSE_FAILED", risk_codes)
        self.assertIn(result["backend"], {"pythonocc", "cadquery"})

        bbox = result["bounding_box"]
        self.assertGreater(bbox["length"], 0)
        self.assertGreater(bbox["width"], 0)
        self.assertGreater(bbox["height"], 0)
        self.assertEqual(bbox["unit"], "mm")

        self.assertGreater(result["volume"]["value"], 0)
        self.assertEqual(result["volume"]["unit"], "mm3")
        self.assertGreater(result["surface_area"]["value"], 0)
        self.assertEqual(result["surface_area"]["unit"], "mm2")

        complexity = result["complexity"]
        self.assertGreater(complexity["face_count"], 0)
        self.assertGreater(complexity["edge_count"], 0)
        self.assertGreaterEqual(complexity["complexity_score"], 0)
        self.assertLessEqual(complexity["complexity_score"], 100)

        profile_summary = result["profile_summary"]
        self.assertGreater(profile_summary["outer_profile_length"], 0)
        self.assertGreater(profile_summary["outer_line_length"], 0)
        self.assertGreaterEqual(profile_summary["outer_arc_length"], 0)
        self.assertGreater(profile_summary["outer_line_count"], 0)
        self.assertGreater(profile_summary["inner_profile_length"], 0)
        self.assertGreater(profile_summary["inner_arc_length"], 0)
        self.assertGreater(profile_summary["inner_arc_count"], 0)
        self.assertGreater(profile_summary["inner_profile_count"], 0)
        self.assertGreater(profile_summary["circular_inner_profile_count"], 0)
        self.assertGreater(profile_summary["total_edge_length"], 0)
        self.assertGreater(profile_summary["top_profile_length"], 0)
        self.assertGreater(profile_summary["circular_edge_count"], 0)
        self.assertGreaterEqual(profile_summary["slot_candidate_count"], 0)

        self.assertIsInstance(result["holes"], list)
        self.assertGreater(sum(item["count"] for item in result["holes"]), 0)
        self.assertEqual(result["hole_summary"]["total_count"], sum(item["count"] for item in result["holes"]))
        self.assertGreater(result["hole_summary"]["by_type"].get("through", 0), 0)
        self.assertIsInstance(result["hole_groups"], list)
        self.assertGreater(len(result["hole_groups"]), 0)
        self.assertGreater(sum(group["count"] for group in result["hole_groups"]), 0)
        self.assertIsInstance(result["counterbore_candidates"], list)
        self.assertIsInstance(result["slot_candidates"], list)
        for slot in result["slot_candidates"]:
            self.assertGreater(slot["avg_profile_length"], 0)
            self.assertGreater(slot["avg_length"], 0)
            self.assertGreater(slot["avg_width"], 0)
        self.assertIsInstance(result["part_type_candidates"], list)


if __name__ == "__main__":
    unittest.main()
