"""L4 策略矩阵逐项断言（方案 §3.1–3.4）。"""

from __future__ import annotations

import unittest

from backend.app.domain_v2.route_engine.families import (
    LARGE_PLATE,
    MACHINING,
    SHEET_METAL,
    TURNING,
)
from backend.app.domain_v2.route_engine.policy import (
    ALLOW,
    CONDITIONAL,
    CONDITIONAL_GEOMETRY,
    DENY,
    REQUIRED,
    policy,
)


class PolicyMatrixTests(unittest.TestCase):
    def test_sheet_metal_denies_machining_family_operations(self) -> None:
        for op in (
            "cnc_rough_milling",
            "cnc_finish_milling",
            "profile_milling",
            "pocket_milling",
            "edm",
            "wire_cut_profile",
            "surface_grinding_rough",
            "saw_cut",
            "turning",
        ):
            self.assertEqual(policy(SHEET_METAL, op), DENY, op)

    def test_sheet_metal_required_and_conditional(self) -> None:
        for op in ("laser_cut_blank", "deburr", "inspection", "protective_packaging"):
            self.assertEqual(policy(SHEET_METAL, op), REQUIRED, op)
        # PR1：折弯不再必经，改为需证据的条件工序。
        self.assertEqual(policy(SHEET_METAL, "bending"), CONDITIONAL)
        self.assertEqual(policy(SHEET_METAL, "sheet_metal_welding"), CONDITIONAL)
        self.assertEqual(policy(SHEET_METAL, "powder_coating"), CONDITIONAL)

    def test_turning_requires_turning_and_denies_milling(self) -> None:
        self.assertEqual(policy(TURNING, "turning"), REQUIRED)
        for op in (
            "cnc_rough_milling",
            "cnc_finish_milling",
            "edm",
            "pocket_milling",
            "wire_cut_profile",
            "surface_grinding_rough",
        ):
            self.assertEqual(policy(TURNING, op), DENY, op)
        self.assertEqual(policy(TURNING, "cylindrical_grinding"), CONDITIONAL)
        self.assertEqual(policy(TURNING, "heat_treatment"), CONDITIONAL)

    def test_large_plate_allows_grinding_and_gates_edm_on_geometry(self) -> None:
        self.assertEqual(policy(LARGE_PLATE, "surface_grinding_rough"), ALLOW)
        for op in ("edm", "wire_cut_profile", "pocket_milling"):
            self.assertEqual(policy(LARGE_PLATE, op), CONDITIONAL_GEOMETRY, op)
        for op in ("large_plate_roughing", "large_plate_finishing", "flatness_inspection"):
            self.assertEqual(policy(LARGE_PLATE, op), REQUIRED, op)

    def test_machining_main_line_required_and_extras_conditional(self) -> None:
        for op in ("cnc_rough_milling", "cnc_finish_milling", "deburr", "inspection"):
            self.assertEqual(policy(MACHINING, op), REQUIRED, op)
        for op in (
            "stress_relief",
            "surface_grinding_rough",
            "wire_cut_profile",
            "support_anti_deformation",
            "soft_jaw_fixture",
            "edm",
        ):
            self.assertEqual(policy(MACHINING, op), CONDITIONAL, op)

    def test_unknown_operation_defaults_to_conditional(self) -> None:
        self.assertEqual(policy(MACHINING, "some_unlisted_op"), CONDITIONAL)


if __name__ == "__main__":
    unittest.main()
