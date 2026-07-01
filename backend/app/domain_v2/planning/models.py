from __future__ import annotations

from collections import defaultdict, deque
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain_v2.facts import EvidenceRef


ChoiceMode = Literal["optional", "exactly_one", "at_least_one"]
OperationScope = Literal["batch", "piece", "feature", "area", "length", "volume", "time", "tooling"]
CategoryDecisionSource = Literal["erp", "plm", "master_data", "snapshot", "inferred", "missing"]


class OperationNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    operation_id: str
    operation_code: str
    process_family: str
    sequence: int = 0
    scope: OperationScope = "piece"
    quantity_driver: str | None = None
    must_follow: list[str] = Field(default_factory=list)
    must_precede: list[str] = Field(default_factory=list)
    incompatible_with: list[str] = Field(default_factory=list)
    choice_group: str | None = None
    choice_mode: ChoiceMode | None = None
    capability_requirements: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    review_status: str = "system_generated"
    trigger_rule: str = ""


class RouteCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    route_id: str
    operation_ids: list[str]
    selected: bool = False
    reason: str = ""
    rejected_reason: str | None = None

    @property
    def operation_codes(self) -> tuple[str, ...]:
        return tuple(self.operation_ids)


class RouteGraph(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    nodes: dict[str, OperationNode] = Field(default_factory=dict)
    candidates: list[RouteCandidate] = Field(default_factory=list)

    def add_node(self, node: OperationNode) -> None:
        self.nodes[node.operation_id] = node

    def topological_sort(self, operation_ids: list[str] | tuple[str, ...] | None = None) -> tuple[OperationNode, ...]:
        selected_ids = set(operation_ids or self.nodes.keys())
        indegree = {operation_id: 0 for operation_id in selected_ids}
        successors: dict[str, list[str]] = defaultdict(list)

        for operation_id in selected_ids:
            node = self.nodes[operation_id]
            for predecessor in node.must_follow:
                if predecessor in selected_ids:
                    indegree[operation_id] += 1
                    successors[predecessor].append(operation_id)
            for successor in node.must_precede:
                if successor in selected_ids:
                    indegree[successor] += 1
                    successors[operation_id].append(successor)

        ready = deque(
            sorted((code for code, degree in indegree.items() if degree == 0), key=self._sort_key)
        )
        ordered: list[OperationNode] = []

        while ready:
            operation_id = ready.popleft()
            ordered.append(self.nodes[operation_id])
            for successor in sorted(successors[operation_id], key=self._sort_key):
                indegree[successor] -= 1
                if indegree[successor] == 0:
                    ready.append(successor)
            ready = deque(sorted(ready, key=self._sort_key))

        if len(ordered) != len(selected_ids):
            raise ValueError("Route graph contains a cycle.")

        return tuple(ordered)

    def valid_candidates(self) -> tuple[RouteCandidate, ...]:
        return tuple(candidate for candidate in self.candidates if self.is_candidate_valid(candidate))

    def selected_candidate(self) -> RouteCandidate:
        selected = [candidate for candidate in self.valid_candidates() if candidate.selected]
        if len(selected) != 1:
            raise ValueError("Expected exactly one selected valid route candidate.")
        return selected[0]

    def selected_operations(self) -> tuple[OperationNode, ...]:
        return self.topological_sort(self.selected_candidate().operation_ids)

    def is_candidate_valid(self, candidate: RouteCandidate) -> bool:
        candidate_ids = set(candidate.operation_ids)
        if not candidate_ids.issubset(self.nodes):
            return False

        for operation_id in candidate.operation_ids:
            node = self.nodes[operation_id]
            if candidate_ids.intersection(node.incompatible_with):
                return False

        groups: dict[str, list[OperationNode]] = defaultdict(list)
        for operation_id in candidate.operation_ids:
            node = self.nodes[operation_id]
            if node.choice_group:
                groups[node.choice_group].append(node)

        for nodes in groups.values():
            modes = {node.choice_mode for node in nodes if node.choice_mode}
            if "exactly_one" in modes and len(nodes) != 1:
                return False
            if "at_least_one" in modes and len(nodes) < 1:
                return False

        return True

    def _sort_key(self, operation_id: str) -> tuple[int, str]:
        node = self.nodes[operation_id]
        return (node.sequence, operation_id)


class CategoryDefinition(BaseModel):
    """Business category routing definition.

    The business_category_code remains the J00x business small category. It is
    not collapsed into a manufacturing family.
    """

    model_config = ConfigDict(frozen=True)

    business_category_code: str
    name: str
    profile_code: str
    operation_codes: tuple[str, ...]
    active: bool = True
    branch_operation_codes: dict[str, tuple[str, ...]] = Field(default_factory=dict)


class BusinessCategoryDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    business_category_code: str | None = None
    source: CategoryDecisionSource = "missing"
    confidence: float = 0.0
    reason: str = ""
    review_reason: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class RouteProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile_code: str
    business_category_code: str
    operation_codes: tuple[str, ...]
    branch_code: str | None = None
    name: str = ""


class RoutePlanningResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    business_category_code: str | None = None
    decision: BusinessCategoryDecision
    profile: RouteProfile | None = None
    route_graph: RouteGraph = Field(default_factory=RouteGraph)
    operations: tuple[OperationNode, ...] = Field(default_factory=tuple)
    review_reason: str | None = None
    assumptions: list[str] = Field(default_factory=list)
