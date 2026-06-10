from __future__ import annotations

import re
from typing import Any

from .part_feature_builder import risk_item, source_ref
from .process_dictionary import PROCESS_NAMES, PROCESS_SEQUENCE


SUPPORTED_PART_TYPES = {"thin_plate", "plate", "block", "small_irregular"}
UNSUPPORTED_PART_TYPES = {"shaft", "complex"}
SAW_CUT_PART_TYPES = {"thin_plate", "plate", "block"}
CNC_PART_TYPES = {"plate", "block", "small_irregular"}

WELDING_KEYWORDS = ("焊接", "焊后", "焊缝", "weld", "welding")
ASSEMBLY_KEYWORDS = ("装配", "组装", "组件", "assembly", "assembled")
WIRE_CUT_KEYWORDS = ("线切割", "线割", "慢走丝", "中走丝", "快走丝", "wire cut", "wire-cut")
HEAT_TREATMENT_KEYWORDS = ("热处理", "淬火", "调质", "回火", "氮化", "hrc", "heat treatment")
CHEMICAL_NICKEL_KEYWORDS = ("化学镍", "化学镀镍", "镀镍", "nickel", "ni-p", "chemical nickel")
DEBURR_KEYWORDS = ("去毛刺", "毛刺", "飞边", "deburr", "burr")
EDGE_BREAK_KEYWORDS = ("锐角倒钝", "锐边", "倒钝", "break edge", "sharp edge")
SCRATCH_PROTECTION_KEYWORDS = ("不得划伤", "不得擦伤", "防划伤", "防擦伤", "scratch")
SUPPORT_PACKAGING_KEYWORDS = ("避免弯曲", "合理支撑")
STRAIGHTENING_KEYWORDS = ("校平", "校直", "straighten")
INSPECTION_KEYWORDS = ("检验", "检测", "全检", "报告", "inspection", "report")
ROUGHNESS_KEYWORDS = ("ra", "粗糙度", "精磨", "磨削", "grinding")
FLATNESS_KEYWORDS = ("平面度", "平行度", "垂直度", "flatness", "parallelism")
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
    operations: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    geometry = part_feature.get("geometry") or {}
    features = part_feature.get("features") or {}
    requirements = part_feature.get("manufacturing_requirements") or {}

    unsupported = unsupported_part_reason(part_feature, inherited_risks)
    if unsupported:
        add_unsupported_route_operations(operations, unsupported)
        risks.append(unsupported_part_risk(unsupported))
        return finalize_route(
            task_id=task_id,
            route_id=route_id,
            operations=operations,
            risks=risks,
        )

    add_material_operation(operations, part_feature)
    add_geometry_review_if_needed(operations, geometry)
    add_blank_operations(operations, geometry)
    add_shape_operations(operations, part_feature)
    risks.extend(add_material_preference_operations(operations, part_feature))
    add_hole_operations(operations, features)
    add_precision_requirement_operations(operations, features)
    add_requirement_operations(operations, requirements)
    add_supported_base_operations(operations, requirements)
    add_inherited_review_operation(operations, inherited_risks)
    risks.extend(resolve_process_conflicts(operations, part_feature))

    return finalize_route(
        task_id=task_id,
        route_id=route_id,
        operations=operations,
        risks=risks,
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


def add_geometry_review_if_needed(
    operations: list[dict[str, Any]],
    geometry: dict[str, Any],
) -> None:
    part_type = geometry.get("part_type")
    if part_type in SUPPORTED_PART_TYPES and has_complete_bounding_box(geometry.get("bounding_box") or {}):
        return
    if part_type in SUPPORTED_PART_TYPES:
        add_operation(
            operations,
            operation_code="review_drawing",
            rule_code="BOUNDING_BOX_MISSING",
            message="零件类型已识别，但毛坯尺寸不完整，需要审图或 3D 确认。",
            source=part_type_source(geometry),
            confidence=0.7,
            requires_review=True,
            review_reason="Bounding box is missing for process recognition.",
        )
    elif not part_type:
        add_operation(
            operations,
            operation_code="review_drawing",
            rule_code="PART_TYPE_MISSING",
            message="零件类型缺失，不能可靠识别下料和主体加工路线。",
            source=system_source("PART_TYPE_MISSING"),
            confidence=0.55,
            requires_review=True,
            review_reason="Part type is missing.",
        )


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

    if part_type in CNC_PART_TYPES:
        requires_review = part_type == "small_irregular" or complexity_score is None
        add_operation(
            operations,
            operation_code="cnc_milling",
            rule_code="CNC_FROM_PART_TYPE",
            message=(
                f"零件类型为 {part_type}，触发 CNC 铣削候选。"
                if requires_review
                else f"零件类型为 {part_type}，触发 CNC 铣削。"
            ),
            source=part_type_source(geometry),
            confidence=part_type_confidence(geometry, 0.72),
            requires_review=requires_review,
            review_reason=(
                "CNC route needs confirmation for small irregular parts or missing complexity."
                if requires_review
                else None
            ),
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
            operation_code="wire_cut_profile",
            rule_code="WIRE_PROFILE_SLOT_CANDIDATE",
            message=f"STEP 复杂度包含槽候选 {slot_count} 个，触发线切割外形候选。",
            source=system_source("WIRE_PROFILE_SLOT_CANDIDATE"),
            confidence=0.72,
            requires_review=True,
            review_reason="Slot candidates may need wire cutting confirmation.",
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
        if geometry_ready and has_heat_or_precision_requirement(part_feature):
            add_operation(
                operations,
                operation_code="finish_grinding",
                rule_code="MATERIAL_TOOL_STEEL_FINISH_GRINDING",
                message="材料为模具钢且存在热处理或精度要求，精磨作为候选工序。",
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

        if hole_type == "through":
            add_operation(
                operations,
                operation_code="drilling",
                rule_code="HOLE_THROUGH",
                message=f"识别到通孔 {count} 个，触发钻孔。",
                source=source,
                confidence=confidence,
            )
        elif hole_type == "blind":
            add_operation(
                operations,
                operation_code="drilling",
                rule_code="HOLE_BLIND",
                message=f"识别到盲孔 {count} 个，触发钻孔。",
                source=source,
                confidence=confidence,
            )
        elif hole_type in {"counterbore", "countersink"}:
            add_operation(
                operations,
                operation_code="drilling",
                rule_code="HOLE_COUNTER_FEATURE_PREDRILL",
                message=f"识别到{hole_type} {count} 个，主孔需要钻孔前置。",
                source=source,
                confidence=confidence,
            )
            add_operation(
                operations,
                operation_code="countersink",
                rule_code="HOLE_COUNTERBORE" if hole_type == "counterbore" else "HOLE_COUNTERSINK",
                message=f"识别到{hole_type} {count} 个，触发沉孔/沉头孔加工。",
                source=source,
                confidence=confidence,
            )
        elif hole_type == "thread_candidate":
            add_operation(
                operations,
                operation_code="drilling",
                rule_code="HOLE_THREAD_PILOT_DRILLING",
                message=f"识别到螺纹孔候选 {count} 个，底孔需要钻孔前置。",
                source=source,
                confidence=confidence,
                requires_review=True,
                review_reason="Thread-hole pilot drilling needs confirmation.",
            )
            add_operation(
                operations,
                operation_code="tapping",
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
                operation_code="drilling",
                rule_code="HOLE_PRECISION_PREDRILL",
                message=f"识别到精孔候选 {count} 个，钻孔作为精孔前置。",
                source=source,
                confidence=confidence,
                requires_review=True,
                review_reason="Precision-hole predrilling needs confirmation.",
            )
            add_operation(
                operations,
                operation_code="precision_hole",
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
                operation_code="precision_hole",
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
                operation_code="finish_grinding",
                rule_code="ROUGHNESS_OR_FLATNESS_REQUIREMENT",
                message="识别到粗糙度、平面度或精密面要求，触发精磨候选。",
                source=source,
                confidence=confidence,
                requires_review=True,
                review_reason="Grinding mapping from precision requirement needs confirmation.",
            )


def add_requirement_operations(
    operations: list[dict[str, Any]],
    requirements: dict[str, Any],
) -> None:
    add_structured_requirement_operations(operations, requirements)

    for item in technical_requirement_items(requirements):
        raw_text = item["raw_text"]
        normalized = normalize_text(raw_text)
        source = item.get("source")
        confidence = item.get("confidence", 0.72)
        requirement_type = item.get("requirement_type")

        if "3d" in normalized and ("未标注" in raw_text or "参见" in raw_text):
            add_operation(
                operations,
                operation_code="review_drawing",
                rule_code="TECH_REQ_REVIEW_3D",
                message="技术要求说明未标注尺寸参见 3D，触发审图/3D确认。",
                source=source,
                confidence=confidence,
                requires_review=True,
                review_reason="Drawing requires 3D confirmation.",
            )

        if has_thread_callout(raw_text):
            add_operation(
                operations,
                operation_code="drilling",
                rule_code="TECH_REQ_THREAD_PILOT_DRILLING",
                message="技术要求包含 M 螺纹标注，底孔需要钻孔前置。",
                source=source,
                confidence=confidence,
                requires_review=True,
                review_reason="Thread callout pilot drilling needs confirmation.",
            )
            add_operation(
                operations,
                operation_code="tapping",
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
                message="技术要求包含去毛刺、飞边或锐角倒钝，触发去毛刺。",
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

        if contains_any(normalized, CHEMICAL_NICKEL_KEYWORDS):
            add_operation(
                operations,
                operation_code="pre_plating_cleaning",
                rule_code="TECH_REQ_PRE_PLATING_CLEANING",
                message="技术要求包含化学镀镍，触发镀前清洗候选。",
                source=source,
                confidence=confidence,
            )
            add_operation(
                operations,
                operation_code="chemical_nickel",
                rule_code="TECH_REQ_CHEMICAL_NICKEL",
                message="技术要求包含化学镀镍/镀镍，触发化学镍。",
                source=source,
                confidence=confidence,
            )
            add_operation(
                operations,
                operation_code="post_plating_inspection",
                rule_code="TECH_REQ_POST_PLATING_INSPECTION",
                message="技术要求包含化学镀镍，触发镀后检验候选。",
                source=source,
                confidence=confidence,
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
                message="技术要求强调防弯曲支撑，触发防护包装。",
                source=source,
                confidence=confidence,
            )

        if requirement_type == "precision" or contains_any(normalized, ROUGHNESS_KEYWORDS + FLATNESS_KEYWORDS):
            if contains_any(normalized, HOLE_PRECISION_KEYWORDS + TIGHT_TOLERANCE_KEYWORDS):
                add_operation(
                    operations,
                    operation_code="precision_hole",
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
                    operation_code="finish_grinding",
                    rule_code="TECH_REQ_FINISH_GRINDING",
                    message="技术要求包含粗糙度、平面度或磨削要求，触发精磨候选。",
                    source=source,
                    confidence=confidence,
                    requires_review=True,
                    review_reason="Grinding requirement needs process confirmation.",
                )


def add_structured_requirement_operations(
    operations: list[dict[str, Any]],
    requirements: dict[str, Any],
) -> None:
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
        if is_chemical_plating(surface_treatment):
            add_operation(
                operations,
                operation_code="pre_plating_cleaning",
                rule_code="SURFACE_TREATMENT_PRE_PLATING",
                message="结构化字段识别到化学镍/镀镍，触发镀前清洗。",
                source=surface_treatment.get("source"),
                confidence=surface_treatment.get("confidence", 0.7),
            )
            add_operation(
                operations,
                operation_code="chemical_nickel",
                rule_code="SURFACE_TREATMENT_CHEMICAL_NICKEL",
                message=f"结构化字段识别到化学镍/镀镍：{surface_treatment.get('raw_text')}。",
                source=surface_treatment.get("source"),
                confidence=surface_treatment.get("confidence", 0.7),
            )
            add_operation(
                operations,
                operation_code="post_plating_inspection",
                rule_code="SURFACE_TREATMENT_POST_PLATING_INSPECTION",
                message="结构化字段识别到化学镍/镀镍，触发镀后检验。",
                source=surface_treatment.get("source"),
                confidence=surface_treatment.get("confidence", 0.7),
            )
        else:
            add_operation(
                operations,
                operation_code="review_drawing",
                rule_code="SURFACE_TREATMENT_UNKNOWN",
                message="结构化字段识别到表面处理，但无法映射到已支持的化学镍工序。",
                source=surface_treatment.get("source"),
                confidence=surface_treatment.get("confidence", 0.55),
                requires_review=True,
                review_reason="Surface treatment is not mapped to a supported process.",
            )

    deburring = requirements.get("deburring") or {}
    if deburring.get("required"):
        add_operation(
            operations,
            operation_code="deburr",
            rule_code="DEBURRING_REQUIRED",
            message="结构化字段识别到去毛刺要求。",
            source=deburring.get("source"),
            confidence=deburring.get("confidence", 0.65),
        )


def add_supported_base_operations(
    operations: list[dict[str, Any]],
    requirements: dict[str, Any],
) -> None:
    inspection = requirements.get("inspection") or {}
    add_operation(
        operations,
        operation_code="inspection",
        rule_code="SUPPORTED_PART_INSPECTION",
        message="支持范围内零件默认需要终检。",
        source=inspection.get("source") or system_source("SUPPORTED_PART_INSPECTION"),
        confidence=inspection.get("confidence", 0.7) if inspection else 0.7,
    )

    packaging = requirements.get("packaging") or {}
    add_operation(
        operations,
        operation_code="protective_packaging",
        rule_code="SUPPORTED_PART_PACKAGING",
        message="支持范围内零件默认需要防护包装。",
        source=packaging.get("source") or system_source("SUPPORTED_PART_PACKAGING"),
        confidence=packaging.get("confidence") or 0.65,
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


def add_unsupported_route_operations(
    operations: list[dict[str, Any]],
    unsupported: dict[str, Any],
) -> None:
    add_operation(
        operations,
        operation_code="review_drawing",
        rule_code=unsupported["rule_code"],
        message=unsupported["message"],
        source=unsupported.get("source"),
        confidence=unsupported.get("confidence", 0.8),
        requires_review=True,
        review_reason=unsupported["review_reason"],
    )
    if unsupported.get("part_type") == "shaft":
        add_operation(
            operations,
            operation_code="turning",
            rule_code="UNSUPPORTED_SHAFT_TURNING",
            message="识别到轴类件，第一版仅提示车削人工确认，不进入自动报价。",
            source=unsupported.get("source"),
            confidence=unsupported.get("confidence", 0.8),
            requires_review=True,
            review_reason="Shaft parts are outside MVP auto-quote scope.",
        )
    elif unsupported.get("part_type") == "complex":
        add_operation(
            operations,
            operation_code="edm",
            rule_code="UNSUPPORTED_COMPLEX_EDM",
            message="识别到复杂件，放电/复杂工艺仅作为人工确认候选。",
            source=unsupported.get("source"),
            confidence=unsupported.get("confidence", 0.72),
            requires_review=True,
            review_reason="Complex parts are outside MVP auto-quote scope.",
        )
    add_operation(
        operations,
        operation_code="manual_review",
        rule_code="UNSUPPORTED_REQUIRES_MANUAL_REVIEW",
        message="不支持件需要转人工复核，不输出完整自动核价路线。",
        source=unsupported.get("source"),
        confidence=0.95,
        requires_review=True,
        review_reason=unsupported["review_reason"],
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
    cnc = operation_by_code(operations, "cnc_milling")
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
            mark_requires_review(
                cnc,
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

    if operation_by_code(operations, "chemical_nickel") and operation_by_code(operations, "precision_hole"):
        risks.append(
            risk_item(
                "SURFACE_TREATMENT_PRECISION_HOLE_RISK",
                "warning",
                "化学镍/镀镍可能影响精孔孔径，需确认镀前尺寸补偿、镀后孔径复检或修孔方案。",
                "process_recognition",
                True,
                [system_source("SURFACE_TREATMENT_PRECISION_HOLE_RISK")],
            )
        )
        mark_requires_review(
            operation_by_code(operations, "precision_hole"),
            "Chemical nickel may require pre-plating compensation or post-plating hole inspection/rework.",
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
        add_operation(
            operations,
            operation_code="finish_grinding",
            rule_code="HEAT_TREATMENT_THIN_PART_FINISH_GRINDING",
            message="热处理叠加薄片/薄壁特征，触发热后精磨候选。",
            source=part_type_source(geometry),
            confidence=0.66,
            requires_review=True,
            review_reason="Heat-treated thin parts may need finish grinding.",
        )

    return risks


def finalize_route(
    *,
    task_id: str,
    route_id: str,
    operations: list[dict[str, Any]],
    risks: list[dict[str, Any]],
) -> dict[str, Any]:
    ordered = sorted(
        operations,
        key=lambda item: PROCESS_SEQUENCE.index(item["operation_code"]),
    )
    for index, operation in enumerate(ordered, start=1):
        operation["sequence"] = index
        operation["operation_id"] = f"op_{index:03d}_{operation['operation_code'].lower()}"

    route_risks = list(risks)
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
        "operations": ordered,
        "requires_review": bool(route_risks),
        "risks": route_risks,
    }


def process_route_review_message(operations: list[dict[str, Any]]) -> str:
    review_codes = {
        str(operation.get("operation_code"))
        for operation in operations
        if operation.get("requires_review")
    }
    route_step_codes = review_codes - {"review_drawing", "manual_review"}
    if route_step_codes:
        return "工艺路线包含需复核工序，需人工确认。"
    if "review_drawing" in review_codes and "manual_review" in review_codes:
        return "图纸审查和解析/特征风险需要人工确认。"
    if "review_drawing" in review_codes:
        return "图纸要求审图或 3D 确认，正式报价前需人工确认。"
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
    existing = next(
        (item for item in operations if item["operation_code"] == operation_code),
        None,
    )
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


def unsupported_part_reason(
    part_feature: dict[str, Any],
    inherited_risks: list[dict[str, Any]],
) -> dict[str, Any] | None:
    geometry = part_feature.get("geometry") or {}
    part_type = geometry.get("part_type")
    if part_type in UNSUPPORTED_PART_TYPES:
        label = "轴类件" if part_type == "shaft" else "复杂件"
        return {
            "part_type": part_type,
            "rule_code": f"UNSUPPORTED_PART_TYPE_{part_type.upper()}",
            "message": f"识别到{label}，第一版不自动核价，转人工确认。",
            "review_reason": f"{part_type} is outside MVP auto-quote scope.",
            "confidence": part_type_confidence(geometry, 0.82),
            "source": part_type_source(geometry),
        }

    texts = all_part_feature_text(part_feature, inherited_risks)
    if contains_any(texts, WELDING_KEYWORDS):
        return {
            "part_type": "weldment",
            "rule_code": "UNSUPPORTED_WELDMENT",
            "message": "技术要求或风险中出现焊接/焊后加工信息，第一版转人工确认。",
            "review_reason": "Weldments are outside MVP auto-quote scope.",
            "confidence": 0.82,
            "source": technical_source(part_feature.get("manufacturing_requirements") or {}, WELDING_KEYWORDS),
        }
    if contains_any(texts, ASSEMBLY_KEYWORDS):
        return {
            "part_type": "assembly",
            "rule_code": "UNSUPPORTED_ASSEMBLY",
            "message": "技术要求或风险中出现装配/组件信息，第一版转人工确认。",
            "review_reason": "Assemblies are outside MVP auto-quote scope.",
            "confidence": 0.82,
            "source": technical_source(part_feature.get("manufacturing_requirements") or {}, ASSEMBLY_KEYWORDS),
        }
    return None


def unsupported_part_risk(unsupported: dict[str, Any]) -> dict[str, Any]:
    return risk_item(
        "UNSUPPORTED_PART_REQUIRES_MANUAL_REVIEW",
        "blocking",
        unsupported["message"],
        "process_recognition",
        True,
        [unsupported.get("source") or system_source(unsupported["rule_code"])],
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


def mark_requires_review(operation: dict[str, Any] | None, reason: str) -> None:
    if not operation:
        return
    operation["requires_review"] = True
    operation["review_reason"] = operation.get("review_reason") or reason


def has_complete_bounding_box(bounding_box: dict[str, Any]) -> bool:
    return all(numeric_value(bounding_box.get(key)) is not None for key in ("length", "width", "height"))


def is_thin_part(geometry: dict[str, Any], complexity: dict[str, Any]) -> bool:
    if geometry.get("part_type") == "thin_plate":
        return True
    if complexity.get("thin_wall_candidate"):
        return True
    bbox = geometry.get("bounding_box") or {}
    dimensions = [
        numeric_value(bbox.get(key))
        for key in ("length", "width", "height")
    ]
    if any(value is None or value <= 0 for value in dimensions):
        return False
    min_dim = min(value for value in dimensions if value is not None)
    max_dim = max(value for value in dimensions if value is not None)
    return min_dim <= 3 and max_dim / min_dim >= 20


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
