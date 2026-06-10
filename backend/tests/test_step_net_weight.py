from __future__ import annotations

import unittest

from standalone_step_parser.step_parser.parser import calculate_net_weight


class StepNetWeightTests(unittest.TestCase):
    def test_calculates_kg_from_kg_per_mm3_without_rounding(self) -> None:
        result = calculate_net_weight(187221.7357, 0.00000785, "kg/mm3")

        self.assertAlmostEqual(result, 1.469690625245, places=12)

    def test_calculates_kg_from_g_per_cm3(self) -> None:
        result = calculate_net_weight(187221.7357, 7.85, "g/cm3")

        self.assertAlmostEqual(result, 1.469690625245, places=12)


if __name__ == "__main__":
    unittest.main()
