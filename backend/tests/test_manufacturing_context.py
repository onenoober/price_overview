from __future__ import annotations

import unittest

from backend.app.domain_v2.facts import EvidenceRef, FactSnapshot, FactValue
from backend.app.domain_v2.manufacturing_context import ManufacturingContextResolver


class ManufacturingContextResolverTests(unittest.TestCase):
    def test_resolves_golden_sheet_metal_context_without_route_conclusion(self) -> None:
        evidence = EvidenceRef(
            source_type="user",
            source_file_id="golden-sheet-metal",
            extractor_version="golden-v1",
        )
        snapshot = FactSnapshot.from_values(
            (
                FactValue(key="material", value="SUS304", evidence=[evidence]),
                FactValue(key="thickness_mm", value=2.0, unit="mm", evidence=[evidence]),
                FactValue(key="equal_thickness", value=True, evidence=[evidence]),
                FactValue(key="hole_count", value=4, evidence=[evidence]),
                FactValue(key="bend_count", value=1, evidence=[evidence]),
                FactValue(key="bend_angles", value=[90], unit="deg", evidence=[evidence]),
            )
        )

        context = ManufacturingContextResolver().resolve(snapshot)

        self.assertEqual(context.geometry_class, "sheet_like")
        self.assertEqual([candidate.stock_form for candidate in context.stock_candidates], ["sheet"])
        self.assertEqual(
            [candidate.family for candidate in context.family_candidates],
            ["sheet_metal"],
        )
        self.assertIn("hole_finishing", context.required_secondary_families)
        self.assertEqual(context.support_level, "L3")
        self.assertEqual(context.conflicts, [])
        self.assertFalse(hasattr(context, "process_route"))
        self.assertNotIn("route", context.family_candidates[0].attributes)

    def test_conflicting_material_facts_downgrade_support(self) -> None:
        snapshot = FactSnapshot.from_values(
            (
                FactValue(key="material", value="SUS304"),
                FactValue(key="material.grade", value="AL6061"),
                FactValue(key="thickness_mm", value=2.0),
                FactValue(key="equal_thickness", value=True),
                FactValue(key="hole_count", value=1),
                FactValue(key="bend_count", value=1),
                FactValue(key="bend_angles", value=[90]),
            )
        )

        context = ManufacturingContextResolver().resolve(snapshot)

        self.assertEqual(context.geometry_class, "sheet_like")
        self.assertEqual(len(context.conflicts), 1)
        self.assertEqual(context.conflicts[0].field, "material")
        self.assertEqual(context.support_level, "L1")


if __name__ == "__main__":
    unittest.main()
