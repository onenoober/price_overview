from __future__ import annotations

from typing import Any

from .catalog import OperationCatalog, default_operation_catalog
from .models import OperationNode, RouteCandidate, RouteGraph


FORBIDDEN_SHEET_METAL_OPERATIONS = frozenset({"cnc_milling", "wire_cut_profile", "welding"})


class SheetMetalPlanner:
    def __init__(self, catalog: OperationCatalog | None = None) -> None:
        self.catalog = catalog or default_operation_catalog()

    def plan(self, part_feature: dict[str, Any]) -> RouteGraph:
        material = self._node("raw_material_check", [], "material and thickness are present")
        prepare = self._node("material_prepare", ["raw_material_check"], "prepare sheet stock")
        laser = self._node("laser_cut_blank", ["material_prepare"], "sheet-metal golden route uses laser blanking")
        punch = self._node("punch_blank", ["material_prepare"], "alternative blanking method")
        wire_blank = self._node("wire_cut_blank", ["material_prepare"], "alternative blanking method")
        bending = self._node("bending", ["laser_cut_blank"], "bend count is present")
        deburr = self._node("deburr", ["bending"], "sheet edges need deburring")
        inspection = self._node("inspection", ["deburr"], "final inspection")
        packaging = self._node("protective_packaging", ["inspection"], "protective packaging")

        nodes = {
            node.operation_code: node
            for node in (material, prepare, laser, punch, wire_blank, bending, deburr, inspection, packaging)
        }
        forbidden = FORBIDDEN_SHEET_METAL_OPERATIONS.intersection(nodes)
        if forbidden:
            raise ValueError(f"Sheet-metal route contains forbidden operations: {sorted(forbidden)}")

        selected_codes = (
            "raw_material_check",
            "material_prepare",
            "laser_cut_blank",
            "bending",
            "deburr",
            "inspection",
            "protective_packaging",
        )
        invalid_conflict_codes = selected_codes[:2] + ("laser_cut_blank", "punch_blank") + selected_codes[3:]

        graph = RouteGraph(
            nodes=nodes,
            candidates=(
                RouteCandidate(
                    route_id="sheet-metal-golden",
                    operation_ids=list(selected_codes),
                    selected=True,
                    reason="golden sheet-metal route",
                ),
                RouteCandidate(
                    route_id="sheet-metal-conflicting-blanking",
                    operation_ids=list(invalid_conflict_codes),
                    selected=False,
                    reason="conflicting blanking choices must be filtered",
                ),
            ),
        )
        graph.topological_sort(list(selected_codes))
        graph.selected_candidate()
        return graph

    def _node(self, operation_code: str, predecessors: list[str], reason: str) -> OperationNode:
        operation = self.catalog.get(operation_code)
        return OperationNode(
            operation_id=operation.code,
            operation_code=operation.code,
            process_family=operation.process_family,
            sequence=operation.sequence,
            scope=operation.scope,  # type: ignore[arg-type]
            quantity_driver=operation.quantity_driver,
            must_follow=predecessors,
            choice_group=operation.choice_group,
            choice_mode=operation.choice_mode,  # type: ignore[arg-type]
            trigger_rule=reason,
        )
