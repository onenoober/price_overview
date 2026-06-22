from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .market_material_pricing import (
    MaterialEstimateProvider,
    MaterialMarketPrice,
    MaterialPriceProvider,
    ProcessPriceProvider,
    SurfaceTreatmentMarketPrice,
    SurfaceTreatmentPriceProvider,
    build_material_estimate_provider_from_env,
    build_material_price_provider_from_env,
    build_surface_treatment_estimate_provider_from_env,
    build_surface_treatment_price_provider_from_env,
)
from .part_feature_builder import risk_item, source_ref
from .process_dictionary import (
    PROCESS_NAMES,
    PROCESS_SEQUENCE,
    quote_process_code_for,
)
from .process_recognition import apply_ai_process_route_suggestion, build_process_route


OPERATION_NAMES = PROCESS_NAMES
OPERATION_LABELS_ZH = PROCESS_NAMES
OPERATION_SEQUENCE = PROCESS_SEQUENCE

MATERIAL_UNIT_PRICES_PER_KG = {
    "Q235A": 4.5,
    "Q235": 4.5,
    "SUS304": 32.0,
    "SKD11": 45.0,
    "S45C": 12.0,
    "45#": 12.0,
    "45": 12.0,
    "AL6061": 28.0,
    "6061": 28.0,
    "6061T6": 28.0,
}

PRICE_SOURCE = {
    "source_type": "manual",
    "source_id": "a_basic_core_bridge",
    "rule_id": "A_BASIC_CORE_FIRST_PASS",
    "version": "a-basic-v1",
}

FIRST_PASS_QUOTE_FORMULA = "系统首版核价规则"
STANDARD_PROCESS_QUOTE_FORMULA = "按华南工序标准：max(工程量 × 单价，起步价)"
STANDARD_SURFACE_QUOTE_FORMULA = "工程量 × 单价"


@dataclass(frozen=True)
class StandardPriceRule:
    unit_price: float
    unit: str
    minimum_charge: float
    price_range_text: str
    quantity_basis: str
    notes: str
    rule_id: str
    source_id: str = "south_china_process_standard"
    version: str = "south-china-process-standard-v1"
    requires_review: bool = False


PROCESS_STANDARD_PRICE_RULES: dict[str, StandardPriceRule] = {
    "saw_cut": StandardPriceRule(
        10.0,
        "pcs",
        8.0,
        "5-15 元/件",
        "件数/刀数",
        "小件按最低收费；第一版按零件数量作为待复核刀数。",
        "SOUTH_CHINA_SAW_CUT",
        requires_review=True,
    ),
    "cnc_milling": StandardPriceRule(
        115.0,
        "hour",
        80.0,
        "80-150 元/h",
        "估算工时",
        "精密件或小批量需加调机；本次取区间中值。",
        "SOUTH_CHINA_CNC_MILLING",
    ),
    "surface_grinding_rough": StandardPriceRule(
        90.0,
        "hour",
        20.0,
        "60-120 元/h",
        "工时/面积",
        "薄片件、热后件常用；面积转工时规则待补充。",
        "SOUTH_CHINA_SURFACE_GRINDING",
        requires_review=True,
    ),
    "finish_grinding": StandardPriceRule(
        90.0,
        "hour",
        20.0,
        "60-120 元/h",
        "工时/面积",
        "薄片件、热后件常用；面积转工时规则待补充。",
        "SOUTH_CHINA_FINISH_GRINDING",
        requires_review=True,
    ),
    "drilling": StandardPriceRule(
        3.5,
        "pcs",
        10.0,
        "2-5 元/孔",
        "孔数量",
        "普通孔；本次取区间中值。",
        "SOUTH_CHINA_DRILLING",
    ),
    "countersink": StandardPriceRule(
        10.0,
        "pcs",
        8.0,
        "5-15 元/孔",
        "沉孔数量",
        "沉孔、沉头孔；本次取区间中值。",
        "SOUTH_CHINA_COUNTERSINK",
    ),
    "tapping": StandardPriceRule(
        10.0,
        "pcs",
        10.0,
        "5-15 元/孔",
        "螺纹孔数量",
        "视螺纹规格调整；本次取区间中值。",
        "SOUTH_CHINA_TAPPING",
        requires_review=True,
    ),
    "precision_hole": StandardPriceRule(
        27.5,
        "pcs",
        20.0,
        "15-40 元/孔",
        "精孔数量",
        "H7、E8、G6 等配合孔；本次取区间中值。",
        "SOUTH_CHINA_PRECISION_HOLE",
        requires_review=True,
    ),
    "wire_cut_blank": StandardPriceRule(
        0.02,
        "mm2",
        40.0,
        "0.01-0.03 元/mm²",
        "切割面积",
        "默认按中走丝参考价；精度等级需复核。",
        "SOUTH_CHINA_WIRE_CUT_BLANK",
        requires_review=True,
    ),
    "wire_cut_profile": StandardPriceRule(
        0.02,
        "mm2",
        40.0,
        "0.01-0.03 元/mm²",
        "切割面积",
        "默认按中走丝参考价；快走丝/慢走丝需按精度要求切换。",
        "SOUTH_CHINA_WIRE_CUT_PROFILE",
        requires_review=True,
    ),
    "laser_cut": StandardPriceRule(
        0.008,
        "mm2",
        30.0,
        "0.005-0.012 元/mm²",
        "切割面积",
        "钣金/板材切割首版按外轮廓长度×厚度估算，材料、厚度和排版需复核。",
        "SOUTH_CHINA_LASER_CUT",
        requires_review=True,
    ),
    "turning": StandardPriceRule(
        105.0,
        "hour",
        60.0,
        "80-130 元/h",
        "估算工时",
        "轴类件首版按包络尺寸和复杂度估算车削工时，装夹、刀具和批量需复核。",
        "SOUTH_CHINA_TURNING",
        requires_review=True,
    ),
    "cylindrical_grinding": StandardPriceRule(
        95.0,
        "hour",
        50.0,
        "70-120 元/h",
        "估算工时",
        "圆磨首版按轴类包络尺寸和精度要求估算，磨削余量、装夹和检测需复核。",
        "SOUTH_CHINA_CYLINDRICAL_GRINDING",
        requires_review=True,
    ),
    "edm": StandardPriceRule(
        120.0,
        "hour",
        80.0,
        "90-150 元/h",
        "估算工时",
        "放电加工首版按复杂度、槽/小R等特征估算，电极、加工深度和表面要求需复核。",
        "SOUTH_CHINA_EDM",
        requires_review=True,
    ),
    "heat_treatment": StandardPriceRule(
        16.5,
        "kg",
        30.0,
        "8-25 元/kg",
        "重量/炉次",
        "小件按炉次摊销；本次取区间中值。",
        "SOUTH_CHINA_HEAT_TREATMENT",
        requires_review=True,
    ),
    "deburr": StandardPriceRule(
        12.5,
        "pcs",
        5.0,
        "5-20 元/件",
        "件数/边复杂度",
        "复杂外形加价；第一版按零件数量并保留复杂度复核。",
        "SOUTH_CHINA_DEBURR",
        requires_review=True,
    ),
    "inspection": StandardPriceRule(
        17.5,
        "pcs",
        10.0,
        "5-30 元/件",
        "件数",
        "检验包装合并计价，含尺寸、外观、防护；本次取区间中值。",
        "SOUTH_CHINA_INSPECTION_PACKAGING",
    ),
    "protective_packaging": StandardPriceRule(
        17.5,
        "pcs",
        10.0,
        "5-30 元/件",
        "件数",
        "仅有包装工序时按检验包装口径计价；若终检同时存在则不重复计价。",
        "SOUTH_CHINA_INSPECTION_PACKAGING",
    ),
}

SURFACE_TREATMENT_STANDARD_PRICE_RULES: dict[str, StandardPriceRule] = {
    code: StandardPriceRule(
        0.0,
        "m2",
        0.0,
        "待表面处理价格库或市场搜索提供",
        "STEP 表面积",
        f"第一版按 STEP 表面积计价；{name}单价优先来自表面处理价格库，缺失时使用 Tavily + GPT 搜索候选价。",
        rule_id,
        source_id="surface_treatment_price_standard",
        requires_review=True,
    )
    for code, name, rule_id in (
        ("chemical_nickel", "化学镍", "SOUTH_CHINA_CHEMICAL_NICKEL"),
        ("sand_blasting", "喷砂", "SOUTH_CHINA_SAND_BLASTING"),
        ("clear_anodizing", "本色阳极氧化", "SOUTH_CHINA_CLEAR_ANODIZING"),
        ("hard_anodizing", "硬质阳极氧化", "SOUTH_CHINA_HARD_ANODIZING"),
        ("color_anodizing", "着色阳极氧化", "SOUTH_CHINA_COLOR_ANODIZING"),
        ("hard_chrome", "镀硬铬", "SOUTH_CHINA_HARD_CHROME"),
        ("powder_coating", "喷塑", "SOUTH_CHINA_POWDER_COATING"),
        ("white_powder_coating", "白色喷塑", "SOUTH_CHINA_WHITE_POWDER_COATING"),
        ("powder_coating_texture", "小桔纹喷塑", "SOUTH_CHINA_TEXTURE_POWDER_COATING"),
    )
}

SURFACE_TREATMENT_OPERATION_CODES = frozenset(SURFACE_TREATMENT_STANDARD_PRICE_RULES)


NON_PRICED_ROUTE_OPERATIONS = {
    "manual_review",
    "unmapped_operation",
    "pre_plating_cleaning",
}

MANAGEMENT_FEE_RATE = 0.05

HOLE_QUANTITY_REVIEW_CONFIDENCE_THRESHOLD = 0.7
CNC_BASE_SETUP_MINUTES = 5.0
CNC_FLIP_SETUP_MINUTES = 0.0
CNC_FACE_MILLING_RATE_MM2_PER_MIN = 5500.0
CNC_CONTOUR_FEED_MM_PER_MIN = 500.0
CNC_CONTOUR_PASSES = 2.0
CNC_SLOT_MINUTES = 2.0
CNC_SMALL_RADIUS_MINUTES = 0.5
CNC_COMPLEXITY_BASE_SCORE = 30.0
CNC_COMPLEXITY_MINUTES_PER_SCORE = 0.05


@dataclass
class PricingCoreResult:
    process_route: dict[str, Any]
    quantity_result: dict[str, Any]
    quote_result: dict[str, Any]


class PricingCoreService:
    service_name = "a_basic_core_bridge"

    def __init__(
        self,
        *,
        material_price_provider: MaterialPriceProvider | None = None,
        material_estimate_provider: MaterialEstimateProvider | None = None,
        process_price_provider: ProcessPriceProvider | None = None,
        surface_treatment_price_provider: SurfaceTreatmentPriceProvider | None = None,
        surface_treatment_estimate_provider: SurfaceTreatmentPriceProvider | None = None,
    ) -> None:
        self.material_price_provider = material_price_provider
        self.material_estimate_provider = material_estimate_provider
        self.process_price_provider = process_price_provider
        self.surface_treatment_price_provider = surface_treatment_price_provider
        self.surface_treatment_estimate_provider = surface_treatment_estimate_provider

    def build_quote(
        self,
        *,
        task_id: str,
        quote_id: str,
        part_feature: dict[str, Any],
        risks: list[dict[str, Any]],
        priced_at: str,
        price_version: str,
        use_market_price_search: bool = True,
        material_region: str = "south_china",
        process_route_ai_suggestion: dict[str, Any] | None = None,
        process_route_override: dict[str, Any] | None = None,
    ) -> PricingCoreResult:
        route_id = f"route_{quote_id.removeprefix('quote_')}"
        inherited_risks = dedupe_risks(list(risks))
        if process_route_override is not None:
            process_route = process_route_override
        else:
            process_route = build_process_route(
                task_id=task_id,
                route_id=route_id,
                part_feature=part_feature,
                inherited_risks=inherited_risks,
            )
        if process_route_ai_suggestion is not None and process_route_override is None:
            process_route = apply_ai_process_route_suggestion(
                process_route,
                process_route_ai_suggestion,
            )
        quantity_result = build_quantity_result(
            task_id=task_id,
            route_id=route_id,
            part_feature=part_feature,
            process_route=process_route,
        )
        all_risks = merge_risks(
            inherited_risks,
            process_route.get("risks", []),
            quantity_result.get("risks", []),
        )
        quote_result = build_quote_result(
            task_id=task_id,
            quote_id=quote_id,
            priced_at=priced_at,
            price_version=price_version,
            part_feature=part_feature,
            process_route=process_route,
            quantity_result=quantity_result,
            risks=all_risks,
            material_price_provider=(
                self.material_price_provider if use_market_price_search else None
            ),
            material_estimate_provider=(
                self.material_estimate_provider if use_market_price_search else None
            ),
            process_price_provider=(
                self.process_price_provider if use_market_price_search else None
            ),
            surface_treatment_price_provider=(
                self.surface_treatment_price_provider if use_market_price_search else None
            ),
            surface_treatment_estimate_provider=(
                self.surface_treatment_estimate_provider if use_market_price_search else None
            ),
            material_region=material_region,
            use_market_price_search=use_market_price_search,
        )
        return PricingCoreResult(
            process_route=process_route,
            quantity_result=quantity_result,
            quote_result=quote_result,
        )


def build_pricing_core_service(
    *,
    material_price_provider: MaterialPriceProvider | None = None,
    material_estimate_provider: MaterialEstimateProvider | None = None,
    process_price_provider: ProcessPriceProvider | None = None,
    surface_treatment_price_provider: SurfaceTreatmentPriceProvider | None = None,
    surface_treatment_estimate_provider: SurfaceTreatmentPriceProvider | None = None,
) -> PricingCoreService:
    return PricingCoreService(
        material_price_provider=(
            material_price_provider
            if material_price_provider is not None
            else build_material_price_provider_from_env()
        ),
        material_estimate_provider=(
            material_estimate_provider
            if material_estimate_provider is not None
            else build_material_estimate_provider_from_env()
        ),
        process_price_provider=process_price_provider,
        surface_treatment_price_provider=(
            surface_treatment_price_provider
            if surface_treatment_price_provider is not None
            else build_surface_treatment_price_provider_from_env()
        ),
        surface_treatment_estimate_provider=(
            surface_treatment_estimate_provider
            if surface_treatment_estimate_provider is not None
            else build_surface_treatment_estimate_provider_from_env()
        ),
    )


def has_review_risk(risks: list[dict[str, Any]]) -> bool:
    return any(risk.get("requires_review") for risk in risks)


def quote_operation_codes(process_route: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    for operation in process_route.get("operations") or []:
        quote_code = quote_process_code_for(operation.get("operation_code"))
        if quote_code:
            codes.add(quote_code)
    return codes


def quote_operation_groups(process_route: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for operation in process_route.get("operations") or []:
        quote_code = quote_process_code_for(operation.get("operation_code"))
        if not quote_code:
            continue
        groups.setdefault(quote_code, []).append(operation)
    return groups


def grouped_operation_explanation(operations: list[dict[str, Any]]) -> str:
    names: list[str] = []
    explanations: list[str] = []
    for operation in operations:
        name = str(operation.get("operation_name") or operation.get("operation_code") or "").strip()
        if name and name not in names:
            names.append(name)
        explanation = str(operation.get("explanation") or "").strip()
        if explanation and explanation not in explanations:
            explanations.append(explanation)
    prefix = f"细工序汇总：{'、'.join(names)}。" if names else ""
    detail = "；".join(explanations[:3])
    return f"{prefix}{detail}".strip() or prefix


def build_quantity_result(
    *,
    task_id: str,
    route_id: str,
    part_feature: dict[str, Any],
    process_route: dict[str, Any],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    material = part_feature.get("material") or {}
    geometry = part_feature.get("geometry") or {}
    features = part_feature.get("features") or {}
    requirements = part_feature.get("manufacturing_requirements") or {}
    operations = quote_operation_codes(process_route)
    part_quantity = numeric_value((part_feature.get("part") or {}).get("quantity"))

    measured_weight_source = geometry.get("step_net_weight") or {}
    measured_weight_value = measured_value(measured_weight_source)
    if measured_weight_value is None:
        measured_weight_source = geometry.get("pdf_weight") or {}
        measured_weight_value = measured_value(measured_weight_source)
    measured_weight_unit = measured_weight_source.get("unit") or "kg"

    bounding_box = geometry.get("bounding_box") or {}
    gross_weight = calculate_gross_weight_from_bbox(material, bounding_box)
    risks.extend(gross_weight["risks"])
    items.append(
        quantity_item(
            quantity_id="qty_material_gross_weight",
            operation_code="material_prepare",
            quantity_type="gross_weight",
            value=gross_weight["value"],
            unit="kg",
            formula="length_mm * width_mm * height_mm * density_kg_per_mm3.",
            basis=gross_weight["basis"],
            requires_review=gross_weight["value"] is None,
            review_reason=(
                None
                if gross_weight["value"] is not None
                else "Bounding box or material density is missing; gross weight cannot be calculated."
            ),
        )
    )
    material_weight = material_pricing_weight_quantity(
        gross_weight_value=gross_weight["value"],
        gross_weight_basis=gross_weight["basis"],
        measured_weight_value=measured_weight_value,
        measured_weight_unit=measured_weight_unit,
        measured_weight_source=measured_weight_source,
    )
    items.append(
        quantity_item(
            quantity_id="qty_material_pricing_weight",
            operation_code="material_prepare",
            quantity_type="material_weight",
            value=material_weight["value"],
            unit="kg",
            formula=material_weight["formula"],
            basis=material_weight["basis"],
            requires_review=material_weight["requires_review"],
            review_reason=material_weight["review_reason"],
        )
    )

    if "saw_cut" in operations:
        saw_cut_quantity = calculate_saw_cut_count(part_quantity)
        risks.extend(saw_cut_quantity["risks"])
        items.append(
            quantity_item(
                quantity_id="qty_saw_cut_count",
                operation_code="saw_cut",
                quantity_type="cut_count",
                value=saw_cut_quantity["value"],
                unit="pcs",
                formula="First-pass saw-cut count uses part.quantity; real knife count and nesting need review.",
                basis=saw_cut_quantity["basis"],
                requires_review=saw_cut_quantity["requires_review"],
                review_reason=saw_cut_quantity["review_reason"],
            )
        )

    if "cnc_milling" in operations:
        complexity = features.get("complexity") or {}
        cnc_quantity = calculate_cnc_estimated_hours(
            geometry,
            complexity,
            material,
        )
        risks.extend(cnc_quantity["risks"])
        items.append(
            quantity_item(
                quantity_id="qty_cnc_estimated_hours",
                operation_code="cnc_milling",
                quantity_type="estimated_hours",
                value=cnc_quantity["value"],
                unit="hour",
                formula=(
                    "装夹分钟 + 翻面找正分钟 + (上下表面面积 ÷ 铣面效率 "
                    "+ 外轮廓长度 × 走刀圈数 ÷ 外轮廓进给 "
                    "+ 槽数量 × 单槽修正分钟 + 小R数量 × 小R修正分钟 "
                    "+ 复杂度修正分钟) × 材料系数"
                ),
                basis=cnc_quantity["basis"],
                requires_review=cnc_quantity["requires_review"],
                review_reason=cnc_quantity["review_reason"],
            )
        )

    for operation_code in ("turning", "cylindrical_grinding", "edm"):
        if operation_code in operations:
            complexity = features.get("complexity") or {}
            estimated_quantity = calculate_special_estimated_hours(
                operation_code=operation_code,
                geometry=geometry,
                complexity=complexity,
                material=material,
            )
            risks.extend(estimated_quantity["risks"])
            items.append(
                quantity_item(
                    quantity_id=f"qty_{operation_code}_estimated_hours",
                    operation_code=operation_code,
                    quantity_type="estimated_hours",
                    value=estimated_quantity["value"],
                    unit="hour",
                    formula=estimated_quantity["formula"],
                    basis=estimated_quantity["basis"],
                    requires_review=estimated_quantity["requires_review"],
                    review_reason=estimated_quantity["review_reason"],
                )
            )

    add_hole_quantities(items, features.get("holes") or [], operations, risks)

    for operation_code in ("wire_cut_blank", "wire_cut_profile", "laser_cut"):
        if operation_code in operations:
            wire_quantity = calculate_wire_cut_area(operation_code, geometry)
            risks.extend(wire_quantity["risks"])
            items.append(
                quantity_item(
                    quantity_id=f"qty_{operation_code}_cut_area",
                    operation_code=operation_code,
                    quantity_type="cut_area",
                    value=wire_quantity["value"],
                    unit="mm2",
                    formula="outer_profile_length_mm * material_thickness_mm.",
                    basis=wire_quantity["basis"],
                    requires_review=wire_quantity["requires_review"],
                    review_reason=wire_quantity["review_reason"],
                )
            )

    for operation_code in ("surface_grinding_rough", "finish_grinding"):
        if operation_code in operations:
            grinding_quantity = calculate_grinding_area(operation_code, bounding_box)
            risks.extend(grinding_quantity["risks"])
            items.append(
                quantity_item(
                    quantity_id=f"qty_{operation_code}_area",
                    operation_code=operation_code,
                    quantity_type="grinding_area",
                    value=grinding_quantity["value"],
                    unit="mm2",
                    formula="grinding_face_count * grinding_face_area_mm2.",
                    basis=grinding_quantity["basis"],
                    requires_review=True,
                    review_reason="Grinding face count is not available in part_feature; quantity needs confirmation.",
                )
            )

    if "heat_treatment" in operations:
        heat_weight = calculate_heat_treatment_weight(
            gross_weight_value=gross_weight["value"],
            gross_weight_basis=gross_weight["basis"],
            measured_weight_value=measured_weight_value,
            measured_weight_unit=measured_weight_unit,
            measured_weight_source=measured_weight_source,
        )
        risks.extend(heat_weight["risks"])
        items.append(
            quantity_item(
                quantity_id="qty_heat_treatment_weight",
                operation_code="heat_treatment",
                quantity_type="heat_weight",
                value=heat_weight["value"],
                unit=heat_weight["unit"],
                formula="Prefer calculated gross_weight; fallback to STEP/PDF measured weight when gross weight is unavailable.",
                basis=heat_weight["basis"],
                requires_review=heat_weight["requires_review"],
                review_reason=heat_weight["review_reason"],
            )
        )

    surface_operations = sorted(
        operations & SURFACE_TREATMENT_OPERATION_CODES,
        key=lambda code: PROCESS_SEQUENCE.index(code),
    )
    for surface_operation in surface_operations:
        surface_quantity = calculate_surface_treatment_area(geometry)
        risks.extend(surface_quantity["risks"])
        surface = requirements.get("surface_treatment") or {}
        surface_name = OPERATION_NAMES[surface_operation]
        items.append(
            quantity_item(
                quantity_id=f"qty_{surface_operation}_surface_area",
                operation_code=surface_operation,
                quantity_type="surface_area",
                value=surface_quantity["value"],
                unit=surface_quantity["unit"],
                formula=f"STEP 表面积换算为 m²，作为{surface_name}表面处理计价工程量。",
                basis=[
                    *surface_quantity["basis"],
                    basis_item("surface_treatment", surface.get("raw_text"), None, surface.get("source")),
                ],
                requires_review=surface_quantity["value"] is None,
                review_reason=(
                    None
                    if surface_quantity["value"] is not None
                    else f"Surface area is missing or unit is unsupported; {surface_name} cannot be priced by area."
                ),
            )
        )

    if "deburr" in operations:
        complexity = features.get("complexity") or {}
        deburring_quantity = calculate_deburr_quantity(complexity, part_quantity)
        risks.extend(deburring_quantity["risks"])
        items.append(
            quantity_item(
                quantity_id="qty_deburring_count",
                operation_code="deburr",
                quantity_type="deburr_count",
                value=deburring_quantity["value"],
                unit=deburring_quantity["unit"],
                formula="part.quantity with STEP complexity_score or edge_count as review basis.",
                basis=deburring_quantity["basis"],
                requires_review=deburring_quantity["requires_review"],
                review_reason=deburring_quantity["review_reason"],
            )
        )

    if part_quantity is None and ("inspection" in operations or "protective_packaging" in operations):
        append_risk_if_missing(
            risks,
            quantity_risk(
                "QUANTITY_PART_COUNT_MISSING",
                "缺少零件数量，无法计算检验或包装工程量。",
                "QUANTITY_PART_COUNT_MISSING",
            ),
        )
    if "inspection" in operations:
        items.append(
            quantity_item(
                quantity_id="qty_inspection_count",
                operation_code="inspection",
                quantity_type="inspection_count",
                value=part_quantity,
                unit="pcs",
                formula="part.quantity.",
                basis=[basis_item("part_quantity", part_quantity, "pcs", system_source("INSPECTION"))],
                requires_review=part_quantity is None,
                review_reason=None if part_quantity is not None else "Part quantity is missing.",
            )
        )

    if "protective_packaging" in operations:
        items.append(
            quantity_item(
                quantity_id="qty_packaging_lot",
                operation_code="protective_packaging",
                quantity_type="manual_quantity",
                value=part_quantity,
                unit="pcs",
                formula="part.quantity for protective packaging pieces.",
                basis=[basis_item("part_quantity", part_quantity, "pcs", system_source("PACKAGING"))],
                requires_review=part_quantity is None,
                review_reason=None if part_quantity is not None else "Part quantity is missing.",
            )
        )

    return {
        "schema_version": "1.0",
        "task_id": task_id,
        "route_id": route_id,
        "items": dedupe_quantity_items(items),
        "risks": risks,
    }


def add_hole_quantities(
    items: list[dict[str, Any]],
    holes: list[dict[str, Any]],
    operations: set[str],
    risks: list[dict[str, Any]],
) -> None:
    drilling_types = {
        "through",
        "blind",
        "counterbore",
        "countersink",
        "thread_candidate",
        "precision_candidate",
    }
    countersink_types = {"counterbore", "countersink"}
    counts = {
        "drilling": 0,
        "countersink": 0,
        "tapping": 0,
        "precision_hole": 0,
    }
    sources: dict[str, dict[str, Any] | None] = {
        "drilling": None,
        "countersink": None,
        "tapping": None,
        "precision_hole": None,
    }
    review_flags = {
        "drilling": False,
        "countersink": False,
        "tapping": False,
        "precision_hole": False,
    }

    for hole in holes:
        hole_type = hole.get("hole_type")
        count = int(hole.get("count") or 0)
        if not count:
            continue
        source = first_source(hole.get("evidence"))
        low_confidence = clamp_confidence(hole.get("confidence")) < HOLE_QUANTITY_REVIEW_CONFIDENCE_THRESHOLD
        if hole_type in drilling_types:
            counts["drilling"] += count
            sources["drilling"] = sources["drilling"] or source
            review_flags["drilling"] = review_flags["drilling"] or low_confidence
        if hole_type in countersink_types:
            counts["countersink"] += count
            sources["countersink"] = sources["countersink"] or source
            review_flags["countersink"] = review_flags["countersink"] or low_confidence
        if hole_type == "thread_candidate":
            counts["tapping"] += count
            sources["tapping"] = sources["tapping"] or source
            review_flags["tapping"] = True
        if hole_type == "precision_candidate":
            counts["precision_hole"] += count
            sources["precision_hole"] = sources["precision_hole"] or source
            review_flags["precision_hole"] = True
        if low_confidence:
            append_risk_if_missing(
                risks,
                quantity_risk(
                    "QUANTITY_LOW_CONFIDENCE_HOLE_COUNT",
                    "孔特征置信度低，孔类工程量需人工确认。",
                    "QUANTITY_LOW_CONFIDENCE_HOLE_COUNT",
                    evidence=[source or system_source("QUANTITY_LOW_CONFIDENCE_HOLE_COUNT")],
                ),
            )

    quantity_specs = {
        "drilling": ("qty_drilling_hole_count", "hole_count", False),
        "countersink": ("qty_counterbore_count", "counterbore_count", False),
        "tapping": ("qty_tapping_thread_count", "thread_count", True),
        "precision_hole": ("qty_precision_hole_count", "precision_hole_count", True),
    }
    for operation_code, count in counts.items():
        if count <= 0 or operation_code not in operations:
            continue
        quantity_id, quantity_type, candidate_requires_review = quantity_specs[operation_code]
        requires_review = candidate_requires_review or review_flags[operation_code]
        items.append(
            quantity_item(
                quantity_id=quantity_id,
                operation_code=operation_code,
                quantity_type=quantity_type,
                value=count,
                unit="pcs",
                formula="Sum detected hole candidates by operation type.",
                basis=[basis_item(operation_code, count, "pcs", sources.get(operation_code))],
                requires_review=requires_review,
                review_reason="Hole type is a candidate or low-confidence and needs confirmation." if requires_review else None,
            )
        )


def build_quote_result(
    *,
    task_id: str,
    quote_id: str,
    priced_at: str,
    price_version: str,
    part_feature: dict[str, Any],
    process_route: dict[str, Any],
    quantity_result: dict[str, Any],
    risks: list[dict[str, Any]],
    material_price_provider: MaterialPriceProvider | None = None,
    material_estimate_provider: MaterialEstimateProvider | None = None,
    process_price_provider: ProcessPriceProvider | None = None,
    surface_treatment_price_provider: SurfaceTreatmentPriceProvider | None = None,
    surface_treatment_estimate_provider: SurfaceTreatmentPriceProvider | None = None,
    material_region: str = "south_china",
    use_market_price_search: bool = True,
) -> dict[str, Any]:
    quote_risks = list(risks)
    items: list[dict[str, Any]] = []
    material = part_feature.get("material") or {}
    material_text = material.get("raw_text") or material.get("standard_code")
    material_quantity = find_quantity(quantity_result, "material_weight")
    if material_quantity is None:
        material_quantity = find_quantity(quantity_result, "gross_weight")
    material_kg = quantity_to_kg(material_quantity)
    material_market_price = find_market_material_price(
        provider=material_price_provider,
        material=material,
        material_text=material_text,
        region=material_region,
    )
    if material_market_price is None and use_market_price_search:
        material_market_price = find_market_material_price(
            provider=material_estimate_provider,
            material=material,
            material_text=material_text,
            region=material_region,
        )
    fallback_material_unit_price = material_unit_price_from_text(material_text)
    uses_fallback_material_price = (
        material_market_price is None and fallback_material_unit_price is not None
    )
    fallback_requires_review = use_market_price_search and uses_fallback_material_price
    material_unit_price = (
        material_market_price.unit_price
        if material_market_price is not None
        else fallback_material_unit_price
    )
    material_price_source = (
        material_market_price.price_source(price_version)
        if material_market_price is not None
        else (
            material_fallback_price_source(price_version, material_text)
            if uses_fallback_material_price
            else PRICE_SOURCE
        )
    )

    if material_kg is not None and material_unit_price is not None:
        amount = round(material_kg * material_unit_price, 2)
        uses_market_price = material_market_price is not None
        uses_review_quantity = bool(material_quantity and material_quantity.get("requires_review"))
        items.append(
            quote_item(
                item_id="item_material",
                item_type="material",
                operation_code="material_prepare",
                quantity=material_kg,
                unit="kg",
                unit_price=material_unit_price,
                amount=amount,
                price_source=material_price_source,
                explanation=material_explanation(
                    material_text,
                    material_market_price,
                    uses_fallback_material_price=uses_fallback_material_price,
                ),
                requires_review=uses_market_price or fallback_requires_review or uses_review_quantity,
            )
        )
        if uses_market_price:
            quote_risks.append(market_price_review_risk(material_market_price))
        if fallback_requires_review:
            quote_risks.append(material_fallback_price_review_risk(material_text, material_unit_price))
        if uses_review_quantity:
            quote_risks.append(material_weight_review_risk(material_quantity))
    else:
        items.append(
            quote_item(
                item_id="item_material_needs_review",
                item_type="material",
                operation_code="material_prepare",
                quantity=material_kg,
                unit="kg" if material_kg is not None else None,
                unit_price=material_unit_price,
                amount=None,
                price_source=material_price_source,
                explanation="Material price or weight is missing.",
                requires_review=True,
            )
        )
        quote_risks.append(missing_price_risk("material_prepare"))

    operation_groups = quote_operation_groups(process_route)
    operation_codes = set(operation_groups)
    for operation_code, grouped_operations in operation_groups.items():
        if operation_code in {
            "material_prepare",
            *SURFACE_TREATMENT_OPERATION_CODES,
            *NON_PRICED_ROUTE_OPERATIONS,
        }:
            continue
        if operation_code == "protective_packaging" and "inspection" in operation_codes:
            continue

        quantity = quantity_for_operation(quantity_result, operation_code)
        value = numeric_value(quantity.get("value")) if quantity else None
        standard_rule = standard_process_price_rule(operation_code)
        quantity_unit = quantity.get("unit") if quantity else None
        units_match = (
            standard_rule is not None
            and quantity_unit_matches(standard_rule.unit, quantity_unit)
        )
        unit_price = standard_rule.unit_price if standard_rule is not None and units_match else None
        amount = (
            calculate_standard_amount(value, standard_rule)
            if value is not None and standard_rule is not None and units_match
            else None
        )
        process_price_source = (
            standard_price_source(standard_rule, price_version, operation_code)
            if standard_rule is not None
            else PRICE_SOURCE
        )
        operation_name = OPERATION_NAMES[operation_code]
        grouped_explanation = grouped_operation_explanation(grouped_operations)
        items.append(
            quote_item(
                item_id=f"item_process_{operation_code.lower()}",
                item_type="process",
                operation_code=operation_code,
                quantity=value,
                unit=quantity_unit or (standard_rule.unit if standard_rule else None),
                unit_price=unit_price,
                amount=amount,
                price_source=process_price_source,
                formula=STANDARD_PROCESS_QUOTE_FORMULA,
                explanation=standard_price_explanation(
                    operation_name,
                    standard_rule,
                    grouped_explanation,
                ),
                requires_review=(
                    any(bool(operation.get("requires_review")) for operation in grouped_operations)
                    or bool(quantity and quantity.get("requires_review"))
                    or amount is None
                    or bool(standard_rule and standard_rule.requires_review)
                ),
            )
        )
        if amount is None:
            quote_risks.append(missing_price_risk(operation_code))

    for surface_operation in sorted(
        operation_codes & SURFACE_TREATMENT_OPERATION_CODES,
        key=lambda code: PROCESS_SEQUENCE.index(code),
    ):
        surface_quantity = quantity_for_operation(quantity_result, surface_operation)
        if not surface_quantity:
            continue
        value = numeric_value(surface_quantity.get("value"))
        standard_rule = SURFACE_TREATMENT_STANDARD_PRICE_RULES[surface_operation]
        quantity_unit = surface_quantity.get("unit")
        treatment_name = OPERATION_NAMES[surface_operation]
        surface_market_price = find_market_surface_treatment_price(
            provider=surface_treatment_price_provider,
            treatment_code=surface_operation,
            treatment_name=treatment_name,
            quantity=surface_quantity,
            material_text=material_text,
            region=material_region,
        )
        if surface_market_price is None:
            surface_market_price = find_market_surface_treatment_price(
                provider=surface_treatment_estimate_provider,
                treatment_code=surface_operation,
                treatment_name=treatment_name,
                quantity=surface_quantity,
                material_text=material_text,
                region=material_region,
            )
        units_match = (
            surface_market_price is not None
            and quantity_unit_matches(surface_market_price.unit, quantity_unit)
        )
        unit_price = surface_market_price.unit_price if units_match else None
        minimum_charge = (
            surface_market_price.minimum_charge
            if surface_market_price is not None and surface_market_price.minimum_charge is not None
            else 0.0
        )
        amount = (
            calculate_amount_with_minimum(value, unit_price, minimum_charge)
            if value is not None and unit_price is not None and units_match
            else None
        )
        price_source = (
            surface_market_price.price_source(price_version)
            if surface_market_price is not None
            else standard_price_source(standard_rule, price_version, surface_operation)
        )
        items.append(
            quote_item(
                item_id=f"item_surface_{surface_operation.lower()}",
                item_type="surface_treatment",
                operation_code=surface_operation,
                quantity=value,
                unit=quantity_unit,
                unit_price=unit_price,
                amount=amount,
                price_source=price_source,
                formula=surface_treatment_quote_formula(minimum_charge, surface_market_price),
                explanation=surface_treatment_price_explanation(
                    treatment_name,
                    surface_market_price,
                    standard_rule,
                    minimum_charge,
                ),
                requires_review=(
                    bool(surface_quantity.get("requires_review"))
                    or amount is None
                    or surface_market_price is not None
                    or standard_rule.requires_review
                ),
            )
        )
        if surface_market_price is not None:
            quote_risks.append(surface_treatment_market_price_review_risk(surface_market_price))
        if amount is None:
            quote_risks.append(missing_price_risk(surface_operation))

    material_amount = sum_amount(items, "material")
    process_amount = sum_amount(items, "process")
    surface_amount = sum_amount(items, "surface_treatment")
    subtotal = material_amount + process_amount + surface_amount
    management_fee = round(material_amount * MANAGEMENT_FEE_RATE, 2)
    tax_base = process_amount + surface_amount + management_fee
    tax_amount = round(tax_base * 0.13, 2)

    if management_fee:
        items.append(
            summary_item(
                "item_management_fee",
                "management_fee",
                management_fee,
                explanation="管理费 = 材料费 × 5%。",
            )
        )
    if tax_amount:
        items.append(
            summary_item(
                "item_tax",
                "tax",
                tax_amount,
                explanation="税费 = (加工费 + 表面处理费 + 管理费) × 13%。",
            )
        )

    system_calculated = round(subtotal + management_fee + tax_amount, 2)
    system_initial_quote = round_up_to_10(system_calculated)
    quote_risks = dedupe_risks(quote_risks)
    status = "pending_review" if has_review_risk(quote_risks) else "priced"

    return {
        "schema_version": "1.0",
        "task_id": task_id,
        "quote_id": quote_id,
        "status": status,
        "currency": "CNY",
        "price_version": price_version,
        "priced_at": priced_at,
        "confirmed_at": None,
        "confirmed_by": None,
        "items": items,
        "summary": {
            "material_amount": material_amount,
            "process_amount": process_amount,
            "surface_treatment_amount": surface_amount,
            "management_fee": management_fee,
            "tax_amount": tax_amount,
            "risk_surcharge_amount": 0.0,
            "system_calculated_amount": system_calculated,
            "system_initial_quote": system_initial_quote,
            "manual_adjustment_amount": 0.0,
            "final_confirmed_amount": None,
        },
        "risks": quote_risks,
        "manual_overrides": [],
    }


def quote_item(
    *,
    item_id: str,
    item_type: str,
    operation_code: str | None,
    quantity: float | int | None,
    unit: str | None,
    unit_price: float | None,
    amount: float | None,
    explanation: str,
    price_source: dict[str, Any] | None = None,
    formula: str = FIRST_PASS_QUOTE_FORMULA,
    requires_review: bool = False,
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "item_type": item_type,
        "operation_code": operation_code,
        "quantity": quantity,
        "unit": unit,
        "unit_price": unit_price,
        "amount": amount,
        "price_source": price_source or PRICE_SOURCE,
        "formula": formula,
        "explanation": explanation,
        "system_amount": amount,
        "final_amount": amount,
        "requires_review": requires_review,
    }


def quantity_item(
    *,
    quantity_id: str,
    operation_code: str,
    quantity_type: str,
    value: float | int | None,
    unit: str,
    formula: str,
    basis: list[dict[str, Any]],
    requires_review: bool = False,
    review_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "quantity_id": quantity_id,
        "operation_code": operation_code,
        "quantity_type": quantity_type,
        "value": value,
        "unit": unit,
        "formula": formula,
        "basis": basis,
        "requires_review": requires_review,
        "review_reason": review_reason,
    }


def basis_item(
    name: str,
    value: str | float | int | bool | None,
    unit: str | None,
    source: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "name": name,
        "value": value,
        "unit": unit,
        "source": source or system_source(name),
    }


def calculate_gross_weight_from_bbox(
    material: dict[str, Any],
    bounding_box: dict[str, Any],
) -> dict[str, Any]:
    dimensions = bbox_dimensions_mm(bounding_box)
    density_info = material_density_info(material)
    density = density_info["density_kg_per_mm3"]
    density_source = density_info["source"]
    basis = [
        basis_item("bounding_box", bounding_box_text(bounding_box), bounding_box.get("unit") or "mm", system_source("GROSS_WEIGHT_BBOX")),
        basis_item("material", material.get("raw_text") or material.get("standard_code"), None, material.get("source")),
        basis_item("density", density_info["display_density"], density_info["display_unit"], density_source),
    ]
    risks: list[dict[str, Any]] = []

    if dimensions is None:
        risks.append(
            quantity_risk(
                "QUANTITY_DIMENSION_MISSING",
                "缺少毛坯长宽厚，无法按长×宽×厚×密度计算材料毛重。",
                "QUANTITY_DIMENSION_MISSING:GROSS_WEIGHT",
            )
        )
    if density is None:
        risks.append(
            quantity_risk(
                "MATERIAL_DENSITY_MISSING",
                "材料密度缺失或单位不支持，无法计算材料毛重。",
                "MATERIAL_DENSITY_MISSING:GROSS_WEIGHT",
                evidence=[material.get("source") or system_source("MATERIAL_DENSITY_MISSING:GROSS_WEIGHT")],
            )
        )

    if dimensions is None or density is None:
        return {"value": None, "basis": basis, "risks": risks}

    length, width, height = dimensions
    value = round(length * width * height * density, 6)
    basis.append(basis_item("density_kg_per_mm3", density, "kg/mm3", density_source))
    return {"value": value, "basis": basis, "risks": risks}


def material_pricing_weight_quantity(
    *,
    gross_weight_value: float | None,
    gross_weight_basis: list[dict[str, Any]],
    measured_weight_value: float | None,
    measured_weight_unit: str,
    measured_weight_source: dict[str, Any],
) -> dict[str, Any]:
    if gross_weight_value is not None:
        return {
            "value": gross_weight_value,
            "formula": "Use calculated gross_weight for material pricing.",
            "basis": [
                basis_item(
                    "gross_weight",
                    gross_weight_value,
                    "kg",
                    system_source("MATERIAL_PRICING_WEIGHT:GROSS_WEIGHT"),
                )
            ],
            "requires_review": False,
            "review_reason": None,
        }

    measured_kg = convert_weight_to_kg(measured_weight_value, measured_weight_unit)
    if measured_kg is not None:
        return {
            "value": round(measured_kg, 6),
            "formula": "Gross weight is unavailable; use STEP/PDF measured weight for material pricing.",
            "basis": [
                *gross_weight_basis,
                basis_item(
                    "fallback_weight",
                    measured_weight_value,
                    measured_weight_unit,
                    measured_weight_source.get("source"),
                ),
            ],
            "requires_review": True,
            "review_reason": "Gross weight is unavailable because material density is missing; STEP/PDF measured weight is used for material pricing.",
        }

    return {
        "value": None,
        "formula": "Gross weight is unavailable and no STEP/PDF measured weight is available.",
        "basis": gross_weight_basis,
        "requires_review": True,
        "review_reason": "Material density and measured weight are missing; material pricing weight cannot be calculated.",
    }


def calculate_cnc_estimated_hours(
    geometry: dict[str, Any],
    complexity: dict[str, Any],
    material: dict[str, Any],
) -> dict[str, Any]:
    bounding_box = geometry.get("bounding_box") or {}
    dimensions = bbox_dimensions_mm(bounding_box)
    bbox_volume = bbox_volume_mm3(bounding_box)
    part_volume = measured_value(geometry.get("volume") or {})
    profile_summary = geometry.get("profile_summary") or {}
    outer_profile_length = numeric_value(profile_summary.get("outer_profile_length"))
    outer_profile_source = step_profile_source(geometry, "CNC_ESTIMATE:OUTER_PROFILE_LENGTH")
    profile_method = "step_profile"

    basis = [
        basis_item("bounding_box", bounding_box_text(bounding_box), bounding_box.get("unit") or "mm", system_source("CNC_ESTIMATE:BBOX")),
        basis_item("bounding_box_volume", bbox_volume, "mm3", system_source("CNC_ESTIMATE:BBOX_VOLUME")),
        basis_item("part_volume", part_volume, (geometry.get("volume") or {}).get("unit"), (geometry.get("volume") or {}).get("source")),
        basis_item("face_count", complexity.get("face_count"), None, system_source("CNC_ESTIMATE:FACE_COUNT")),
        basis_item("edge_count", complexity.get("edge_count"), None, system_source("CNC_ESTIMATE:EDGE_COUNT")),
        basis_item("complexity_score", complexity.get("complexity_score"), None, system_source("CNC_ESTIMATE:COMPLEXITY_SCORE")),
    ]
    risks: list[dict[str, Any]] = []

    if dimensions is None:
        risks.append(
            quantity_risk(
                "QUANTITY_DIMENSION_MISSING",
                "缺少 CNC 估算所需的包络长宽厚，无法计算 CNC 估算工时。",
                "QUANTITY_DIMENSION_MISSING:CNC_ESTIMATE",
            )
        )
        return {
            "value": None,
            "basis": basis,
            "risks": risks,
            "requires_review": True,
            "review_reason": "缺少包络长宽厚，无法计算 CNC 估算工时。",
        }

    major_length, major_width = major_face_dimensions_from_dimensions(dimensions)
    top_bottom_face_area = round(2 * major_length * major_width, 4)
    if outer_profile_length is None:
        outer_profile_length = round(2 * (major_length + major_width), 4)
        outer_profile_source = system_source("CNC_ESTIMATE:RECTANGULAR_PROFILE_FALLBACK")
        profile_method = "rectangular_bbox_fallback"

    slot_count = non_negative_numeric_value(complexity.get("slot_count"))
    small_radius_count = non_negative_numeric_value(complexity.get("small_radius_count"))
    complexity_score = non_negative_numeric_value(complexity.get("complexity_score"))
    material_factor = cnc_material_factor(material)

    setup_minutes = CNC_BASE_SETUP_MINUTES
    flip_setup_minutes = CNC_FLIP_SETUP_MINUTES
    face_milling_minutes = top_bottom_face_area / CNC_FACE_MILLING_RATE_MM2_PER_MIN
    contour_milling_minutes = (
        outer_profile_length * CNC_CONTOUR_PASSES / CNC_CONTOUR_FEED_MM_PER_MIN
    )
    slot_minutes = slot_count * CNC_SLOT_MINUTES
    small_radius_minutes = small_radius_count * CNC_SMALL_RADIUS_MINUTES
    complexity_adjustment_minutes = max(
        0.0,
        complexity_score - CNC_COMPLEXITY_BASE_SCORE,
    ) * CNC_COMPLEXITY_MINUTES_PER_SCORE
    cutting_minutes = (
        face_milling_minutes
        + contour_milling_minutes
        + slot_minutes
        + small_radius_minutes
        + complexity_adjustment_minutes
    ) * material_factor
    total_minutes = setup_minutes + flip_setup_minutes + cutting_minutes

    basis.extend(
        [
            basis_item("top_bottom_face_area", top_bottom_face_area, "mm2", system_source("CNC_ESTIMATE:TOP_BOTTOM_FACE_AREA")),
            basis_item("setup_minutes", setup_minutes, "min", system_source("CNC_ESTIMATE:SETUP_MINUTES")),
            basis_item("flip_setup_minutes", flip_setup_minutes, "min", system_source("CNC_ESTIMATE:FLIP_SETUP_MINUTES")),
            basis_item("face_milling_rate", CNC_FACE_MILLING_RATE_MM2_PER_MIN, "mm2/min", system_source("CNC_ESTIMATE:FACE_MILLING_RATE")),
            basis_item("face_milling_minutes", round(face_milling_minutes, 4), "min", system_source("CNC_ESTIMATE:FACE_MILLING_MINUTES")),
            basis_item("outer_profile_length", outer_profile_length, "mm", outer_profile_source),
            basis_item("outer_profile_method", profile_method, None, outer_profile_source),
            basis_item("contour_passes", CNC_CONTOUR_PASSES, None, system_source("CNC_ESTIMATE:CONTOUR_PASSES")),
            basis_item("contour_feed_rate", CNC_CONTOUR_FEED_MM_PER_MIN, "mm/min", system_source("CNC_ESTIMATE:CONTOUR_FEED_RATE")),
            basis_item("contour_milling_minutes", round(contour_milling_minutes, 4), "min", system_source("CNC_ESTIMATE:CONTOUR_MILLING_MINUTES")),
            basis_item("slot_count", slot_count, None, system_source("CNC_ESTIMATE:SLOT_COUNT")),
            basis_item("slot_minutes", round(slot_minutes, 4), "min", system_source("CNC_ESTIMATE:SLOT_MINUTES")),
            basis_item("small_radius_count", small_radius_count, None, system_source("CNC_ESTIMATE:SMALL_RADIUS_COUNT")),
            basis_item("small_radius_minutes", round(small_radius_minutes, 4), "min", system_source("CNC_ESTIMATE:SMALL_RADIUS_MINUTES")),
            basis_item("complexity_adjustment_minutes", round(complexity_adjustment_minutes, 4), "min", system_source("CNC_ESTIMATE:COMPLEXITY_ADJUSTMENT")),
            basis_item("material_factor", material_factor, None, material.get("source") or system_source("CNC_ESTIMATE:MATERIAL_FACTOR")),
            basis_item("cutting_minutes", round(cutting_minutes, 4), "min", system_source("CNC_ESTIMATE:CUTTING_MINUTES")),
            basis_item("total_estimated_minutes", round(total_minutes, 4), "min", system_source("CNC_ESTIMATE:TOTAL_MINUTES")),
        ]
    )
    risks.append(
        quantity_risk(
            "QUANTITY_CNC_ESTIMATE_REQUIRES_REVIEW",
            "CNC 工时采用装夹、上下表面、外轮廓、特征和复杂度经验参数估算，需复核装夹次数、翻面和节拍参数。",
            "QUANTITY_CNC_ESTIMATE_REQUIRES_REVIEW",
        )
    )

    return {
        "value": round(total_minutes / 60, 4),
        "basis": basis,
        "risks": risks,
        "requires_review": True,
        "review_reason": "CNC 工时按默认装夹、上下表面、外轮廓、特征和复杂度参数估算，需人工复核装夹次数、是否翻面、实际机台节拍和材料系数。",
    }


def calculate_special_estimated_hours(
    *,
    operation_code: str,
    geometry: dict[str, Any],
    complexity: dict[str, Any],
    material: dict[str, Any],
) -> dict[str, Any]:
    bounding_box = geometry.get("bounding_box") or {}
    dimensions = bbox_dimensions_mm(bounding_box)
    bbox_volume = bbox_volume_mm3(bounding_box)
    complexity_score = non_negative_numeric_value(complexity.get("complexity_score"))
    slot_count = non_negative_numeric_value(complexity.get("slot_count"))
    small_radius_count = non_negative_numeric_value(complexity.get("small_radius_count"))
    material_factor = cnc_material_factor(material)
    basis = [
        basis_item("bounding_box", bounding_box_text(bounding_box), bounding_box.get("unit") or "mm", system_source(f"{operation_code.upper()}_ESTIMATE:BBOX")),
        basis_item("bounding_box_volume", bbox_volume, "mm3", system_source(f"{operation_code.upper()}_ESTIMATE:BBOX_VOLUME")),
        basis_item("complexity_score", complexity.get("complexity_score"), None, system_source(f"{operation_code.upper()}_ESTIMATE:COMPLEXITY_SCORE")),
        basis_item("slot_count", slot_count, None, system_source(f"{operation_code.upper()}_ESTIMATE:SLOT_COUNT")),
        basis_item("small_radius_count", small_radius_count, None, system_source(f"{operation_code.upper()}_ESTIMATE:SMALL_RADIUS_COUNT")),
        basis_item("material_factor", material_factor, None, material.get("source") or system_source(f"{operation_code.upper()}_ESTIMATE:MATERIAL_FACTOR")),
    ]
    risks: list[dict[str, Any]] = []
    rule_prefix = operation_code.upper()

    if dimensions is None:
        risks.append(
            quantity_risk(
                "QUANTITY_DIMENSION_MISSING",
                f"缺少 {operation_code} 估算所需的包络长宽厚，无法计算估算工时。",
                f"QUANTITY_DIMENSION_MISSING:{rule_prefix}_ESTIMATE",
            )
        )
        return {
            "value": None,
            "basis": basis,
            "risks": risks,
            "requires_review": True,
            "review_reason": "缺少包络长宽厚，无法计算估算工时。",
            "formula": "首版估算工时需要包络尺寸、复杂度和材料系数。",
        }

    length, width, height = sorted(dimensions, reverse=True)
    major_diameter = max(width, height)
    slenderness = length / major_diameter if major_diameter else 1.0
    complexity_minutes = max(0.0, complexity_score - CNC_COMPLEXITY_BASE_SCORE) * CNC_COMPLEXITY_MINUTES_PER_SCORE

    if operation_code == "turning":
        setup_minutes = 8.0
        size_minutes = (length * max(major_diameter, 1.0)) / 1800.0
        feature_minutes = slot_count * 4.0 + small_radius_count * 1.5
        slenderness_minutes = max(0.0, slenderness - 6.0) * 2.0
        formula = "装夹分钟 + 长度×直径系数 + 槽/小R修正 + 长径比修正 + 复杂度修正。"
    elif operation_code == "cylindrical_grinding":
        setup_minutes = 10.0
        size_minutes = (length * max(major_diameter, 1.0)) / 2600.0
        feature_minutes = small_radius_count * 1.0
        slenderness_minutes = max(0.0, slenderness - 8.0) * 2.5
        formula = "装夹分钟 + 长度×直径系数 + 小R修正 + 长径比修正 + 复杂度修正。"
    else:
        setup_minutes = 15.0
        size_minutes = max(0.0, bbox_volume or 0.0) / 120000.0
        feature_minutes = slot_count * 6.0 + small_radius_count * 3.0
        slenderness_minutes = 0.0
        formula = "装夹分钟 + 包络体积系数 + 槽/小R修正 + 复杂度修正。"

    total_minutes = (
        setup_minutes
        + size_minutes
        + feature_minutes
        + slenderness_minutes
        + complexity_minutes
    ) * material_factor
    basis.extend(
        [
            basis_item("major_length", length, "mm", system_source(f"{rule_prefix}_ESTIMATE:MAJOR_LENGTH")),
            basis_item("major_diameter_or_width", major_diameter, "mm", system_source(f"{rule_prefix}_ESTIMATE:MAJOR_DIAMETER_OR_WIDTH")),
            basis_item("slenderness", round(slenderness, 4), None, system_source(f"{rule_prefix}_ESTIMATE:SLENDERNESS")),
            basis_item("setup_minutes", setup_minutes, "min", system_source(f"{rule_prefix}_ESTIMATE:SETUP_MINUTES")),
            basis_item("size_minutes", round(size_minutes, 4), "min", system_source(f"{rule_prefix}_ESTIMATE:SIZE_MINUTES")),
            basis_item("feature_minutes", round(feature_minutes, 4), "min", system_source(f"{rule_prefix}_ESTIMATE:FEATURE_MINUTES")),
            basis_item("slenderness_minutes", round(slenderness_minutes, 4), "min", system_source(f"{rule_prefix}_ESTIMATE:SLENDERNESS_MINUTES")),
            basis_item("complexity_minutes", round(complexity_minutes, 4), "min", system_source(f"{rule_prefix}_ESTIMATE:COMPLEXITY_MINUTES")),
            basis_item("total_estimated_minutes", round(total_minutes, 4), "min", system_source(f"{rule_prefix}_ESTIMATE:TOTAL_MINUTES")),
        ]
    )
    risks.append(
        quantity_risk(
            f"QUANTITY_{rule_prefix}_ESTIMATE_REQUIRES_REVIEW",
            f"{operation_code} 工时采用包络尺寸、复杂度和材料系数估算，需复核装夹、实际加工内容和节拍参数。",
            f"QUANTITY_{rule_prefix}_ESTIMATE_REQUIRES_REVIEW",
        )
    )

    return {
        "value": round(total_minutes / 60, 4),
        "basis": basis,
        "risks": risks,
        "requires_review": True,
        "review_reason": "首版工时按包络尺寸、复杂度和材料系数估算，需人工复核实际加工路线、装夹和节拍。",
        "formula": formula,
    }


def calculate_wire_cut_area(
    operation_code: str,
    geometry: dict[str, Any],
) -> dict[str, Any]:
    bounding_box = geometry.get("bounding_box") or {}
    profile_summary = geometry.get("profile_summary") or {}
    outer_profile_length = numeric_value(profile_summary.get("outer_profile_length"))
    thickness = material_thickness_mm(bounding_box)
    basis = [
        basis_item(
            "outer_profile_length",
            outer_profile_length,
            "mm",
            step_profile_source(geometry, f"WIRE_CUT:{operation_code}:OUTER_PROFILE_LENGTH"),
        ),
        basis_item("material_thickness", thickness, "mm", system_source(f"WIRE_CUT:{operation_code}:THICKNESS")),
    ]
    risks: list[dict[str, Any]] = []
    if outer_profile_length is None:
        risks.append(
            quantity_risk(
                "QUANTITY_WIRE_CUT_LENGTH_MISSING",
                "缺少线切割外轮廓长度，无法按外轮廓长度×材料厚度计算线切割工程量。",
                f"QUANTITY_WIRE_CUT_LENGTH_MISSING:{operation_code}",
            )
        )
    if thickness is None:
        risks.append(
            quantity_risk(
                "QUANTITY_DIMENSION_MISSING",
                "缺少材料厚度，无法计算线切割工程量。",
                f"QUANTITY_DIMENSION_MISSING:{operation_code}",
            )
        )
    if outer_profile_length is None or thickness is None:
        return {
            "value": None,
            "basis": basis,
            "risks": risks,
            "requires_review": True,
            "review_reason": "Wire-cut outer profile length or material thickness is missing.",
        }

    return {
        "value": round(outer_profile_length * thickness, 4),
        "basis": basis,
        "risks": risks,
        "requires_review": False,
        "review_reason": None,
    }


def calculate_grinding_area(
    operation_code: str,
    bounding_box: dict[str, Any],
) -> dict[str, Any]:
    face_area = major_face_area_mm2(bounding_box)
    basis = [
        basis_item("grinding_face_count", None, None, system_source(f"GRINDING:{operation_code}:FACE_COUNT_MISSING")),
        basis_item("major_face_area", face_area, "mm2", system_source(f"GRINDING:{operation_code}:MAJOR_FACE_AREA")),
    ]
    risks = [
        quantity_risk(
            "QUANTITY_GRINDING_FACE_COUNT_MISSING",
            "缺少磨削面数量，无法按磨削面积计算真实工程量。",
            f"QUANTITY_GRINDING_FACE_COUNT_MISSING:{operation_code}",
        )
    ]
    if face_area is None:
        risks.append(
            quantity_risk(
                "QUANTITY_DIMENSION_MISSING",
                "缺少长宽高，无法计算磨削基准面积。",
                f"QUANTITY_DIMENSION_MISSING:{operation_code}",
            )
        )
    return {"value": None, "basis": basis, "risks": risks}


def calculate_saw_cut_count(part_quantity: float | None) -> dict[str, Any]:
    basis = [
        basis_item(
            "part_quantity",
            part_quantity,
            "pcs",
            system_source("SAW_CUT:PART_QUANTITY_AS_FIRST_PASS_COUNT"),
        )
    ]
    if part_quantity is None:
        return {
            "value": None,
            "basis": basis,
            "requires_review": True,
            "review_reason": "Part quantity is missing; saw-cut count needs manual input.",
            "risks": [
                quantity_risk(
                    "QUANTITY_SAW_CUT_COUNT_MISSING",
                    "缺少零件数量，无法按件数/刀数计算锯切下料工程量。",
                    "QUANTITY_SAW_CUT_COUNT_MISSING",
                )
            ],
        }

    return {
        "value": part_quantity,
        "basis": basis,
        "requires_review": True,
        "review_reason": "锯切下料第一版按零件数量估算，实际刀数、排版和余量需人工复核。",
        "risks": [
            quantity_risk(
                "QUANTITY_SAW_CUT_COUNT_REQUIRES_REVIEW",
                "锯切下料按零件数量作为第一版刀数估算，需复核实际刀数、排版和余量。",
                "QUANTITY_SAW_CUT_COUNT_REQUIRES_REVIEW",
            )
        ],
    }


def step_profile_source(geometry: dict[str, Any], rule_code: str) -> dict[str, Any]:
    volume_source = (geometry.get("volume") or {}).get("source") or {}
    if isinstance(volume_source, dict) and volume_source.get("source_type") == "step":
        return source_ref(
            "step",
            file_id=volume_source.get("file_id"),
            rule_code=rule_code,
        )
    return system_source(rule_code)


def calculate_heat_treatment_weight(
    *,
    gross_weight_value: float | None,
    gross_weight_basis: list[dict[str, Any]],
    measured_weight_value: float | None,
    measured_weight_unit: str,
    measured_weight_source: dict[str, Any],
) -> dict[str, Any]:
    if gross_weight_value is not None:
        return {
            "value": gross_weight_value,
            "unit": "kg",
            "basis": [basis_item("gross_weight", gross_weight_value, "kg", system_source("HEAT_TREATMENT:GROSS_WEIGHT"))],
            "requires_review": False,
            "review_reason": None,
            "risks": [],
        }

    measured_kg = convert_weight_to_kg(measured_weight_value, measured_weight_unit)
    if measured_kg is not None:
        return {
            "value": round(measured_kg, 6),
            "unit": "kg",
            "basis": [
                *gross_weight_basis,
                basis_item("fallback_weight", measured_weight_value, measured_weight_unit, measured_weight_source.get("source")),
            ],
            "requires_review": True,
            "review_reason": "Gross weight is unavailable; STEP/PDF measured weight is used as heat-treatment fallback.",
            "risks": [
                quantity_risk(
                    "QUANTITY_HEAT_WEIGHT_FALLBACK",
                    "热处理毛坯重量缺失，已使用 STEP/PDF 重量作为待确认工程量。",
                    "QUANTITY_HEAT_WEIGHT_FALLBACK",
                )
            ],
        }

    return {
        "value": None,
        "unit": "kg",
        "basis": gross_weight_basis,
        "requires_review": True,
        "review_reason": "No gross, STEP, or PDF weight is available for heat treatment.",
        "risks": [
            quantity_risk(
                "QUANTITY_WEIGHT_MISSING",
                "未找到可用材料重量，热处理工程量需人工复核。",
                "QUANTITY_WEIGHT_MISSING:HEAT_TREATMENT",
            )
        ],
    }


def calculate_surface_treatment_area(geometry: dict[str, Any]) -> dict[str, Any]:
    surface = geometry.get("surface_area") or {}
    value = measured_value(surface)
    unit = str(surface.get("unit") or "mm2")
    converted = convert_area_to_m2(value, unit)
    basis = [
        basis_item("surface_area", value, unit, surface.get("source")),
        basis_item("surface_area_m2", converted, "m2", surface.get("source")),
    ]
    if converted is None:
        return {
            "value": None,
            "unit": "m2",
            "basis": basis,
            "risks": [
                quantity_risk(
                    "QUANTITY_SURFACE_AREA_MISSING",
                    "缺少可用表面积或单位不支持，无法计算表面处理工程量。",
                    "QUANTITY_SURFACE_AREA_MISSING",
                )
            ],
        }
    return {"value": round(converted, 6), "unit": "m2", "basis": basis, "risks": []}


def calculate_surface_treatment_weight(
    *,
    gross_weight_value: float | None,
    gross_weight_basis: list[dict[str, Any]],
    measured_weight_value: float | None,
    measured_weight_unit: str,
    measured_weight_source: dict[str, Any],
) -> dict[str, Any]:
    measured_kg = convert_weight_to_kg(measured_weight_value, measured_weight_unit)
    if measured_kg is not None:
        return {
            "value": round(measured_kg, 6),
            "unit": "kg",
            "basis": [
                basis_item(
                    "net_weight",
                    measured_weight_value,
                    measured_weight_unit,
                    measured_weight_source.get("source"),
                )
            ],
            "requires_review": False,
            "review_reason": None,
            "risks": [],
        }

    if gross_weight_value is not None:
        return {
            "value": gross_weight_value,
            "unit": "kg",
            "basis": [
                *gross_weight_basis,
                basis_item(
                    "surface_weight_fallback",
                    gross_weight_value,
                    "kg",
                    system_source("SURFACE_TREATMENT:GROSS_WEIGHT_FALLBACK"),
                ),
            ],
            "requires_review": True,
            "review_reason": "Surface treatment net weight is unavailable; calculated gross weight is used as a first-pass fallback.",
            "risks": [
                quantity_risk(
                    "QUANTITY_SURFACE_WEIGHT_GROSS_FALLBACK",
                    "表面处理净重缺失，已使用毛坯重量作为第一版待复核工程量。",
                    "QUANTITY_SURFACE_WEIGHT_GROSS_FALLBACK",
                )
            ],
        }

    return {
        "value": None,
        "unit": "kg",
        "basis": gross_weight_basis,
        "requires_review": True,
        "review_reason": "No net, STEP, PDF, or calculated gross weight is available for surface treatment.",
        "risks": [
            quantity_risk(
                "QUANTITY_SURFACE_WEIGHT_MISSING",
                "缺少表面处理净重/毛重，无法计算表面处理工程量。",
                "QUANTITY_SURFACE_WEIGHT_MISSING",
            )
        ],
    }


def calculate_deburr_quantity(
    complexity: dict[str, Any],
    part_quantity: float | None,
) -> dict[str, Any]:
    score = numeric_value(complexity.get("complexity_score"))
    edge_count = numeric_value(complexity.get("edge_count"))
    basis = [
        basis_item("part_quantity", part_quantity, "pcs", system_source("DEBURRING:PART_QUANTITY")),
        basis_item("complexity_score", score, None, system_source("DEBURRING:COMPLEXITY_SCORE")),
        basis_item("edge_count", edge_count, None, system_source("DEBURRING:EDGE_COUNT")),
    ]
    if part_quantity is None:
        return {
            "value": None,
            "unit": "pcs",
            "basis": basis,
            "requires_review": True,
            "review_reason": "Part quantity is missing; deburring count needs manual input.",
            "risks": [
                quantity_risk(
                    "QUANTITY_DEBURR_PART_COUNT_MISSING",
                    "缺少零件数量，无法按件数计算去毛刺工程量。",
                    "QUANTITY_DEBURR_PART_COUNT_MISSING",
                )
            ],
        }

    if score is None and edge_count is None:
        return {
            "value": part_quantity,
            "unit": "pcs",
            "basis": basis,
            "requires_review": True,
            "review_reason": "Deburring is priced by piece, but edge complexity is missing and needs review.",
            "risks": [
                quantity_risk(
                    "QUANTITY_DEBURR_COMPLEXITY_MISSING",
                    "去毛刺按件数先计价，但缺少复杂度评分和边数量，复杂外形加价需人工复核。",
                    "QUANTITY_DEBURR_COMPLEXITY_MISSING",
                )
            ],
        }

    return {
        "value": part_quantity,
        "unit": "pcs",
        "basis": basis,
        "requires_review": False,
        "review_reason": None,
        "risks": [],
    }


def calculate_deburr_complexity(complexity: dict[str, Any]) -> dict[str, Any]:
    score = numeric_value(complexity.get("complexity_score"))
    if score is not None:
        return {
            "value": round(score, 2),
            "basis": [basis_item("complexity_score", score, None, system_source("DEBURRING:COMPLEXITY_SCORE"))],
            "requires_review": False,
            "review_reason": None,
            "risks": [],
        }

    edge_count = numeric_value(complexity.get("edge_count"))
    if edge_count is not None:
        return {
            "value": round(edge_count, 2),
            "basis": [basis_item("edge_count", edge_count, None, system_source("DEBURRING:EDGE_COUNT"))],
            "requires_review": True,
            "review_reason": "complexity_score is missing; edge_count is used as deburring complexity proxy.",
            "risks": [
                quantity_risk(
                    "QUANTITY_DEBURR_COMPLEXITY_FALLBACK",
                    "去毛刺复杂度评分缺失，已使用边数量作为待确认工程量。",
                    "QUANTITY_DEBURR_COMPLEXITY_FALLBACK",
                )
            ],
        }

    return {
        "value": None,
        "basis": [basis_item("complexity_score", None, None, system_source("DEBURRING:COMPLEXITY_SCORE"))],
        "requires_review": True,
        "review_reason": "STEP complexity_score and edge_count are missing; deburring quantity needs manual input.",
        "risks": [
            quantity_risk(
                "QUANTITY_DEBURR_COMPLEXITY_MISSING",
                "缺少复杂度评分和边数量，无法计算去毛刺工程量。",
                "QUANTITY_DEBURR_COMPLEXITY_MISSING",
            )
        ],
    }


def summary_item(
    item_id: str,
    item_type: str,
    amount: float,
    *,
    explanation: str = "First-pass quote summary item.",
    requires_review: bool = False,
) -> dict[str, Any]:
    return quote_item(
        item_id=item_id,
        item_type=item_type,
        operation_code=None,
        quantity=1,
        unit="lot",
        unit_price=amount,
        amount=amount,
        explanation=explanation,
        requires_review=requires_review,
    )


def standard_process_price_rule(operation_code: str) -> StandardPriceRule | None:
    return PROCESS_STANDARD_PRICE_RULES.get(operation_code)


def standard_price_source(
    rule: StandardPriceRule,
    price_version: str,
    operation_code: str,
) -> dict[str, Any]:
    return {
        "source_type": "manual",
        "source_id": rule.source_id,
        "rule_id": f"{rule.rule_id}:{operation_code}",
        "version": price_version or rule.version,
    }


def calculate_standard_amount(value: float, rule: StandardPriceRule) -> float:
    return calculate_amount_with_minimum(value, rule.unit_price, rule.minimum_charge)


def calculate_amount_with_minimum(
    value: float,
    unit_price: float,
    minimum_charge: float,
) -> float:
    variable_amount = round(value * unit_price, 2)
    return round(max(variable_amount, minimum_charge), 2)


def standard_price_explanation(
    operation_name: str,
    rule: StandardPriceRule | None,
    fallback_explanation: Any,
) -> str:
    if rule is None:
        return str(fallback_explanation or operation_name)
    minimum_text = (
        f"，起步价 {rule.minimum_charge:g} 元"
        if rule.minimum_charge
        else ""
    )
    return (
        f"{operation_name}按华南工序计价标准计算："
        f"工程量来源={rule.quantity_basis}，参考单价={rule.price_range_text}，"
        f"本次取 {rule.unit_price:g} 元/{rule.unit}{minimum_text}。"
        f"{rule.notes}"
    )


def surface_treatment_quote_formula(
    minimum_charge: float,
    market_price: SurfaceTreatmentMarketPrice | None,
) -> str:
    basis = (
        "按表面处理AI估算价"
        if market_price is not None and market_price.source_type == "ai_estimate"
        else "按表面处理市场价"
    )
    if minimum_charge:
        return f"{basis}：max(工程量 × 单价，起步价)"
    return f"{basis}：工程量 × 单价"


def surface_treatment_price_explanation(
    treatment_name: str,
    market_price: SurfaceTreatmentMarketPrice | None,
    rule: StandardPriceRule,
    minimum_charge: float,
) -> str:
    if market_price is None:
        return (
            f"{treatment_name}单价缺失：{rule.notes}"
            "未找到与当前工程量单位匹配的表面处理市场价。"
        )
    if market_price.source_type == "ai_estimate":
        minimum_text = f"，起步价 {minimum_charge:g} 元" if minimum_charge else ""
        return (
            f"{treatment_name}单价来自 GPT-only 估算："
            f"{market_price.region}，{market_price.unit_price:g} {market_price.unit}{minimum_text}。"
            "该价格不是实时市场价，需人工复核膜厚、面积、批量、供应商报价和含税口径。"
        )
    minimum_text = f"，起步价 {minimum_charge:g} 元" if minimum_charge else ""
    return (
        f"{treatment_name}单价来自 Tavily + GPT 表面处理市场搜索："
        f"{market_price.region}，{market_price.unit_price:g} {market_price.unit}{minimum_text}。"
        "需复核来源、地区、计价单位、日期和含税口径。"
    )


def quantity_unit_matches(rule_unit: str, quantity_unit: Any) -> bool:
    if quantity_unit in (None, ""):
        return False
    return normalize_price_unit(rule_unit) == normalize_price_unit(quantity_unit)


def normalize_price_unit(unit: Any) -> str:
    text = str(unit or "").strip().lower()
    aliases = {
        "h": "hour",
        "hr": "hour",
        "hrs": "hour",
        "hours": "hour",
        "pcs": "pcs",
        "pc": "pcs",
        "piece": "pcs",
        "pieces": "pcs",
        "hole": "pcs",
        "holes": "pcs",
        "孔": "pcs",
        "件": "pcs",
        "kg": "kg",
        "cny/kg": "kg",
        "元/kg": "kg",
        "元/公斤": "kg",
        "kilogram": "kg",
        "kilograms": "kg",
        "cny/hour": "hour",
        "cny/h": "hour",
        "元/小时": "hour",
        "元/时": "hour",
        "元/h": "hour",
        "cny/pcs": "pcs",
        "元/件": "pcs",
        "元/个": "pcs",
        "元/孔": "pcs",
        "mm²": "mm2",
        "㎜²": "mm2",
        "cny/mm2": "mm2",
        "元/mm2": "mm2",
        "元/mm²": "mm2",
        "square millimeter": "mm2",
        "square millimeters": "mm2",
        "m2": "m2",
        "m²": "m2",
        "㎡": "m2",
        "cny/m2": "m2",
        "元/m2": "m2",
        "元/m²": "m2",
        "元/平方米": "m2",
        "square meter": "m2",
        "square meters": "m2",
    }
    return aliases.get(text, text)


def find_market_material_price(
    *,
    provider: MaterialPriceProvider | MaterialEstimateProvider | None,
    material: dict[str, Any],
    material_text: Any,
    region: str,
) -> MaterialMarketPrice | None:
    if provider is None:
        return None
    return provider.find_unit_price(
        material_text=material.get("standard_code") or material_text,
        material_spec=material.get("spec") or material.get("raw_text"),
        region=str(material.get("region") or region or "south_china"),
    )


def find_market_surface_treatment_price(
    *,
    provider: SurfaceTreatmentPriceProvider | None,
    treatment_code: str,
    treatment_name: str,
    quantity: dict[str, Any] | None,
    material_text: Any,
    region: str,
) -> SurfaceTreatmentMarketPrice | None:
    if provider is None or quantity is None:
        return None
    return provider.find_unit_price(
        treatment_code=treatment_code,
        treatment_name=treatment_name,
        quantity_unit=quantity.get("unit"),
        material_text=material_text,
        region=region or "south_china",
    )


def material_explanation(
    material_text: Any,
    market_price: MaterialMarketPrice | None,
    *,
    uses_fallback_material_price: bool = False,
) -> str:
    if uses_fallback_material_price:
        return (
            f"Material {material_text} uses first-pass built-in material price by weight. "
            "Review material grade, specification, supplier quote, region, and tax basis."
        )
    if market_price is None:
        return f"Material {material_text} priced by weight."
    if market_price.source_type == "ai_estimate":
        return (
            f"材料 {material_text} 单价来自 GPT-only 估算："
            f"{market_price.region}，{market_price.unit_price:g} {market_price.unit}。"
            "该价格不是实时市场价，需人工复核材料牌号、规格、供应商报价和含税口径。"
        )
    return (
        f"材料 {material_text} 单价来自 Tavily + GPT 实时行情搜索："
        f"{market_price.region}，{market_price.unit_price:g} {market_price.unit}。"
        "需复核来源、地区、规格、日期和含税口径。"
    )


def material_fallback_price_source(price_version: str, material_text: Any) -> dict[str, Any]:
    material_code = normalize_material_text(material_text).upper() or "UNKNOWN"
    return {
        "source_type": "manual",
        "source_id": "a_basic_material_price_table",
        "rule_id": f"A_BASIC_MATERIAL_PRICE_FALLBACK:{material_code}",
        "version": price_version or "a-basic-v1",
    }


def material_fallback_price_review_risk(material_text: Any, unit_price: float) -> dict[str, Any]:
    return risk_item(
        "MATERIAL_FALLBACK_PRICE_REQUIRES_REVIEW",
        "warning",
        (
            "Material unit price uses built-in first-pass price because market search "
            "did not return a usable price. Review supplier quote, specification, "
            "region, date, and tax basis before confirmation."
        ),
        "pricing_core",
        True,
        [
            source_ref(
                "price_rule",
                raw_text=f"{material_text}; built-in unit price {unit_price} CNY/kg",
                rule_code="A_BASIC_MATERIAL_PRICE_FALLBACK",
            )
        ],
    )


def material_weight_review_risk(material_quantity: dict[str, Any]) -> dict[str, Any]:
    return risk_item(
        "MATERIAL_WEIGHT_REQUIRES_REVIEW",
        "warning",
        (
            "Material pricing weight is not calculated from gross weight because "
            "trusted material density is missing. Review the fallback STEP/PDF "
            "weight before confirming the material cost."
        ),
        "pricing_core",
        True,
        [
            source_ref(
                "price_rule",
                raw_text=str(material_quantity.get("review_reason") or ""),
                rule_code="MATERIAL_PRICING_WEIGHT_REQUIRES_REVIEW",
            )
        ],
    )


def market_price_review_risk(market_price: MaterialMarketPrice) -> dict[str, Any]:
    if market_price.source_type == "ai_estimate":
        return risk_item(
            "MATERIAL_AI_ESTIMATE_REQUIRES_REVIEW",
            "warning",
            (
                "材料单价来自 GPT-only 估算，不是实时市场价；"
                "请复核材料牌号、规格、供应商报价、地区和含税口径后再确认报价。"
            ),
            "pricing_core",
            True,
            [
                source_ref(
                    "price_rule",
                    location=market_price.url,
                    raw_text=(
                        f"{market_price.material_code}; AI估算价; "
                        f"{market_price.unit_price} {market_price.unit}; "
                        f"confidence={market_price.confidence}; {market_price.snippet}"
                    ),
                    rule_code=market_price.rule_id,
                )
            ],
        )
    return risk_item(
        "MARKET_PRICE_REQUIRES_REVIEW",
        "warning",
        (
            "材料单价来自实时网络搜索，尚未进入已审核价格规则；"
            "请复核来源、地区、规格、日期和含税口径后再确认报价。"
        ),
        "pricing_core",
        True,
        [
            source_ref(
                "price_rule",
                location=market_price.url,
                raw_text=(
                    f"{market_price.title}; {market_price.unit_price} "
                    f"{market_price.unit}; confidence={market_price.confidence}"
                ),
                rule_code=market_price.rule_id,
            )
        ],
    )


def surface_treatment_market_price_review_risk(
    market_price: SurfaceTreatmentMarketPrice,
) -> dict[str, Any]:
    if market_price.source_type == "ai_estimate":
        return risk_item(
            "SURFACE_TREATMENT_AI_ESTIMATE_REQUIRES_REVIEW",
            "warning",
            (
                "表面处理单价来自 GPT-only 估算，不是实时市场价；"
                "请复核膜厚、面积、批量、供应商报价和含税口径后再确认报价。"
            ),
            "pricing_core",
            True,
            [
                source_ref(
                    "price_rule",
                    location=market_price.url,
                    raw_text=(
                        f"{market_price.treatment_name}; AI估算价; "
                        f"{market_price.unit_price} {market_price.unit}; "
                        f"confidence={market_price.confidence}; {market_price.snippet}"
                    ),
                    rule_code=market_price.rule_id,
                )
            ],
        )
    return risk_item(
        "SURFACE_TREATMENT_MARKET_PRICE_REQUIRES_REVIEW",
        "warning",
        (
            "表面处理单价来自实时网络搜索，尚未进入已审核价格规则；"
            "请复核来源、地区、表面处理类型、单位、日期和含税口径后再确认报价。"
        ),
        "pricing_core",
        True,
        [
            source_ref(
                "price_rule",
                location=market_price.url,
                raw_text=(
                    f"{market_price.treatment_name}; {market_price.title}; "
                    f"{market_price.unit_price} {market_price.unit}; "
                    f"confidence={market_price.confidence}"
                ),
                rule_code=market_price.rule_id,
            )
        ],
    )


def measured_value(value: dict[str, Any] | None) -> float | None:
    if not value:
        return None
    return numeric_value(value.get("value"))


def numeric_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def dimension_factor_to_mm(unit: Any) -> float | None:
    text = str(unit or "mm").strip().lower()
    if text in {"mm", "millimeter", "millimeters"}:
        return 1.0
    if text in {"cm", "centimeter", "centimeters"}:
        return 10.0
    if text in {"m", "meter", "meters"}:
        return 1000.0
    return None


def bbox_dimensions_mm(bounding_box: dict[str, Any]) -> tuple[float, float, float] | None:
    factor = dimension_factor_to_mm(bounding_box.get("unit"))
    length = numeric_value(bounding_box.get("length"))
    width = numeric_value(bounding_box.get("width"))
    height = numeric_value(bounding_box.get("height"))
    if factor is None or length is None or width is None or height is None:
        return None
    return (length * factor, width * factor, height * factor)


def bbox_volume_mm3(bounding_box: dict[str, Any]) -> float | None:
    dimensions = bbox_dimensions_mm(bounding_box)
    if dimensions is None:
        return None
    length, width, height = dimensions
    return round(length * width * height, 4)


def major_face_dimensions_from_dimensions(
    dimensions: tuple[float, float, float],
) -> tuple[float, float]:
    ordered = sorted(dimensions, reverse=True)
    return ordered[0], ordered[1]


def material_thickness_mm(bounding_box: dict[str, Any]) -> float | None:
    dimensions = bbox_dimensions_mm(bounding_box)
    if dimensions is None:
        return None
    return round(min(dimensions), 4)


def major_face_area_mm2(bounding_box: dict[str, Any]) -> float | None:
    dimensions = bbox_dimensions_mm(bounding_box)
    if dimensions is None:
        return None
    major_length, major_width = major_face_dimensions_from_dimensions(dimensions)
    return round(major_length * major_width, 4)


def non_negative_numeric_value(value: Any) -> float:
    number = numeric_value(value)
    if number is None:
        return 0.0
    return max(0.0, number)


def density_kg_per_mm3(material: dict[str, Any]) -> float | None:
    density = numeric_value(material.get("density"))
    if density is None:
        return None
    unit = str(material.get("density_unit") or "").strip().lower()
    if unit in {"kg/mm3", "kg/mm^3"}:
        return density
    if unit in {"g/cm3", "g/cm^3", "g/cc"}:
        return density / 1_000_000
    if unit in {"kg/m3", "kg/m^3"}:
        return density / 1_000_000_000
    if unit in {"g/mm3", "g/mm^3"}:
        return density / 1000
    return None


def material_density_info(material: dict[str, Any]) -> dict[str, Any]:
    density = density_kg_per_mm3(material)
    return {
        "density_kg_per_mm3": density,
        "display_density": material.get("density"),
        "display_unit": material.get("density_unit"),
        "source": material.get("source"),
    }


def convert_area_to_m2(value: float | None, unit: Any) -> float | None:
    if value is None:
        return None
    text = str(unit or "mm2").strip().lower()
    if text in {"m2", "m^2", "㎡"}:
        return value
    if text in {"mm2", "mm^2"}:
        return value / 1_000_000
    if text in {"cm2", "cm^2"}:
        return value / 10_000
    return None


def convert_weight_to_kg(value: float | None, unit: Any) -> float | None:
    if value is None:
        return None
    text = str(unit or "kg").strip().lower()
    if text == "kg":
        return value
    if text == "g":
        return value / 1000
    return None


def quantity_to_kg(quantity: dict[str, Any] | None) -> float | None:
    if not quantity:
        return None
    value = numeric_value(quantity.get("value"))
    if value is None:
        return None
    converted = convert_weight_to_kg(value, quantity.get("unit"))
    return converted if converted is not None else value


def quantity_for_operation(
    quantity_result: dict[str, Any],
    operation_code: str,
) -> dict[str, Any] | None:
    for item in quantity_result.get("items") or []:
        if item.get("operation_code") == operation_code:
            return item
    return None


def find_quantity(
    quantity_result: dict[str, Any],
    quantity_type: str,
) -> dict[str, Any] | None:
    for item in quantity_result.get("items") or []:
        if item.get("quantity_type") == quantity_type:
            return item
    return None


def bbox_cut_area(bounding_box: dict[str, Any]) -> float | None:
    dimensions = bbox_dimensions_mm(bounding_box)
    if dimensions is None:
        return None
    length, width, _height = dimensions
    return round(length * width, 4)


def bounding_box_text(bounding_box: dict[str, Any]) -> str | None:
    length = bounding_box.get("length")
    width = bounding_box.get("width")
    height = bounding_box.get("height")
    if length is None or width is None or height is None:
        return None
    return f"{length}x{width}x{height}"


def is_chemical_plating(requirement: dict[str, Any]) -> bool:
    text = " ".join(
        str(value or "")
        for value in [
            requirement.get("standard_code"),
            requirement.get("raw_text"),
        ]
    ).upper()
    return (
        "CHEMICAL" in text
        or "NICKEL" in text
        or "NI" in text
        or "化学" in text
        or "镍" in text
    )


def cnc_material_factor(material: dict[str, Any]) -> float:
    text = normalize_material_text(
        " ".join(
            str(value or "")
            for value in (
                material.get("raw_text"),
                material.get("standard_code"),
                material.get("standard_name"),
            )
        )
    )
    if any(keyword in text for keyword in ("al6061", "6061", "铝", "aluminum", "aluminium")):
        return 0.8
    if any(keyword in text for keyword in ("sus304", "304不锈钢", "不锈钢304", "stainless")):
        return 1.3
    if any(keyword in text for keyword in ("skd11", "dc53", "cr12", "cr12mov", "模具钢", "工具钢", "toolsteel")):
        return 1.4
    return 1.0


def normalize_material_text(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
        .replace("/", "")
    )


def material_unit_price_from_text(raw_text: Any) -> float | None:
    if raw_text in (None, ""):
        return None
    text = str(raw_text).strip().upper().replace(" ", "").replace("-", "")
    if text in MATERIAL_UNIT_PRICES_PER_KG:
        return MATERIAL_UNIT_PRICES_PER_KG[text]
    for material_key, unit_price in MATERIAL_UNIT_PRICES_PER_KG.items():
        if material_key in text:
            return unit_price
    return None


def sum_amount(items: list[dict[str, Any]], item_type: str) -> float:
    return round(
        sum(float(item.get("amount") or 0) for item in items if item.get("item_type") == item_type),
        2,
    )


def round_up_to_10(value: float) -> float:
    if value <= 0:
        return 0.0
    return float(int((value + 9.99) // 10 * 10))


def missing_price_risk(operation_code: str) -> dict[str, Any]:
    operation_name = OPERATION_LABELS_ZH.get(operation_code, operation_code)
    return risk_item(
        "MISSING_PRICE_OR_QUANTITY",
        "warning",
        f"{operation_name}缺少单价或工程量，需补录后复核报价。",
        "pricing_core",
        True,
        [system_source(f"MISSING_PRICE_OR_QUANTITY:{operation_code}")],
    )


def quantity_risk(
    code: str,
    message: str,
    rule_code: str,
    *,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return risk_item(
        code,
        "warning",
        message,
        "pricing_core",
        True,
        evidence or [system_source(rule_code)],
    )


def append_risk_if_missing(
    risks: list[dict[str, Any]],
    risk: dict[str, Any],
) -> None:
    code = risk.get("code")
    message = risk.get("message")
    if any(item.get("code") == code and item.get("message") == message for item in risks):
        return
    risks.append(risk)


def merge_risks(*risk_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return dedupe_risks([risk for group in risk_groups for risk in group])


def dedupe_risks(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped = []
    for risk in risks:
        key = (str(risk.get("code")), str(risk.get("message")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(risk)
    return deduped


def dedupe_quantity_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped = []
    for item in items:
        quantity_id = item["quantity_id"]
        if quantity_id in seen:
            continue
        seen.add(quantity_id)
        deduped.append(item)
    return deduped


def first_source(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
        return None
    return value if isinstance(value, dict) else None


def system_source(rule_code: str) -> dict[str, Any]:
    return source_ref("system", rule_code=rule_code)


def clamp_confidence(value: Any) -> float:
    number = numeric_value(value)
    if number is None:
        return 0.0
    return min(1.0, max(0.0, number))
