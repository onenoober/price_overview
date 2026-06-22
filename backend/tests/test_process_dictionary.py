from __future__ import annotations

import unittest

from backend.app.process_dictionary import (
    PROCESS_APPLICABLE_SCENARIOS,
    PROCESS_DEFINITIONS,
    PROCESS_DICTIONARY,
    PROCESS_SEQUENCE,
    normalize_process_code,
    process_name_for_code,
)


class ProcessDictionaryTests(unittest.TestCase):
    def test_process_codes_are_unique_and_ordered(self) -> None:
        codes = [definition.process_code for definition in PROCESS_DEFINITIONS]
        sequences = [definition.sequence for definition in PROCESS_DEFINITIONS]

        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(len(sequences), len(set(sequences)))
        self.assertEqual(
            PROCESS_SEQUENCE,
            [
                definition.process_code
                for definition in sorted(
                    PROCESS_DEFINITIONS,
                    key=lambda item: item.sequence,
                )
            ],
        )

    def test_legacy_operation_codes_normalize_to_dictionary_codes(self) -> None:
        self.assertEqual(normalize_process_code("CNC"), "cnc_milling")
        self.assertEqual(normalize_process_code("DEBURRING"), "deburr")
        self.assertEqual(normalize_process_code("edge_chamfer"), "deburr")
        self.assertEqual(normalize_process_code("post_plating_inspection"), "surface_inspection")
        self.assertEqual(normalize_process_code("anti_bending_packaging"), "protective_packaging")
        self.assertEqual(normalize_process_code("rust_prevention_packaging"), "protective_packaging")
        self.assertEqual(normalize_process_code("MANUAL_REVIEW"), "manual_review")
        self.assertEqual(process_name_for_code("PRECISION_HOLE"), "精孔加工")

    def test_special_processes_are_quotable_but_require_review(self) -> None:
        for code in ("turning", "cylindrical_grinding", "laser_cut", "edm"):
            definition = PROCESS_DICTIONARY[code]
            self.assertTrue(definition.is_supported_in_mvp)
            self.assertTrue(definition.requires_manual_confirm)
            self.assertTrue(definition.auto_quote_enabled)

    def test_detailed_processes_follow_standard_manufacturing_order(self) -> None:
        sequence = {
            code: PROCESS_SEQUENCE.index(code)
            for code in PROCESS_SEQUENCE
        }

        ordered_groups = [
            ("raw_material_check", "material_prepare", "saw_cut"),
            ("laser_cut", "fixture_setup", "cnc_rough_milling"),
            ("turning_rough", "drilling", "countersink", "tapping"),
            ("pcd_hole_pattern", "pcd_hole_inspection", "countersink"),
            ("cnc_rough_milling", "drilling_through", "blind_tapping", "slot_milling", "cnc_finish_milling"),
            ("side_tapping", "thread_inspection", "profile_milling"),
            ("tapping", "profile_milling", "slot_milling", "pocket_milling", "edm"),
            ("weld_inspection", "first_article_inspection", "in_process_inspection", "cnc_finish_milling"),
            ("edm", "cnc_finish_milling", "heat_treatment", "finish_grinding"),
            ("heat_treatment", "straightening", "precision_hole", "reaming", "boring"),
            ("precision_surface_finish", "precision_hole_inspection", "flatness_inspection", "hardness_inspection", "deburr"),
            ("cleaning", "surface_masking", "chemical_nickel", "thread_chasing"),
            ("thread_chasing", "post_anodize_reaming", "post_chrome_polishing", "post_surface_precision_hole_check"),
            ("post_weld_machining", "weld_inspection", "cnc_finish_milling"),
            ("post_surface_precision_hole_check", "coating_thickness_inspection", "surface_inspection", "post_chrome_inspection", "inspection", "protective_packaging"),
        ]

        for group in ordered_groups:
            with self.subTest(group=group):
                self.assertEqual(
                    [sequence[code] for code in group],
                    sorted(sequence[code] for code in group),
                )

    def test_all_processes_have_applicable_scenario_metadata(self) -> None:
        codes = {definition.process_code for definition in PROCESS_DEFINITIONS}

        self.assertEqual(set(PROCESS_APPLICABLE_SCENARIOS), codes)
        for definition in PROCESS_DEFINITIONS:
            payload = definition.to_dict()
            self.assertIsInstance(payload["applicable_scenarios"], str)
            self.assertTrue(payload["applicable_scenarios"].strip())

    def test_unmapped_operation_is_review_only(self) -> None:
        definition = PROCESS_DICTIONARY["unmapped_operation"]

        self.assertTrue(definition.is_supported_in_mvp)
        self.assertTrue(definition.requires_manual_confirm)
        self.assertFalse(definition.auto_quote_enabled)


if __name__ == "__main__":
    unittest.main()
