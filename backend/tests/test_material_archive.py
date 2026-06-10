from __future__ import annotations

import unittest

from backend.app.material_archive import lookup_material_density


class MaterialArchiveTests(unittest.TestCase):
    def test_lookup_pdf_material_45_density(self) -> None:
        match = lookup_material_density("45")

        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.material_name, "45#钢")
        self.assertEqual(match.density_g_cm3, 7.85)
        self.assertEqual(match.density_kg_mm3, 0.00000785)
        self.assertEqual(match.to_step_density()["density_unit"], "kg/mm3")


if __name__ == "__main__":
    unittest.main()
