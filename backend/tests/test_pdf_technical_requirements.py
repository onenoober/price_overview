from __future__ import annotations

import unittest

from backend.app.parser_service import (
    TOLERANCE_PATTERN,
    collect_pattern_matches,
    extract_technical_requirements,
    split_tolerance_only_technical_matches,
    vision_content_to_matches,
)


class PdfTechnicalRequirementExtractionTests(unittest.TestCase):
    def test_unspecified_tolerance_marker_is_not_technical_requirement(self) -> None:
        blocks = [
            block(
                page=1,
                text="未注公差标记",
                bbox=[100.0, 100.0, 180.0, 112.0],
                block_index=13,
                parent_block_index=3,
            )
        ]

        requirements = extract_technical_requirements(
            pdf_file={"file_id": "file_pdf_001"},
            blocks=blocks,
        )
        tolerances = collect_pattern_matches(
            pdf_file={"file_id": "file_pdf_001"},
            blocks=blocks,
            pattern=TOLERANCE_PATTERN,
        )

        self.assertEqual(requirements, [])
        self.assertEqual([item["text"] for item in tolerances], ["未注公差标记"])

    def test_tolerance_line_inside_technical_block_is_not_requirement(self) -> None:
        blocks = [
            block(
                page=1,
                text="技术要求\n未注公差按 GB/T 1804-m\n去毛刺",
                bbox=[80.0, 120.0, 240.0, 160.0],
                block_index=20,
                parent_block_index=8,
            )
        ]

        requirements = extract_technical_requirements(
            pdf_file={"file_id": "file_pdf_001"},
            blocks=blocks,
        )
        tolerances = collect_pattern_matches(
            pdf_file={"file_id": "file_pdf_001"},
            blocks=blocks,
            pattern=TOLERANCE_PATTERN,
        )

        self.assertEqual([item["text"] for item in requirements], ["去毛刺"])
        self.assertEqual(
            [item["text"] for item in tolerances],
            ["未注公差按 GB/T 1804-m"],
        )

    def test_vision_tolerance_marker_is_remapped_from_technical_requirements(self) -> None:
        matches = vision_content_to_matches(
            pdf_file={"file_id": "file_pdf_001"},
            content={
                "technical_requirements": [
                    {"text": "未注公差标记", "confidence": 0.72},
                    {"text": "去毛刺", "confidence": 0.76},
                ]
            },
            list_key="technical_requirements",
            rule_code="PDF_VISION:TECHNICAL_REQUIREMENT",
        )

        requirements, tolerances = split_tolerance_only_technical_matches(
            matches,
            rule_code="PDF_VISION:TOLERANCE",
        )

        self.assertEqual([item["text"] for item in requirements], ["去毛刺"])
        self.assertEqual([item["text"] for item in tolerances], ["未注公差标记"])
        self.assertEqual(tolerances[0]["evidence"]["rule_code"], "PDF_VISION:TOLERANCE")


def block(
    *,
    page: int,
    text: str,
    bbox: list[float],
    block_index: int,
    parent_block_index: int,
) -> dict:
    return {
        "page": page,
        "text": text,
        "bbox": bbox,
        "block_index": block_index,
        "parent_block_index": parent_block_index,
    }


if __name__ == "__main__":
    unittest.main()
