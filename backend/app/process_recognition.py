from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .part_feature_builder import risk_item, source_ref
from .process_dictionary import (
    PROCESS_NAMES,
    PROCESS_SEQUENCE,
    normalize_process_code,
    quote_process_code_for,
)


UNMAPPED_OPERATION_CODE = "unmapped_operation"
ROUTE_META_OPERATION_CODES: set[str] = {"manual_review"}


@dataclass(frozen=True)
class ProcessStageDefinition:
    stage_code: str
    stage_name: str
    description: str
    sequence: int
    operation_codes: tuple[str, ...]


STAGE_DEFINITIONS: tuple[ProcessStageDefinition, ...] = (
    ProcessStageDefinition(
        "material_preparation",
        "来料/备料",
        "确认材料牌号、规格、毛坯状态并准备材料。",
        10,
        ("raw_material_check", "material_prepare"),
    ),
    ProcessStageDefinition(
        "blanking",
        "下料/开料",
        "根据零件类型、毛坯尺寸和材料选择锯切、激光或线割开料。",
        20,
        ("saw_cut", "laser_cut_blank", "laser_cut", "weld_material_cut", "wire_cut_blank"),
    ),
    ProcessStageDefinition(
        "fixture_and_datum",
        "装夹/基准建立",
        "确定装夹、找正、软爪/夹具、防变形支撑和加工基准。",
        30,
        ("fixture_setup", "soft_jaw_fixture", "support_anti_deformation", "second_setup", "side_setup"),
    ),
    ProcessStageDefinition(
        "rough_machining",
        "主体粗加工",
        "先建立主要基准、去除大余量、粗加工主体形状。",
        40,
        (
            "surface_grinding_rough",
            "cnc_milling",
            "cnc_rough_milling",
            "turning",
            "turning_rough",
            "facing",
            "center_drilling",
            "fit_up",
            "welding",
            "weld_grinding",
        ),
    ),
    ProcessStageDefinition(
        "hole_machining",
        "孔预加工",
        "普通孔、侧孔、PCD孔组和螺纹底孔先行加工。",
        50,
        ("drilling", "drilling_through", "drilling_blind", "side_hole_machining", "pcd_hole_pattern", "reverse_side_machining"),
    ),
    ProcessStageDefinition(
        "thread_and_counterbore",
        "沉孔/攻牙",
        "沉孔、反面沉孔、通牙、盲牙、细牙和侧面攻牙。",
        60,
        (
            "countersink",
            "counterbore",
            "countersink_90",
            "reverse_counterbore",
            "tapping",
            "tapping_through",
            "blind_tapping",
            "fine_thread_tapping",
            "side_tapping",
        ),
    ),
    ProcessStageDefinition(
        "profile_and_cavity",
        "外形/槽/型腔加工",
        "加工外形轮廓、槽、台阶、型腔、放电区域和焊后安装面。",
        70,
        ("profile_milling", "step_milling", "slot_milling", "pocket_milling", "edm", "post_weld_machining", "wire_cut_profile"),
    ),
    ProcessStageDefinition(
        "heat_and_stabilize",
        "热处理/去应力",
        "按图纸热处理或在粗精加工之间去应力、时效以稳定尺寸。",
        80,
        ("heat_treatment", "stress_relief"),
    ),
    ProcessStageDefinition(
        "post_heat_correction",
        "热后恢复加工",
        "热处理后按变形、尺寸面、孔、螺纹、氧化皮和硬度验证安排恢复加工。",
        90,
        (
            "straightening",
            "cnc_finish_milling",
            "precision_surface_finish",
            "finish_grinding",
            "cylindrical_grinding",
            "precision_hole",
            "reaming",
            "boring",
            "thread_chasing",
            "sand_blasting",
            "cleaning",
            "hardness_inspection",
        ),
    ),
    ProcessStageDefinition(
        "finish_and_precision",
        "精加工/精孔",
        "稳定后完成精铣、精车、精密面修正、精孔、铰孔和镗孔。",
        100,
        ("cnc_finish_milling", "turning_finish", "grooving_turning", "precision_surface_finish", "precision_hole", "reaming", "boring"),
    ),
    ProcessStageDefinition(
        "deburr_cleaning",
        "去毛刺/倒角/清洗",
        "去毛刺、倒角、锐角倒钝、清洗和去油去屑。",
        110,
        ("deburr", "chamfer_turning", "cleaning"),
    ),
    ProcessStageDefinition(
        "pre_surface",
        "表处前处理",
        "表处前清洗、遮蔽螺纹孔/精孔/功能面。",
        120,
        ("pre_plating_cleaning", "surface_masking", "hard_chrome_masking", "anodize_masking", "powder_masking", "welding_prepare"),
    ),
    ProcessStageDefinition(
        "surface_treatment",
        "表面处理",
        "化学镍、阳极氧化、镀硬铬、喷塑、喷砂等表面处理。",
        130,
        (
            "sand_blasting",
            "chemical_nickel",
            "clear_anodizing",
            "hard_anodizing",
            "color_anodizing",
            "hard_chrome",
            "powder_coating",
            "white_powder_coating",
            "powder_coating_texture",
        ),
    ),
    ProcessStageDefinition(
        "post_surface",
        "表处后处理/复检",
        "表处后回攻清牙、除氢、复铰、修磨和精孔复检。",
        140,
        ("dehydrogenation_bake", "thread_chasing", "post_anodize_reaming", "post_chrome_polishing", "post_surface_precision_hole_check"),
    ),
    ProcessStageDefinition(
        "inspection",
        "专项检验/终检",
        "首件、过程、螺纹、精孔、膜厚、外观、平面度和终检。",
        150,
        (
            "pcd_hole_inspection",
            "thread_inspection",
            "weld_inspection",
            "first_article_inspection",
            "in_process_inspection",
            "precision_hole_inspection",
            "flatness_inspection",
            "coating_thickness_inspection",
            "surface_inspection",
            "post_chrome_inspection",
            "inspection",
        ),
    ),
    ProcessStageDefinition(
        "packaging",
        "防护包装",
        "终检后进行防划伤、防弯曲、防锈和防碰伤包装。",
        160,
        ("protective_packaging",),
    ),
)

STAGE_DICTIONARY = {definition.stage_code: definition for definition in STAGE_DEFINITIONS}
STAGE_SEQUENCE = [definition.stage_code for definition in sorted(STAGE_DEFINITIONS, key=lambda item: item.sequence)]
OPERATION_STAGE_MAP = {
    operation_code: definition.stage_code
    for definition in STAGE_DEFINITIONS
    for operation_code in definition.operation_codes
}
STAGE_REQUIRED_OPERATION_CODES: dict[str, tuple[str, ...]] = {
    "material_preparation": ("raw_material_check", "material_prepare"),
    "blanking": ("saw_cut", "laser_cut_blank", "laser_cut", "weld_material_cut", "wire_cut_blank"),
    "fixture_and_datum": ("fixture_setup", "soft_jaw_fixture", "support_anti_deformation", "second_setup", "side_setup"),
    "rough_machining": ("surface_grinding_rough", "cnc_milling", "cnc_rough_milling", "turning", "turning_rough", "fit_up", "welding"),
    "hole_machining": ("drilling", "drilling_through", "drilling_blind", "side_hole_machining", "pcd_hole_pattern", "reverse_side_machining"),
    "thread_and_counterbore": ("countersink", "counterbore", "countersink_90", "reverse_counterbore", "tapping", "tapping_through", "blind_tapping", "fine_thread_tapping", "side_tapping"),
    "profile_and_cavity": ("profile_milling", "step_milling", "slot_milling", "pocket_milling", "edm", "post_weld_machining", "wire_cut_profile"),
    "heat_and_stabilize": ("heat_treatment", "stress_relief"),
    "post_heat_correction": ("straightening", "cnc_finish_milling", "precision_surface_finish", "finish_grinding", "cylindrical_grinding", "precision_hole", "reaming", "boring", "thread_chasing", "sand_blasting", "cleaning", "hardness_inspection"),
    "finish_and_precision": ("cnc_finish_milling", "turning_finish", "grooving_turning", "precision_surface_finish", "precision_hole", "reaming", "boring"),
    "deburr_cleaning": ("deburr", "chamfer_turning", "cleaning"),
    "pre_surface": ("pre_plating_cleaning", "surface_masking", "hard_chrome_masking", "anodize_masking", "powder_masking", "welding_prepare"),
    "surface_treatment": ("sand_blasting", "chemical_nickel", "clear_anodizing", "hard_anodizing", "color_anodizing", "hard_chrome", "powder_coating", "white_powder_coating", "powder_coating_texture"),
    "post_surface": ("dehydrogenation_bake", "thread_chasing", "post_anodize_reaming", "post_chrome_polishing", "post_surface_precision_hole_check"),
    "inspection": ("pcd_hole_inspection", "thread_inspection", "weld_inspection", "first_article_inspection", "in_process_inspection", "precision_hole_inspection", "flatness_inspection", "coating_thickness_inspection", "surface_inspection", "post_chrome_inspection", "inspection"),
    "packaging": ("protective_packaging",),
}


SUPPORTED_PART_TYPES = {
    "thin_plate",
    "plate",
    "block",
    "complex_block",
    "precision_block",
    "small_irregular",
    "shaft",
    "complex",
    "assembly_candidate",
    "complex_surface_candidate",
    "long_bar",
    "simple_block",
    "shaft_candidate",
    "roller_candidate",
    "unknown",
}
SAW_CUT_PART_TYPES = {
    "thin_plate",
    "plate",
    "block",
    "complex_block",
    "precision_block",
    "long_bar",
    "simple_block",
}
CNC_PART_TYPES = {
    "plate",
    "block",
    "complex_block",
    "precision_block",
    "small_irregular",
    "long_bar",
    "simple_block",
}
COMPLEX_REVIEW_PART_TYPES = {"complex", "assembly_candidate", "complex_surface_candidate", "unknown"}
TURNING_PART_TYPES = {"shaft", "shaft_candidate", "roller_candidate"}
REVIEW_PART_TYPES = COMPLEX_REVIEW_PART_TYPES | {"small_irregular", "shaft_candidate", "roller_candidate"}

WELDING_KEYWORDS = ("焊接", "焊后", "焊缝", "weld", "welding")
ASSEMBLY_KEYWORDS = ("装配", "组装", "组件", "assembly", "assembled")
WIRE_CUT_KEYWORDS = ("线切割", "线割", "慢走丝", "中走丝", "快走丝", "wire cut", "wire-cut")
HEAT_TREATMENT_KEYWORDS = ("热处理", "淬火", "调质", "回火", "氮化", "hrc", "heat treatment")
HARDNESS_INSPECTION_KEYWORDS = ("硬度", "hrc", "hv", "hb", "硬度检测", "硬度检验", "hardness")
HEAT_OXIDE_KEYWORDS = (
    "氧化皮",
    "去氧化皮",
    "除氧化皮",
    "热处理发黑",
    "发黑",
    "烧伤",
    "氧化层",
    "scale",
    "oxide scale",
    "blackened",
)
CHEMICAL_NICKEL_KEYWORDS = ("化学镍", "化学镀镍", "镀镍", "nickel", "ni-p", "chemical nickel")
SURFACE_TREATMENT_OPERATION_CODES = {
    "chemical_nickel",
    "clear_anodizing",
    "hard_anodizing",
    "color_anodizing",
    "hard_chrome",
    "powder_coating",
    "white_powder_coating",
    "powder_coating_texture",
    "sand_blasting",
}
DEBURR_KEYWORDS = ("去毛刺", "毛刺", "飞边", "deburr", "burr")
EDGE_BREAK_KEYWORDS = ("锐角倒钝", "锐边", "倒钝", "break edge", "sharp edge")
SCRATCH_PROTECTION_KEYWORDS = ("不得划伤", "不得擦伤", "防划伤", "防擦伤", "scratch")
SUPPORT_PACKAGING_KEYWORDS = ("避免弯曲", "合理支撑")
STRAIGHTENING_KEYWORDS = ("校平", "校直", "straighten")
INSPECTION_KEYWORDS = ("检验", "检测", "全检", "报告", "inspection", "report")
GRINDING_KEYWORDS = ("精磨", "磨削", "平面磨", "磨床", "grinding", "grind")
ROUGHNESS_KEYWORDS = ("ra", "粗糙度", "精磨", "磨削", "grinding")
FLATNESS_KEYWORDS = ("平面度", "平行度", "垂直度", "flatness", "parallelism")
THICKNESS_PRECISION_KEYWORDS = (
    "厚度公差",
    "厚度尺寸",
    "厚度精度",
    "等厚",
    "关键面",
    "基准面",
    "定位面",
    "配合面",
    "thickness",
    "datum face",
    "mounting face",
)
CYLINDRICAL_GRINDING_KEYWORDS = (
    "外圆磨",
    "圆磨",
    "外圆精磨",
    "轴颈",
    "同轴度",
    "圆跳动",
    "cylindrical grinding",
    "runout",
    "coaxial",
)
HOLE_PRECISION_KEYWORDS = ("h7", "h8", "e8", "g6", "铰孔", "镗孔", "精孔", "配合孔", "ream")
TIGHT_TOLERANCE_KEYWORDS = ("±0.01", "+/-0.01", "+-0.01", "±0.02", "+/-0.02", "+-0.02")
THREAD_CALLOUT_PATTERN = re.compile(r"(?<![A-Za-z])M\s*\d+(?:\.\d+)?", re.IGNORECASE)

TOOL_STEEL_KEYWORDS = ("skd11", "dc53", "cr12", "cr12mov", "模具钢", "工具钢", "tool steel")
STAINLESS_STEEL_KEYWORDS = ("sus304", "304不锈钢", "不锈钢304", "stainless")
ALUMINUM_KEYWORDS = ("al6061", "6061", "6061-t6", "6061t6", "铝", "aluminum", "aluminium")


def build_process_route(
    *,
    task_id: str,
    route_id: str,
    part_feature: dict[str, Any],
    inherited_risks: list[dict[str, Any]],
) -> dict[str, Any]:
    stage_route = plan_process_stages(
        part_feature=part_feature,
        inherited_risks=inherited_risks,
    )
    operations, risks = expand_stage_route_to_operations(
        stage_route=stage_route,
        part_feature=part_feature,
        inherited_risks=inherited_risks,
    )

    return finalize_route(
        task_id=task_id,
        route_id=route_id,
        operations=operations,
        risks=risks,
        stage_route=stage_route,
    )


def build_ai_generated_process_route(
    *,
    task_id: str,
    route_id: str,
    ai_output: dict[str, Any] | None,
    inherited_risks: list[dict[str, Any]],
    part_feature: dict[str, Any] | None = None,
    auto_accept: bool = True,
) -> dict[str, Any]:
    operations: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    stage_route: list[dict[str, Any]] = []
    if not isinstance(ai_output, dict):
        risks.append(ai_process_route_generation_unavailable_risk(ai_output))
        add_operation(
            operations,
            operation_code="manual_review",
            rule_code="AI_PROCESS_ROUTE_GENERATION_MISSING",
            message="AI autonomous process route output is missing.",
            source=system_source("AI_PROCESS_ROUTE_GENERATION_MISSING"),
            confidence=0.0,
            requires_review=True,
            review_reason="AI autonomous process route output is missing.",
        )
    else:
        content = ai_output.get("content")
        if not isinstance(content, dict) or content.get("available") is False:
            risks.append(ai_process_route_generation_unavailable_risk(ai_output))
            add_operation(
                operations,
                operation_code="manual_review",
                rule_code="AI_PROCESS_ROUTE_GENERATION_UNAVAILABLE",
                message=string_value((content or {}).get("summary"))
                or "AI autonomous process route is unavailable.",
                source=ai_source(ai_output, "AI_PROCESS_ROUTE_GENERATION_UNAVAILABLE"),
                confidence=ai_output_confidence(ai_output),
                requires_review=True,
                review_reason="AI autonomous process route is unavailable.",
            )
        else:
            applied_count = 0
            if isinstance(content.get("stages"), list):
                applied_count = add_ai_generated_stages(
                    stage_route,
                    ai_output,
                    risks=risks,
                    auto_accept=auto_accept,
                )
            if applied_count and isinstance(part_feature, dict):
                expanded_operations, expanded_risks = expand_stage_route_to_operations(
                    stage_route=stage_route,
                    part_feature=part_feature,
                    inherited_risks=inherited_risks,
                )
                operations.extend(expanded_operations)
                risks.extend(expanded_risks)
            if not operations:
                applied_count = add_ai_generated_operations(
                    operations,
                    ai_output,
                    auto_accept=auto_accept,
                )
            if applied_count == 0:
                add_operation(
                    operations,
                    operation_code="manual_review",
                    rule_code="AI_PROCESS_ROUTE_GENERATION_EMPTY",
                    message=string_value(content.get("summary"))
                    or "AI autonomous process route did not contain any accepted stages or operations.",
                    source=ai_source(ai_output, "AI_PROCESS_ROUTE_GENERATION_EMPTY"),
                    confidence=ai_output_confidence(ai_output),
                    requires_review=True,
                    review_reason="AI autonomous process route did not contain any accepted stages or operations.",
                )
            elif content.get("review_required") and not auto_accept:
                risks.append(
                    risk_item(
                        "AI_PROCESS_ROUTE_REVIEW_REQUIRED",
                        "warning",
                        string_value(content.get("summary"))
                        or "AI 自主识别工艺路线需要人工复核。",
                        "process_recognition",
                        True,
                        [ai_source(ai_output, "AI_PROCESS_ROUTE_REVIEW_REQUIRED")],
                    )
                )
            risks.append(
                risk_item(
                    "AI_PROCESS_ROUTE_GENERATED",
                    "warning" if content.get("review_required") and not auto_accept else "info",
                    f"AI 自主识别工艺路线已生成，采纳 {applied_count} 个阶段/工序。",
                    "process_recognition",
                    bool(content.get("review_required") and not auto_accept),
                    [ai_source(ai_output, "AI_PROCESS_ROUTE_GENERATED")],
                )
            )

    if not auto_accept:
        append_inherited_review_risks(risks, inherited_risks)
    return finalize_route(
        task_id=task_id,
        route_id=route_id,
        operations=operations,
        risks=risks,
        stage_route=stage_route,
        allow_unmapped_without_review=auto_accept,
        preserve_input_order=True,
    )


def plan_process_stages(
    *,
    part_feature: dict[str, Any],
    inherited_risks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    geometry = part_feature.get("geometry") or {}
    features = part_feature.get("features") or {}
    requirements = part_feature.get("manufacturing_requirements") or {}
    material = part_feature.get("material") or {}
    complexity = features.get("complexity") or {}
    part_type = geometry.get("part_type")
    bbox_complete = has_complete_bounding_box(geometry.get("bounding_box") or {})
    holes = [hole for hole in features.get("holes") or [] if int_value(hole.get("count")) or 0]
    complexity_score = numeric_value(complexity.get("complexity_score"))
    high_complexity = complexity_score is not None and complexity_score >= 60
    thin_or_deformation_risk = (
        part_type == "thin_plate"
        or is_thin_part(geometry, complexity)
        or has_deformation_risk_geometry(geometry)
    )
    tech_text = technical_text(requirements)
    material_normalized = material_text(material)
    heat_required = bool((requirements.get("heat_treatment") or {}).get("required")) or contains_any(tech_text, HEAT_TREATMENT_KEYWORDS)
    surface_code = planned_surface_treatment_code(requirements)
    surface_required = surface_code is not None
    thread_required = (
        any(is_thread_hole(hole) for hole in holes)
        or any(is_side_thread_hole(hole) for hole in holes)
        or any(has_thread_callout(item.get("raw_text")) for item in technical_requirement_items(requirements))
    )
    counterbore_required = any(
        hole.get("hole_type") in {"counterbore", "countersink", "countersink_90", "reverse_counterbore"}
        for hole in holes
    )
    precision_required = (
        any(is_precision_hole(hole) for hole in holes)
        or bool(features.get("precision_requirements"))
        or contains_any(tech_text, HOLE_PRECISION_KEYWORDS + TIGHT_TOLERANCE_KEYWORDS + ROUGHNESS_KEYWORDS + FLATNESS_KEYWORDS)
    )
    slot_or_profile_required = (
        (int_value(complexity.get("slot_count")) or 0) > 0
        or bool(features.get("slots"))
        or has_wire_profile_geometry(geometry, complexity)
        or contains_any(tech_text, WIRE_CUT_KEYWORDS)
    )
    rough_required = part_type in CNC_PART_TYPES or part_type in COMPLEX_REVIEW_PART_TYPES or part_type in TURNING_PART_TYPES or part_type == "thin_plate" or high_complexity
    machining_required = rough_required or bool(holes) or precision_required or slot_or_profile_required

    stages: list[dict[str, Any]] = []
    add_stage(
        stages,
        "material_preparation",
        rule_code="STAGE_MATERIAL_PREPARATION",
        message="所有报价零件先进入来料确认和备料阶段。",
        source=material.get("source") or system_source("STAGE_MATERIAL_PREPARATION"),
        confidence=0.86 if material else 0.55,
        requires_review=not bool(material),
        review_reason=None if material else "材料信息缺失，备料规格需要人工确认。",
    )
    add_stage(
        stages,
        "blanking",
        rule_code="STAGE_BLANKING",
        message="零件加工前需要确定下料/开料方式。",
        source=part_type_source(geometry) if part_type else system_source("STAGE_BLANKING"),
        confidence=0.78 if bbox_complete else 0.48,
        requires_review=not bbox_complete,
        review_reason=None if bbox_complete else "毛坯尺寸不完整，下料方式需要人工确认。",
    )

    if part_type in CNC_PART_TYPES or part_type in COMPLEX_REVIEW_PART_TYPES or thin_or_deformation_risk or any(is_side_hole(hole) for hole in holes):
        add_stage(
            stages,
            "fixture_and_datum",
            rule_code="STAGE_FIXTURE_AND_DATUM",
            message="根据零件类型、侧孔/翻面和变形风险规划装夹、基准和支撑。",
            source=part_type_source(geometry) if part_type else system_source("STAGE_FIXTURE_AND_DATUM"),
            confidence=0.7,
            requires_review=part_type in REVIEW_PART_TYPES or thin_or_deformation_risk,
            review_reason="装夹次数、基准策略或防变形支撑需要工艺复核。",
        )

    if rough_required or contains_any(material_normalized, TOOL_STEEL_KEYWORDS):
        add_stage(
            stages,
            "rough_machining",
            rule_code="STAGE_ROUGH_MACHINING",
            message="先进行主体粗加工/粗磨，建立稳定基准并去除大余量。",
            source=part_type_source(geometry) if part_type else system_source("STAGE_ROUGH_MACHINING"),
            confidence=0.72,
            requires_review=part_type in REVIEW_PART_TYPES or high_complexity,
            review_reason="主体粗加工路线或机时估算需要工艺复核。",
        )

    if holes or thread_required or precision_required:
        add_stage(
            stages,
            "hole_machining",
            rule_code="STAGE_HOLE_MACHINING",
            message="识别到孔、螺纹底孔或精孔证据，需要安排孔预加工。",
            source=system_source("STAGE_HOLE_MACHINING"),
            confidence=0.72,
            requires_review=precision_required,
            review_reason="精孔或高精度孔的前置孔加工方案需要确认。" if precision_required else None,
        )

    if thread_required or counterbore_required:
        add_stage(
            stages,
            "thread_and_counterbore",
            rule_code="STAGE_THREAD_AND_COUNTERBORE",
            message="识别到螺纹、沉孔或反面沉孔证据，需要安排沉孔/攻牙阶段。",
            source=system_source("STAGE_THREAD_AND_COUNTERBORE"),
            confidence=0.72,
            requires_review=True,
            review_reason="请确认沉孔方向、螺纹深度和攻牙方式。",
        )

    if part_type in CNC_PART_TYPES or part_type in COMPLEX_REVIEW_PART_TYPES or slot_or_profile_required:
        add_stage(
            stages,
            "profile_and_cavity",
            rule_code="STAGE_PROFILE_AND_CAVITY",
            message="需要在主体稳定后加工外形、槽、台阶、型腔或特殊轮廓。",
            source=part_type_source(geometry) if part_type else system_source("STAGE_PROFILE_AND_CAVITY"),
            confidence=0.68,
            requires_review=slot_or_profile_required or part_type in COMPLEX_REVIEW_PART_TYPES,
            review_reason="外形/槽/型腔加工方式需要结合图纸和STEP复核。" if (slot_or_profile_required or part_type in COMPLEX_REVIEW_PART_TYPES) else None,
        )

    if heat_required or (contains_any(material_normalized, TOOL_STEEL_KEYWORDS) and (precision_required or contains_any(tech_text, ROUGHNESS_KEYWORDS + FLATNESS_KEYWORDS))):
        add_stage(
            stages,
            "heat_and_stabilize",
            rule_code="STAGE_HEAT_AND_STABILIZE",
            message="材料或技术要求显示需要热处理/去应力，并应放在精加工前后合适位置。",
            source=(requirements.get("heat_treatment") or {}).get("source") or system_source("STAGE_HEAT_AND_STABILIZE"),
            confidence=0.82 if heat_required else 0.6,
            requires_review=not heat_required,
            review_reason=None if heat_required else "模具钢叠加精度要求，是否热处理或去应力需要确认。",
        )

    if heat_required and should_plan_after_heat_treatment_recovery(part_feature):
        add_stage(
            stages,
            "post_heat_correction",
            rule_code="STAGE_POST_HEAT_CORRECTION",
            message="热处理后存在变形、尺寸面、孔、螺纹、氧化皮或硬度验证需求，需要安排热后恢复加工阶段。",
            source=system_source("STAGE_POST_HEAT_CORRECTION"),
            confidence=0.64,
            requires_review=True,
            review_reason="请确认热后校平、精磨、精孔恢复、回攻清牙、表面恢复和硬度检测策略。",
        )

    if machining_required or precision_required or heat_required:
        add_stage(
            stages,
            "finish_and_precision",
            rule_code="STAGE_FINISH_AND_PRECISION",
            message="粗加工/热处理后完成精加工、精孔和关键尺寸修正。",
            source=system_source("STAGE_FINISH_AND_PRECISION"),
            confidence=0.7,
            requires_review=precision_required or heat_required,
            review_reason="精加工余量、精孔顺序和检具要求需要确认。" if (precision_required or heat_required) else None,
        )

    if machining_required or (requirements.get("deburring") or {}).get("required") or contains_any(tech_text, DEBURR_KEYWORDS + EDGE_BREAK_KEYWORDS):
        add_stage(
            stages,
            "deburr_cleaning",
            rule_code="STAGE_DEBURR_CLEANING",
            message="机加工后需要去毛刺、倒角和清洗。",
            source=(requirements.get("deburring") or {}).get("source") or system_source("STAGE_DEBURR_CLEANING"),
            confidence=0.72,
        )

    if surface_required:
        add_stage(
            stages,
            "pre_surface",
            rule_code="STAGE_PRE_SURFACE",
            message="表面处理前需要清洗，并评估螺纹、精孔和功能面的遮蔽。",
            source=(requirements.get("surface_treatment") or {}).get("source") or system_source("STAGE_PRE_SURFACE"),
            confidence=0.72,
            requires_review=True,
            review_reason="表处前遮蔽范围需要确认。",
        )
        add_stage(
            stages,
            "surface_treatment",
            rule_code="STAGE_SURFACE_TREATMENT",
            message="技术要求识别到表面处理，需要安排对应表处阶段。",
            source=(requirements.get("surface_treatment") or {}).get("source") or system_source("STAGE_SURFACE_TREATMENT"),
            confidence=0.8,
            requires_review=surface_code != "chemical_nickel",
            review_reason="请确认表面处理类型、颜色、膜厚和外协标准。" if surface_code != "chemical_nickel" else None,
        )
        add_stage(
            stages,
            "post_surface",
            rule_code="STAGE_POST_SURFACE",
            message="表处后需要根据螺纹、精孔、硬铬或阳极氧化安排后处理和复检。",
            source=system_source("STAGE_POST_SURFACE"),
            confidence=0.66,
            requires_review=thread_required or precision_required or surface_code in {"hard_chrome", "clear_anodizing", "hard_anodizing", "color_anodizing"},
            review_reason="表处后回攻、复铰、除氢或精孔复检需要工艺确认。",
        )

    add_stage(
        stages,
        "inspection",
        rule_code="STAGE_INSPECTION",
        message="所有报价零件需要专项检验和终检。",
        source=(requirements.get("inspection") or {}).get("source") or system_source("STAGE_INSPECTION"),
        confidence=0.76,
        requires_review=precision_required or surface_required or high_complexity,
        review_reason="专项检验范围和检验频次需要确认。" if (precision_required or surface_required or high_complexity) else None,
    )
    add_stage(
        stages,
        "packaging",
        rule_code="STAGE_PACKAGING",
        message="终检后统一进入防护包装，包含防划伤、防弯曲和防锈保护。",
        source=(requirements.get("packaging") or {}).get("source") or system_source("STAGE_PACKAGING"),
        confidence=0.7,
    )

    if any(risk.get("requires_review") for risk in inherited_risks):
        mark_stage_requires_review(stages, "material_preparation", "解析或特征融合阶段存在风险，需要在正式报价前复核。")

    return finalize_stage_route(stages)


def expand_stage_route_to_operations(
    *,
    stage_route: list[dict[str, Any]],
    part_feature: dict[str, Any],
    inherited_risks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    operations: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    geometry = part_feature.get("geometry") or {}
    features = part_feature.get("features") or {}
    requirements = part_feature.get("manufacturing_requirements") or {}
    stage_codes = {str(stage.get("stage_code") or "") for stage in stage_route}

    risks.extend(add_geometry_review_risks(geometry))
    if "material_preparation" in stage_codes:
        add_material_operation(operations, part_feature)
    if "blanking" in stage_codes:
        add_blank_operations(operations, geometry)

    if stage_codes & {
        "fixture_and_datum",
        "rough_machining",
        "profile_and_cavity",
        "heat_and_stabilize",
        "post_heat_correction",
        "finish_and_precision",
    }:
        add_shape_operations(operations, part_feature)
        risks.extend(add_material_preference_operations(operations, part_feature))

    if stage_codes & {"hole_machining", "thread_and_counterbore", "finish_and_precision"}:
        add_hole_operations(operations, features)
        add_precision_requirement_operations(operations, features)

    risks.extend(add_requirement_operations(operations, requirements))
    add_stage_anchor_operations(operations, stage_codes, part_feature)
    add_after_heat_treatment_recovery_operations(operations, stage_codes, part_feature)
    add_post_process_dependent_operations(operations)
    add_inspection_decision_operations(operations, part_feature)
    add_supported_base_operations(operations, requirements)
    add_inherited_review_operation(operations, inherited_risks)
    risks.extend(resolve_process_conflicts(operations, part_feature))
    return operations, risks


def planned_surface_treatment_code(requirements: dict[str, Any]) -> str | None:
    surface_treatment = requirements.get("surface_treatment") or {}
    if surface_treatment.get("required"):
        surface_code = surface_treatment_operation_code(surface_treatment)
        if surface_code:
            return surface_code
    for item in technical_requirement_items(requirements):
        surface_code = surface_treatment_operation_code(
            {
                "standard_code": item.get("standard_code"),
                "raw_text": item.get("raw_text"),
            }
        )
        if surface_code:
            return surface_code
    return None


def add_stage_anchor_operations(
    operations: list[dict[str, Any]],
    stage_codes: set[str],
    part_feature: dict[str, Any],
) -> None:
    geometry = part_feature.get("geometry") or {}
    features = part_feature.get("features") or {}
    requirements = part_feature.get("manufacturing_requirements") or {}
    complexity = features.get("complexity") or {}
    tech_text = technical_text(requirements)

    if "heat_and_stabilize" in stage_codes and not any(
        operation_by_code(operations, code)
        for code in ("heat_treatment", "stress_relief")
    ):
        add_operation(
            operations,
            operation_code="stress_relief",
            rule_code="STAGE_HEAT_AND_STABILIZE_STRESS_RELIEF",
            message="阶段路线包含热处理/去应力，但未落到具体热处理工序，补充去应力候选以保持阶段与详细工序一致。",
            source=system_source("STAGE_HEAT_AND_STABILIZE_STRESS_RELIEF"),
            confidence=0.56,
            requires_review=True,
            review_reason="请确认该阶段应为热处理、去应力还是仅作为风险提示。",
        )

    if "post_heat_correction" not in stage_codes:
        return
    if any(
        operation_by_code(operations, code)
        for code in ("straightening", "finish_grinding", "cylindrical_grinding")
    ):
        return

    if should_add_post_heat_cylindrical_grinding(part_feature):
        add_operation(
            operations,
            operation_code="cylindrical_grinding",
            rule_code="STAGE_POST_HEAT_CORRECTION_CYLINDRICAL_GRINDING",
            message="阶段路线包含热后恢复加工，且零件为轴类或存在外圆/同轴度/跳动精度证据，展开为热后圆磨候选。",
            source=system_source("STAGE_POST_HEAT_CORRECTION_CYLINDRICAL_GRINDING"),
            confidence=0.64,
            requires_review=True,
            review_reason="请确认热后是否需要圆磨修正关键外圆或配合尺寸。",
        )
        return

    if should_add_post_heat_straightening(part_feature):
        add_operation(
            operations,
            operation_code="straightening",
            rule_code="STAGE_POST_HEAT_CORRECTION_STRAIGHTENING",
            message="阶段路线包含热后恢复加工，且存在校平/校直、薄板、薄壁或长条件变形风险证据，展开为热后校平/校直候选。",
            source=system_source("STAGE_POST_HEAT_CORRECTION_STRAIGHTENING"),
            confidence=0.66,
            requires_review=True,
            review_reason="请确认热处理后是否需要校平/校直。",
        )

    if should_add_post_heat_finish_grinding(part_feature):
        add_operation(
            operations,
            operation_code="finish_grinding",
            rule_code="STAGE_POST_HEAT_CORRECTION_FINISH_GRINDING",
            message="阶段路线包含热后恢复加工，且存在精磨、平面度、粗糙度、厚度或关键基准面精度证据，展开为热后精磨候选。",
            source=system_source("STAGE_POST_HEAT_CORRECTION_FINISH_GRINDING"),
            confidence=0.64,
            requires_review=True,
            review_reason="请确认热处理后是否需要精磨或以其他精加工方式修正尺寸。",
        )


def add_after_heat_treatment_recovery_operations(
    operations: list[dict[str, Any]],
    stage_codes: set[str],
    part_feature: dict[str, Any],
) -> None:
    if "post_heat_correction" not in stage_codes:
        return
    if not operation_by_code(operations, "heat_treatment"):
        return

    features = part_feature.get("features") or {}
    requirements = part_feature.get("manufacturing_requirements") or {}
    holes = features.get("holes") or []
    text = post_heat_decision_text(part_feature)
    source = system_source("AFTER_HEAT_TREATMENT_RECOVERY")

    add_operation(
        operations,
        operation_code="hardness_inspection",
        rule_code="AFTER_HEAT_HARDNESS_INSPECTION",
        message="热处理后需要验证硬度或热处理状态，安排硬度检测。",
        source=source,
        confidence=0.72 if contains_any(text, HARDNESS_INSPECTION_KEYWORDS) else 0.62,
        requires_review=True,
        review_reason="请确认硬度范围、检测位置和检测报告要求。",
    )

    if should_add_post_heat_straightening(part_feature) and not operation_by_code(operations, "straightening"):
        add_operation(
            operations,
            operation_code="straightening",
            rule_code="AFTER_HEAT_DEFORMATION_RECOVERY",
            message="热处理后存在变形风险，安排校平/校直作为恢复加工候选。",
            source=source,
            confidence=0.66,
            requires_review=True,
            review_reason="请确认热处理后实际变形量和校平/校直方式。",
        )

    if should_add_post_heat_cylindrical_grinding(part_feature) and not operation_by_code(operations, "cylindrical_grinding"):
        add_operation(
            operations,
            operation_code="cylindrical_grinding",
            rule_code="AFTER_HEAT_CYLINDRICAL_RECOVERY",
            message="热处理后轴类或外圆精度需要恢复，安排圆磨候选。",
            source=source,
            confidence=0.64,
            requires_review=True,
            review_reason="请确认热后外圆、轴颈、同轴度或跳动恢复方式。",
        )

    if should_add_post_heat_finish_grinding(part_feature):
        if not operation_by_code(operations, "finish_grinding"):
            add_operation(
                operations,
                operation_code="finish_grinding",
                rule_code="AFTER_HEAT_SURFACE_DIMENSION_RECOVERY",
                message="热处理后存在平面度、粗糙度、厚度或关键面精度证据，安排精磨恢复尺寸候选。",
                source=source,
                confidence=0.66,
                requires_review=True,
                review_reason="请确认热后精磨余量、基准面和尺寸恢复策略。",
            )
        if not operation_by_code(operations, "precision_surface_finish"):
            add_operation(
                operations,
                operation_code="precision_surface_finish",
                rule_code="AFTER_HEAT_PRECISION_SURFACE_RECOVERY",
                message="热处理后关键定位面或配合面可能需要精密面修正。",
                source=source,
                confidence=0.58,
                requires_review=True,
                review_reason="请确认是 CNC 精修、精磨还是其他方式恢复关键面尺寸。",
            )

    if any(is_precision_hole(hole) for hole in holes) or contains_any(text, HOLE_PRECISION_KEYWORDS):
        preferred_code = post_heat_precision_hole_recovery_code(holes, text)
        add_operation(
            operations,
            operation_code=preferred_code,
            rule_code="AFTER_HEAT_PRECISION_HOLE_RECOVERY",
            message="热处理后精孔可能发生收缩或位置变化，安排精孔恢复加工候选。",
            source=source,
            confidence=0.66,
            requires_review=True,
            review_reason="请确认热后精孔余量、孔径公差和铰孔/镗孔/精孔方式。",
        )

    if has_thread_after_heat_recovery(part_feature):
        add_operation(
            operations,
            operation_code="thread_chasing",
            rule_code="AFTER_HEAT_THREAD_CHASING",
            message="热处理后螺纹可能有氧化、毛刺或卡牙风险，安排回攻/清牙候选。",
            source=source,
            confidence=0.62,
            requires_review=True,
            review_reason="请确认热处理后螺纹是否需要回攻/清牙以及是否已做遮蔽保护。",
        )

    if contains_any(text, HEAT_OXIDE_KEYWORDS):
        add_operation(
            operations,
            operation_code="sand_blasting",
            rule_code="AFTER_HEAT_OXIDE_SANDBLASTING",
            message="热处理后存在氧化皮、发黑或烧伤表面恢复证据，安排喷砂候选。",
            source=source,
            confidence=0.64,
            requires_review=True,
            review_reason="请确认热后氧化皮去除方式、表面粗糙度和后续表处要求。",
        )
        add_operation(
            operations,
            operation_code="cleaning",
            rule_code="AFTER_HEAT_OXIDE_CLEANING",
            message="热处理后表面恢复需要清洗去油去屑。",
            source=source,
            confidence=0.62,
            requires_review=True,
            review_reason="请确认热后清洗标准和是否进入后续表面处理。",
        )

    if planned_surface_treatment_code(requirements):
        add_operation(
            operations,
            operation_code="pre_plating_cleaning",
            rule_code="AFTER_HEAT_PRE_SURFACE_CLEANING",
            message="热处理后仍有后续表面处理，需要保留表处前清洗/准备。",
            source=source,
            confidence=0.62,
            requires_review=True,
            review_reason="请确认热处理后到表面处理前的清洗、防锈和遮蔽要求。",
        )


def add_stage(
    stages: list[dict[str, Any]],
    stage_code: str,
    *,
    rule_code: str,
    message: str,
    source: dict[str, Any] | None,
    confidence: float,
    requires_review: bool = False,
    review_reason: str | None = None,
) -> None:
    definition = STAGE_DICTIONARY[stage_code]
    reason = {
        "rule_code": rule_code,
        "message": message,
        "source": source or system_source(rule_code),
    }
    existing = stage_by_code(stages, stage_code)
    if existing:
        existing["trigger_reasons"].append(reason)
        existing["confidence"] = max(existing["confidence"], clamp_confidence(confidence))
        existing["requires_review"] = bool(existing["requires_review"] or requires_review)
        existing["review_reason"] = existing.get("review_reason") or review_reason
        return

    stages.append(
        {
            "stage_id": "",
            "stage_code": stage_code,
            "stage_name": definition.stage_name,
            "sequence": 1,
            "description": definition.description,
            "planned_operation_codes": list(definition.operation_codes),
            "trigger_reasons": [reason],
            "confidence": clamp_confidence(confidence),
            "requires_review": requires_review,
            "review_reason": review_reason,
        }
    )


def stage_by_code(stages: list[dict[str, Any]], stage_code: str) -> dict[str, Any] | None:
    return next((stage for stage in stages if stage.get("stage_code") == stage_code), None)


def mark_stage_requires_review(stages: list[dict[str, Any]], stage_code: str, reason: str) -> None:
    stage = stage_by_code(stages, stage_code)
    if not stage:
        return
    stage["requires_review"] = True
    stage["review_reason"] = stage.get("review_reason") or reason


def finalize_stage_route(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(stages, key=stage_sequence_key)
    for index, stage in enumerate(ordered, start=1):
        stage_code = str(stage["stage_code"]).lower()
        stage["sequence"] = index
        stage["stage_id"] = f"stage_{index:03d}_{stage_code}"
    return ordered


def stage_sequence_key(stage: dict[str, Any]) -> tuple[int, str]:
    stage_code = str(stage.get("stage_code") or "")
    try:
        sequence = STAGE_SEQUENCE.index(stage_code)
    except ValueError:
        sequence = len(STAGE_SEQUENCE)
    return (sequence, str(stage.get("stage_name") or stage_code))


def is_thread_hole(hole: dict[str, Any]) -> bool:
    return str(hole.get("hole_type") or "") in {
        "thread_candidate",
        "thread",
        "tapped",
        "tapping",
        "blind_thread",
        "through_thread",
    }


def is_precision_hole(hole: dict[str, Any]) -> bool:
    return str(hole.get("hole_type") or "") in {
        "precision_candidate",
        "precision",
        "reaming",
        "boring",
    } or contains_any(
        normalize_text(
            " ".join(
                str(value or "")
                for value in (
                    hole.get("raw_text"),
                    hole.get("standard_type"),
                    hole.get("tolerance"),
                    hole.get("fit"),
                )
            )
        ),
        HOLE_PRECISION_KEYWORDS + TIGHT_TOLERANCE_KEYWORDS,
    )


def is_side_thread_hole(hole: dict[str, Any]) -> bool:
    if not is_side_hole(hole):
        return False
    if is_thread_hole(hole):
        return True
    text = normalize_text(
        " ".join(
            str(value or "")
            for value in (
                hole.get("hole_type"),
                hole.get("raw_text"),
                hole.get("standard_type"),
                hole.get("feature_role"),
            )
        )
    )
    return has_thread_callout(hole.get("raw_text")) or contains_any(
        text,
        ("螺纹", "攻牙", "攻丝", "thread", "tapping"),
    )


def add_material_operation(
    operations: list[dict[str, Any]],
    part_feature: dict[str, Any],
) -> None:
    material = part_feature.get("material") or {}
    material_text = material.get("raw_text") or material.get("standard_code")
    add_operation(
        operations,
        operation_code="material_prepare",
        rule_code="MATERIAL_PRESENT" if material_text else "MATERIAL_MISSING",
        message="材料字段存在，触发备料。" if material_text else "材料字段缺失，备料需人工确认。",
        source=material.get("source"),
        confidence=0.85 if material_text else 0.3,
        requires_review=not bool(material_text),
        review_reason=None if material_text else "Material is missing.",
    )
    if material_text:
        add_operation(
            operations,
            operation_code="raw_material_check",
            rule_code="RAW_MATERIAL_CHECK_FROM_MATERIAL",
            message="材料已识别，备料前需确认牌号、规格、毛坯尺寸和表面状态。",
            source=material.get("source"),
            confidence=0.78,
        )
    else:
        add_operation(
            operations,
            operation_code="raw_material_check",
            rule_code="RAW_MATERIAL_CHECK_MATERIAL_MISSING",
            message="材料缺失，来料牌号和规格需要人工确认。",
            source=material.get("source") or system_source("RAW_MATERIAL_CHECK_MATERIAL_MISSING"),
            confidence=0.35,
            requires_review=True,
            review_reason="材料牌号和毛坯规格缺失。",
        )


def add_geometry_review_risks(
    geometry: dict[str, Any],
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    part_type = geometry.get("part_type")
    if part_type in REVIEW_PART_TYPES:
        risks.append(
            risk_item(
                "PART_TYPE_REQUIRES_REVIEW",
                "warning",
                f"零件类型为 {part_type}，属于候选、复杂或未知粗分类，需人工确认后再用于完整工艺和报价。",
                "process_recognition",
                True,
                [part_type_source(geometry)],
            )
        )
    if part_type in SUPPORTED_PART_TYPES and has_complete_bounding_box(geometry.get("bounding_box") or {}):
        return risks
    if part_type in SUPPORTED_PART_TYPES:
        risks.append(
            risk_item(
                "BOUNDING_BOX_MISSING",
                "warning",
                "零件类型已识别，但毛坯尺寸不完整，需人工确认毛坯尺寸后再定下料和主体加工路线。",
                "process_recognition",
                True,
                [part_type_source(geometry)],
            )
        )
    elif not part_type:
        risks.append(
            risk_item(
                "PART_TYPE_MISSING",
                "warning",
                "零件类型缺失，不能可靠识别下料和主体加工路线，需人工确认。",
                "process_recognition",
                True,
                [system_source("PART_TYPE_MISSING")],
            )
        )
    return risks


def add_blank_operations(
    operations: list[dict[str, Any]],
    geometry: dict[str, Any],
) -> None:
    part_type = geometry.get("part_type")
    bbox = geometry.get("bounding_box") or {}
    if not has_complete_bounding_box(bbox):
        return

    if part_type in SAW_CUT_PART_TYPES:
        add_operation(
            operations,
            operation_code="saw_cut",
            rule_code="BLANK_SAW_CUT_FROM_PART_TYPE",
            message=f"零件类型为 {part_type} 且毛坯尺寸完整，触发锯切下料。",
            source=part_type_source(geometry),
            confidence=part_type_confidence(geometry, 0.78),
        )
    elif part_type == "small_irregular":
        add_operation(
            operations,
            operation_code="wire_cut_blank",
            rule_code="WIRE_CUT_BLANK_SMALL_IRREGULAR",
            message="零件类型为小型异形件，线割开料作为候选下料方式。",
            source=part_type_source(geometry),
            confidence=part_type_confidence(geometry, 0.68),
            requires_review=True,
            review_reason="Small irregular blanking method needs confirmation.",
        )


def add_shape_operations(
    operations: list[dict[str, Any]],
    part_feature: dict[str, Any],
) -> None:
    geometry = part_feature.get("geometry") or {}
    features = part_feature.get("features") or {}
    complexity = features.get("complexity") or {}
    requirements = part_feature.get("manufacturing_requirements") or {}
    part_type = geometry.get("part_type")
    complexity_score = numeric_value(complexity.get("complexity_score"))
    slot_count = int_value(complexity.get("slot_count")) or 0
    small_radius_count = int_value(complexity.get("small_radius_count")) or 0
    wire_profile_geometry = has_wire_profile_geometry(geometry, complexity)
    tech_text = technical_text(requirements)
    thin_or_deformation_risk = (
        part_type == "thin_plate"
        or is_thin_part(geometry, complexity)
        or has_deformation_risk_geometry(geometry)
    )
    high_complexity = complexity_score is not None and complexity_score >= 60

    if part_type in CNC_PART_TYPES:
        requires_review = part_type == "small_irregular" or complexity_score is None
        add_operation(
            operations,
            operation_code="fixture_setup",
            rule_code="FIXTURE_SETUP_FROM_PART_TYPE",
            message=f"零件类型为 {part_type}，CNC 加工前需要装夹/找正。",
            source=part_type_source(geometry),
            confidence=part_type_confidence(geometry, 0.7),
            requires_review=requires_review,
            review_reason=(
                "Fixture setup count needs confirmation for small irregular parts or missing complexity."
                if requires_review
                else None
            ),
        )
        add_operation(
            operations,
            operation_code="cnc_rough_milling",
            rule_code="CNC_ROUGH_MILLING_FROM_PART_TYPE",
            message=f"零件类型为 {part_type}，触发 CNC 粗铣建立基准和去余量。",
            source=part_type_source(geometry),
            confidence=part_type_confidence(geometry, 0.72),
            requires_review=requires_review,
            review_reason=(
                "CNC rough milling route needs confirmation for small irregular parts or missing complexity."
                if requires_review
                else None
            ),
        )
        add_operation(
            operations,
            operation_code="cnc_finish_milling",
            rule_code="CNC_FROM_PART_TYPE",
            message=(
                f"零件类型为 {part_type}，触发 CNC 精铣候选。"
                if requires_review
                else f"零件类型为 {part_type}，触发 CNC 精铣。"
            ),
            source=part_type_source(geometry),
            confidence=part_type_confidence(geometry, 0.72),
            requires_review=requires_review,
            review_reason=(
                "CNC finish milling route needs confirmation for small irregular parts or missing complexity."
                if requires_review
                else None
            ),
        )
        if part_type in {
            "plate",
            "block",
            "complex_block",
            "precision_block",
            "small_irregular",
            "long_bar",
            "simple_block",
        }:
            add_operation(
                operations,
                operation_code="profile_milling",
                rule_code="PROFILE_MILLING_FROM_PART_TYPE",
                message=f"零件类型为 {part_type}，外形轮廓铣削作为主体外形加工。",
                source=part_type_source(geometry),
                confidence=part_type_confidence(geometry, 0.68),
                requires_review=requires_review,
                review_reason=(
                    "Profile milling route needs confirmation for small irregular parts or missing complexity."
                    if requires_review
                    else None
                ),
            )

    if part_type in COMPLEX_REVIEW_PART_TYPES:
        add_operation(
            operations,
            operation_code="fixture_setup",
            rule_code="FIXTURE_SETUP_COMPLEX_PART",
            message="复杂件需要在粗加工前确认加工基准和装夹方案。",
            source=part_type_source(geometry),
            confidence=part_type_confidence(geometry, 0.66),
            requires_review=True,
            review_reason="复杂件装夹次数和基准策略需要工艺复核。",
        )

    if part_type in REVIEW_PART_TYPES or high_complexity:
        add_operation(
            operations,
            operation_code="soft_jaw_fixture",
            rule_code="SOFT_JAW_FIXTURE_FROM_GEOMETRY_RISK",
            message="异形、复杂或高复杂度几何可能需要软爪/专用夹具。",
            source=part_type_source(geometry) if part_type else system_source("SOFT_JAW_FIXTURE_FROM_GEOMETRY_RISK"),
            confidence=0.62 if high_complexity else part_type_confidence(geometry, 0.62),
            requires_review=True,
            review_reason="请确认是否需要软爪或专用夹具。",
        )

    if thin_or_deformation_risk:
        add_operation(
            operations,
            operation_code="support_anti_deformation",
            rule_code="SUPPORT_ANTI_DEFORMATION_FROM_GEOMETRY",
            message="薄板、大板或长条件需要规划防变形支撑。",
            source=part_type_source(geometry) if part_type else system_source("SUPPORT_ANTI_DEFORMATION_FROM_GEOMETRY"),
            confidence=0.66,
            requires_review=True,
            review_reason="请确认装夹支撑、对称加工和变形余量。",
        )

    if part_type == "thin_plate" or is_thin_part(geometry, complexity):
        add_operation(
            operations,
            operation_code="wire_cut_profile",
            rule_code="WIRE_PROFILE_THIN_PART",
            message="薄片件或薄壁候选触发线切割外形候选。",
            source=part_type_source(geometry),
            confidence=0.78,
            requires_review=True,
            review_reason="Wire-cut profile is a candidate and needs process confirmation.",
        )
        add_operation(
            operations,
            operation_code="surface_grinding_rough",
            rule_code="THIN_PART_REFERENCE_GRINDING",
            message="薄片件需要建立基准和平面厚度控制，触发平面粗磨候选。",
            source=part_type_source(geometry),
            confidence=0.62,
            requires_review=True,
            review_reason="Thin-part grinding requirement needs confirmation.",
        )
        add_operation(
            operations,
            operation_code="straightening",
            rule_code="THIN_PART_STRAIGHTENING_CANDIDATE",
            message="薄片件存在变形风险，校平/校直作为候选工序。",
            source=part_type_source(geometry),
            confidence=0.62,
            requires_review=True,
            review_reason="Thin-part straightening is a candidate and needs confirmation.",
        )
    if slot_count > 0:
        add_operation(
            operations,
            operation_code="slot_milling",
            rule_code="WIRE_PROFILE_SLOT_CANDIDATE",
            message=f"STEP 复杂度包含槽候选 {slot_count} 个，触发槽加工候选。",
            source=system_source("WIRE_PROFILE_SLOT_CANDIDATE"),
            confidence=0.72,
            requires_review=True,
            review_reason="Slot machining method needs confirmation.",
        )

    if small_radius_count >= 3 and wire_profile_geometry:
        add_operation(
            operations,
            operation_code="wire_cut_profile",
            rule_code="WIRE_PROFILE_SMALL_RADIUS",
            message=f"STEP 外轮廓/槽特征叠加小 R 候选 {small_radius_count} 个，触发线切割候选。",
            source=system_source("WIRE_PROFILE_SMALL_RADIUS"),
            confidence=0.68,
            requires_review=True,
            review_reason="Small-radius machining method needs confirmation.",
        )

    if complexity_score is not None and complexity_score >= 60 and wire_profile_geometry:
        add_operation(
            operations,
            operation_code="wire_cut_profile",
            rule_code="WIRE_PROFILE_COMPLEXITY_SCORE",
            message=f"外轮廓/槽特征叠加复杂度评分 {complexity_score:g}，触发线切割外形候选。",
            source=system_source("WIRE_PROFILE_COMPLEXITY_SCORE"),
            confidence=0.65,
            requires_review=True,
            review_reason="High complexity may need wire cutting confirmation.",
        )

    if contains_any(tech_text, WIRE_CUT_KEYWORDS):
        add_operation(
            operations,
            operation_code="wire_cut_profile",
            rule_code="TECH_REQ_WIRE_CUT",
            message="技术要求明确出现线切割/走丝，触发线切割外形。",
            source=technical_source(requirements, WIRE_CUT_KEYWORDS),
            confidence=0.86,
            requires_review=False,
        )

    if part_type in TURNING_PART_TYPES:
        add_operation(
            operations,
            operation_code="turning_rough",
            rule_code="TURNING_ROUGH_FROM_SHAFT_PART_TYPE",
            message=f"零件类型为 {part_type}，触发粗车去余量候选。",
            source=part_type_source(geometry),
            confidence=part_type_confidence(geometry, 0.78),
            requires_review=True,
            review_reason="Shaft rough turning route and machine-hour estimate need process review.",
        )
        add_operation(
            operations,
            operation_code="turning_finish",
            rule_code="TURNING_FROM_SHAFT_PART_TYPE",
            message=f"零件类型为 {part_type}，触发精车加工候选。",
            source=part_type_source(geometry),
            confidence=part_type_confidence(geometry, 0.78),
            requires_review=True,
            review_reason="Shaft finish turning route and machine-hour estimate need process review.",
        )
        if has_heat_or_precision_requirement(part_feature):
            add_operation(
                operations,
                operation_code="cylindrical_grinding",
                rule_code="CYLINDRICAL_GRINDING_SHAFT_PRECISION",
                message="轴类/滚筒候选叠加热处理或精度要求，触发圆磨候选。",
                source=part_type_source(geometry),
                confidence=part_type_confidence(geometry, 0.68),
                requires_review=True,
                review_reason="Shaft precision or heat-treatment requirement may need cylindrical grinding.",
            )

    if part_type in COMPLEX_REVIEW_PART_TYPES:
        add_operation(
            operations,
            operation_code="cnc_rough_milling",
            rule_code="CNC_FROM_COMPLEX_PART_TYPE",
            message="零件类型为复杂件，触发 CNC 粗加工估算。",
            source=part_type_source(geometry),
            confidence=part_type_confidence(geometry, 0.68),
            requires_review=True,
            review_reason="Complex-part CNC route needs process review.",
        )
        add_operation(
            operations,
            operation_code="cnc_finish_milling",
            rule_code="CNC_FINISH_FROM_COMPLEX_PART_TYPE",
            message="零件类型为复杂件，触发 CNC 精加工估算。",
            source=part_type_source(geometry),
            confidence=part_type_confidence(geometry, 0.68),
            requires_review=True,
            review_reason="Complex-part CNC finish route needs process review.",
        )
        add_operation(
            operations,
            operation_code="pocket_milling",
            rule_code="POCKET_MILLING_COMPLEX_PART_CANDIDATE",
            message="复杂件可能存在型腔、凹槽或减重槽，型腔/凹槽加工作为候选。",
            source=part_type_source(geometry),
            confidence=part_type_confidence(geometry, 0.58),
            requires_review=True,
            review_reason="Complex geometry may need pocket milling; confirm with drawing and STEP features.",
        )
        add_operation(
            operations,
            operation_code="edm",
            rule_code="EDM_COMPLEX_PART_CANDIDATE",
            message="复杂件可能存在型腔、窄槽或难加工区域，放电加工作为候选工序。",
            source=part_type_source(geometry),
            confidence=part_type_confidence(geometry, 0.58),
            requires_review=True,
            review_reason="Complex geometry may need EDM; confirm with drawing and STEP features.",
        )

    if high_complexity or thin_or_deformation_risk:
        add_operation(
            operations,
            operation_code="stress_relief",
            rule_code="STRESS_RELIEF_FROM_ROUGHING_RISK",
            message="高复杂度或易变形几何可能需要粗加工后、精加工前去应力/时效。",
            source=part_type_source(geometry) if part_type else system_source("STRESS_RELIEF_FROM_ROUGHING_RISK"),
            confidence=0.58,
            requires_review=True,
            review_reason="请确认是否需要在粗精加工之间安排去应力或时效。",
        )


def add_material_preference_operations(
    operations: list[dict[str, Any]],
    part_feature: dict[str, Any],
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    material = part_feature.get("material") or {}
    geometry = part_feature.get("geometry") or {}
    features = part_feature.get("features") or {}
    complexity = features.get("complexity") or {}
    text = material_text(material)
    source = material.get("source") or system_source("MATERIAL_RULE")
    geometry_ready = (
        geometry.get("part_type") in SUPPORTED_PART_TYPES
        and has_complete_bounding_box(geometry.get("bounding_box") or {})
    )

    if contains_any(text, TOOL_STEEL_KEYWORDS):
        if geometry_ready and should_prefer_wire_cut_for_tool_steel(geometry, complexity):
            add_operation(
                operations,
                operation_code="wire_cut_profile",
                rule_code="MATERIAL_TOOL_STEEL_WIRE_CUT",
                message="材料为模具钢且叠加薄片/异形/槽/小R等特征，线切割外形作为候选。",
                source=source,
                confidence=0.68,
                requires_review=True,
                review_reason="Tool-steel wire-cut preference needs process confirmation.",
            )
        if geometry_ready:
            add_operation(
                operations,
                operation_code="surface_grinding_rough",
                rule_code="MATERIAL_TOOL_STEEL_REFERENCE_GRINDING",
                message="材料为模具钢，平面粗磨作为建立基准和控制变形的候选工序。",
                source=source,
                confidence=0.58,
                requires_review=True,
                review_reason="Tool-steel grinding preference needs confirmation.",
            )
        if geometry_ready and should_add_post_heat_finish_grinding(part_feature):
            add_operation(
                operations,
                operation_code="finish_grinding",
                rule_code="MATERIAL_TOOL_STEEL_FINISH_GRINDING",
                message="材料为模具钢且存在精磨、平面度、粗糙度、厚度或关键基准面精度证据，精磨作为候选工序。",
                source=source,
                confidence=0.62,
                requires_review=True,
                review_reason="Tool-steel finish grinding needs confirmation.",
            )
        risks.append(
            risk_item(
                "MATERIAL_PROCESS_RISK",
                "warning",
                "模具钢可能存在热处理变形、淬硬后加工困难或磨削需求，需复核工艺路线。",
                "process_recognition",
                True,
                [source],
            )
        )
    elif contains_any(text, STAINLESS_STEEL_KEYWORDS):
        risks.append(
            risk_item(
                "MATERIAL_PROCESS_RISK",
                "warning",
                "SUS304/不锈钢可能存在加工硬化和刀具磨损风险，需复核刀具和加工参数。",
                "process_recognition",
                True,
                [source],
            )
        )
    elif contains_any(text, ALUMINUM_KEYWORDS):
        add_operation(
            operations,
            operation_code="protective_packaging",
            rule_code="MATERIAL_ALUMINUM_SURFACE_PROTECTION",
            message="铝件表面易划伤，触发防护包装。",
            source=source,
            confidence=0.64,
        )
        risks.append(
            risk_item(
                "MATERIAL_PROCESS_RISK",
                "warning",
                "铝件存在表面划伤风险，需关注表面保护和外观要求。",
                "process_recognition",
                True,
                [source],
            )
        )

    return risks


def add_hole_operations(
    operations: list[dict[str, Any]],
    features: dict[str, Any],
) -> None:
    for hole in features.get("holes") or []:
        hole_type = hole.get("hole_type")
        count = int_value(hole.get("count")) or 0
        if not count:
            continue
        confidence = hole.get("confidence", 0.7)
        source = first_source(hole.get("evidence"))
        if is_side_hole(hole):
            add_operation(
                operations,
                operation_code="second_setup",
                rule_code="HOLE_SECOND_SETUP_FROM_SIDE_FEATURE",
                message="识别到侧孔/反面孔证据，可能需要增加装夹或转换基准。",
                source=source,
                confidence=confidence,
                requires_review=True,
                review_reason="请确认侧向/反面加工的装夹次数和基准转换。",
            )
            add_operation(
                operations,
                operation_code="side_setup",
                rule_code="HOLE_SIDE_SETUP_FROM_SIDE_FEATURE",
                message="识别到侧孔证据，侧孔加工前可能需要侧向装夹。",
                source=source,
                confidence=confidence,
                requires_review=True,
                review_reason="请确认侧孔夹具和机床可达性。",
            )
            add_operation(
                operations,
                operation_code="side_hole_machining",
                rule_code="HOLE_SIDE_MACHINING",
                message=f"识别到侧孔证据 {count} 个，触发侧面孔加工。",
                source=source,
                confidence=confidence,
                requires_review=True,
                review_reason="请确认侧孔方向、装夹方式和加工可达性。",
            )
        if is_reverse_hole(hole):
            add_operation(
                operations,
                operation_code="second_setup",
                rule_code="HOLE_SECOND_SETUP_FROM_REVERSE_FEATURE",
                message="识别到反面孔证据，可能需要二次装夹。",
                source=source,
                confidence=confidence,
                requires_review=True,
                review_reason="请确认反面加工装夹和基准转换。",
            )
            add_operation(
                operations,
                operation_code="reverse_side_machining",
                rule_code="HOLE_REVERSE_SIDE_MACHINING",
                message=f"识别到反面孔证据 {count} 个，触发反面加工。",
                source=source,
                confidence=confidence,
                requires_review=True,
                review_reason="请确认该特征是否需要从反面加工。",
            )

        if hole_type == "through":
            add_operation(
                operations,
                operation_code="drilling_through",
                rule_code="HOLE_THROUGH",
                message=f"识别到通孔 {count} 个，触发钻孔。",
                source=source,
                confidence=confidence,
            )
        elif hole_type == "blind":
            add_operation(
                operations,
                operation_code="drilling_blind",
                rule_code="HOLE_BLIND",
                message=f"识别到盲孔 {count} 个，触发钻孔。",
                source=source,
                confidence=confidence,
            )
        elif hole_type in {"counterbore", "countersink"}:
            add_operation(
                operations,
                operation_code="drilling_through" if hole.get("through") else "drilling",
                rule_code="HOLE_COUNTER_FEATURE_PREDRILL",
                message=f"识别到{hole_type} {count} 个，主孔需要钻孔前置。",
                source=source,
                confidence=confidence,
            )
            add_operation(
                operations,
                operation_code="counterbore" if hole_type == "counterbore" else "countersink",
                rule_code="HOLE_COUNTERBORE" if hole_type == "counterbore" else "HOLE_COUNTERSINK",
                message=f"识别到{hole_type} {count} 个，触发沉孔/沉头孔加工。",
                source=source,
                confidence=confidence,
            )
        elif hole_type == "thread_candidate":
            if is_side_hole(hole):
                add_operation(
                    operations,
                    operation_code="side_tapping",
                    rule_code="HOLE_SIDE_THREAD_CANDIDATE",
                    message=f"识别到侧向螺纹孔候选 {count} 个，触发侧面攻牙候选。",
                    source=source,
                    confidence=confidence,
                    requires_review=True,
                    review_reason="请确认侧面攻牙方向、夹具和螺纹标注。",
                )
            add_operation(
                operations,
                operation_code="drilling_through" if hole.get("through") else "drilling_blind",
                rule_code="HOLE_THREAD_PILOT_DRILLING",
                message=f"识别到螺纹孔候选 {count} 个，底孔需要钻孔前置。",
                source=source,
                confidence=confidence,
                requires_review=True,
                review_reason="Thread-hole pilot drilling needs confirmation.",
            )
            add_operation(
                operations,
                operation_code="tapping_through" if hole.get("through") else "blind_tapping",
                rule_code="HOLE_THREAD_CANDIDATE",
                message=f"识别到螺纹孔候选 {count} 个，触发攻牙候选。",
                source=source,
                confidence=confidence,
                requires_review=True,
                review_reason="Thread holes are candidates and need manual or A-side confirmation.",
            )
        elif hole_type == "precision_candidate":
            add_operation(
                operations,
                operation_code="drilling_through" if hole.get("through") else "drilling",
                rule_code="HOLE_PRECISION_PREDRILL",
                message=f"识别到精孔候选 {count} 个，钻孔作为精孔前置。",
                source=source,
                confidence=confidence,
                requires_review=True,
                review_reason="Precision-hole predrilling needs confirmation.",
            )
            add_operation(
                operations,
                operation_code="reaming" if precision_hole_prefers_reaming(hole) else "precision_hole",
                rule_code="HOLE_PRECISION_CANDIDATE",
                message=f"识别到精孔候选 {count} 个，触发精孔加工候选。",
                source=source,
                confidence=confidence,
                requires_review=True,
                review_reason="Precision holes are candidates and need manual or A-side confirmation.",
            )


def add_precision_requirement_operations(
    operations: list[dict[str, Any]],
    features: dict[str, Any],
) -> None:
    for item in features.get("precision_requirements") or []:
        text = " ".join(
            str(value or "")
            for value in (
                item.get("raw_text"),
                item.get("standard_type"),
            )
        )
        normalized = normalize_text(text)
        source = item.get("source")
        confidence = item.get("confidence", 0.65)

        if contains_any(normalized, HOLE_PRECISION_KEYWORDS) or contains_any(normalized, TIGHT_TOLERANCE_KEYWORDS):
            add_operation(
                operations,
                operation_code="drilling",
                rule_code="PRECISION_REQUIREMENT_PREDRILL",
                message="高精度孔或紧公差候选需要钻孔前置。",
                source=source,
                confidence=confidence,
                requires_review=True,
                review_reason="Precision requirement needs hole-process confirmation.",
            )
            add_operation(
                operations,
                operation_code="reaming" if "h7" in normalized else "precision_hole",
                rule_code="PRECISION_REQUIREMENT",
                message="识别到 H7/E8/G6/紧公差等精度要求，触发精孔加工候选。",
                source=source,
                confidence=confidence,
                requires_review=True,
                review_reason="Precision requirement needs process confirmation.",
            )

        if contains_any(normalized, ROUGHNESS_KEYWORDS) or contains_any(normalized, FLATNESS_KEYWORDS):
            add_operation(
                operations,
                operation_code="precision_surface_finish",
                rule_code="ROUGHNESS_OR_FLATNESS_REQUIREMENT",
                message="识别到粗糙度、平面度或精密面要求，触发精密面修正候选。",
                source=source,
                confidence=confidence,
                requires_review=True,
                review_reason="Grinding mapping from precision requirement needs confirmation.",
            )


def add_requirement_operations(
    operations: list[dict[str, Any]],
    requirements: dict[str, Any],
) -> list[dict[str, Any]]:
    risks = add_structured_requirement_operations(operations, requirements)

    for item in technical_requirement_items(requirements):
        raw_text = item["raw_text"]
        normalized = normalize_text(raw_text)
        source = item.get("source")
        confidence = item.get("confidence", 0.72)
        requirement_type = item.get("requirement_type")

        if "3d" in normalized and ("未标注" in raw_text or "参见" in raw_text):
            risks.append(
                risk_item(
                    "TECH_REQ_REVIEW_3D",
                    "warning",
                    "技术要求说明未标注尺寸参见 3D，需人工确认 3D 与图纸约束后再定正式工艺路线。",
                    "process_recognition",
                    True,
                    [source or system_source("TECH_REQ_REVIEW_3D")],
                )
            )

        if has_thread_callout(raw_text):
            add_operation(
                operations,
                operation_code="drilling_through" if contains_any(normalized, ("贯穿", "通孔", "through")) else "drilling",
                rule_code="TECH_REQ_THREAD_PILOT_DRILLING",
                message="技术要求包含 M 螺纹标注，底孔需要钻孔前置。",
                source=source,
                confidence=confidence,
                requires_review=True,
                review_reason="Thread callout pilot drilling needs confirmation.",
            )
            add_operation(
                operations,
                operation_code="tapping_through" if contains_any(normalized, ("贯穿", "通孔", "through")) else "tapping",
                rule_code="TECH_REQ_THREAD_TAPPING",
                message="技术要求包含 M 螺纹标注，触发攻牙候选。",
                source=source,
                confidence=confidence,
                requires_review=True,
                review_reason="Thread callout needs tapping confirmation.",
            )

        if requirement_type in {"deburring", "edge_break"} or contains_any(normalized, DEBURR_KEYWORDS + EDGE_BREAK_KEYWORDS):
            add_operation(
                operations,
                operation_code="deburr",
                rule_code="TECH_REQ_DEBURR_OR_EDGE_BREAK",
                message="技术要求包含去毛刺、飞边、锐角倒钝或倒角，触发去毛刺/倒角合并工序。",
                source=source,
                confidence=confidence,
            )

        if requirement_type == "heat_treatment" or contains_any(normalized, HEAT_TREATMENT_KEYWORDS):
            add_operation(
                operations,
                operation_code="heat_treatment",
                rule_code="TECH_REQ_HEAT_TREATMENT",
                message="技术要求包含热处理关键词，触发热处理。",
                source=source,
                confidence=confidence,
            )

        surface_code = surface_treatment_operation_code(
            {
                "standard_code": item.get("standard_code"),
                "raw_text": raw_text,
            }
        )
        if surface_code:
            add_surface_treatment_operations(
                operations,
                surface_treatment={
                    "raw_text": raw_text,
                    "source": source,
                    "confidence": confidence,
                },
                surface_code=surface_code,
            )

        if requirement_type == "inspection" or contains_any(normalized, INSPECTION_KEYWORDS):
            add_operation(
                operations,
                operation_code="inspection",
                rule_code="TECH_REQ_INSPECTION",
                message="技术要求包含检验/检测要求，触发终检。",
                source=source,
                confidence=confidence,
            )

        if requirement_type == "packaging" or contains_any(normalized, SCRATCH_PROTECTION_KEYWORDS):
            add_operation(
                operations,
                operation_code="protective_packaging",
                rule_code="TECH_REQ_PROTECTIVE_PACKAGING",
                message="技术要求包含防划伤、防擦伤或包装要求，触发防护包装。",
                source=source,
                confidence=confidence,
            )

        if contains_any(normalized, STRAIGHTENING_KEYWORDS):
            add_operation(
                operations,
                operation_code="straightening",
                rule_code="TECH_REQ_STRAIGHTENING",
                message="技术要求明确包含校平/校直，触发校平/校直候选。",
                source=source,
                confidence=confidence,
                requires_review=True,
                review_reason="Straightening requirement needs process confirmation.",
            )

        if contains_any(normalized, SUPPORT_PACKAGING_KEYWORDS):
            add_operation(
                operations,
                operation_code="protective_packaging",
                rule_code="TECH_REQ_SUPPORT_PACKAGING",
                message="技术要求强调防弯曲支撑，归并到防护包装。",
                source=source,
                confidence=confidence,
            )

        if requirement_type == "precision" or contains_any(normalized, ROUGHNESS_KEYWORDS + FLATNESS_KEYWORDS):
            if contains_any(normalized, HOLE_PRECISION_KEYWORDS + TIGHT_TOLERANCE_KEYWORDS):
                add_operation(
                    operations,
                    operation_code="reaming" if "h7" in normalized else "precision_hole",
                    rule_code="TECH_REQ_PRECISION_HOLE",
                    message="技术要求包含高精度孔或紧公差，触发精孔加工候选。",
                    source=source,
                    confidence=confidence,
                    requires_review=True,
                    review_reason="Precision technical requirement needs process confirmation.",
                )
            if contains_any(normalized, ROUGHNESS_KEYWORDS + FLATNESS_KEYWORDS):
                add_operation(
                    operations,
                    operation_code="precision_surface_finish",
                    rule_code="TECH_REQ_FINISH_GRINDING",
                    message="技术要求包含粗糙度、平面度或磨削要求，触发精密面修正候选。",
                    source=source,
                    confidence=confidence,
                    requires_review=True,
                    review_reason="Grinding requirement needs process confirmation.",
                )

    return risks


def add_structured_requirement_operations(
    operations: list[dict[str, Any]],
    requirements: dict[str, Any],
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    heat_treatment = requirements.get("heat_treatment") or {}
    if heat_treatment.get("required"):
        add_operation(
            operations,
            operation_code="heat_treatment",
            rule_code="HEAT_TREATMENT_REQUIRED",
            message=f"结构化字段识别到热处理：{heat_treatment.get('raw_text')}。",
            source=heat_treatment.get("source"),
            confidence=heat_treatment.get("confidence", 0.7),
        )

    surface_treatment = requirements.get("surface_treatment") or {}
    if surface_treatment.get("required"):
        surface_code = surface_treatment_operation_code(surface_treatment)
        if surface_code:
            add_surface_treatment_operations(
                operations,
                surface_treatment=surface_treatment,
                surface_code=surface_code,
            )
        else:
            risks.append(
                risk_item(
                    "SURFACE_TREATMENT_UNKNOWN",
                    "warning",
                    "结构化字段识别到表面处理，但无法映射到已支持的表面处理工序，需人工确认。",
                    "process_recognition",
                    True,
                    [
                        surface_treatment.get("source")
                        or system_source("SURFACE_TREATMENT_UNKNOWN")
                    ],
                )
            )

    deburring = requirements.get("deburring") or {}
    if deburring.get("required"):
        add_operation(
            operations,
            operation_code="deburr",
            rule_code="DEBURRING_REQUIRED",
            message="结构化字段识别到去毛刺、锐角倒钝或倒角要求，归并到去毛刺/倒角工序。",
            source=deburring.get("source"),
            confidence=deburring.get("confidence", 0.65),
        )
    return risks


def add_supported_base_operations(
    operations: list[dict[str, Any]],
    requirements: dict[str, Any],
) -> None:
    inspection = requirements.get("inspection") or {}
    add_operation(
        operations,
        operation_code="inspection",
        rule_code="SUPPORTED_PART_INSPECTION",
        message="报价零件默认需要终检。",
        source=inspection.get("source") or system_source("SUPPORTED_PART_INSPECTION"),
        confidence=inspection.get("confidence", 0.7) if inspection else 0.7,
    )

    packaging = requirements.get("packaging") or {}
    add_operation(
        operations,
        operation_code="protective_packaging",
        rule_code="SUPPORTED_PART_PACKAGING",
        message="报价零件默认需要防护包装。",
        source=packaging.get("source") or system_source("SUPPORTED_PART_PACKAGING"),
        confidence=packaging.get("confidence") or 0.65,
    )


def add_inspection_decision_operations(
    operations: list[dict[str, Any]],
    part_feature: dict[str, Any],
) -> None:
    geometry = part_feature.get("geometry") or {}
    features = part_feature.get("features") or {}
    requirements = part_feature.get("manufacturing_requirements") or {}
    part_quantity = numeric_value((part_feature.get("part") or {}).get("quantity"))
    codes = {str(operation.get("operation_code") or "") for operation in operations}
    complexity = features.get("complexity") or {}
    complexity_score = numeric_value(complexity.get("complexity_score"))
    high_complexity = complexity_score is not None and complexity_score >= 60
    multi_setup = bool(codes & {"second_setup", "reverse_side_machining", "side_setup", "side_hole_machining"})
    precision_hole = bool(codes & {"precision_hole", "reaming", "boring", "post_anodize_reaming"})
    thread = bool(codes & {"tapping", "tapping_through", "blind_tapping", "fine_thread_tapping", "side_tapping"})
    surface = bool(codes & SURFACE_TREATMENT_OPERATION_CODES)
    flatness = (
        has_flatness_requirement(features, requirements)
        or is_thin_part(geometry, complexity)
        or has_deformation_risk_geometry(geometry)
    )

    if part_quantity is not None and part_quantity > 1 and (high_complexity or multi_setup or precision_hole or surface):
        add_operation(
            operations,
            operation_code="first_article_inspection",
            rule_code="FIRST_ARTICLE_INSPECTION_FROM_BATCH_RISK",
            message="批量加工且存在工艺风险，需要先做首件检验再继续生产。",
            source=system_source("FIRST_ARTICLE_INSPECTION_FROM_BATCH_RISK"),
            confidence=0.68,
            requires_review=True,
            review_reason="请确认首件检验范围和验收标准。",
        )

    if high_complexity or multi_setup or precision_hole or (requirements.get("heat_treatment") or {}).get("required"):
        add_operation(
            operations,
            operation_code="in_process_inspection",
            rule_code="IN_PROCESS_INSPECTION_FROM_ROUTE_RISK",
            message="路线存在高复杂度、多次装夹、精孔或热处理风险，增加过程检验。",
            source=system_source("IN_PROCESS_INSPECTION_FROM_ROUTE_RISK"),
            confidence=0.68,
            requires_review=True,
            review_reason="请确认粗加工、换装夹、热处理和精加工之间的关键尺寸检验时机。",
        )

    if thread:
        add_operation(
            operations,
            operation_code="thread_inspection",
            rule_code="THREAD_INSPECTION_FROM_THREAD_PROCESS",
            message="路线包含螺纹加工，需要安排螺纹通止规检验。",
            source=system_source("THREAD_INSPECTION_FROM_THREAD_PROCESS"),
            confidence=0.7,
        )

    if precision_hole:
        add_operation(
            operations,
            operation_code="precision_hole_inspection",
            rule_code="PRECISION_HOLE_INSPECTION_FROM_PRECISION_PROCESS",
            message="路线包含精孔加工，需要安排孔径和配合专项检验。",
            source=system_source("PRECISION_HOLE_INSPECTION_FROM_PRECISION_PROCESS"),
            confidence=0.72,
            requires_review=True,
            review_reason="请确认精孔公差、检具和检验频次。",
        )

    if has_pcd_hole_pattern(features):
        add_operation(
            operations,
            operation_code="pcd_hole_pattern",
            rule_code="PCD_HOLE_PATTERN_FROM_FEATURES",
            message="识别到 PCD/圆周孔组证据，触发 PCD 孔组加工。",
            source=system_source("PCD_HOLE_PATTERN_FROM_FEATURES"),
            confidence=0.64,
            requires_review=True,
            review_reason="请确认 PCD 孔数、节圆和角度位置。",
        )
        add_operation(
            operations,
            operation_code="pcd_hole_inspection",
            rule_code="PCD_HOLE_INSPECTION_FROM_FEATURES",
            message="PCD 孔组需要检查节圆和位置度。",
            source=system_source("PCD_HOLE_INSPECTION_FROM_FEATURES"),
            confidence=0.66,
            requires_review=True,
            review_reason="请确认 PCD 检验方法和公差要求。",
        )

    if flatness:
        add_operation(
            operations,
            operation_code="flatness_inspection",
            rule_code="FLATNESS_INSPECTION_FROM_REQUIREMENT_OR_GEOMETRY",
            message="识别到平面度、平行度或薄板风险，需要安排平面度检验。",
            source=system_source("FLATNESS_INSPECTION_FROM_REQUIREMENT_OR_GEOMETRY"),
            confidence=0.68,
            requires_review=True,
            review_reason="请确认平面度/平行度公差和检验基准。",
        )

    if surface:
        add_operation(
            operations,
            operation_code="coating_thickness_inspection",
            rule_code="SURFACE_TREATMENT_FINAL_COATING_INSPECTION",
            message="路线包含表面处理，需要确认镀层/膜厚检验。",
            source=system_source("SURFACE_TREATMENT_FINAL_COATING_INSPECTION"),
            confidence=0.64,
            requires_review=True,
            review_reason="请确认镀层/膜厚要求和测量方法。",
        )
        add_operation(
            operations,
            operation_code="surface_inspection",
            rule_code="SURFACE_TREATMENT_FINAL_SURFACE_INSPECTION",
            message="路线包含表面处理，需要最终外观和覆盖状态检验。",
            source=system_source("SURFACE_TREATMENT_FINAL_SURFACE_INSPECTION"),
            confidence=0.72,
        )


def add_post_process_dependent_operations(operations: list[dict[str, Any]]) -> None:
    codes = {str(operation.get("operation_code") or "") for operation in operations}
    thread_codes = {"tapping", "tapping_through", "blind_tapping", "fine_thread_tapping", "side_tapping"}
    precision_hole_codes = {"precision_hole", "reaming", "boring", "post_anodize_reaming"}
    surface_codes = codes & SURFACE_TREATMENT_OPERATION_CODES
    if codes & SURFACE_TREATMENT_OPERATION_CODES and codes & thread_codes:
        add_operation(
            operations,
            operation_code="thread_chasing",
            rule_code="POST_SURFACE_THREAD_CHASING_CANDIDATE",
            message="路线包含表面处理和螺纹孔，表处后回攻/清牙作为候选。",
            source=system_source("POST_SURFACE_THREAD_CHASING_CANDIDATE"),
            confidence=0.62,
            requires_review=True,
            review_reason="请确认螺纹是否需要遮蔽或表处后回攻/清牙。",
        )
        add_operation(
            operations,
            operation_code="thread_inspection",
            rule_code="POST_SURFACE_THREAD_INSPECTION",
            message="路线包含表面处理和螺纹孔，螺纹通止规检验作为终检项。",
            source=system_source("POST_SURFACE_THREAD_INSPECTION"),
            confidence=0.68,
        )
    if codes & SURFACE_TREATMENT_OPERATION_CODES and codes & precision_hole_codes:
        add_operation(
            operations,
            operation_code="post_surface_precision_hole_check",
            rule_code="POST_SURFACE_PRECISION_HOLE_CHECK",
            message="路线包含表面处理和精孔，表处后精孔复检作为候选。",
            source=system_source("POST_SURFACE_PRECISION_HOLE_CHECK"),
            confidence=0.66,
            requires_review=True,
            review_reason="请确认镀层/氧化膜对精孔尺寸的影响。",
        )
    if surface_codes:
        add_operation(
            operations,
            operation_code="coating_thickness_inspection",
            rule_code="SURFACE_TREATMENT_COATING_THICKNESS_INSPECTION",
            message="表面处理厚度影响交付状态时，需要安排膜厚/镀层厚度检验。",
            source=system_source("SURFACE_TREATMENT_COATING_THICKNESS_INSPECTION"),
            confidence=0.64,
            requires_review=True,
            review_reason="请确认镀层/膜厚要求和测量方法。",
        )
        add_operation(
            operations,
            operation_code="surface_inspection",
            rule_code="SURFACE_TREATMENT_SURFACE_INSPECTION",
            message="表面处理路线需要外观和覆盖状态检验。",
            source=system_source("SURFACE_TREATMENT_SURFACE_INSPECTION"),
            confidence=0.7,
        )
    if surface_codes & {"clear_anodizing", "hard_anodizing", "color_anodizing"} and codes & precision_hole_codes:
        add_operation(
            operations,
            operation_code="post_anodize_reaming",
            rule_code="POST_ANODIZE_REAMING_CANDIDATE",
            message="阳极氧化叠加精孔时，氧化后复铰可作为候选工序。",
            source=system_source("POST_ANODIZE_REAMING_CANDIDATE"),
            confidence=0.56,
            requires_review=True,
            review_reason="请确认氧化膜是否影响 H7/配合孔，并判断是否需要氧化后复铰。",
        )
    if "hard_chrome" in surface_codes:
        add_operation(
            operations,
            operation_code="dehydrogenation_bake",
            rule_code="HARD_CHROME_DEHYDROGENATION_CANDIDATE",
            message="镀硬铬路线可能因材料和硬度风险需要除氢处理。",
            source=system_source("HARD_CHROME_DEHYDROGENATION_CANDIDATE"),
            confidence=0.56,
            requires_review=True,
            review_reason="请确认材料硬度以及镀硬铬后是否需要除氢处理。",
        )
        add_operation(
            operations,
            operation_code="post_chrome_inspection",
            rule_code="HARD_CHROME_POST_INSPECTION",
            message="镀硬铬后需要检查外观、镀层厚度和关键尺寸。",
            source=system_source("HARD_CHROME_POST_INSPECTION"),
            confidence=0.68,
        )
        if codes & precision_hole_codes:
            add_operation(
                operations,
                operation_code="post_chrome_polishing",
                rule_code="HARD_CHROME_POST_POLISHING_CANDIDATE",
                message="镀硬铬叠加精密/配合特征时，可能需要镀后抛光或修正。",
                source=system_source("HARD_CHROME_POST_POLISHING_CANDIDATE"),
                confidence=0.56,
                requires_review=True,
                review_reason="请确认配合特征是否需要镀后抛光/修磨。",
            )


def add_inherited_review_operation(
    operations: list[dict[str, Any]],
    inherited_risks: list[dict[str, Any]],
) -> None:
    if not any(risk.get("requires_review") for risk in inherited_risks):
        return
    add_operation(
        operations,
        operation_code="manual_review",
        rule_code="INHERITED_REVIEW_RISK",
        message="解析或特征融合阶段已产生待复核风险。",
        source=system_source("INHERITED_REVIEW_RISK"),
        confidence=0.9,
        requires_review=True,
        review_reason="Inherited parse/fusion risks require review before formal quoting.",
    )


def resolve_process_conflicts(
    operations: list[dict[str, Any]],
    part_feature: dict[str, Any],
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    geometry = part_feature.get("geometry") or {}
    features = part_feature.get("features") or {}
    complexity = features.get("complexity") or {}
    requirements = part_feature.get("manufacturing_requirements") or {}
    part_type = geometry.get("part_type")
    complexity_score = numeric_value(complexity.get("complexity_score"))
    slot_count = int_value(complexity.get("slot_count")) or 0
    small_radius_count = int_value(complexity.get("small_radius_count")) or 0
    wire_profile_geometry = has_wire_profile_geometry(geometry, complexity)
    cnc_operations = operations_by_quote_code(operations, "cnc_milling")
    cnc = cnc_operations[0] if cnc_operations else None
    wire = operation_by_code(operations, "wire_cut_profile")

    if cnc and wire:
        prefer_wire = (
            part_type in {"thin_plate", "small_irregular"}
            or is_thin_part(geometry, complexity)
            or slot_count > 0
            or (small_radius_count >= 3 and wire_profile_geometry)
            or (complexity_score is not None and complexity_score >= 60 and wire_profile_geometry)
            or contains_any(technical_text(requirements), WIRE_CUT_KEYWORDS)
        )
        if prefer_wire:
            for cnc_operation in cnc_operations:
                mark_requires_review(
                    cnc_operation,
                    "CNC 与线切割同时命中，当前规则按薄片/异形/槽/小R/复杂度优先线切割，CNC 需人工确认。",
                )
        else:
            mark_requires_review(
                wire,
                "CNC 与线切割同时命中，当前规则按板件/块件优先 CNC，线切割候选需人工确认。",
            )
        risks.append(
            risk_item(
                "CNC_WIRE_CUT_CONFLICT",
                "warning",
                "CNC 与线切割均命中，已按零件类型、厚度和复杂度保留主工序并标记候选复核。",
                "process_recognition",
                True,
                [part_type_source(geometry)],
            )
        )

    precision_hole_operations = operations_by_quote_code(operations, "precision_hole")
    surface_operations = [
        operation
        for operation in operations
        if operation.get("operation_code") in SURFACE_TREATMENT_OPERATION_CODES
    ]
    if surface_operations and precision_hole_operations:
        surface_names = "、".join(
            str(operation.get("operation_name") or operation.get("operation_code"))
            for operation in surface_operations[:3]
        )
        risks.append(
            risk_item(
                "SURFACE_TREATMENT_PRECISION_HOLE_RISK",
                "warning",
                f"{surface_names}可能影响精孔孔径，需确认表处前尺寸补偿、表处后孔径复检或修孔方案。",
                "process_recognition",
                True,
                [system_source("SURFACE_TREATMENT_PRECISION_HOLE_RISK")],
            )
        )
        for precision_hole_operation in precision_hole_operations:
            mark_requires_review(
                precision_hole_operation,
                "Surface treatment may require pre-treatment compensation or post-treatment hole inspection/rework.",
            )

    heat = operation_by_code(operations, "heat_treatment")
    if heat and (is_thin_part(geometry, complexity) or geometry.get("part_type") == "thin_plate"):
        add_operation(
            operations,
            operation_code="straightening",
            rule_code="HEAT_TREATMENT_THIN_PART_STRAIGHTENING",
            message="热处理叠加薄片/薄壁特征，触发热后校平/校直候选。",
            source=part_type_source(geometry),
            confidence=0.68,
            requires_review=True,
            review_reason="Heat-treated thin parts may need straightening.",
        )
    if heat and should_add_post_heat_finish_grinding(part_feature):
        add_operation(
            operations,
            operation_code="finish_grinding",
            rule_code="HEAT_TREATMENT_FINISH_GRINDING_PRECISION_EVIDENCE",
            message="热处理叠加精磨、平面度、粗糙度、厚度或关键基准面精度证据，触发热后精磨候选。",
            source=system_source("HEAT_TREATMENT_FINISH_GRINDING_PRECISION_EVIDENCE"),
            confidence=0.66,
            requires_review=True,
            review_reason="Heat-treated precision surfaces may need finish grinding.",
        )

    return risks


def finalize_route(
    *,
    task_id: str,
    route_id: str,
    operations: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    stage_route: list[dict[str, Any]] | None = None,
    allow_unmapped_without_review: bool = False,
    preserve_input_order: bool = False,
) -> dict[str, Any]:
    route_risks = list(risks)
    route_risks.extend(meta_operation_review_risks(operations))
    visible_operations = [
        operation
        for operation in operations
        if str(operation.get("operation_code") or "") not in ROUTE_META_OPERATION_CODES
    ]
    ordered = list(visible_operations) if preserve_input_order else sorted(
        visible_operations,
        key=operation_sequence_key,
    )
    operation_code_counts: dict[str, int] = {}
    for index, operation in enumerate(ordered, start=1):
        operation["sequence"] = index
        operation_code = str(operation["operation_code"]).lower()
        operation_code_counts[operation_code] = operation_code_counts.get(operation_code, 0) + 1
        duplicate_suffix = (
            f"_{operation_code_counts[operation_code]:02d}"
            if operation_code_counts[operation_code] > 1
            else ""
        )
        operation["operation_id"] = f"op_{index:03d}_{operation_code}{duplicate_suffix}"

    normalized_stage_route, stage_risks = synchronize_stage_route_with_operations(
        stage_route or [],
        ordered,
    )
    route_risks.extend(stage_risks)

    unmapped_operations = [
        operation
        for operation in ordered
        if operation.get("operation_code") == UNMAPPED_OPERATION_CODE
    ]
    if unmapped_operations and not allow_unmapped_without_review:
        names = "、".join(
            str(operation.get("operation_name") or PROCESS_NAMES[UNMAPPED_OPERATION_CODE])
            for operation in unmapped_operations[:5]
        )
        route_risks.append(
            risk_item(
                "UNMAPPED_OPERATION_REQUIRES_REVIEW",
                "warning",
                f"识别到当前工序字典未登记的工序：{names}。需人工确认是否新增字典、映射到已有工序或删除。",
                "process_recognition",
                True,
                [system_source("UNMAPPED_OPERATION_REQUIRES_REVIEW")],
            )
        )
    if any(operation.get("requires_review") for operation in ordered):
        route_risks.append(
            risk_item(
                "PROCESS_ROUTE_REQUIRES_REVIEW",
                "warning",
                process_route_review_message(ordered),
                "process_recognition",
                True,
                [system_source("PROCESS_ROUTE_REQUIRES_REVIEW")],
            )
        )
    route_risks = dedupe_risks(route_risks)

    return {
        "schema_version": "1.0",
        "task_id": task_id,
        "route_id": route_id,
        "stage_route": normalized_stage_route,
        "operations": ordered,
        "requires_review": any(
            bool(risk.get("requires_review"))
            for risk in route_risks
            if isinstance(risk, dict)
        ),
        "risks": route_risks,
    }


def meta_operation_review_risks(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    route_risks: list[dict[str, Any]] = []
    for operation in operations:
        operation_code = str(operation.get("operation_code") or "")
        if operation_code not in ROUTE_META_OPERATION_CODES:
            continue
        if not operation.get("requires_review"):
            continue

        reasons = [
            reason
            for reason in operation.get("trigger_reasons") or []
            if isinstance(reason, dict)
        ]
        first_reason = reasons[0] if reasons else {}
        rule_code = str(first_reason.get("rule_code") or operation_code.upper())
        evidence = [
            reason.get("source")
            for reason in reasons
            if isinstance(reason.get("source"), dict)
        ]
        message = str(
            operation.get("explanation")
            or operation.get("review_reason")
            or f"{operation.get('operation_name') or operation_code}需要人工确认。"
        )
        route_risks.append(
            risk_item(
                rule_code,
                "warning",
                message,
                "process_recognition",
                True,
                evidence or [system_source(rule_code)],
            )
        )
    return route_risks


def synchronize_stage_route_with_operations(
    stage_route: list[dict[str, Any]],
    operations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized_stages = [dict(stage) for stage in stage_route if isinstance(stage, dict)]
    risks: list[dict[str, Any]] = []
    stage_codes = {str(stage.get("stage_code") or "") for stage in normalized_stages}
    actual_by_stage: dict[str, list[str]] = {stage_code: [] for stage_code in stage_codes}
    names_by_stage = {
        definition.stage_code: definition.stage_name
        for definition in STAGE_DEFINITIONS
    }

    for operation in operations:
        operation_code = str(operation.get("operation_code") or "")
        stage_code = operation_stage_code(operation, stage_codes)
        if not stage_code:
            if operation_code == UNMAPPED_OPERATION_CODE:
                operation["stage_code"] = None
                operation["stage_name"] = None
                continue
            risks.append(
                risk_item(
                    "OPERATION_WITHOUT_STAGE",
                    "warning",
                    f"详细工序 {operation.get('operation_name') or operation_code} 未能映射到任何工艺阶段，需补充阶段字典或调整工序归属。",
                    "process_recognition",
                    True,
                    [system_source("OPERATION_WITHOUT_STAGE")],
                )
            )
            operation["stage_code"] = None
            operation["stage_name"] = None
            continue

        operation["stage_code"] = stage_code
        operation["stage_name"] = names_by_stage.get(stage_code, stage_code)
        actual_by_stage.setdefault(stage_code, []).append(operation_code)

    for stage in normalized_stages:
        stage_code = str(stage.get("stage_code") or "")
        actual_codes = dedupe_preserve_order(actual_by_stage.get(stage_code, []))
        stage["actual_operation_codes"] = actual_codes
        if actual_codes:
            continue

        required_codes = STAGE_REQUIRED_OPERATION_CODES.get(stage_code, ())
        if not required_codes:
            continue
        stage["requires_review"] = True
        stage["review_reason"] = stage.get("review_reason") or "该阶段已被规划，但未展开出对应详细工序。"
        risks.append(
            risk_item(
                "STAGE_WITHOUT_OPERATION",
                "warning",
                f"工艺阶段“{stage.get('stage_name') or stage_code}”已规划，但详细工序未展开出对应工序，需确认阶段是否应保留或补充工序规则。",
                "process_recognition",
                True,
                [system_source("STAGE_WITHOUT_OPERATION")],
            )
        )

    return normalized_stages, risks


def operation_stage_code(operation: dict[str, Any], active_stage_codes: set[str]) -> str | None:
    operation_code = str(operation.get("operation_code") or "")
    if "post_heat_correction" in active_stage_codes and operation_has_after_heat_reason(operation):
        return "post_heat_correction"

    explicit_stage_code = OPERATION_STAGE_MAP.get(operation_code)
    if explicit_stage_code:
        if not active_stage_codes or explicit_stage_code in active_stage_codes:
            return explicit_stage_code

    quote_stage_code = OPERATION_STAGE_MAP.get(str(quote_process_code_for(operation_code) or ""))
    if quote_stage_code:
        if not active_stage_codes or quote_stage_code in active_stage_codes:
            return quote_stage_code

    return explicit_stage_code or quote_stage_code


def operation_has_after_heat_reason(operation: dict[str, Any]) -> bool:
    for reason in operation.get("trigger_reasons") or []:
        if not isinstance(reason, dict):
            continue
        rule_code = str(reason.get("rule_code") or "")
        if rule_code.startswith("AFTER_HEAT_") or rule_code.startswith("STAGE_POST_HEAT_CORRECTION"):
            return True
    return False


def dedupe_preserve_order(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def add_ai_generated_stages(
    stages: list[dict[str, Any]],
    ai_output: dict[str, Any],
    *,
    risks: list[dict[str, Any]] | None = None,
    auto_accept: bool = False,
) -> int:
    content = ai_output.get("content") if isinstance(ai_output, dict) else {}
    applied_count = 0
    for item in (content or {}).get("stages") or []:
        if not isinstance(item, dict):
            continue
        confidence = clamp_confidence(float_value(item.get("confidence"), 0.0))
        if confidence < 0.35:
            continue
        stage_code = ai_generated_stage_code(item)
        if stage_code not in STAGE_DICTIONARY:
            if risks is not None:
                raw_name = (
                    string_value(item.get("stage_name_raw"))
                    or string_value(item.get("stage_code"))
                    or "未知阶段"
                )
                risks.append(
                    risk_item(
                        "AI_UNMAPPED_STAGE",
                        "warning",
                        f"AI 输出了阶段字典外的工艺阶段：{raw_name}，已忽略并等待人工确认。",
                        "process_recognition",
                        True,
                        [ai_source(ai_output, "AI_UNMAPPED_STAGE")],
                    )
                )
            continue

        add_stage(
            stages,
            stage_code,
            rule_code=f"AI_STAGE_{stage_code.upper()}",
            message=(
                string_value(item.get("reason"))
                or string_value(item.get("evidence_summary"))
                or f"AI 规划出 {STAGE_DICTIONARY[stage_code].stage_name} 阶段。"
            ),
            source=ai_source(ai_output, f"AI_STAGE_{stage_code.upper()}"),
            confidence=confidence,
            requires_review=False if auto_accept else bool(item.get("requires_review")),
            review_reason=(
                None
                if auto_accept or not item.get("requires_review")
                else string_value(item.get("evidence_summary")) or "AI stage planning needs review."
            ),
        )
        applied_count += 1
    if applied_count:
        stages[:] = finalize_stage_route(stages)
    return applied_count


def ai_generated_stage_code(item: dict[str, Any]) -> str | None:
    for key in ("stage_code", "stage_name_raw", "stage_name"):
        value = string_value(item.get(key))
        if not value:
            continue
        normalized = normalize_stage_code(value)
        if normalized:
            return normalized
    return string_value(item.get("stage_code"))


def normalize_stage_code(value: Any) -> str | None:
    text = string_value(value)
    if not text:
        return None
    code = "_".join(text.strip().lower().replace("/", " ").replace("-", " ").split())
    if code in STAGE_DICTIONARY:
        return code

    normalized_text = normalize_text(text)
    aliases = {
        "material_preparation": ("来料", "备料", "材料准备", "material", "materialprepare"),
        "blanking": ("下料", "开料", "锯切", "blanking", "cutting"),
        "fixture_and_datum": ("装夹", "找正", "基准", "fixture", "datum", "setup"),
        "rough_machining": ("粗加工", "粗铣", "主体粗加工", "rough"),
        "hole_machining": ("孔预加工", "孔加工", "钻孔", "hole", "drill"),
        "thread_and_counterbore": ("攻牙", "攻丝", "沉孔", "螺纹", "thread", "tapping", "counterbore"),
        "profile_and_cavity": ("外形", "轮廓", "槽", "台阶", "型腔", "profile", "slot", "cavity"),
        "heat_and_stabilize": ("热处理", "去应力", "时效", "heat", "stress"),
        "post_heat_correction": ("热后", "校平", "校直", "精磨", "postheat", "straightening"),
        "finish_and_precision": ("精加工", "精铣", "精孔", "精修", "finish", "precision"),
        "deburr_cleaning": ("去毛刺", "倒角", "锐角倒钝", "清洗", "deburr", "cleaning"),
        "pre_surface": ("表处前", "镀前", "遮蔽", "presurface", "masking"),
        "surface_treatment": ("表面处理", "表处", "电镀", "阳极", "喷塑", "喷砂", "surface"),
        "post_surface": ("表处后", "镀后", "回攻", "膜后", "postsurface"),
        "inspection": ("检验", "检测", "终检", "inspection", "qc"),
        "packaging": ("包装", "防护包装", "package", "packaging"),
    }
    compact_text = normalized_text.replace(" ", "")
    for stage_code, keywords in aliases.items():
        for keyword in keywords:
            normalized_keyword = normalize_text(keyword).replace(" ", "")
            if normalized_keyword and normalized_keyword in compact_text:
                return stage_code
    return None


def add_ai_generated_operations(
    operations: list[dict[str, Any]],
    ai_output: dict[str, Any],
    *,
    auto_accept: bool = False,
) -> int:
    content = ai_output.get("content") if isinstance(ai_output, dict) else {}
    applied_count = 0
    for item in (content or {}).get("operations") or []:
        if not isinstance(item, dict):
            continue
        confidence = clamp_confidence(float_value(item.get("confidence"), 0.0))
        if confidence < 0.35:
            continue
        operation_code = ai_generated_operation_code(item)
        if operation_code not in PROCESS_NAMES or operation_code == UNMAPPED_OPERATION_CODE:
            add_unmapped_ai_operation(
                operations,
                suggestion=item,
                ai_output=ai_output,
                confidence=confidence,
                requires_review=not auto_accept,
            )
            applied_count += 1
            continue

        message = (
            string_value(item.get("reason"))
            or string_value(item.get("evidence_summary"))
            or f"AI 自主识别出 {PROCESS_NAMES[operation_code]} 工序。"
        )
        review_reason = string_value(item.get("evidence_summary"))
        add_operation(
            operations,
            operation_code=operation_code,
            rule_code=f"AI_ROUTE_{operation_code.upper()}",
            message=message,
            source=ai_source(ai_output, f"AI_ROUTE_{operation_code.upper()}"),
            confidence=confidence,
            requires_review=False if auto_accept else bool(item.get("requires_review")),
            review_reason=(
                None
                if auto_accept
                else review_reason if item.get("requires_review") else None
            ),
        )
        applied_count += 1
    return applied_count


def ai_generated_operation_code(item: dict[str, Any]) -> str | None:
    for key in ("operation_code", "operation_name_raw", "operation_name"):
        operation_code = normalize_process_code(item.get(key))
        if operation_code:
            return operation_code
    return string_value(item.get("operation_code"))


def apply_ai_process_route_suggestion(
    process_route: dict[str, Any],
    ai_output: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(ai_output, dict):
        return process_route
    content = ai_output.get("content")
    if not isinstance(content, dict) or content.get("available") is False:
        return process_route

    operations = list(process_route.get("operations") or [])
    risks = list(process_route.get("risks") or [])
    applied_count = 0
    rejected_count = 0
    for suggestion in content.get("suggestions") or []:
        if not isinstance(suggestion, dict):
            continue
        result = apply_single_ai_process_suggestion(operations, suggestion, ai_output)
        if result in {"applied", "applied_unmapped"}:
            applied_count += 1
        elif result == "rejected":
            rejected_count += 1
            risks.append(ai_process_suggestion_rejected_risk(suggestion, ai_output))

    if content.get("review_required") and applied_count == 0:
        add_operation(
            operations,
            operation_code="manual_review",
            rule_code="AI_PROCESS_ROUTE_REVIEW_REQUIRED",
            message=string_value(content.get("summary")) or "AI 建议对规则工艺路线进行人工复核。",
            source=ai_source(ai_output, "AI_PROCESS_ROUTE_REVIEW_REQUIRED"),
            confidence=ai_output_confidence(ai_output),
            requires_review=True,
            review_reason="AI suggested process route review.",
        )

    if applied_count or rejected_count:
        risks.append(
            risk_item(
                "AI_PROCESS_ROUTE_SUGGESTION_APPLIED",
                "warning" if applied_count else "info",
                f"AI 工序建议已校验：采纳 {applied_count} 项，拒绝 {rejected_count} 项。",
                "process_recognition",
                bool(applied_count or rejected_count),
                [ai_source(ai_output, "AI_PROCESS_ROUTE_SUGGESTION")],
            )
        )

    return finalize_route(
        task_id=process_route["task_id"],
        route_id=process_route["route_id"],
        operations=operations,
        risks=risks,
        stage_route=list(process_route.get("stage_route") or []),
    )


def apply_single_ai_process_suggestion(
    operations: list[dict[str, Any]],
    suggestion: dict[str, Any],
    ai_output: dict[str, Any],
) -> str:
    action = string_value(suggestion.get("action"))
    operation_code = normalize_process_code(suggestion.get("operation_code")) or string_value(suggestion.get("operation_code"))
    if action not in {"add", "review", "keep"}:
        return "rejected"
    if action == "keep":
        return "ignored"
    confidence = clamp_confidence(float_value(suggestion.get("confidence"), 0.0))
    if confidence < 0.55:
        return "rejected"
    if operation_code not in PROCESS_NAMES or operation_code == UNMAPPED_OPERATION_CODE:
        add_unmapped_ai_operation(
            operations,
            suggestion=suggestion,
            ai_output=ai_output,
            confidence=confidence,
        )
        return "applied_unmapped"
    existing = operation_by_code(operations, operation_code)
    message = string_value(suggestion.get("reason")) or "AI 建议复核该工序。"
    review_reason = string_value(suggestion.get("evidence_summary")) or "AI process suggestion."
    if action == "review":
        if not existing:
            add_operation(
                operations,
                operation_code="manual_review",
                rule_code=f"AI_REVIEW_{operation_code.upper()}",
                message=f"AI 建议复核 {PROCESS_NAMES[operation_code]}：{message}",
                source=ai_source(ai_output, f"AI_REVIEW_{operation_code.upper()}"),
                confidence=confidence,
                requires_review=True,
                review_reason=review_reason,
            )
            return "applied"
        add_operation(
            operations,
            operation_code=operation_code,
            rule_code=f"AI_REVIEW_{operation_code.upper()}",
            message=message,
            source=ai_source(ai_output, f"AI_REVIEW_{operation_code.upper()}"),
            confidence=confidence,
            requires_review=True,
            review_reason=review_reason,
        )
        return "applied"

    if existing:
        add_operation(
            operations,
            operation_code=operation_code,
            rule_code=f"AI_CONFIRM_{operation_code.upper()}",
            message=message,
            source=ai_source(ai_output, f"AI_CONFIRM_{operation_code.upper()}"),
            confidence=confidence,
            requires_review=False,
            review_reason=review_reason,
        )
        return "applied"
    add_operation(
        operations,
        operation_code=operation_code,
        rule_code=f"AI_ADD_{operation_code.upper()}",
        message=message,
        source=ai_source(ai_output, f"AI_ADD_{operation_code.upper()}"),
        confidence=confidence,
        requires_review=False,
        review_reason=None,
    )
    return "applied"


def ai_process_suggestion_rejected_risk(
    suggestion: dict[str, Any],
    ai_output: dict[str, Any],
) -> dict[str, Any]:
    operation_code = string_value(suggestion.get("operation_code")) or "-"
    return risk_item(
        "AI_PROCESS_ROUTE_SUGGESTION_REJECTED",
        "info",
        f"AI 工序建议未采纳：{operation_code}。原因：编码非法、动作非法或置信度过低。",
        "process_recognition",
        False,
        [ai_source(ai_output, "AI_PROCESS_ROUTE_SUGGESTION_REJECTED")],
    )


def ai_process_route_generation_unavailable_risk(ai_output: dict[str, Any] | None) -> dict[str, Any]:
    content = ai_output.get("content") if isinstance(ai_output, dict) else {}
    message = (
        string_value(content.get("error_message")) if isinstance(content, dict) else None
    )
    return risk_item(
        "AI_PROCESS_ROUTE_GENERATION_UNAVAILABLE",
        "warning",
        f"AI 自主工序识别不可用，无法在暂停规则识别模式下生成完整工艺路线。{message or ''}".strip(),
        "process_recognition",
        True,
        [ai_source(ai_output or {}, "AI_PROCESS_ROUTE_GENERATION_UNAVAILABLE")],
    )


def append_inherited_review_risks(
    risks: list[dict[str, Any]],
    inherited_risks: list[dict[str, Any]],
) -> None:
    if not any(risk.get("requires_review") for risk in inherited_risks or []):
        return
    risks.append(
        risk_item(
            "INHERITED_REVIEW_RISK",
            "warning",
            "解析或特征融合阶段存在待复核风险，正式报价前需要人工确认。",
            "process_recognition",
            True,
            [system_source("INHERITED_REVIEW_RISK")],
        )
    )


def add_unmapped_ai_operation(
    operations: list[dict[str, Any]],
    *,
    suggestion: dict[str, Any],
    ai_output: dict[str, Any],
    confidence: float,
    requires_review: bool = True,
) -> None:
    raw_name = unmapped_operation_name(suggestion)
    message = string_value(suggestion.get("reason")) or f"AI 识别到字典外工序：{raw_name}。"
    evidence = string_value(suggestion.get("evidence_summary"))
    operation_name = f"未登记工序：{raw_name}"
    review_reason = (
        f"AI 识别到当前工序字典未登记的工序“{raw_name}”，需人工确认是否新增字典、映射到已有工序或删除。"
    )
    if evidence:
        review_reason = f"{review_reason} 依据：{evidence}"

    existing = unmapped_operation_by_name(operations, operation_name)
    reason = {
        "rule_code": "AI_UNMAPPED_OPERATION",
        "message": message,
        "source": ai_source(ai_output, "AI_UNMAPPED_OPERATION"),
    }
    if existing:
        existing["trigger_reasons"].append(reason)
        existing["confidence"] = max(existing["confidence"], confidence)
        existing["requires_review"] = bool(existing["requires_review"] or requires_review)
        if requires_review:
            existing["review_reason"] = existing.get("review_reason") or review_reason
        return

    operations.append(
        {
            "operation_id": "",
            "operation_code": UNMAPPED_OPERATION_CODE,
            "operation_name": operation_name,
            "sequence": 1,
            "trigger_reasons": [reason],
            "confidence": confidence,
            "requires_review": requires_review,
            "review_reason": review_reason if requires_review else None,
            "explanation": message,
        }
    )


def unmapped_operation_name(suggestion: dict[str, Any]) -> str:
    for key in ("operation_name_raw", "operation_name", "operation_code"):
        value = string_value(suggestion.get(key))
        if value:
            return value
    return "未知工序"


def process_route_review_message(operations: list[dict[str, Any]]) -> str:
    review_codes = {
        str(operation.get("operation_code"))
        for operation in operations
        if operation.get("requires_review")
    }
    route_step_codes = review_codes - {"manual_review"}
    if route_step_codes:
        return "工艺路线包含需复核工序，需人工确认。"
    if "manual_review" in review_codes:
        return "解析或特征融合阶段存在待复核风险，正式报价前需人工确认。"
    return "工艺路线存在待复核项，需人工确认。"


def add_operation(
    operations: list[dict[str, Any]],
    *,
    operation_code: str,
    rule_code: str,
    message: str,
    source: dict[str, Any] | None,
    confidence: float,
    requires_review: bool = False,
    review_reason: str | None = None,
) -> None:
    existing = operation_by_code(operations, operation_code)
    reason = {
        "rule_code": rule_code,
        "message": message,
        "source": source or system_source(rule_code),
    }
    if existing:
        existing["trigger_reasons"].append(reason)
        existing["confidence"] = max(existing["confidence"], clamp_confidence(confidence))
        existing["requires_review"] = bool(existing["requires_review"] or requires_review)
        existing["review_reason"] = existing.get("review_reason") or review_reason
        existing["explanation"] = existing.get("explanation") or message
        return

    operations.append(
        {
            "operation_id": "",
            "operation_code": operation_code,
            "operation_name": PROCESS_NAMES[operation_code],
            "sequence": 1,
            "trigger_reasons": [reason],
            "confidence": clamp_confidence(confidence),
            "requires_review": requires_review,
            "review_reason": review_reason,
            "explanation": message,
        }
    )


def technical_requirement_items(requirements: dict[str, Any]) -> list[dict[str, Any]]:
    details = requirements.get("technical_requirement_details") or []
    if details:
        return [
            {
                "raw_text": str(item.get("raw_text") or "").strip(),
                "requirement_type": item.get("requirement_type") or classify_technical_text(item.get("raw_text")),
                "standard_code": item.get("standard_code"),
                "confidence": item.get("confidence", 0.72),
                "source": item.get("source") or source_ref(
                    "pdf",
                    location="technical_requirements",
                    raw_text=item.get("raw_text"),
                ),
            }
            for item in details
            if str(item.get("raw_text") or "").strip()
        ]

    result = []
    for raw_text in requirements.get("technical_requirements") or []:
        text = str(raw_text or "").strip()
        if not text:
            continue
        result.append(
            {
                "raw_text": text,
                "requirement_type": classify_technical_text(text),
                "standard_code": "",
                "confidence": 0.68,
                "source": source_ref("pdf", location="technical_requirements", raw_text=text),
            }
        )
    return result


def material_text(material: dict[str, Any]) -> str:
    return normalize_text(
        " ".join(
            str(value or "")
            for value in (
                material.get("raw_text"),
                material.get("standard_code"),
                material.get("standard_name"),
            )
        )
    )


def should_prefer_wire_cut_for_tool_steel(
    geometry: dict[str, Any],
    complexity: dict[str, Any],
) -> bool:
    part_type = geometry.get("part_type")
    return (
        part_type in {"thin_plate", "small_irregular"}
        or is_thin_part(geometry, complexity)
        or (int_value(complexity.get("slot_count")) or 0) > 0
        or (
            (int_value(complexity.get("small_radius_count")) or 0) >= 3
            and has_wire_profile_geometry(geometry, complexity)
        )
    )


def has_wire_profile_geometry(
    geometry: dict[str, Any],
    complexity: dict[str, Any],
) -> bool:
    profile = geometry.get("profile_summary") or {}
    return (
        (int_value(complexity.get("slot_count")) or 0) > 0
        or (int_value(profile.get("slot_candidate_count")) or 0) > 0
        or (int_value(profile.get("outer_arc_count")) or 0) > 0
        or (numeric_value(profile.get("outer_arc_length")) or 0) > 0
    )


def has_heat_or_precision_requirement(part_feature: dict[str, Any]) -> bool:
    requirements = part_feature.get("manufacturing_requirements") or {}
    features = part_feature.get("features") or {}
    if (requirements.get("heat_treatment") or {}).get("required"):
        return True
    if features.get("precision_requirements"):
        return True
    return any(
        contains_any(
            normalize_text(item.get("raw_text") if isinstance(item, dict) else item),
            ROUGHNESS_KEYWORDS + FLATNESS_KEYWORDS + HOLE_PRECISION_KEYWORDS + TIGHT_TOLERANCE_KEYWORDS,
        )
        for item in technical_requirement_items(requirements)
    )


def has_heat_treatment_requirement(part_feature: dict[str, Any]) -> bool:
    requirements = part_feature.get("manufacturing_requirements") or {}
    return bool((requirements.get("heat_treatment") or {}).get("required")) or contains_any(
        technical_text(requirements),
        HEAT_TREATMENT_KEYWORDS,
    )


def feature_precision_text(features: dict[str, Any]) -> str:
    texts: list[str] = []
    for item in features.get("precision_requirements") or []:
        if isinstance(item, dict):
            texts.extend(
                str(item.get(key) or "")
                for key in ("raw_text", "standard_type", "tolerance", "feature_role")
            )
        else:
            texts.append(str(item or ""))
    for hole in features.get("holes") or []:
        if not isinstance(hole, dict):
            continue
        texts.extend(
            str(hole.get(key) or "")
            for key in ("raw_text", "standard_type", "tolerance", "fit", "feature_role", "hole_type")
        )
    return normalize_text(" ".join(texts))


def post_heat_decision_text(part_feature: dict[str, Any]) -> str:
    return normalize_text(
        " ".join(
            (
                technical_text(part_feature.get("manufacturing_requirements") or {}),
                feature_precision_text(part_feature.get("features") or {}),
                material_text(part_feature.get("material") or {}),
            )
        )
    )


def should_add_post_heat_straightening(part_feature: dict[str, Any]) -> bool:
    geometry = part_feature.get("geometry") or {}
    complexity = (part_feature.get("features") or {}).get("complexity") or {}
    text = post_heat_decision_text(part_feature)
    return (
        contains_any(text, STRAIGHTENING_KEYWORDS)
        or geometry.get("part_type") == "thin_plate"
        or is_thin_part(geometry, complexity)
        or has_deformation_risk_geometry(geometry)
    )


def should_add_post_heat_finish_grinding(part_feature: dict[str, Any]) -> bool:
    text = post_heat_decision_text(part_feature)
    return contains_any(
        text,
        GRINDING_KEYWORDS + ROUGHNESS_KEYWORDS + FLATNESS_KEYWORDS + THICKNESS_PRECISION_KEYWORDS,
    )


def should_add_post_heat_cylindrical_grinding(part_feature: dict[str, Any]) -> bool:
    geometry = part_feature.get("geometry") or {}
    text = post_heat_decision_text(part_feature)
    if contains_any(text, CYLINDRICAL_GRINDING_KEYWORDS):
        return True
    return geometry.get("part_type") == "shaft" and has_heat_treatment_requirement(part_feature)


def should_plan_post_heat_correction_stage(part_feature: dict[str, Any]) -> bool:
    return (
        should_add_post_heat_straightening(part_feature)
        or should_add_post_heat_finish_grinding(part_feature)
        or should_add_post_heat_cylindrical_grinding(part_feature)
    )


def should_plan_after_heat_treatment_recovery(part_feature: dict[str, Any]) -> bool:
    features = part_feature.get("features") or {}
    requirements = part_feature.get("manufacturing_requirements") or {}
    holes = features.get("holes") or []
    text = post_heat_decision_text(part_feature)
    return (
        should_plan_post_heat_correction_stage(part_feature)
        or any(is_precision_hole(hole) for hole in holes)
        or has_thread_after_heat_recovery(part_feature)
        or contains_any(text, HOLE_PRECISION_KEYWORDS + HEAT_OXIDE_KEYWORDS + HARDNESS_INSPECTION_KEYWORDS)
        or planned_surface_treatment_code(requirements) is not None
        or bool((requirements.get("heat_treatment") or {}).get("required"))
    )


def has_thread_after_heat_recovery(part_feature: dict[str, Any]) -> bool:
    features = part_feature.get("features") or {}
    requirements = part_feature.get("manufacturing_requirements") or {}
    holes = features.get("holes") or []
    return (
        any(is_thread_hole(hole) or is_side_thread_hole(hole) for hole in holes)
        or any(has_thread_callout(item.get("raw_text")) for item in technical_requirement_items(requirements))
    )


def post_heat_precision_hole_recovery_code(holes: list[dict[str, Any]], text: str) -> str:
    for hole in holes:
        if not isinstance(hole, dict) or not is_precision_hole(hole):
            continue
        hole_text = normalize_text(
            " ".join(
                str(hole.get(key) or "")
                for key in ("raw_text", "standard_type", "tolerance", "fit", "hole_type")
            )
        )
        diameter = numeric_value(hole.get("diameter"))
        if "h7" in hole_text and (diameter is None or diameter <= 12):
            return "reaming"
        if "e8" in hole_text or "g6" in hole_text or (diameter is not None and diameter >= 30):
            return "boring"
    if "h7" in text:
        return "reaming"
    if contains_any(text, ("e8", "g6", "镗孔", "boring")):
        return "boring"
    return "precision_hole"


def has_thread_callout(text: Any) -> bool:
    if text in (None, ""):
        return False
    return THREAD_CALLOUT_PATTERN.search(str(text)) is not None


def classify_technical_text(raw_text: Any) -> str:
    text = normalize_text(raw_text)
    if contains_any(text, DEBURR_KEYWORDS):
        return "deburring"
    if contains_any(text, EDGE_BREAK_KEYWORDS):
        return "edge_break"
    if contains_any(text, HEAT_TREATMENT_KEYWORDS):
        return "heat_treatment"
    if contains_any(text, CHEMICAL_NICKEL_KEYWORDS):
        return "surface_treatment"
    if contains_any(text, SCRATCH_PROTECTION_KEYWORDS):
        return "packaging"
    if contains_any(text, INSPECTION_KEYWORDS):
        return "inspection"
    if contains_any(text, ROUGHNESS_KEYWORDS + FLATNESS_KEYWORDS + HOLE_PRECISION_KEYWORDS + TIGHT_TOLERANCE_KEYWORDS):
        return "precision"
    return "general"


def operation_by_code(
    operations: list[dict[str, Any]],
    operation_code: str,
) -> dict[str, Any] | None:
    return next(
        (item for item in operations if item.get("operation_code") == operation_code),
        None,
    )


def operations_by_quote_code(
    operations: list[dict[str, Any]],
    quote_process_code: str,
) -> list[dict[str, Any]]:
    return [
        item
        for item in operations
        if quote_process_code_for(item.get("operation_code")) == quote_process_code
    ]


def unmapped_operation_by_name(
    operations: list[dict[str, Any]],
    operation_name: str,
) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in operations
            if item.get("operation_code") == UNMAPPED_OPERATION_CODE
            and item.get("operation_name") == operation_name
        ),
        None,
    )


def operation_sequence_key(operation: dict[str, Any]) -> tuple[int, str]:
    operation_code = str(operation.get("operation_code") or "")
    try:
        sequence = PROCESS_SEQUENCE.index(operation_code)
    except ValueError:
        sequence = len(PROCESS_SEQUENCE)
    return (sequence, str(operation.get("operation_name") or operation_code))


def mark_requires_review(operation: dict[str, Any] | None, reason: str) -> None:
    if not operation:
        return
    operation["requires_review"] = True
    operation["review_reason"] = operation.get("review_reason") or reason


def precision_hole_prefers_reaming(hole: dict[str, Any]) -> bool:
    text = normalize_text(
        " ".join(
            str(value or "")
            for value in (
                hole.get("raw_text"),
                hole.get("standard_type"),
                hole.get("tolerance"),
                hole.get("fit"),
            )
        )
    )
    diameter = numeric_value(hole.get("diameter"))
    return "h7" in text or (diameter is not None and diameter <= 12)


def has_complete_bounding_box(bounding_box: dict[str, Any]) -> bool:
    return all(numeric_value(bounding_box.get(key)) is not None for key in ("length", "width", "height"))


def bounding_box_dimensions(geometry: dict[str, Any]) -> list[float]:
    bbox = geometry.get("bounding_box") or {}
    dimensions = [
        numeric_value(bbox.get(key))
        for key in ("length", "width", "height")
    ]
    return [
        value
        for value in dimensions
        if value is not None and value > 0
    ]


def has_deformation_risk_geometry(geometry: dict[str, Any]) -> bool:
    dimensions = bounding_box_dimensions(geometry)
    if len(dimensions) != 3:
        return False
    min_dim = min(dimensions)
    max_dim = max(dimensions)
    middle_dim = sorted(dimensions)[1]
    return (
        (min_dim <= 5 and max_dim / min_dim >= 15)
        or (min_dim <= 8 and max_dim >= 300)
        or (middle_dim <= 20 and max_dim / middle_dim >= 12)
    )


def is_thin_part(geometry: dict[str, Any], complexity: dict[str, Any]) -> bool:
    if geometry.get("part_type") == "thin_plate":
        return True
    if complexity.get("thin_wall_candidate"):
        return True
    dimensions = bounding_box_dimensions(geometry)
    if len(dimensions) != 3:
        return False
    min_dim = min(dimensions)
    max_dim = max(dimensions)
    return min_dim <= 3 and max_dim / min_dim >= 20


def is_side_hole(hole: dict[str, Any]) -> bool:
    text = normalize_text(
        " ".join(
            str(hole.get(key) or "")
            for key in (
                "side",
                "face",
                "orientation",
                "direction",
                "axis",
                "raw_text",
                "position",
                "feature_role",
            )
        )
    )
    return bool(hole.get("side_hole") or contains_any(text, ("side", "lateral", "endface", "端面", "侧面", "侧孔", "侧向")))


def is_reverse_hole(hole: dict[str, Any]) -> bool:
    text = normalize_text(
        " ".join(
            str(hole.get(key) or "")
            for key in ("side", "face", "orientation", "direction", "raw_text", "position", "feature_role")
        )
    )
    return bool(hole.get("reverse_side") or hole.get("back_side") or contains_any(text, ("reverse", "backside", "back", "背面", "反面")))


def has_pcd_hole_pattern(features: dict[str, Any]) -> bool:
    summary = features.get("hole_summary") or {}
    by_type = summary.get("by_type") or {}
    if any(str(key).lower() in {"pcd", "pcd_hole", "pcd_hole_pattern"} and int_value(value) for key, value in by_type.items()):
        return True
    for hole in features.get("holes") or []:
        text = normalize_text(
            " ".join(
                str(hole.get(key) or "")
                for key in ("hole_type", "pattern", "raw_text", "feature_role")
            )
        )
        if contains_any(text, ("pcd", "pitchcircle", "bolt_circle", "分度", "圆周")):
            return True
    return False


def has_flatness_requirement(features: dict[str, Any], requirements: dict[str, Any]) -> bool:
    for item in features.get("precision_requirements") or []:
        text = normalize_text(
            " ".join(
                str(value or "")
                for value in (item.get("raw_text"), item.get("standard_type"))
            )
        )
        if contains_any(text, FLATNESS_KEYWORDS):
            return True
    return contains_any(technical_text(requirements), FLATNESS_KEYWORDS)


def surface_masking_operation_code(surface_code: str) -> str | None:
    if surface_code in {"clear_anodizing", "hard_anodizing", "color_anodizing"}:
        return "anodize_masking"
    if surface_code == "hard_chrome":
        return "hard_chrome_masking"
    if surface_code in {"powder_coating", "white_powder_coating", "powder_coating_texture"}:
        return "powder_masking"
    return None


def part_type_source(geometry: dict[str, Any]) -> dict[str, Any]:
    part_type = geometry.get("part_type")
    candidates = geometry.get("part_type_candidates") or []
    for candidate in candidates:
        if candidate.get("part_type") == part_type and isinstance(candidate.get("source"), dict):
            return candidate["source"]
    return system_source("PART_TYPE")


def part_type_confidence(geometry: dict[str, Any], fallback: float) -> float:
    confidence = numeric_value(geometry.get("part_type_confidence"))
    if confidence is not None:
        return clamp_confidence(confidence)
    candidates = geometry.get("part_type_candidates") or []
    for candidate in candidates:
        if candidate.get("part_type") == geometry.get("part_type"):
            confidence = numeric_value(candidate.get("confidence"))
            if confidence is not None:
                return clamp_confidence(confidence)
    return fallback


def technical_text(requirements: dict[str, Any]) -> str:
    texts: list[str] = []
    for key in ("technical_requirements",):
        for item in requirements.get(key) or []:
            texts.append(str(item or ""))
    for item in requirements.get("technical_requirement_details") or []:
        texts.append(str(item.get("raw_text") or ""))
    for key in ("heat_treatment", "surface_treatment", "deburring", "inspection", "packaging"):
        requirement = requirements.get(key) or {}
        texts.append(str(requirement.get("raw_text") or ""))
        texts.append(str(requirement.get("standard_code") or ""))
    return normalize_text(" ".join(texts))


def technical_source(
    requirements: dict[str, Any],
    keywords: tuple[str, ...],
) -> dict[str, Any]:
    for item in technical_requirement_items(requirements):
        if contains_any(normalize_text(item["raw_text"]), keywords):
            source = item.get("source")
            if isinstance(source, dict):
                return source
    return system_source("TECHNICAL_REQUIREMENT")


def all_part_feature_text(
    part_feature: dict[str, Any],
    inherited_risks: list[dict[str, Any]],
) -> str:
    texts: list[str] = []
    part = part_feature.get("part") or {}
    texts.extend(str(part.get(key) or "") for key in ("part_name", "drawing_no", "revision"))
    texts.append(technical_text(part_feature.get("manufacturing_requirements") or {}))
    for risk in list(part_feature.get("risks") or []) + list(inherited_risks or []):
        texts.append(str(risk.get("code") or ""))
        texts.append(str(risk.get("message") or ""))
    return normalize_text(" ".join(texts))


def first_source(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
        return None
    return value if isinstance(value, dict) else None


def system_source(rule_code: str) -> dict[str, Any]:
    return source_ref("system", rule_code=rule_code)


def ai_source(ai_output: dict[str, Any], rule_code: str) -> dict[str, Any]:
    content = ai_output.get("content") if isinstance(ai_output, dict) else {}
    raw_text = string_value(content.get("summary")) if isinstance(content, dict) else None
    return source_ref(
        "ai",
        location=string_value(ai_output.get("model_name")) if isinstance(ai_output, dict) else None,
        raw_text=raw_text,
        rule_code=rule_code,
    )


def ai_output_confidence(ai_output: dict[str, Any]) -> float:
    return clamp_confidence(float_value((ai_output or {}).get("confidence"), 0.0))


def clamp_confidence(value: Any) -> float:
    number = numeric_value(value)
    if number is None:
        return 0.0
    return min(1.0, max(0.0, number))


def numeric_value(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def float_value(value: Any, default: float) -> float:
    number = numeric_value(value)
    return default if number is None else number


def string_value(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def int_value(value: Any) -> int | None:
    number = numeric_value(value)
    if number is None:
        return None
    return int(number)


def normalize_text(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "")


def contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    normalized = normalize_text(text)
    return any(normalize_text(keyword) in normalized for keyword in keywords)


def is_chemical_plating(requirement: dict[str, Any]) -> bool:
    text = " ".join(
        str(value or "")
        for value in [
            requirement.get("standard_code"),
            requirement.get("raw_text"),
        ]
    )
    return contains_any(text, CHEMICAL_NICKEL_KEYWORDS)


def surface_treatment_operation_code(requirement: dict[str, Any]) -> str | None:
    standard_code = str(requirement.get("standard_code") or "").strip().upper()
    mapping = {
        "CHEMICAL_NICKEL": "chemical_nickel",
        "CHEMICAL_NICKEL_PLATING": "chemical_nickel",
        "CHEMICAL_PLATING": "chemical_nickel",
        "CLEAR_ANODIZING": "clear_anodizing",
        "ANODIZING": "clear_anodizing",
        "HARD_ANODIZING": "hard_anodizing",
        "COLOR_ANODIZING": "color_anodizing",
        "HARD_CHROME": "hard_chrome",
        "HARD_CHROME_PLATING": "hard_chrome",
        "POWDER_COATING": "powder_coating",
        "WHITE_POWDER_COATING": "white_powder_coating",
        "POWDER_COATING_TEXTURE": "powder_coating_texture",
        "SAND_BLASTING": "sand_blasting",
    }
    if standard_code in mapping:
        return mapping[standard_code]

    raw_text = str(requirement.get("raw_text") or "")
    if contains_any(raw_text, CHEMICAL_NICKEL_KEYWORDS):
        return "chemical_nickel"
    if contains_any(raw_text, ("硬质阳极", "硬阳", "hard anod")):
        return "hard_anodizing"
    if contains_any(raw_text, ("着色阳极", "彩色阳极", "黑色阳极", "color anod", "black anod")):
        return "color_anodizing"
    if contains_any(raw_text, ("镀硬铬", "硬铬", "hard chrome", "chrome plating")):
        return "hard_chrome"
    if contains_any(raw_text, ("小桔纹白色喷塑", "小橘纹白色喷塑", "桔纹喷塑", "橘纹喷塑", "texture powder")):
        return "powder_coating_texture"
    if contains_any(raw_text, ("白色喷塑", "亮白喷塑")):
        return "white_powder_coating"
    if contains_any(raw_text, ("喷塑", "粉末喷涂", "powder coating")):
        return "powder_coating"
    if contains_any(raw_text, ("阳极", "anod")):
        return "clear_anodizing"
    if contains_any(raw_text, ("喷砂", "sand blast", "sandblast")):
        return "sand_blasting"
    return None


def add_surface_treatment_operations(
    operations: list[dict[str, Any]],
    *,
    surface_treatment: dict[str, Any],
    surface_code: str,
) -> None:
    source = surface_treatment.get("source")
    confidence = surface_treatment.get("confidence", 0.7)
    raw_text = surface_treatment.get("raw_text")
    if surface_code == "chemical_nickel":
        add_operation(
            operations,
            operation_code="pre_plating_cleaning",
            rule_code="SURFACE_TREATMENT_PRE_PLATING",
            message="结构化字段识别到化学镍/镀镍，触发镀前清洗。",
            source=source,
            confidence=confidence,
        )
        add_operation(
            operations,
            operation_code="chemical_nickel",
            rule_code="SURFACE_TREATMENT_CHEMICAL_NICKEL",
            message=f"结构化字段识别到化学镍/镀镍：{raw_text}。",
            source=source,
            confidence=confidence,
        )
        add_operation(
            operations,
            operation_code="surface_masking",
            rule_code="SURFACE_TREATMENT_MASKING_CANDIDATE",
            message="结构化字段识别到化学镍/镀镍，螺纹孔、精孔或配合面可能需要遮蔽。",
            source=source,
            confidence=max(0.45, float_value(surface_treatment.get("confidence"), 0.7) - 0.12),
            requires_review=True,
            review_reason="Surface masking depends on threaded holes, precision holes, and functional surfaces.",
        )
        add_operation(
            operations,
            operation_code="post_surface_precision_hole_check",
            rule_code="SURFACE_TREATMENT_POST_HOLE_CHECK_CANDIDATE",
            message="结构化字段识别到化学镍/镀镍，镀后孔径、螺纹和关键尺寸复检作为候选。",
            source=source,
            confidence=max(0.45, float_value(surface_treatment.get("confidence"), 0.7) - 0.1),
            requires_review=True,
            review_reason="Post-plating hole and thread checks depend on functional tolerances.",
        )
        return

    rule_codes = {
        "clear_anodizing": "SURFACE_TREATMENT_CLEAR_ANODIZING",
        "hard_anodizing": "SURFACE_TREATMENT_HARD_ANODIZING",
        "color_anodizing": "SURFACE_TREATMENT_COLOR_ANODIZING",
        "hard_chrome": "SURFACE_TREATMENT_HARD_CHROME",
        "powder_coating": "SURFACE_TREATMENT_POWDER_COATING",
        "white_powder_coating": "SURFACE_TREATMENT_WHITE_POWDER_COATING",
        "powder_coating_texture": "SURFACE_TREATMENT_POWDER_COATING_TEXTURE",
        "sand_blasting": "SURFACE_TREATMENT_SAND_BLASTING",
    }
    add_operation(
        operations,
        operation_code="pre_plating_cleaning",
        rule_code="SURFACE_TREATMENT_PRE_PLATING",
        message=f"结构化字段识别到表面处理：{raw_text}，触发表处前清洗。",
        source=source,
        confidence=confidence,
    )
    masking_code = surface_masking_operation_code(surface_code)
    if masking_code:
        add_operation(
            operations,
            operation_code=masking_code,
            rule_code=f"SURFACE_TREATMENT_{masking_code.upper()}_CANDIDATE",
            message="表面处理可能需要对螺纹、精孔或功能面进行遮蔽。",
            source=source,
            confidence=max(0.45, float_value(surface_treatment.get("confidence"), 0.7) - 0.12),
            requires_review=True,
            review_reason="表处前请确认螺纹、精孔和功能面的遮蔽要求。",
        )
    add_operation(
        operations,
        operation_code=surface_code,
        rule_code=rule_codes.get(surface_code, "SURFACE_TREATMENT_MAPPED"),
        message=f"结构化字段识别到表面处理：{raw_text}。",
        source=source,
        confidence=confidence,
    )


def dedupe_risks(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result = []
    for risk in risks:
        key = (str(risk.get("code")), str(risk.get("message")))
        if key in seen:
            continue
        seen.add(key)
        result.append(risk)
    return result
