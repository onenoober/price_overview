from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain_v2.facts import FactSnapshot

from .catalog import OperationCatalog, default_operation_catalog
from .models import OperationNode, RouteCandidate, RouteGraph
from .sheet_metal import SheetMetalPlanner


PlannerType = Literal["planner", "orchestrator", "review"]
RouteStatus = Literal["planned", "review_required"]

EXPLICIT_CATEGORY_KEYS = (
    "business_category_code",
    "business_category",
    "category_code",
    "erp_category_code",
    "plm_category_code",
    "material_category_code",
)
MASTER_DATA_VERSION_KEYS = ("master_data_version", "category_master_data_version")
UNKNOWN_PLANNER_REVIEW = "UNMAPPED_CATEGORY_REVIEW"


class CategoryDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    business_category_code: str
    category_name: str
    parent_code: str = "J00"
    active: bool = True
    rule_version: str = "2026.06"
    business_definition: str = ""
    planner_type: PlannerType
    planner_key: str
    route_profile: str
    base_planners: list[str] = Field(default_factory=list)
    requires_bom: bool = False
    priority: int = 0
    prohibited_operations: list[str] = Field(default_factory=list)
    prohibited_profiles: list[str] = Field(default_factory=list)
    business_rules: dict[str, Any] = Field(default_factory=dict)

    @property
    def category_code(self) -> str:
        return self.business_category_code


class BusinessCategoryDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    business_category_code: str | None = None
    category_name: str | None = None
    source: str = "unresolved"
    confidence: float = 0.0
    master_data_version: str | None = None
    review_reason: str | None = None
    conflicts: list[str] = Field(default_factory=list)

    @property
    def category_code(self) -> str | None:
        return self.business_category_code

    @property
    def is_unmapped(self) -> bool:
        return self.review_reason == UNKNOWN_PLANNER_REVIEW


class RouteProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    business_category_code: str
    profile: str
    planner_type: PlannerType
    planner_key: str
    base_planners: list[str] = Field(default_factory=list)
    requires_child_routes: bool = False
    service_scope: str = "full_manufacture"
    assembly_mode: str = "single_part"
    prohibited_operations: list[str] = Field(default_factory=list)
    prohibited_profiles: list[str] = Field(default_factory=list)
    rule_version: str = "2026.06"

    @property
    def category_code(self) -> str:
        return self.business_category_code


class RoutePlanningResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    status: RouteStatus
    category_decision: BusinessCategoryDecision
    route_profile: RouteProfile | None = None
    route_graph: RouteGraph | None = None
    review_reason: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    excluded_operations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def business_category(self) -> dict[str, Any]:
        return {
            "code": self.category_decision.business_category_code,
            "name": self.category_decision.category_name,
            "source": self.category_decision.source,
            "confidence": self.category_decision.confidence,
            "master_data_version": self.category_decision.master_data_version,
        }

    @property
    def planner_type(self) -> str | None:
        return None if self.route_profile is None else self.route_profile.planner_type

    def selected_operations(self) -> tuple[OperationNode, ...]:
        if self.route_graph is None:
            return ()
        return self.route_graph.selected_operations()


class CategoryRegistry:
    def __init__(self, definitions: tuple[CategoryDefinition, ...]) -> None:
        self._definitions = {
            definition.business_category_code: definition for definition in definitions
        }

    def get(self, business_category_code: str) -> CategoryDefinition | None:
        return self._definitions.get(business_category_code)

    def all(self) -> tuple[CategoryDefinition, ...]:
        return tuple(
            sorted(self._definitions.values(), key=lambda item: item.business_category_code)
        )

    def resolve(self, snapshot: FactSnapshot) -> BusinessCategoryDecision:
        explicit = _first_text(snapshot, *EXPLICIT_CATEGORY_KEYS)
        master_data_version = _first_text(snapshot, *MASTER_DATA_VERSION_KEYS)
        if explicit:
            code = explicit.upper()
            definition = self.get(code)
            if definition and definition.active:
                return BusinessCategoryDecision(
                    business_category_code=definition.business_category_code,
                    category_name=definition.category_name,
                    source="erp_plm_master_data",
                    confidence=1.0,
                    master_data_version=master_data_version,
                )
            return BusinessCategoryDecision(
                business_category_code=code,
                source="erp_plm_master_data",
                confidence=1.0,
                master_data_version=master_data_version,
                review_reason=UNKNOWN_PLANNER_REVIEW,
            )

        inferred_code = self._infer_code(snapshot)
        if inferred_code:
            definition = self._definitions[inferred_code]
            return BusinessCategoryDecision(
                business_category_code=definition.business_category_code,
                category_name=definition.category_name,
                source="inferred_business_semantics",
                confidence=0.74,
                master_data_version=master_data_version,
            )

        return BusinessCategoryDecision(
            master_data_version=master_data_version,
            review_reason=UNKNOWN_PLANNER_REVIEW,
        )

    def route_profile_for(self, decision: BusinessCategoryDecision) -> RouteProfile | None:
        if not decision.business_category_code:
            return None
        definition = self.get(decision.business_category_code)
        if definition is None or not definition.active:
            return None
        return RouteProfile(
            business_category_code=definition.business_category_code,
            profile=definition.route_profile,
            planner_type=definition.planner_type,
            planner_key=definition.planner_key,
            base_planners=list(definition.base_planners),
            requires_child_routes=definition.requires_bom,
            assembly_mode=_assembly_mode(definition),
            prohibited_operations=list(definition.prohibited_operations),
            prohibited_profiles=list(definition.prohibited_profiles),
            rule_version=definition.rule_version,
        )

    def _infer_code(self, snapshot: FactSnapshot) -> str | None:
        business_text = " ".join(
            item
            for item in (
                _first_text(snapshot, "part_type_raw", "part_category_raw"),
                _first_text(snapshot, "part_name", "name", "description"),
                _first_text(snapshot, "technical_requirements", "requirements"),
                _first_text(snapshot, "service_scope"),
            )
            if item
        ).lower()

        semantic_rules = (
            ("J012", ("rework", "\u8fd4\u5de5")),
            ("J009", ("rubber coating", "coating only", "\u5305\u80f6")),
            ("J013", ("frame enclosure", "enclosure", "\u673a\u67b6\u5916\u7f69")),
            ("J014", ("nameplate", "\u94ed\u724c")),
            ("J015", ("crate", "packaging product", "\u6728\u7bb1", "\u5305\u6750")),
            ("J016", ("custom standard", "\u5b9a\u5236\u6807\u51c6\u4ef6")),
            ("J006", ("fastened", "\u62fc\u7ec4", "\u87ba\u4e1d\u8fde\u63a5")),
            ("J004", ("sheet metal", "\u94a3\u91d1", "\u6298\u5f2f", "\u6fc0\u5149")),
            ("J007", ("weldment", "\u710a\u63a5")),
            ("J005", ("profile", "\u578b\u6750")),
            ("J002", ("shaft", "rotational", "\u5706\u4ef6", "\u8f74")),
            ("J003", ("large plate", "granite", "\u5927\u677f", "\u5927\u7406\u77f3", "\u82b1\u5c97\u77f3")),
            ("J001", ("prismatic", "\u65b9\u4ef6", "\u677f\u7c7b", "\u5757\u7c7b")),
        )
        for code, aliases in semantic_rules:
            if any(alias in business_text for alias in aliases):
                return code

        max_dimension = _max_dimension_mm(snapshot)
        part_form = (_first_text(snapshot, "part_form", "geometry_class") or "").lower()
        if max_dimension is not None and part_form in {"prismatic", "sheet_like", "plate", "block"}:
            return "J003" if max_dimension > 500 else "J001"
        return None


class CategoryRoutePlanner:
    def __init__(
        self,
        *,
        registry: CategoryRegistry | None = None,
        catalog: OperationCatalog | None = None,
    ) -> None:
        self.registry = registry or default_category_registry()
        self.catalog = catalog or default_operation_catalog()

    def plan(self, snapshot: FactSnapshot) -> RoutePlanningResult:
        decision = self.registry.resolve(snapshot)
        if decision.review_reason:
            return RoutePlanningResult(
                status="review_required",
                category_decision=decision,
                review_reason=decision.review_reason,
                assumptions=["category_registry_version=2026.06"],
            )

        profile = self.registry.route_profile_for(decision)
        if profile is None or profile.planner_key == "review":
            return RoutePlanningResult(
                status="review_required",
                category_decision=decision,
                review_reason=UNKNOWN_PLANNER_REVIEW,
                assumptions=["category_registry_version=2026.06"],
            )

        if self._profile_conflicts(profile, snapshot):
            return RoutePlanningResult(
                status="review_required",
                category_decision=decision,
                route_profile=profile,
                review_reason="CATEGORY_PROFILE_CONFLICT",
                assumptions=["category_registry_version=2026.06"],
            )

        graph = self._build_graph(profile, snapshot)
        forbidden = set(profile.prohibited_operations)
        selected_codes = {node.operation_code for node in graph.selected_operations()}
        leaked = sorted(forbidden & selected_codes)
        if leaked:
            return RoutePlanningResult(
                status="review_required",
                category_decision=decision,
                route_profile=profile,
                route_graph=graph,
                review_reason="PROHIBITED_OPERATION_LEAKAGE",
                assumptions=["category_registry_version=2026.06"],
                excluded_operations=leaked,
            )

        return RoutePlanningResult(
            status="planned",
            category_decision=decision,
            route_profile=profile,
            route_graph=graph,
            assumptions=self._assumptions(profile, snapshot),
            excluded_operations=sorted(forbidden),
            metadata={"large_base_branch": _large_base_branch(snapshot)}
            if profile.planner_key == "large_base"
            else {},
        )

    def _build_graph(self, profile: RouteProfile, snapshot: FactSnapshot) -> RouteGraph:
        if profile.planner_key == "sheet_metal":
            graph = SheetMetalPlanner(self.catalog).plan({"part_type": "sheet_metal"})
            return _append_operations(
                graph,
                self.catalog,
                ("sheet_metal_welding",),
                route_id="sheet-metal-with-welding",
                reason="J004 includes sheet-metal welding",
                insert_after="bending",
            )

        operation_codes = _operation_codes_for_profile(profile, snapshot)
        return _linear_graph(
            self.catalog,
            operation_codes,
            route_id=f"{profile.profile}-golden",
            reason=f"{profile.business_category_code} {profile.profile} route",
        )

    def _profile_conflicts(self, profile: RouteProfile, snapshot: FactSnapshot) -> bool:
        if "sheet_metal_primary" not in profile.prohibited_profiles:
            return False
        text = " ".join(
            item
            for item in (
                _first_text(snapshot, "part_type_raw", "part_category_raw"),
                _first_text(snapshot, "part_form", "geometry_class"),
                _first_text(snapshot, "primary_process"),
            )
            if item
        ).lower()
        return any(token in text for token in ("sheet metal", "\u94a3\u91d1", "\u6298\u5f2f"))

    def _assumptions(self, profile: RouteProfile, snapshot: FactSnapshot) -> list[str]:
        assumptions = [
            "category_registry_version=2026.06",
            f"route_profile_version={profile.rule_version}",
        ]
        if profile.planner_key == "large_base":
            assumptions.append(f"large_base_branch={_large_base_branch(snapshot)}")
        return assumptions


def default_category_registry() -> CategoryRegistry:
    return CategoryRegistry(
        (
            CategoryDefinition(
                business_category_code="J001",
                category_name="Prismatic part",
                business_definition="Plate/block part with single direction length <= 500mm",
                planner_type="planner",
                planner_key="prismatic",
                route_profile="prismatic_part",
                base_planners=["prismatic"],
                priority=50,
                business_rules={"max_single_direction_mm": 500},
            ),
            CategoryDefinition(
                business_category_code="J002",
                category_name="Rotational part",
                business_definition="Shaft and sleeve rotational parts",
                planner_type="planner",
                planner_key="rotational",
                route_profile="rotational_part",
                base_planners=["rotational"],
                priority=50,
            ),
            CategoryDefinition(
                business_category_code="J003",
                category_name="Large base",
                business_definition="Large plate, granite or machine base over 500mm",
                planner_type="planner",
                planner_key="large_base",
                route_profile="large_base",
                base_planners=["large_metal_plate", "granite_base"],
                priority=55,
                business_rules={"min_single_direction_exclusive_mm": 500},
            ),
            CategoryDefinition(
                business_category_code="J004",
                category_name="Sheet metal",
                business_definition="Laser, bending and sheet-metal welding",
                planner_type="planner",
                planner_key="sheet_metal",
                route_profile="sheet_metal",
                base_planners=["sheet_metal"],
                priority=80,
                prohibited_operations=["cnc_milling", "wire_cut_profile"],
            ),
            CategoryDefinition(
                business_category_code="J005",
                category_name="Profile",
                business_definition="Aluminum/profile support parts",
                planner_type="planner",
                planner_key="profile",
                route_profile="profile",
                base_planners=["profile"],
                priority=50,
            ),
            CategoryDefinition(
                business_category_code="J006",
                category_name="Mechanical assembly",
                business_definition="Screw-fastened assemblies",
                planner_type="orchestrator",
                planner_key="mechanical_assembly",
                route_profile="mechanical_assembly",
                base_planners=["child_routes", "mechanical_assembly"],
                requires_bom=True,
                priority=70,
            ),
            CategoryDefinition(
                business_category_code="J007",
                category_name="Weldment",
                business_definition="Welded fixed assembly, excluding sheet-metal parts",
                planner_type="orchestrator",
                planner_key="weldment",
                route_profile="weldment",
                base_planners=["child_routes", "weldment"],
                requires_bom=True,
                priority=70,
                prohibited_profiles=["sheet_metal_primary"],
            ),
            CategoryDefinition(
                business_category_code="J009",
                category_name="Rubber coating",
                business_definition="Rubber coating product or service",
                planner_type="orchestrator",
                planner_key="rubber_coating",
                route_profile="rubber_coating",
                base_planners=["substrate_review", "rubber_coating"],
                priority=90,
            ),
            CategoryDefinition(
                business_category_code="J012",
                category_name="Standard part rework",
                business_definition="Rework service for standard parts",
                planner_type="planner",
                planner_key="standard_part_rework",
                route_profile="standard_part_rework",
                base_planners=["rework"],
                priority=90,
            ),
            CategoryDefinition(
                business_category_code="J013",
                category_name="Frame enclosure",
                business_definition="Composite frame/enclosure product",
                planner_type="orchestrator",
                planner_key="frame_enclosure",
                route_profile="frame_enclosure",
                base_planners=["sheet_metal", "profile", "weldment", "mechanical_assembly"],
                requires_bom=True,
                priority=95,
            ),
            CategoryDefinition(
                business_category_code="J014",
                category_name="Nameplate",
                business_definition="Nameplate special light-processing route",
                planner_type="planner",
                planner_key="nameplate",
                route_profile="nameplate",
                base_planners=["nameplate"],
                priority=90,
            ),
            CategoryDefinition(
                business_category_code="J015",
                category_name="Wooden crate and packaging",
                business_definition="Packaging product route",
                planner_type="planner",
                planner_key="packaging_product",
                route_profile="packaging_product",
                base_planners=["packaging_product"],
                priority=90,
            ),
            CategoryDefinition(
                business_category_code="J016",
                category_name="Custom standard part",
                business_definition="Customized standard part make/buy route",
                planner_type="orchestrator",
                planner_key="custom_standard_part",
                route_profile="custom_standard_part",
                base_planners=["make_buy", "basic_planner_delegate"],
                priority=90,
            ),
        )
    )


def build_route_for_snapshot(snapshot: FactSnapshot) -> RoutePlanningResult:
    return CategoryRoutePlanner().plan(snapshot)


def _operation_codes_for_profile(profile: RouteProfile, snapshot: FactSnapshot) -> tuple[str, ...]:
    if profile.planner_key == "prismatic":
        return ("raw_material_check", "saw_cut", "cnc_milling", "deburr", "inspection", "protective_packaging")
    if profile.planner_key == "rotational":
        return ("raw_material_check", "saw_cut", "turning", "deburr", "inspection", "protective_packaging")
    if profile.planner_key == "large_base":
        if _large_base_branch(snapshot) == "granite_or_stone_base":
            return ("raw_material_check", "granite_cutting", "granite_grinding", "insert_installation", "dimensional_inspection", "protective_packaging")
        return ("raw_material_check", "saw_cut", "large_plate_roughing", "stress_relief", "large_plate_finishing", "inspection", "protective_packaging")
    if profile.planner_key == "profile":
        return ("raw_material_check", "profile_cut", "profile_drilling", "profile_finish", "inspection", "protective_packaging")
    if profile.planner_key == "mechanical_assembly":
        return ("child_route_review", "mechanical_assembly", "inspection", "protective_packaging")
    if profile.planner_key == "weldment":
        return ("child_route_review", "weld_fit_up", "welding", "weld_straightening", "inspection", "protective_packaging")
    if profile.planner_key == "rubber_coating":
        return ("incoming_check", "surface_preparation", "rubber_coating", "vulcanization", "inspection", "protective_packaging")
    if profile.planner_key == "standard_part_rework":
        return ("incoming_check", "rework_difference_review", "local_rework", "final_reinspection")
    if profile.planner_key == "frame_enclosure":
        return ("child_route_review", "weld_fit_up", "welding", "mechanical_assembly", "inspection", "protective_packaging")
    if profile.planner_key == "nameplate":
        return ("raw_material_check", "nameplate_blank", "etching_or_marking", "coloring", "adhesive_backing", "inspection", "protective_packaging")
    if profile.planner_key == "packaging_product":
        return ("packaging_design", "packaging_material_cut", "packaging_assembly", "inspection")
    if profile.planner_key == "custom_standard_part":
        return ("make_buy_decision", "custom_standard_part_review", "dimensional_inspection", "protective_packaging")
    raise ValueError(UNKNOWN_PLANNER_REVIEW)


def _linear_graph(
    catalog: OperationCatalog,
    operation_codes: tuple[str, ...],
    *,
    route_id: str,
    reason: str,
) -> RouteGraph:
    nodes: dict[str, OperationNode] = {}
    previous: str | None = None
    for operation_code in operation_codes:
        operation = catalog.get(operation_code)
        nodes[operation.code] = OperationNode(
            operation_id=operation.code,
            operation_code=operation.code,
            process_family=operation.process_family,
            sequence=operation.sequence,
            scope=operation.scope,  # type: ignore[arg-type]
            quantity_driver=operation.quantity_driver,
            must_follow=[previous] if previous else [],
            choice_group=operation.choice_group,
            choice_mode=operation.choice_mode,  # type: ignore[arg-type]
            trigger_rule=reason,
        )
        previous = operation.code

    graph = RouteGraph(
        nodes=nodes,
        candidates=[
            RouteCandidate(
                route_id=route_id,
                operation_ids=list(operation_codes),
                selected=True,
                reason=reason,
            )
        ],
    )
    graph.selected_candidate()
    graph.selected_operations()
    return graph


def _append_operations(
    graph: RouteGraph,
    catalog: OperationCatalog,
    operation_codes: tuple[str, ...],
    *,
    route_id: str,
    reason: str,
    insert_after: str,
) -> RouteGraph:
    selected = list(graph.selected_candidate().operation_ids)
    insert_index = selected.index(insert_after) + 1 if insert_after in selected else len(selected)
    updated_ids = selected[:insert_index] + list(operation_codes) + selected[insert_index:]
    nodes = dict(graph.nodes)
    predecessor = insert_after if insert_after in selected else (selected[-1] if selected else None)
    successor = selected[insert_index] if insert_index < len(selected) else None
    for operation_code in operation_codes:
        operation = catalog.get(operation_code)
        nodes[operation.code] = OperationNode(
            operation_id=operation.code,
            operation_code=operation.code,
            process_family=operation.process_family,
            sequence=operation.sequence,
            scope=operation.scope,  # type: ignore[arg-type]
            quantity_driver=operation.quantity_driver,
            must_follow=[predecessor] if predecessor else [],
            must_precede=[successor] if successor else [],
            trigger_rule=reason,
        )
        predecessor = operation.code

    updated = RouteGraph(
        nodes=nodes,
        candidates=[
            RouteCandidate(
                route_id=route_id,
                operation_ids=updated_ids,
                selected=True,
                reason=reason,
            )
        ],
    )
    updated.selected_operations()
    return updated


def _large_base_branch(snapshot: FactSnapshot) -> str:
    explicit = _first_text(snapshot, "large_base_branch", "j003_branch")
    if explicit:
        normalized = explicit.lower()
        if any(token in normalized for token in ("granite", "stone", "\u5927\u7406\u77f3", "\u82b1\u5c97\u77f3")):
            return "granite_or_stone_base"
        if any(token in normalized for token in ("metal", "\u91d1\u5c5e")):
            return "metal_large_plate"

    material = (_first_text(snapshot, "material", "material.grade", "material_name") or "").lower()
    if any(token in material for token in ("granite", "marble", "stone", "\u5927\u7406\u77f3", "\u82b1\u5c97\u77f3")):
        return "granite_or_stone_base"
    return "metal_large_plate"


def _max_dimension_mm(snapshot: FactSnapshot) -> float | None:
    direct = _as_float(snapshot.first_value("max_dimension_mm", "single_direction_length_mm"))
    if direct is not None:
        return direct
    envelope = snapshot.first_value("envelope_mm", "bounding_box_mm")
    if isinstance(envelope, (list, tuple)):
        values = [_as_float(value) for value in envelope]
        values = [value for value in values if value is not None]
        return max(values) if values else None
    return None


def _assembly_mode(definition: CategoryDefinition) -> str:
    if definition.requires_bom:
        return "composite"
    if definition.business_category_code in {"J006", "J007", "J013"}:
        return "composite"
    return "single_part"


def _first_text(snapshot: FactSnapshot, *keys: str) -> str | None:
    value = snapshot.first_value(*keys)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

