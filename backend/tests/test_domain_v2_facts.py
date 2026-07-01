from __future__ import annotations

import unittest

from backend.app.domain_v2.facts import EvidenceRef, FactSnapshot, FactValue


class DomainV2FactTests(unittest.TestCase):
    def test_fact_snapshot_preserves_neutral_values_and_evidence(self) -> None:
        evidence = EvidenceRef(
            source_type="pdf",
            source_file_id="drawing-001",
            page=1,
            raw_text="SUS304 t=2.0",
            extractor_version="pdf-test-v1",
        )
        snapshot = FactSnapshot.from_values(
            (
                FactValue(
                    key="material",
                    value="SUS304",
                    confidence=0.92,
                    evidence=[evidence],
                    status="observed",
                ),
                FactValue(
                    key="thickness_mm",
                    value=2.0,
                    unit="mm",
                    evidence=[evidence],
                    status="observed",
                ),
            ),
            snapshot_id="part-a",
        )

        self.assertEqual(snapshot.schema_version, "2.0")
        self.assertEqual(snapshot.snapshot_id, "part-a")
        self.assertEqual(snapshot.first_value("material"), "SUS304")
        self.assertEqual(snapshot.first_value("thickness_mm"), 2.0)
        self.assertEqual(snapshot.evidence_for("material"), [evidence])

    def test_fact_value_rejects_invalid_confidence(self) -> None:
        with self.assertRaises(ValueError):
            FactValue(key="material", value="SUS304", confidence=1.2)


if __name__ == "__main__":
    unittest.main()
