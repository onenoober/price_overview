from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.app.material_archive import MaterialArchiveRecord, lookup_material_density


class MaterialArchiveTests(unittest.TestCase):
    def test_lookup_pdf_material_45_density(self) -> None:
        with patch(
            "backend.app.material_archive.material_archive_records",
            return_value=(
                MaterialArchiveRecord(
                    material_name="45#钢",
                    spec="",
                    unit="kg",
                    unit_price=None,
                    density_g_cm3=7.85,
                    archive_file="test.xlsx",
                ),
            ),
        ):
            match = lookup_material_density("45")

        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.material_name, "45#钢")
        self.assertEqual(match.density_g_cm3, 7.85)
        self.assertEqual(match.density_kg_mm3, 0.00000785)
        self.assertEqual(match.to_step_density()["density_unit"], "kg/mm3")


if __name__ == "__main__":
    unittest.main()
