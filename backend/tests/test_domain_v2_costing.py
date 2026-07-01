from __future__ import annotations

import unittest
from decimal import Decimal

from backend.app.domain_v2.costing import CostEngine, RateSnapshot
from backend.app.domain_v2.planning import RouteCandidate
from backend.app.domain_v2.quantities import QuantityLine


class DomainV2CostingTests(unittest.TestCase):
    def test_cost_engine_uses_decimal_and_only_selected_route(self) -> None:
        selected_route = RouteCandidate(
            route_id="selected",
            operation_ids=["laser_cut_blank", "bending"],
            selected=True,
        )
        quantities = (
            QuantityLine(
                operation_code="laser_cut_blank",
                scope="length",
                quantity=Decimal("1200.5"),
                unit="mm",
                formula_trace={"outer_profile_length": "600.25", "thickness": "2"},
            ),
            QuantityLine(
                operation_code="bending",
                scope="feature",
                quantity=Decimal("4"),
                unit="bend",
                formula_trace={"bend_count": "4"},
            ),
            QuantityLine(
                operation_code="punch_blank",
                scope="feature",
                quantity=Decimal("99"),
                unit="hit",
                formula_trace={"note": "not selected"},
            ),
        )
        rates = RateSnapshot(
            snapshot_id="rates-2026-06-22",
            rates={
                "laser_cut_blank": Decimal("0.008"),
                "bending": Decimal("3.50"),
                "punch_blank": Decimal("1.00"),
            },
        )

        lines = CostEngine().calculate(selected_route, quantities, rates)

        self.assertEqual([line.operation_code for line in lines], ["laser_cut_blank", "bending"])
        self.assertNotIn("punch_blank", {line.operation_code for line in lines})
        for line in lines:
            self.assertIsInstance(line.quantity, Decimal)
            self.assertIsInstance(line.unit_rate, Decimal)
            self.assertIsInstance(line.amount, Decimal)
            self.assertEqual(line.rate_snapshot_id, "rates-2026-06-22")
            self.assertIn("cost_formula", line.formula_trace)

        self.assertEqual(lines[0].amount, Decimal("9.6040"))
        self.assertEqual(lines[1].amount, Decimal("14.00"))

    def test_quantity_line_rejects_non_decimal_value(self) -> None:
        with self.assertRaises(TypeError):
            QuantityLine(
                operation_code="bending",
                scope="feature",
                quantity=4,  # type: ignore[arg-type]
                unit="bend",
                formula_trace={"bend_count": "4"},
            )


if __name__ == "__main__":
    unittest.main()
