from __future__ import annotations

import unittest

from backend.app.process_dictionary import (
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
        self.assertEqual(normalize_process_code("MANUAL_REVIEW"), "manual_review")
        self.assertEqual(process_name_for_code("PRECISION_HOLE"), "精孔加工")

    def test_reserved_processes_require_manual_confirmation(self) -> None:
        for code in ("turning", "cylindrical_grinding", "laser_cut", "edm"):
            definition = PROCESS_DICTIONARY[code]
            self.assertFalse(definition.is_supported_in_mvp)
            self.assertTrue(definition.requires_manual_confirm)
            self.assertFalse(definition.auto_quote_enabled)


if __name__ == "__main__":
    unittest.main()
