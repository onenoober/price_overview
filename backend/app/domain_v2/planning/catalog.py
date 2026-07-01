from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .models import CategoryDefinition


class OperationDefinition(BaseModel):
    """Planning-only operation metadata. Prices deliberately do not live here."""

    model_config = ConfigDict(frozen=True)

    code: str
    name: str
    process_family: str
    sequence: int
    quantity_driver: str
    scope: str = "piece"
    unit: str
    choice_group: str | None = None
    choice_mode: str | None = None


class OperationCatalog:
    def __init__(self, operations: tuple[OperationDefinition, ...]) -> None:
        self._operations = {operation.code: operation for operation in operations}

    def get(self, code: str) -> OperationDefinition:
        return self._operations[code]

    def has(self, code: str) -> bool:
        return code in self._operations

    def all(self) -> tuple[OperationDefinition, ...]:
        return tuple(sorted(self._operations.values(), key=lambda item: item.sequence))


class CategoryCatalog:
    def __init__(self, categories: tuple[CategoryDefinition, ...]) -> None:
        self._categories = {
            category.business_category_code: category for category in categories
        }

    def get(self, business_category_code: str) -> CategoryDefinition:
        return self._categories[business_category_code]

    def find(self, business_category_code: str | None) -> CategoryDefinition | None:
        if business_category_code is None:
            return None
        return self._categories.get(business_category_code)

    def has(self, business_category_code: str) -> bool:
        return business_category_code in self._categories

    def all(self) -> tuple[CategoryDefinition, ...]:
        return tuple(
            sorted(self._categories.values(), key=lambda item: item.business_category_code)
        )


def default_operation_catalog() -> OperationCatalog:
    return OperationCatalog(
        (
            OperationDefinition(
                code="raw_material_check",
                name="Raw material check",
                process_family="sheet_metal",
                sequence=10,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="material_prepare",
                name="Material prepare",
                process_family="sheet_metal",
                sequence=20,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="saw_cut",
                name="Saw cut stock",
                process_family="prismatic_machining",
                sequence=25,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="laser_cut_blank",
                name="Laser cut blank",
                process_family="sheet_metal",
                sequence=30,
                quantity_driver="cut_length",
                scope="length",
                unit="m",
                choice_group="sheet_metal_blanking",
                choice_mode="exactly_one",
            ),
            OperationDefinition(
                code="punch_blank",
                name="Punch blank",
                process_family="sheet_metal",
                sequence=32,
                quantity_driver="hit_count",
                unit="pcs",
                choice_group="sheet_metal_blanking",
                choice_mode="exactly_one",
            ),
            OperationDefinition(
                code="wire_cut_blank",
                name="Wire cut blank",
                process_family="sheet_metal",
                sequence=40,
                quantity_driver="cut_length",
                scope="length",
                unit="m",
                choice_group="sheet_metal_blanking",
                choice_mode="exactly_one",
            ),
            OperationDefinition(
                code="bending",
                name="Bending",
                process_family="sheet_metal",
                sequence=70,
                quantity_driver="bend_count",
                scope="feature",
                unit="bend",
            ),
            OperationDefinition(
                code="deburr",
                name="Deburr",
                process_family="shared_finishing",
                sequence=150,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="inspection",
                name="Inspection",
                process_family="shared_inspection",
                sequence=199,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="protective_packaging",
                name="Protective packaging",
                process_family="shared_packaging",
                sequence=200,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="turning",
                name="Turning",
                process_family="rotational_machining",
                sequence=55,
                quantity_driver="estimated_hours",
                scope="time",
                unit="hour",
            ),
            OperationDefinition(
                code="cnc_milling",
                name="CNC milling",
                process_family="prismatic_machining",
                sequence=60,
                quantity_driver="estimated_hours",
                scope="time",
                unit="hour",
            ),
            OperationDefinition(
                code="wire_cut_profile",
                name="Wire cut profile",
                process_family="edm",
                sequence=100,
                quantity_driver="cut_length",
                scope="length",
                unit="m",
            ),
            OperationDefinition(
                code="sheet_metal_welding",
                name="Sheet metal welding",
                process_family="sheet_metal",
                sequence=90,
                quantity_driver="weld_length",
                scope="length",
                unit="mm",
            ),
            OperationDefinition(
                code="profile_cut",
                name="Profile cut",
                process_family="profile",
                sequence=25,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="profile_drilling",
                name="Profile drilling",
                process_family="profile",
                sequence=85,
                quantity_driver="hole_count",
                scope="feature",
                unit="hole",
            ),
            OperationDefinition(
                code="profile_finish",
                name="Profile finish",
                process_family="profile",
                sequence=155,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="large_plate_roughing",
                name="Large plate roughing",
                process_family="large_base",
                sequence=45,
                quantity_driver="estimated_hours",
                scope="time",
                unit="hour",
            ),
            OperationDefinition(
                code="large_plate_finishing",
                name="Large plate finishing",
                process_family="large_base",
                sequence=95,
                quantity_driver="estimated_hours",
                scope="time",
                unit="hour",
            ),
            OperationDefinition(
                code="stress_relief",
                name="Stress relief",
                process_family="heat_treatment",
                sequence=80,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="granite_cutting",
                name="Granite cutting",
                process_family="stone_base",
                sequence=25,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="granite_grinding",
                name="Granite grinding",
                process_family="stone_base",
                sequence=70,
                quantity_driver="area",
                scope="area",
                unit="m2",
            ),
            OperationDefinition(
                code="insert_installation",
                name="Insert installation",
                process_family="stone_base",
                sequence=110,
                quantity_driver="insert_count",
                scope="feature",
                unit="pcs",
            ),
            OperationDefinition(
                code="welding",
                name="Welding",
                process_family="weldment",
                sequence=65,
                quantity_driver="weld_length",
                scope="length",
                unit="mm",
            ),
            OperationDefinition(
                code="weld_fit_up",
                name="Weld fit-up",
                process_family="weldment",
                sequence=45,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="weld_straightening",
                name="Weld straightening",
                process_family="weldment",
                sequence=120,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="mechanical_assembly",
                name="Mechanical assembly",
                process_family="assembly",
                sequence=170,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="child_route_review",
                name="Child route review",
                process_family="assembly",
                sequence=15,
                quantity_driver="bom_item_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="surface_preparation",
                name="Surface preparation",
                process_family="rubber_coating",
                sequence=45,
                quantity_driver="area",
                scope="area",
                unit="m2",
            ),
            OperationDefinition(
                code="rubber_coating",
                name="Rubber coating",
                process_family="rubber_coating",
                sequence=90,
                quantity_driver="area",
                scope="area",
                unit="m2",
            ),
            OperationDefinition(
                code="vulcanization",
                name="Vulcanization",
                process_family="rubber_coating",
                sequence=120,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="incoming_check",
                name="Incoming check",
                process_family="rework",
                sequence=10,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="rework_difference_review",
                name="Rework difference review",
                process_family="rework",
                sequence=30,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="local_rework",
                name="Local rework",
                process_family="rework",
                sequence=80,
                quantity_driver="estimated_hours",
                scope="time",
                unit="hour",
            ),
            OperationDefinition(
                code="final_reinspection",
                name="Final reinspection",
                process_family="rework",
                sequence=180,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="nameplate_blank",
                name="Nameplate blank",
                process_family="nameplate",
                sequence=30,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="etching_or_marking",
                name="Etching or marking",
                process_family="nameplate",
                sequence=70,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="coloring",
                name="Coloring",
                process_family="nameplate",
                sequence=100,
                quantity_driver="area",
                scope="area",
                unit="m2",
            ),
            OperationDefinition(
                code="adhesive_backing",
                name="Adhesive backing",
                process_family="nameplate",
                sequence=130,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="packaging_design",
                name="Packaging design",
                process_family="packaging_product",
                sequence=10,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="packaging_material_cut",
                name="Packaging material cut",
                process_family="packaging_product",
                sequence=45,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="packaging_assembly",
                name="Packaging assembly",
                process_family="packaging_product",
                sequence=120,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="make_buy_decision",
                name="Make or buy decision",
                process_family="custom_standard_part",
                sequence=10,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="custom_standard_part_review",
                name="Custom standard part review",
                process_family="custom_standard_part",
                sequence=40,
                quantity_driver="piece_count",
                unit="pcs",
            ),
            OperationDefinition(
                code="dimensional_inspection",
                name="Dimensional inspection",
                process_family="shared_inspection",
                sequence=180,
                quantity_driver="piece_count",
                unit="pcs",
            ),
        )
    )


def default_category_catalog() -> CategoryCatalog:
    return CategoryCatalog(
        (
            CategoryDefinition(
                business_category_code="J001",
                name="Prismatic machining",
                profile_code="prismatic",
                operation_codes=(
                    "raw_material_check",
                    "saw_cut",
                    "cnc_milling",
                    "deburr",
                    "dimensional_inspection",
                    "protective_packaging",
                ),
            ),
            CategoryDefinition(
                business_category_code="J002",
                name="Rotational machining",
                profile_code="rotational",
                operation_codes=(
                    "raw_material_check",
                    "saw_cut",
                    "turning",
                    "deburr",
                    "dimensional_inspection",
                    "protective_packaging",
                ),
            ),
            CategoryDefinition(
                business_category_code="J003",
                name="Large plate or base",
                profile_code="large_base",
                operation_codes=(
                    "raw_material_check",
                    "large_plate_roughing",
                    "stress_relief",
                    "large_plate_finishing",
                    "dimensional_inspection",
                    "protective_packaging",
                ),
                branch_operation_codes={
                    "metal_large_plate": (
                        "raw_material_check",
                        "large_plate_roughing",
                        "stress_relief",
                        "large_plate_finishing",
                        "dimensional_inspection",
                        "protective_packaging",
                    ),
                    "granite_or_stone_base": (
                        "raw_material_check",
                        "granite_cutting",
                        "granite_grinding",
                        "insert_installation",
                        "dimensional_inspection",
                        "protective_packaging",
                    ),
                },
            ),
            CategoryDefinition(
                business_category_code="J004",
                name="Sheet-metal weldment",
                profile_code="sheet_metal_weldment",
                operation_codes=(
                    "material_prepare",
                    "laser_cut_blank",
                    "bending",
                    "sheet_metal_welding",
                    "deburr",
                    "inspection",
                    "protective_packaging",
                ),
            ),
            CategoryDefinition(
                business_category_code="J005",
                name="Profile processing",
                profile_code="profile",
                operation_codes=(
                    "raw_material_check",
                    "profile_cut",
                    "profile_drilling",
                    "profile_finish",
                    "inspection",
                    "protective_packaging",
                ),
            ),
            CategoryDefinition(
                business_category_code="J006",
                name="Sheet-metal primary",
                profile_code="sheet_metal_primary",
                operation_codes=(
                    "raw_material_check",
                    "material_prepare",
                    "laser_cut_blank",
                    "bending",
                    "deburr",
                    "inspection",
                    "protective_packaging",
                ),
            ),
            CategoryDefinition(
                business_category_code="J007",
                name="Assembly or weldment",
                profile_code="assembly_weldment",
                operation_codes=(
                    "child_route_review",
                    "weld_fit_up",
                    "welding",
                    "weld_straightening",
                    "mechanical_assembly",
                    "inspection",
                    "protective_packaging",
                ),
            ),
            CategoryDefinition(
                business_category_code="J009",
                name="Rubber coating",
                profile_code="rubber_coating",
                operation_codes=(
                    "incoming_check",
                    "surface_preparation",
                    "rubber_coating",
                    "vulcanization",
                    "final_reinspection",
                    "protective_packaging",
                ),
            ),
            CategoryDefinition(
                business_category_code="J012",
                name="Rework",
                profile_code="rework",
                operation_codes=(
                    "incoming_check",
                    "rework_difference_review",
                    "local_rework",
                    "final_reinspection",
                    "protective_packaging",
                ),
            ),
            CategoryDefinition(
                business_category_code="J013",
                name="Nameplate",
                profile_code="nameplate",
                operation_codes=(
                    "nameplate_blank",
                    "etching_or_marking",
                    "coloring",
                    "adhesive_backing",
                    "inspection",
                    "protective_packaging",
                ),
            ),
            CategoryDefinition(
                business_category_code="J014",
                name="Packaging",
                profile_code="packaging",
                operation_codes=(
                    "packaging_design",
                    "packaging_material_cut",
                    "packaging_assembly",
                    "inspection",
                ),
            ),
            CategoryDefinition(
                business_category_code="J015",
                name="Standard part procurement",
                profile_code="standard_part",
                operation_codes=(
                    "make_buy_decision",
                    "custom_standard_part_review",
                    "incoming_check",
                    "protective_packaging",
                ),
            ),
            CategoryDefinition(
                business_category_code="J016",
                name="Custom standard part",
                profile_code="custom_standard_part",
                operation_codes=(
                    "make_buy_decision",
                    "custom_standard_part_review",
                    "dimensional_inspection",
                    "protective_packaging",
                ),
            ),
        )
    )
