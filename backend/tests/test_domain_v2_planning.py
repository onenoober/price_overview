from __future__ import annotations

import unittest

from backend.app.domain_v2.planning import OperationNode, RouteCandidate, RouteGraph, SheetMetalPlanner


class DomainV2PlanningTests(unittest.TestCase):
    def test_sheet_metal_golden_route_has_no_forbidden_operations(self) -> None:
        graph = SheetMetalPlanner().plan({"part_type": "sheet_metal"})

        operation_codes = {node.operation_code for node in graph.selected_operations()}

        self.assertFalse({"cnc_milling", "wire_cut_profile", "welding"} & operation_codes)
        self.assertIn("laser_cut_blank", operation_codes)
        self.assertIn("bending", operation_codes)

    def test_operation_nodes_keep_dag_constraints_and_evidence_fields(self) -> None:
        graph = SheetMetalPlanner().plan({"part_type": "sheet_metal"})
        laser = graph.nodes["laser_cut_blank"]

        self.assertEqual(laser.process_family, "sheet_metal")
        self.assertFalse(hasattr(laser, "display_stage"))
        self.assertEqual(laser.must_follow, ["material_prepare"])
        self.assertEqual(laser.choice_group, "sheet_metal_blanking")
        self.assertEqual(laser.choice_mode, "exactly_one")
        self.assertEqual(laser.review_status, "system_generated")
        self.assertEqual(laser.evidence, [])

    def test_dag_topological_sort_respects_dependencies(self) -> None:
        graph = SheetMetalPlanner().plan({"part_type": "sheet_metal"})

        ordered_codes = [node.operation_code for node in graph.selected_operations()]

        self.assertLess(ordered_codes.index("raw_material_check"), ordered_codes.index("material_prepare"))
        self.assertLess(ordered_codes.index("material_prepare"), ordered_codes.index("laser_cut_blank"))
        self.assertLess(ordered_codes.index("laser_cut_blank"), ordered_codes.index("bending"))
        self.assertLess(ordered_codes.index("inspection"), ordered_codes.index("protective_packaging"))

    def test_exactly_one_choice_group_filters_conflicting_routes(self) -> None:
        graph = SheetMetalPlanner().plan({"part_type": "sheet_metal"})

        valid_route_ids = {candidate.route_id for candidate in graph.valid_candidates()}

        self.assertEqual(valid_route_ids, {"sheet-metal-golden"})
        selected_codes = graph.selected_candidate().operation_codes
        self.assertNotIn("punch_blank", selected_codes)

    def test_topological_sort_rejects_cycles(self) -> None:
        graph = RouteGraph(
            nodes={
                "a": OperationNode(
                    operation_id="a",
                    operation_code="a",
                    process_family="test",
                    sequence=10,
                    must_follow=["b"],
                ),
                "b": OperationNode(
                    operation_id="b",
                    operation_code="b",
                    process_family="test",
                    sequence=20,
                    must_follow=["a"],
                ),
            },
            candidates=[RouteCandidate(route_id="cyclic", operation_ids=["a", "b"], selected=True)],
        )

        with self.assertRaises(ValueError):
            graph.topological_sort(["a", "b"])


if __name__ == "__main__":
    unittest.main()
