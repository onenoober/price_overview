"""L3 路 鐗瑰緛涓庤瘉鎹眰 (Features & Evidence).

鎶婂嚑浣曠壒寰併€佸瓟/铻虹汗銆佽〃澶?鐑鐞嗗瓧娈点€佹妧鏈姹傝浆鎴?璇佹嵁鍊欓€夊伐搴?锛屼緵 L4 鐭╅樀鍒ゆ柇鏄惁鎻掑叆銆?鍑犱綍鍦ㄨ繖閲?*鍙槸浜岀骇鐗瑰緛锛屼笉鑳芥崲鏃?*銆傝〃澶勮瘉鎹彧璁ゅ己鏉ユ簮锛堟爣棰樻爮瀛楁锛夛紱鎶€鏈姹傛寜鍙ュ紡
鍋氳涔夊垎绾э紙required / conditional / instructional锛夈€?"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from backend.app.part_feature_builder import source_ref
from backend.app.process_recognition import (
    DEBURR_KEYWORDS,
    EDGE_BREAK_KEYWORDS,
    FLATNESS_KEYWORDS,
    HEAT_TREATMENT_KEYWORDS,
    ROUGHNESS_KEYWORDS,
    STRAIGHTENING_KEYWORDS,
    THERMAL_DISTORTION_MATERIALS,
    TOOL_STEEL_KEYWORDS,
    WELDING_KEYWORDS,
    WIRE_CUT_KEYWORDS,
    contains_any,
    has_thread_callout,
    has_wire_profile_geometry,
    int_value,
    is_precision_hole,
    is_side_hole,
    is_thread_hole,
    material_text,
    match_material_code,
    normalize_text,
    numeric_value,
    surface_treatment_operation_code,
    surface_treatment_operation_codes,
    technical_requirement_items,
    technical_text,
)

from .config import route_detailing_enabled
from .families import LARGE_PLATE, MACHINING, SHEET_METAL, TURNING
from .parsed_part import ParsedPart
from .reviews import (
    LONG_STRIP_BOUNDARY_REVIEW,
    SURFACE_TREATMENT_UNVERIFIED,
    WELDING_CONDITIONAL_TEXT,
)


# Evidence strengths. field/tech_required/geometry are strong evidence; tech_conditional is a candidate.
FIELD = "field"
GEOMETRY = "geometry"
TECH_REQUIRED = "tech_required"
TECH_CONDITIONAL = "tech_conditional"

# Bending/forming evidence keywords.
BENDING_KEYWORDS = (
    "\u6298\u5f2f",
    "\u6298\u8fb9",
    "\u6298\u5f2f\u89d2",
    "\u5f2f\u66f2\u534a\u5f84",
    "\u6298\u6210",
    "\u6210\u5f62",
    "bend",
    "bending",
)
SHEET_FORM_NAME_KEYWORDS = (
    "\u652f\u67b6",
    "\u652f\u6491\u67b6",
    "\u62a4\u7f69",
    "\u6846\u67b6",
    "\u6321\u677f",
    "\u76d6\u677f",
)
SHEET_FORM_WEAK_NAME_KEYWORDS = ("\u6258\u677f",)
FLAT_SHEET_MAX_THICKNESS_MM = 30.0
FORMED_SHEET_PART_TYPES = ("formed_sheet", "bent_sheet", "assembly_candidate")

# Turning auxiliary-process evidence keywords.
FLAT_KEYWORDS = (
    "\u6241\u4f4d",
    "\u94e3\u6241",
    "\u94e3\u65b9",
    "flat",
    "wrench flat",
    "\u5bf9\u8fb9",
    "\u5bf9\u79f0\u94e3",
)
KEYWAY_KEYWORDS = ("\u952e\u69fd", "keyway", "key slot")
OBROUND_SLOT_KEYWORDS = (
    "\u957f\u5706",
    "\u8170\u578b",
    "\u8170\u5f62",
    "\u957f\u5706\u69fd",
    "\u957f\u5706\u5b54",
    "obround",
    "oblong",
)
EDM_KEYWORDS = ("\u7535\u706b\u82b1", "\u653e\u7535", "edm")
CROSS_HOLE_KEYWORDS = (
    "\u5f84\u5411\u5b54",
    "\u6a2a\u5411\u5b54",
    "\u4fa7\u5b54",
    "cross hole",
    "radial hole",
)
OBROUND_DIMENSION_PATTERN = re.compile(
    r"(?<!\d)(?:\d+\s*[xX×]\s*)?(?P<a>\d+(?:\.\d+)?)\s*[xX×]\s*(?P<b>\d+(?:\.\d+)?)"
)

EXTERNAL_THREAD_KEYWORDS = (
    "\u5916\u87ba\u7eb9",
    "\u8f66\u87ba\u7eb9",
    "\u87ba\u6746",
    "\u87ba\u67f1",
    "external thread",
)
HARDNESS_PATTERN = re.compile(r"\b(?:HRC|HB|HV)\s*[:：]?\s*\d", re.IGNORECASE)

INTERNAL_THREAD_KEYWORDS = (
    "\u87ba\u7eb9\u5b54",
    "\u653b\u7259",
    "\u653b\u4e1d",
    "\u76f2\u7259",
    "\u901a\u7259",
    "\u6709\u6548\u87ba\u7eb9\u6df1\u5ea6",
    "threaded hole",
    "tap",
)

CONDITIONAL_MARKERS = (
    "\u5bf9\u4e8e",
    "\u5f53",
    "\u5982\u679c",
    "\u5728",
    "\u82e5",
    "\u9700\u8981\u65f6",
    "\u5982\u9700",
)
INSTRUCTIONAL_MARKERS = (
    "\u5e94\u906e\u6321",
    "\u906e\u6321",
    "\u6ce8\u610f",
    "\u4e0d\u5f97",
    "\u4e25\u7981",
    "\u907f\u514d",
    "\u9632\u6b62",
    "\u4fdd\u8bc1",
    "\u786e\u4fdd",
)


@dataclass(frozen=True)
class Candidate:
    op_code: str
    strength: str
    rule_code: str
    message: str
    source: dict[str, Any]
    confidence: float = 0.7
    requires_review: bool = False
    review_reason: str | None = None
    review_code: str | None = None
    review_only: bool = False

    @property
    def is_geometry(self) -> bool:
        return self.strength == GEOMETRY


@dataclass(frozen=True)
class AxisProfile:
    subtype: str
    slenderness: float | None
    is_thin_ring: bool
    has_large_coaxial_bore: bool
    has_thread: bool
    has_real_milling_feature: bool
    surface_scope_confidence: float
    subtype_confidence: float


AXIS_SLENDER_OR_ROLLER = "SLENDER_OR_ROLLER"
AXIS_SHORT_RING = "SHORT_RING"
AXIS_UNKNOWN = "UNKNOWN"

AXIS_STRAIGHTNESS_KEYWORDS = (
    "直线度",
    "同轴度",
    "跳动",
    "straightness",
    "coaxiality",
    "runout",
)

AXIS_SUPPORT_BENDING_KEYWORDS = (
    "避免弯曲",
    "防止弯曲",
    "合理支撑",
)

SURFACE_LOCAL_SCOPE_KEYWORDS = (
    "局部",
    "遮蔽",
    "非镀",
    "不镀",
    "保护",
    "mask",
    "masking",
    "partial",
    "selective",
)


def build_axis_profile(
    parsed: ParsedPart,
    holes: list[dict[str, Any]],
    tech_text: str,
) -> AxisProfile:
    dims = _axis_dimensions(parsed.geometry)
    slenderness = _axis_slenderness(dims)
    is_thin_ring = _is_axis_thin_ring(dims)
    surface = parsed.requirements.get("surface_treatment") or {}
    surface_text = normalize_text(
        " ".join(str(surface.get(key) or "") for key in ("raw_text", "standard_code"))
    )
    has_large_bore = any(_is_large_axis_bore_hole(hole, dims) for hole in holes)
    has_thread = any(is_thread_hole(hole) for hole in holes)
    subtype = AXIS_UNKNOWN
    subtype_confidence = 0.0
    part_type = parsed.geometry_part_type or ""
    part_name = normalize_text(
        " ".join(
            str(value or "")
            for value in (
                (parsed.part_feature.get("part") or {}).get("part_name"),
                parsed.business_class.raw_text,
            )
        )
    )
    if len(dims) >= 2:
        if is_thin_ring or part_type in {"ring", "washer"} or contains_any(part_name, ("垫圈", "隔套", "定位圈", "ring", "washer", "sleeve")):
            subtype = AXIS_SHORT_RING
            subtype_confidence = 0.82
        elif (
            (slenderness is not None and slenderness >= 3.0)
            or part_type in {"shaft", "shaft_candidate", "long_bar", "roller_candidate"}
            or contains_any(part_name, ("轴", "滚筒", "滚轮", "roller", "shaft"))
        ):
            subtype = AXIS_SLENDER_OR_ROLLER
            subtype_confidence = 0.78
        else:
            subtype_confidence = 0.35

    return AxisProfile(
        subtype=subtype,
        slenderness=slenderness,
        is_thin_ring=is_thin_ring,
        has_large_coaxial_bore=has_large_bore,
        has_thread=has_thread,
        has_real_milling_feature=False,
        surface_scope_confidence=0.8 if contains_any(surface_text, SURFACE_LOCAL_SCOPE_KEYWORDS) else 0.0,
        subtype_confidence=subtype_confidence,
    )


def _axis_dimensions(geometry: dict[str, Any]) -> list[float]:
    bbox = geometry.get("bounding_box") or {}
    values = [
        numeric_value(bbox.get("length")),
        numeric_value(bbox.get("width")),
        numeric_value(bbox.get("height")),
        numeric_value(bbox.get("thickness")),
        numeric_value(bbox.get("diameter")),
    ]
    return sorted(round(value, 6) for value in values if value and value > 0)


def _axis_slenderness(dims: list[float]) -> float | None:
    if len(dims) < 2 or dims[0] <= 0:
        return None
    return dims[-1] / dims[0]


def _is_axis_thin_ring(dims: list[float]) -> bool:
    if len(dims) < 3:
        return False
    thickness, mid, outer = dims[0], dims[1], dims[-1]
    if outer <= 0 or mid <= 0:
        return False
    round_plan = mid / outer >= 0.75
    thin = thickness <= 8.0 or thickness / mid <= 0.35
    return round_plan and thin


def _is_large_axis_bore_hole(hole: dict[str, Any], dims: list[float]) -> bool:
    if len(dims) < 2:
        return False
    hole_type = str(hole.get("hole_type") or "")
    if hole_type not in {"blind", "through", "precision_candidate"}:
        return False
    count = int_value(hole.get("count")) or 0
    if count <= 0 or count > 2:
        return False
    diameter = numeric_value(hole.get("diameter"))
    depth = numeric_value(hole.get("depth"))
    if diameter is None or depth is None:
        return False
    outer_diameter = _axis_outer_diameter_from_dims(dims)
    if outer_diameter <= 0:
        return False
    deep_cavity = depth >= max(15.0, outer_diameter * 0.6)
    large_relative_diameter = diameter / outer_diameter >= 0.4
    large_absolute_diameter = diameter >= 20.0
    return deep_cavity and large_relative_diameter and large_absolute_diameter


def _axis_outer_diameter_from_dims(dims: list[float]) -> float:
    if len(dims) < 2:
        return 0.0
    unique = sorted({round(value, 6) for value in dims})
    if len(unique) >= 2 and len(dims) >= 3:
        smallest_count = sum(1 for value in dims if abs(value - unique[0]) < 1e-6)
        if smallest_count >= 2:
            return unique[0]
    return unique[-2] if len(unique) >= 2 else unique[-1]


def _axis_has_outer_grinding_evidence(
    tech_text: str,
    holes: list[dict[str, Any]],
    hard_chrome_surface: bool,
) -> bool:
    text = normalize_text(
        " ".join([tech_text] + [_hole_text(hole) for hole in holes])
    )
    return (
        contains_any(text, ("外圆", "外径", "圆跳动", "径向跳动", "同轴度", "cylindrical", "od grinding"))
        or (hard_chrome_surface and contains_any(text, ("镀后磨", "镀后抛光", "镀后修磨")))
    )


def collect_evidence(parsed: ParsedPart, family_hint: str | None = None) -> list[Candidate]:
    candidates: list[Candidate] = []
    requirements = parsed.requirements
    features = parsed.features
    geometry = parsed.geometry
    complexity = features.get("complexity") or {}
    tech_text = technical_text(requirements)
    material_normalized = material_text(parsed.material)
    holes = [hole for hole in (features.get("holes") or []) if int_value(hole.get("count")) or 0]
    axis_profile = build_axis_profile(parsed, holes, tech_text) if family_hint == TURNING else None

    _add_surface_evidence(candidates, parsed, family_hint=family_hint)
    _add_heat_evidence(candidates, requirements, tech_text)
    _add_hole_evidence(
        candidates,
        holes,
        requirements,
        family_hint=family_hint,
        geometry=geometry,
        axis_profile=axis_profile,
    )
    _add_shaft_milling_evidence(
        candidates,
        parsed,
        tech_text,
        holes,
        family_hint=family_hint,
        axis_profile=axis_profile,
    )
    _add_bending_evidence(candidates, parsed, tech_text, family_hint=family_hint)
    _add_welding_evidence(candidates, geometry, parsed, requirements, family_hint=family_hint)
    _add_profile_geometry_evidence(candidates, geometry, features, complexity, tech_text, family_hint=family_hint)
    _add_machining_geometry_evidence(candidates, parsed, complexity, family_hint=family_hint)
    _add_finishing_evidence(
        candidates,
        parsed,
        tech_text,
        material_normalized,
        holes,
        family_hint=family_hint,
        axis_profile=axis_profile,
    )
    _add_long_strip_boundary_review(candidates, parsed, material_normalized, family_hint=family_hint)
    if route_detailing_enabled():
        _add_detailing_evidence(
            candidates,
            parsed,
            tech_text,
            material_normalized,
            holes,
            family_hint=family_hint,
            axis_profile=axis_profile,
        )
    _add_deburr_evidence(candidates, requirements, tech_text)
    return candidates


# --- 琛ㄥ锛氬彧璁ゅ己鏉ユ簮 ---------------------------------------------------------

def _add_surface_evidence(
    candidates: list[Candidate],
    parsed: ParsedPart,
    family_hint: str | None = None,
) -> None:
    requirements = parsed.requirements
    surface = requirements.get("surface_treatment") or {}
    # Strong source: title-block surface-treatment field.
    if surface.get("required"):
        ops = surface_treatment_operation_codes(
            surface, material=parsed.material, family=family_hint
        )
        if ops:
            for op in ops:
                candidates.append(
                    Candidate(
                        op_code=op,
                        strength=FIELD,
                        rule_code="SURFACE_TREATMENT_FIELD",
                        message="Title-block surface-treatment field maps to this operation.",
                        source=surface.get("source") or source_ref("system", rule_code="SURFACE_TREATMENT_FIELD"),
                        confidence=0.82,
                        requires_review=op != "chemical_nickel",
                        review_reason="Confirm treatment type, color, coating thickness, and supplier standard.",
                    )
                )
            return

    # Weak source: technical requirements text only; review instead of binding.
    for item in technical_requirement_items(requirements):
        raw = item.get("raw_text")
        if _classify_sentence(raw) == "instructional":
            continue
        op = surface_treatment_operation_code(
            {"standard_code": item.get("standard_code"), "raw_text": raw}
        )
        if op:
            candidates.append(
                Candidate(
                    op_code=op,
                    strength=TECH_CONDITIONAL,
                    rule_code="SURFACE_TREATMENT_TECH_TEXT",
                    message="Surface treatment appears only in technical text; keep as review candidate.",
                    source=source_ref("system", rule_code=SURFACE_TREATMENT_UNVERIFIED, raw_text=str(raw or "")),
                    confidence=0.4,
                    requires_review=True,
                    review_reason="Confirm whether this text requires actual surface treatment.",
                    review_code=SURFACE_TREATMENT_UNVERIFIED,
                )
            )
            return


def _add_heat_evidence(
    candidates: list[Candidate], requirements: dict[str, Any], tech_text: str
) -> None:
    heat = requirements.get("heat_treatment") or {}
    if heat.get("required"):
        candidates.append(
            Candidate(
                op_code="heat_treatment",
                strength=FIELD,
                rule_code="HEAT_TREATMENT_FIELD",
                message="Title-block heat-treatment field maps to heat treatment.",
                source=heat.get("source") or source_ref("system", rule_code="HEAT_TREATMENT_FIELD"),
                confidence=0.82,
            )
        )
        return
    if _has_actionable_heat_treatment_text(requirements, tech_text):
        candidates.append(
            Candidate(
                op_code="heat_treatment",
                strength=TECH_REQUIRED,
                rule_code="HEAT_TREATMENT_TECH",
                message="Technical requirements mention heat treatment.",
                source=source_ref("system", rule_code="HEAT_TREATMENT_TECH"),
                confidence=0.7,
                requires_review=True,
                review_reason="Confirm heat-treatment type and hardness requirement.",
            )
        )


def _has_actionable_heat_treatment_text(requirements: dict[str, Any], tech_text: str) -> bool:
    actionable_keywords = ("淬火", "调质", "回火", "氮化", "渗碳", "时效", "hrc", "hb", "hv", "quench", "temper")
    for item in technical_requirement_items(requirements):
        raw = str(item.get("raw_text") or "").strip()
        text = normalize_text(raw)
        if not text or text in {"热处理", "heat treatment"}:
            continue
        if contains_any(text, actionable_keywords):
            return True
    return contains_any(normalize_text(tech_text), actionable_keywords)


def _add_hole_evidence(
    candidates: list[Candidate],
    holes: list[dict[str, Any]],
    requirements: dict[str, Any],
    family_hint: str | None = None,
    geometry: dict[str, Any] | None = None,
    axis_profile: AxisProfile | None = None,
) -> None:
    # Turning parts use a separate hole model.
    if family_hint == TURNING:
        _add_turning_hole_evidence(candidates, holes, requirements, geometry or {}, axis_profile)
        return

    buckets = _classify_holes(holes)
    if holes:
        candidates.append(
            Candidate(
                op_code="drilling",
                strength=GEOMETRY,
                rule_code="HOLE_DRILLING",
                message="Hole features detected; add drilling operation.",
                source=source_ref("step", rule_code="HOLE_DRILLING"),
                confidence=0.72,
            )
        )
    thread = (
        buckets["has_thread"]
        or any(has_thread_callout(item.get("raw_text")) for item in technical_requirement_items(requirements))
    )
    if thread:
        candidates.append(
            Candidate(
                op_code="tapping",
                strength=GEOMETRY,
                rule_code="THREAD_TAPPING",
                message="Thread evidence detected; add tapping operation.",
                source=source_ref("step", rule_code="THREAD_TAPPING"),
                confidence=0.72,
            )
        )
    suppress_counterbore = (
        family_hint == SHEET_METAL
        and (
            _has_obround_hole_signal(holes, requirements)
            or (buckets["has_countersink"] and _has_only_shallow_counterbore_signal(holes))
        )
        and not _has_explicit_counterbore_signal(holes, requirements)
    )
    suppress_countersink = (
        family_hint == SHEET_METAL
        and buckets["has_counterbore"]
        and _has_redundant_countersink_signal(holes)
        and not _has_explicit_countersink_signal(holes, requirements)
    )
    if buckets["has_counterbore"] and not suppress_counterbore:
        weak_machining_counterbore = family_hint == MACHINING and not _has_explicit_counterbore_signal(holes, requirements)
        if weak_machining_counterbore:
            candidates.append(
                Candidate(
                    op_code="counterbore",
                    strength=GEOMETRY,
                    rule_code="COUNTERBORE_WEAK_GEOMETRY",
                    message="STEP suggests counterbore geometry, but drawing callout or complete counterbore dimensions were not found.",
                    source=source_ref("step", rule_code="COUNTERBORE_WEAK_GEOMETRY"),
                    confidence=0.42,
                    requires_review=True,
                    review_reason="Confirm whether counterbore machining is required before adding it to the formal route.",
                    review_code="WEAK_MACHINING_COUNTERBORE_REVIEW",
                    review_only=True,
                )
            )
        else:
            candidates.append(
                Candidate(
                    op_code="counterbore",
                    strength=GEOMETRY,
                    rule_code="COUNTERBORE",
                    message="Counterbore feature detected; add counterbore operation.",
                    source=source_ref("step", rule_code="COUNTERBORE"),
                    confidence=0.7,
                )
            )
    if buckets["has_countersink"] and not suppress_countersink:
        candidates.append(
            Candidate(
                op_code="countersink",
                strength=GEOMETRY,
                rule_code="COUNTERSINK",
                message="Countersink or chamfered-hole feature detected; add countersink operation.",
                source=source_ref("step", rule_code="COUNTERSINK"),
                confidence=0.7,
            )
        )


def classify_thread_text(text: Any) -> str | None:
    """Classify thread text as external, internal, or absent."""

    normalized = normalize_text(text)
    if contains_any(normalized, EXTERNAL_THREAD_KEYWORDS):
        return "external"
    if contains_any(normalized, INTERNAL_THREAD_KEYWORDS):
        return "internal"
    return None


_COUNTERBORE_TYPES = {"counterbore", "reverse_counterbore"}
_COUNTERSINK_TYPES = {"countersink", "countersink_90"}


def _classify_holes(holes: list[dict[str, Any]]) -> dict[str, bool]:
    types = {str(hole.get("hole_type") or "") for hole in holes}
    return {
        "has_round": bool(types & {"through", "blind"}),
        "has_counterbore": any(_has_counterbore_signal(hole) for hole in holes),
        "has_countersink": any(_has_countersink_signal(hole) for hole in holes),
        "has_thread": any(is_thread_hole(hole) for hole in holes),
        "has_precision": any(is_precision_hole(hole) for hole in holes),
    }


def _hole_text(hole: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("raw_text", "standard_type", "feature_role", "description"):
        value = hole.get(key)
        if value:
            parts.append(str(value))
    for evidence in hole.get("evidence") or []:
        if isinstance(evidence, dict) and evidence.get("raw_text"):
            parts.append(str(evidence.get("raw_text")))
    return normalize_text(" ".join(parts))


def _all_hole_text(holes: list[dict[str, Any]], requirements: dict[str, Any]) -> str:
    return normalize_text(
        " ".join(
            [_hole_text(hole) for hole in holes]
            + [str(item.get("raw_text") or "") for item in technical_requirement_items(requirements)]
        )
    )


def _has_obround_hole_signal(holes: list[dict[str, Any]], requirements: dict[str, Any]) -> bool:
    text = _all_hole_text(holes, requirements)
    if contains_any(text, OBROUND_SLOT_KEYWORDS):
        return True
    for match in OBROUND_DIMENSION_PATTERN.finditer(text):
        a = numeric_value(match.group("a")) or 0.0
        b = numeric_value(match.group("b")) or 0.0
        if min(a, b) > 0 and max(a, b) / min(a, b) >= 3.0:
            return True
    return False


def _has_explicit_counterbore_text(holes: list[dict[str, Any]], requirements: dict[str, Any]) -> bool:
    return contains_any(
        _all_hole_text(holes, requirements),
        ("counterbore", "c-bore", "cbore", "\u6c89\u5b54", "\u53f0\u9636\u5b54"),
    )


def _has_explicit_countersink_text(holes: list[dict[str, Any]], requirements: dict[str, Any]) -> bool:
    return contains_any(
        _all_hole_text(holes, requirements),
        ("countersink", "c-sink", "csk", "\u6c89\u5934", "\u5012\u89d2", "90\u00b0"),
    )


def _has_explicit_counterbore_signal(holes: list[dict[str, Any]], requirements: dict[str, Any]) -> bool:
    if _has_explicit_counterbore_text(holes, requirements):
        return True
    return any(
        str(hole.get("hole_type") or "") in _COUNTERBORE_TYPES
        and numeric_value(hole.get("counterbore_diameter")) is not None
        and numeric_value(hole.get("counterbore_depth")) is not None
        for hole in holes
    )


def _has_explicit_countersink_signal(holes: list[dict[str, Any]], requirements: dict[str, Any]) -> bool:
    return _has_explicit_countersink_text(holes, requirements)


def _has_only_shallow_counterbore_signal(holes: list[dict[str, Any]]) -> bool:
    counterbore_holes = [
        hole
        for hole in holes
        if str(hole.get("hole_type") or "") in _COUNTERBORE_TYPES
        or numeric_value(hole.get("counterbore_diameter"))
    ]
    if not counterbore_holes:
        return False
    for hole in counterbore_holes:
        depth = numeric_value(hole.get("counterbore_depth"))
        if depth is None:
            return False
        if depth > 0.6:
            return False
    return True


def _has_counterbore_signal(hole: dict[str, Any]) -> bool:
    hole_type = str(hole.get("hole_type") or "")
    if hole_type in _COUNTERBORE_TYPES:
        if _has_implausible_counterbore_geometry(hole):
            return False
        return True
    text = _hole_text(hole)
    if hole_type in {"thread", "thread_candidate"} and not contains_any(
        text, ("counterbore", "c-bore", "cbore", "沉孔", "台阶孔")
    ):
        return False
    if contains_any(text, ("counterbore", "c-bore", "cbore", "沉孔", "台阶孔")):
        return True
    diameter = numeric_value(hole.get("counterbore_diameter"))
    depth = numeric_value(hole.get("counterbore_depth"))
    if diameter is None or depth is None:
        return False
    if diameter <= 0 or depth <= 0:
        return False
    return depth <= max(diameter * 3.0, diameter + 6.0)


def _has_countersink_signal(hole: dict[str, Any]) -> bool:
    hole_type = str(hole.get("hole_type") or "")
    if hole_type in _COUNTERSINK_TYPES:
        return True
    text = _hole_text(hole)
    angle = numeric_value(hole.get("countersink_angle"))
    if contains_any(text, ("countersink", "沉头", "倒角")):
        return angle is None or 45 <= angle <= 120
    return angle is not None and 45 <= angle <= 120


def _has_implausible_counterbore_geometry(hole: dict[str, Any]) -> bool:
    diameter = numeric_value(hole.get("diameter"))
    counterbore_diameter = numeric_value(hole.get("counterbore_diameter"))
    counterbore_depth = numeric_value(hole.get("counterbore_depth"))
    if diameter is None or counterbore_diameter is None or counterbore_depth is None:
        return False
    if counterbore_diameter <= diameter or counterbore_depth <= 0:
        return True
    return counterbore_depth > max(counterbore_diameter * 3.0, diameter * 4.0, 20.0)


def _has_redundant_countersink_signal(holes: list[dict[str, Any]]) -> bool:
    counterbore_holes = [hole for hole in holes if _has_counterbore_signal(hole)]
    countersink_holes = [hole for hole in holes if str(hole.get("hole_type") or "") in _COUNTERSINK_TYPES]
    if not counterbore_holes or not countersink_holes:
        return False
    for sink in countersink_holes:
        sink_diameter = numeric_value(sink.get("diameter"))
        sink_major = numeric_value(sink.get("countersink_diameter"))
        if sink_diameter is None or sink_major is None:
            continue
        for bore in counterbore_holes:
            bore_diameter = numeric_value(bore.get("diameter"))
            bore_major = numeric_value(bore.get("counterbore_diameter"))
            if bore_diameter is None or bore_major is None:
                continue
            if abs(sink_diameter - bore_diameter) <= 0.25 and abs(sink_major - bore_major) <= 0.25:
                return True
    return False



def _external_thread_geometry_diameters(
    holes: list[dict[str, Any]], geometry: dict[str, Any]
) -> set[float]:
    """轴端外圆螺纹的几何判据：螺纹特征直径接近零件最小横截面（≈外圆）即视为外螺纹。

    返回被判为外螺纹的螺纹直径集合（用于把它们从内螺纹/攻牙判定中排除）。仅作保守的
    几何兜底，下游 external_thread_turning 只产复核候选。
    """

    bbox = geometry.get("bounding_box") or {}
    dims = sorted(
        value
        for value in (
            numeric_value(bbox.get("length")),
            numeric_value(bbox.get("width")),
            numeric_value(bbox.get("height")),
            numeric_value(bbox.get("thickness")),
        )
        if value and value > 0
    )
    if len(dims) < 2:
        return set()
    cross_section = dims[0]  # 最小维度 ≈ 轴的外圆直径量级
    if cross_section <= 0:
        return set()
    result: set[float] = set()
    for hole in holes:
        hole_type = str(hole.get("hole_type") or "")
        if not (is_thread_hole(hole) or hole_type in {"thread", "thread_candidate"}):
            continue
        diameter = numeric_value(hole.get("diameter"))
        if diameter and diameter >= 0.6 * cross_section:
            result.add(round(diameter, 2))
    return result


def _add_turning_hole_evidence(
    candidates: list[Candidate],
    holes: list[dict[str, Any]],
    requirements: dict[str, Any],
    geometry: dict[str, Any] | None = None,
    axis_profile: AxisProfile | None = None,
) -> None:
    """Model turning-part holes without confusing external threads with tapping."""

    items = technical_requirement_items(requirements)
    tech_thread_kinds = {classify_thread_text(item.get("raw_text")) for item in items}
    tech_thread_kinds.discard(None)
    has_external_text = "external" in tech_thread_kinds
    has_internal_text = "internal" in tech_thread_kinds
    # 轴端外圆螺纹的几何判据（无"外螺纹"文本时的兜底）。
    external_geom_diameters = _external_thread_geometry_diameters(holes, geometry or {})
    has_external_geom = bool(external_geom_diameters)

    plain_count = 0
    diameters: set[float] = set()
    has_counterbore = False
    has_countersink = False
    internal_geom_thread = False
    has_large_bore = bool(axis_profile and axis_profile.has_large_coaxial_bore)
    for hole in holes:
        hole_type = str(hole.get("hole_type") or "")
        count = int_value(hole.get("count")) or 0
        diameter = numeric_value(hole.get("diameter"))
        if diameter:
            diameters.add(round(diameter, 2))
        if _has_counterbore_signal(hole):
            has_counterbore = True
        if _has_countersink_signal(hole):
            has_countersink = True
        is_thread = is_thread_hole(hole) or hole_type in {"thread", "thread_candidate"}
        if is_thread:
            # 文本判定外螺纹时，所有螺纹特征都视为外螺纹（不产攻牙）；否则按直径是否
            # 接近外圆判断：外圆量级 → 外螺纹，小径/未知 → 内螺纹孔。
            if not has_external_text:
                d = round(diameter, 2) if diameter else None
                if d is None or d not in external_geom_diameters:
                    internal_geom_thread = True
            continue
        plain_count += count

    # 外螺纹：文本或几何任一命中 → 车外螺纹（几何来源仅产复核候选，更保守）。
    if has_external_text:
        candidates.append(
            Candidate(
                op_code="external_thread_turning",
                strength=TECH_REQUIRED,
                rule_code="EXTERNAL_THREAD_TURNING",
                message="External thread text detected; add external thread turning.",
                source=source_ref("system", rule_code="EXTERNAL_THREAD_TURNING"),
                confidence=0.68,
            )
        )
    elif has_external_geom:
        candidates.append(
            Candidate(
                op_code="external_thread_turning",
                strength=GEOMETRY,
                rule_code="EXTERNAL_THREAD_TURNING_GEOMETRY",
                message="Thread feature on outer diameter detected; likely external thread turning.",
                source=source_ref("step", rule_code="EXTERNAL_THREAD_TURNING_GEOMETRY"),
                confidence=0.5,
                requires_review=True,
                review_reason="Confirm this is an external thread (turned), not an internal tapped hole.",
            )
        )

    multi_diameter = len(diameters) >= 2
    real_hole_signal = (
        plain_count >= 3 or multi_diameter or has_internal_text or internal_geom_thread or has_large_bore
    )
    if not real_hole_signal:
        return

    candidates.append(
        Candidate(
            op_code="drilling",
            strength=GEOMETRY,
            rule_code="TURNING_HOLE_DRILLING",
            message="Real hole evidence detected on turning part; add drilling.",
            source=source_ref("step", rule_code="TURNING_HOLE_DRILLING"),
            confidence=0.7,
        )
    )

    # 攻牙只针对真实内螺纹孔（小径或内螺纹文本），且无外螺纹文本覆盖；外圆螺纹绝不映射 tapping。
    if (has_internal_text or internal_geom_thread) and not has_external_text:
        candidates.append(
            Candidate(
                op_code="tapping",
                strength=TECH_REQUIRED,
                rule_code="TURNING_INTERNAL_TAPPING",
                message="Internal thread hole evidence detected; add tapping.",
                source=source_ref("system", rule_code="TURNING_INTERNAL_TAPPING"),
                confidence=0.68,
            )
        )
    if has_counterbore:
        candidates.append(
            Candidate(
                op_code="counterbore",
                strength=GEOMETRY,
                rule_code="TURNING_COUNTERBORE",
                message="Counterbore feature detected on turning part; add counterbore.",
                source=source_ref("step", rule_code="TURNING_COUNTERBORE"),
                confidence=0.66,
            )
        )
    if has_countersink:
        candidates.append(
            Candidate(
                op_code="countersink",
                strength=GEOMETRY,
                rule_code="TURNING_COUNTERSINK",
                message="Countersink feature detected on turning part; add countersink.",
                source=source_ref("step", rule_code="TURNING_COUNTERSINK"),
                confidence=0.64,
                requires_review=True,
                review_reason="Confirm this is not only an end-face chamfer signal.",
            )
        )
    if has_large_bore:
        candidates.append(
            Candidate(
                op_code="boring",
                strength=GEOMETRY,
                rule_code="TURNING_LARGE_COAXIAL_BORE",
                message="Large deep coaxial bore detected on turning part; add boring.",
                source=source_ref("step", rule_code="TURNING_LARGE_COAXIAL_BORE"),
                confidence=0.62,
                requires_review=True,
                review_reason="Confirm large bore diameter, depth, tolerance, and machining method.",
            )
        )

def _add_shaft_milling_evidence(
    candidates: list[Candidate],
    parsed: ParsedPart,
    tech_text: str,
    holes: list[dict[str, Any]],
    family_hint: str | None = None,
    axis_profile: AxisProfile | None = None,
) -> None:
    if family_hint != TURNING:
        return

    features = parsed.features
    complexity = features.get("complexity") or {}
    geometry = parsed.geometry
    hole_text = _all_hole_text(holes, parsed.requirements)
    combined_text = normalize_text(f"{tech_text} {hole_text}")

    has_flat = contains_any(combined_text, FLAT_KEYWORDS) or bool(features.get("flat_count"))
    has_keyway = contains_any(combined_text, KEYWAY_KEYWORDS) or bool(features.get("keyway_count"))
    has_obround = (
        contains_any(combined_text, OBROUND_SLOT_KEYWORDS)
        or _has_obround_hole_signal(holes, parsed.requirements)
        or (int_value(complexity.get("slot_count")) or 0) > 0
    )
    # 横孔/径向孔证据：文本关键字 或 侧孔几何（真实证据，非 part_type 噪声）。
    has_cross = contains_any(combined_text, CROSS_HOLE_KEYWORDS) or any(
        is_side_hole(hole) for hole in holes
    )
    complex_shaft_surface = _is_complex_shaft_surface(parsed, complexity)
    if axis_profile and axis_profile.subtype == AXIS_SHORT_RING:
        complex_shaft_surface = False

    # STEP 噪声类 complex_surface_candidate 且无任何真实铣削/横孔证据 → 仅产复核，不入路线。
    if (
        (parsed.geometry_part_type or "") == "complex_surface_candidate"
        and not (has_flat or has_obround or has_keyway or has_cross or complex_shaft_surface)
    ):
        candidates.append(
            Candidate(
                op_code="shaft_milling",
                strength=GEOMETRY,
                rule_code="SHAFT_SURFACE_REVIEW",
                message="STEP identified a complex rotational surface but no concrete milling feature; review only.",
                source=source_ref("step", rule_code="SHAFT_SURFACE_REVIEW"),
                confidence=0.3,
                requires_review=True,
                review_reason="Confirm whether real flats/keyway/cross holes exist before adding milling.",
                review_code="SHAFT_SURFACE_REVIEW",
                review_only=True,
            )
        )

    if has_keyway:
        candidates.append(
            Candidate(
                op_code="keyway_milling",
                strength=TECH_CONDITIONAL,
                rule_code="SHAFT_KEYWAY_MILLING",
                message="Keyway evidence detected on shaft; add keyway milling candidate.",
                source=source_ref("system", rule_code="SHAFT_KEYWAY_MILLING"),
                confidence=0.6,
                requires_review=True,
                review_reason="Confirm keyway size, location, and fixture requirement.",
            )
        )
    if has_flat or has_obround or complex_shaft_surface:
        candidates.append(
            Candidate(
                op_code="shaft_milling",
                strength=TECH_CONDITIONAL,
                rule_code="SHAFT_MILLING_AUXILIARY",
                message="Flat, obround slot, or complex non-turned surface detected; add shaft milling candidate.",
                source=source_ref("system", rule_code="SHAFT_MILLING_AUXILIARY"),
                confidence=0.58,
                requires_review=True,
                review_reason="Confirm feature count, location, and fixture method.",
            )
        )
    if has_cross:
        candidates.append(
            Candidate(
                op_code="cross_drilling",
                strength=TECH_CONDITIONAL,
                rule_code="SHAFT_CROSS_DRILLING",
                message="Radial or cross-hole evidence detected on shaft; add cross drilling candidate.",
                source=source_ref("system", rule_code="SHAFT_CROSS_DRILLING"),
                confidence=0.55,
                requires_review=True,
                review_reason="Confirm cross-hole position, diameter, and fixture method.",
            )
        )


def _is_complex_shaft_surface(parsed: ParsedPart, complexity: dict[str, Any]) -> bool:
    part_type = parsed.geometry_part_type or ""
    score = numeric_value(complexity.get("complexity_score")) or 0.0
    bbox = parsed.geometry.get("bounding_box") or {}
    dims = sorted(
        value
        for value in (
            numeric_value(bbox.get("length")),
            numeric_value(bbox.get("width")),
            numeric_value(bbox.get("height")),
            numeric_value(bbox.get("thickness")),
        )
        if value and value > 0
    )
    if len(dims) < 3:
        return False
    shaft_like = dims[-1] / max(dims[1], 1.0) >= 3.0 and dims[1] / max(dims[0], 1.0) <= 1.5
    if (parsed.geometry_part_type or "") not in {"complex_surface_candidate", "shaft", "shaft_candidate", "long_bar"}:
        return False
    face_count = numeric_value(complexity.get("face_count")) or 0.0
    edge_count = numeric_value(complexity.get("edge_count")) or 0.0
    hole_count = numeric_value(complexity.get("hole_count")) or 0.0
    # 仅高复杂度分数视为真实复杂回转面证据；STEP 噪声类 complex_surface_candidate
    # 不再单独触发 shaft_milling（改由 _add_shaft_milling_evidence 产复核）。
    medium_complex_axis = score >= 50 and face_count >= 50 and edge_count >= 100 and hole_count >= 1
    high_complex_axis = score >= 70 and face_count >= 50 and edge_count >= 100 and hole_count >= 1
    return shaft_like and (high_complex_axis or medium_complex_axis)


def _add_bending_evidence(
    candidates: list[Candidate],
    parsed: ParsedPart,
    tech_text: str,
    family_hint: str | None = None,
) -> None:
    """Add bending evidence only when sheet-metal forming evidence is present."""

    if family_hint != SHEET_METAL:
        return

    # Text evidence: technical notes or drawing text mention bending.
    if contains_any(tech_text, BENDING_KEYWORDS):
        candidates.append(
            Candidate(
                op_code="bending",
                strength=TECH_REQUIRED,
                rule_code="BENDING_TEXT",
                message="Bending or forming text detected; add bending operation.",
                source=source_ref("system", rule_code="BENDING_TEXT"),
                confidence=0.72,
            )
        )
        return

    # Geometry evidence: formed/envelope candidates are not treated as flat sheet.
    part_type = parsed.geometry_part_type or ""
    formed = (
        part_type in FORMED_SHEET_PART_TYPES
        or _is_formed_envelope(parsed.geometry)
        or _has_sheet_form_name_geometry(parsed)
    )
    if formed:
        candidates.append(
            Candidate(
                op_code="bending",
                strength=GEOMETRY,
                rule_code="BENDING_GEOMETRY",
                message="STEP geometry indicates a formed sheet candidate; add bending operation.",
                source=source_ref("step", rule_code="BENDING_GEOMETRY"),
                confidence=0.68,
                requires_review=True,
                review_reason="Confirm bend count, bend angle, and forming order.",
            )
        )


def _is_formed_envelope(geometry: dict[str, Any]) -> bool:
    """Detect formed sheet envelopes using 3D bounding dimensions."""

    bbox = geometry.get("bounding_box") or {}
    thickness = numeric_value(bbox.get("thickness"))
    length = numeric_value(bbox.get("length")) or 0.0
    width = numeric_value(bbox.get("width")) or 0.0
    height = numeric_value(bbox.get("height")) or 0.0
    if thickness is not None and thickness > 0:
        dims = sorted([value for value in (length, width) if value and value > 0] + [thickness])
    else:
        dims = sorted(value for value in (length, width, height) if value and value > 0)
    if len(dims) < 3:
        return False
    return dims[0] >= FLAT_SHEET_MAX_THICKNESS_MM


def _has_sheet_form_name_geometry(parsed: ParsedPart) -> bool:
    """Use part name plus envelope as supplemental sheet-form evidence."""

    part_name = str(((parsed.part_feature.get("part") or {}).get("part_name")) or "")
    has_strong_name = any(keyword in part_name for keyword in SHEET_FORM_NAME_KEYWORDS)
    has_weak_name = any(keyword in part_name for keyword in SHEET_FORM_WEAK_NAME_KEYWORDS)
    if not (has_strong_name or has_weak_name):
        return False
    bbox = parsed.geometry.get("bounding_box") or {}
    dims = sorted(
        value
        for value in (
            numeric_value(bbox.get("length")),
            numeric_value(bbox.get("width")),
            numeric_value(bbox.get("height")),
            numeric_value(bbox.get("thickness")),
        )
        if value and value > 0
    )
    if len(dims) < 3:
        return False
    thickness = numeric_value(bbox.get("thickness"))
    if thickness is not None and thickness > 0:
        dims_without_thickness = sorted(
            value
            for value in (
                numeric_value(bbox.get("length")),
                numeric_value(bbox.get("width")),
                numeric_value(bbox.get("height")),
            )
            if value and value > 0 and abs(value - thickness) > 0.25
        )
        envelope_height = dims_without_thickness[0] if dims_without_thickness else 0.0
        if has_weak_name and not has_strong_name:
            return envelope_height >= max(thickness * 6.0, 20.0)
        return envelope_height >= max(thickness * 4.0, 15.0)

    # Small L/Z brackets often look like a thin dimension plus two comparable
    # envelope dimensions; treating this as formed evidence is safer than
    # losing bending on sheet-metal supports.
    if has_strong_name and dims[0] <= 8 and dims[1] >= 15 and dims[-1] / max(dims[1], 1.0) <= 3.0:
        return True
    return dims[0] >= 20 and dims[-1] / max(dims[0], 1.0) <= 8


def _add_welding_evidence(
    candidates: list[Candidate],
    geometry: dict[str, Any],
    parsed: ParsedPart,
    requirements: dict[str, Any],
    family_hint: str | None = None,
) -> None:
    # Welding is sheet-metal-only evidence.
    if family_hint != SHEET_METAL:
        return

    fusion = str(geometry.get("fusion_type") or "")
    part_type = parsed.geometry_part_type or ""
    assembly_signal = "assembly" in fusion or part_type == "assembly_candidate"
    if assembly_signal:
        _add_sheet_metal_welding_chain(
            candidates,
            source=source_ref("step", rule_code="WELDING_ASSEMBLY_GEOMETRY"),
            rule_prefix="WELDING_ASSEMBLY",
            confidence=0.66,
        )
        candidates.append(
            Candidate(
                op_code="sheet_metal_welding",
                strength=GEOMETRY,
                rule_code="WELDING_ASSEMBLY_GEOMETRY",
                message="STEP geometry indicates assembly or welding candidate; add sheet-metal welding.",
                source=source_ref("step", rule_code="WELDING_ASSEMBLY_GEOMETRY"),
                confidence=0.72,
                requires_review=True,
                review_reason="Confirm weld location, weld form, and post-weld finishing.",
            )
        )

    # PDF text extraction may split a conditional welding note across lines.
    pending_conditional = False
    for item in technical_requirement_items(requirements):
        raw = item.get("raw_text")
        if not contains_any(str(raw or ""), WELDING_KEYWORDS):
            pending_conditional = _classify_sentence(raw) == "conditional"
            continue
        kind = _classify_sentence(raw)
        # 条件句优先：模板"对于尺寸较大的钣金件…进行焊接加固…焊后打磨"恒为条件句，
        # 不得因含"进行/焊后打磨"被提级为必焊（否则单片钣金件被误加焊接）。
        if pending_conditional and kind == "required":
            kind = "conditional"
        # _has_explicit_welding_action 只能把被误判为 instructional 的真实焊接句抢救成
        # required，绝不覆盖 conditional。
        if kind == "instructional" and _has_explicit_welding_action(raw):
            kind = "required"
        pending_conditional = False
        if kind == "instructional":
            continue
        if kind == "conditional":
            candidates.append(
                Candidate(
                    op_code="sheet_metal_welding",
                    strength=TECH_CONDITIONAL,
                    rule_code=WELDING_CONDITIONAL_TEXT,
                    message="Welding appears in a conditional note; keep as review-only evidence.",
                    source=source_ref(
                        "system",
                        rule_code=WELDING_CONDITIONAL_TEXT,
                        raw_text=str(raw or ""),
                    ),
                    confidence=0.35,
                    requires_review=True,
                    review_reason="Confirm whether the condition applies to this part.",
                    review_code=WELDING_CONDITIONAL_TEXT,
                    review_only=True,
                )
            )
            continue
        candidates.append(
            Candidate(
                op_code="sheet_metal_welding",
                strength=TECH_REQUIRED,
                rule_code="WELDING_REQUIRED_TEXT",
                message="Technical requirements explicitly mention welding; add welding operation.",
                source=source_ref("system", rule_code="WELDING_REQUIRED_TEXT", raw_text=str(raw or "")),
                confidence=0.65,
                requires_review=True,
                review_reason="Confirm weld location, method, and post-weld handling.",
            )
        )
        _add_sheet_metal_welding_chain(
            candidates,
            source=source_ref("system", rule_code="WELDING_REQUIRED_TEXT", raw_text=str(raw or "")),
            rule_prefix="WELDING_TEXT",
            confidence=0.6,
        )


def _has_explicit_welding_action(raw: Any) -> bool:
    text = normalize_text(raw)
    return contains_any(text, ("进行", "必须", "要求", "应", "焊后打磨", "焊后处理", "焊后磨平"))


def _add_sheet_metal_welding_chain(
    candidates: list[Candidate],
    *,
    source: dict[str, Any],
    rule_prefix: str,
    confidence: float,
) -> None:
    for op_code, message in (
        ("welding_prepare", "Sheet-metal weldment needs weld preparation."),
        ("fit_up", "Sheet-metal weldment needs fit-up and tack positioning."),
        ("weld_grinding", "Sheet-metal weldment needs post-weld grinding or cleanup."),
        ("weld_inspection", "Sheet-metal weldment needs weld inspection."),
    ):
        candidates.append(
            Candidate(
                op_code=op_code,
                strength=GEOMETRY,
                rule_code=f"{rule_prefix}_{op_code.upper()}",
                message=message,
                source=source,
                confidence=confidence,
                requires_review=op_code != "weld_inspection",
                review_reason="Confirm weld locations, fixture method, and post-weld finishing.",
            )
        )


def _add_profile_geometry_evidence(
    candidates: list[Candidate],
    geometry: dict[str, Any],
    features: dict[str, Any],
    complexity: dict[str, Any],
    tech_text: str,
    family_hint: str | None = None,
) -> None:
    slot_signal = (int_value(complexity.get("slot_count")) or 0) > 0 or bool(features.get("slots"))
    pocket_signal = _has_pocket_geometry(features, complexity, tech_text)
    wire_signal = _has_strong_wire_signal(geometry, complexity, tech_text)
    edm_signal = _has_strong_edm_signal(complexity, tech_text)

    if slot_signal:
        weak_machining_slot = family_hint == MACHINING and not contains_any(
            tech_text, ("槽", "长圆", "腰型", "slot", "obround", "oblong")
        ) and not features.get("slots")
        if weak_machining_slot:
            candidates.append(
                Candidate(
                    op_code="slot_milling",
                    strength=GEOMETRY,
                    rule_code="SLOT_MILLING_WEAK_GEOMETRY",
                    message="STEP complexity suggests slot geometry, but explicit slot features or drawing text were not found.",
                    source=source_ref("step", rule_code="SLOT_MILLING_WEAK_GEOMETRY"),
                    confidence=0.38,
                    requires_review=True,
                    review_reason="Confirm whether slot milling is required before adding it to the formal route.",
                    review_code="WEAK_MACHINING_SLOT_REVIEW",
                    review_only=True,
                )
            )
        else:
            candidates.append(
                Candidate(
                    op_code="slot_milling",
                    strength=GEOMETRY,
                    rule_code="SLOT_MILLING",
                    message="Slot geometry detected; add slot milling candidate.",
                    source=source_ref("step", rule_code="SLOT_MILLING"),
                    confidence=0.6,
                )
            )
    if pocket_signal:
        candidates.append(
            Candidate(
                op_code="pocket_milling",
                strength=GEOMETRY if not contains_any(tech_text, ("鍨嬭厰", "鍑硅厰", "pocket")) else TECH_REQUIRED,
                rule_code="POCKET_MILLING",
                message="Pocket geometry or text detected; add pocket milling candidate.",
                source=source_ref("step", rule_code="POCKET_MILLING"),
                confidence=0.55,
            )
        )
    if wire_signal:
        candidates.append(
            Candidate(
                op_code="wire_cut_profile",
                strength=GEOMETRY,
                rule_code="WIRE_CUT_PROFILE",
                message="Wire-cut profile evidence detected; add wire-cut candidate.",
                source=source_ref("step", rule_code="WIRE_CUT_PROFILE"),
                confidence=0.6,
            )
        )
    if edm_signal:
        candidates.append(
            Candidate(
                op_code="edm",
                strength=GEOMETRY if not contains_any(tech_text, EDM_KEYWORDS) else TECH_REQUIRED,
                rule_code="EDM",
                message="Strong EDM evidence detected; add EDM candidate.",
                source=source_ref("step", rule_code="EDM"),
                confidence=0.5,
            )
        )


def _has_pocket_geometry(features: dict[str, Any], complexity: dict[str, Any], tech_text: str) -> bool:
    if contains_any(tech_text, ("鍨嬭厰", "鍑硅厰", "鎸栨Ы", "pocket")):
        return True
    if features.get("pockets"):
        return True
    return (int_value(complexity.get("pocket_count")) or 0) > 0


def _has_strong_wire_signal(
    geometry: dict[str, Any], complexity: dict[str, Any], tech_text: str
) -> bool:
    if contains_any(tech_text, WIRE_CUT_KEYWORDS):
        return True
    profile = geometry.get("profile_summary") or {}
    # Ordinary slots/arcs should not trigger wire cutting without an explicit candidate.
    return (int_value(profile.get("wire_cut_candidate_count")) or 0) > 0


def _has_strong_edm_signal(complexity: dict[str, Any], tech_text: str) -> bool:
    if contains_any(tech_text, EDM_KEYWORDS):
        return True
    return (int_value(complexity.get("deep_pocket_count")) or 0) > 0


def _add_machining_geometry_evidence(
    candidates: list[Candidate],
    parsed: ParsedPart,
    complexity: dict[str, Any],
    family_hint: str | None = None,
) -> None:
    """Add milling candidates for complex geometry; policy matrix decides eligibility."""

    # 大板族用 large_plate_roughing/finishing 作主线，通用 CNC 候选从源头不生成，
    # 避免"被触发→被 DENY→报 FORBIDDEN_OP_TRIGGERED_REVIEW"的中间态。
    if family_hint == LARGE_PLATE:
        return

    score = numeric_value(complexity.get("complexity_score"))
    high_complexity = score is not None and score >= 60
    part_type = parsed.geometry_part_type or ""
    cnc_like = high_complexity or part_type in {
        "plate",
        "block",
        "complex_block",
        "precision_block",
        "complex",
        "small_irregular",
    }
    if cnc_like:
        for op, rule in (("cnc_rough_milling", "CNC_ROUGH"), ("cnc_finish_milling", "CNC_FINISH")):
            candidates.append(
                Candidate(
                    op_code=op,
                    strength=GEOMETRY,
                    rule_code=rule,
                    message="Geometry suggests milling; policy matrix decides whether it applies.",
                    source=source_ref("step", rule_code=rule),
                    confidence=0.55,
                )
            )


def _add_finishing_evidence(
    candidates: list[Candidate],
    parsed: ParsedPart,
    tech_text: str,
    material_normalized: str,
    holes: list[dict[str, Any]],
    family_hint: str | None = None,
    axis_profile: AxisProfile | None = None,
) -> None:
    bbox = parsed.geometry.get("bounding_box") or {}
    thickness = numeric_value(bbox.get("thickness")) or numeric_value(bbox.get("height")) or 0.0
    length = numeric_value(bbox.get("length")) or 0.0
    width = numeric_value(bbox.get("width")) or 0.0
    dims = sorted(value for value in (length, width, thickness) if value > 0)
    shortest = dims[0] if dims else 0.0
    longest = dims[-1] if dims else 0.0
    aspect = (longest / shortest) if shortest > 0 else 0.0
    is_long_strip = aspect >= 4.0 and longest >= 200.0
    is_long_plate = family_hint == LARGE_PLATE and is_long_strip
    # 大板按材料分层：铝长板不去应力（改校平/防变形复核），钢长板仍去应力。
    is_aluminum = contains_any(
        material_normalized, ("6061", "6063", "7075", "5052", "aluminum", "aluminium")
    )
    is_long_plate_steel = is_long_plate and not is_aluminum
    is_long_plate_aluminum = is_long_plate and is_aluminum
    surface = parsed.requirements.get("surface_treatment") or {}
    surface_text = normalize_text(
        " ".join(str(surface.get(key) or "") for key in ("raw_text", "standard_code"))
    )
    hard_chrome_surface = contains_any(surface_text, ("闀€纭摤", "纭摤", "hard_chrome", "hard chrome"))
    explicit_surface_grinding = contains_any(
        tech_text,
        ("surface grinding", "grinding", "flatness") + ROUGHNESS_KEYWORDS + FLATNESS_KEYWORDS,
    )
    steel_hard_chrome_large_plate = (
        family_hint == LARGE_PLATE
        and longest >= 800
        and hard_chrome_surface
        and contains_any(material_normalized, ("45", "40cr", "cr12", "skd"))
    )
    needs_surface_grinding = explicit_surface_grinding or steel_hard_chrome_large_plate
    if needs_surface_grinding:
        candidates.append(
            Candidate(
                op_code="surface_grinding_rough",
                strength=GEOMETRY,
                rule_code="SURFACE_GRINDING",
                message="Surface grinding or flatness evidence detected; add grinding candidate.",
                source=source_ref("system", rule_code="SURFACE_GRINDING"),
                confidence=0.55,
            )
        )
    turning_finish_precision = (
        needs_surface_grinding
        or hard_chrome_surface
        or bool((parsed.requirements.get("heat_treatment") or {}).get("required"))
        or any(is_precision_hole(hole) for hole in holes)
    )
    if family_hint == TURNING and turning_finish_precision:
        if axis_profile and axis_profile.subtype == AXIS_SHORT_RING and not _axis_has_outer_grinding_evidence(
            tech_text, holes, hard_chrome_surface
        ):
            candidates.append(
                Candidate(
                    op_code="finish_grinding",
                    strength=GEOMETRY,
                    rule_code="AXIS_SHORT_RING_FINISH_GRINDING",
                    message="Short ring or washer turning part needs face/thickness finish grinding instead of default cylindrical grinding.",
                    source=source_ref("system", rule_code="AXIS_SHORT_RING_FINISH_GRINDING"),
                    confidence=0.56,
                    requires_review=True,
                    review_reason="Confirm whether face/thickness grinding or cylindrical grinding is required.",
                )
            )
        else:
            candidates.append(
                Candidate(
                    op_code="cylindrical_grinding",
                    strength=GEOMETRY,
                    rule_code="CYLINDRICAL_GRINDING",
                    message="Turning precision evidence detected; add cylindrical grinding candidate.",
                    source=source_ref("system", rule_code="CYLINDRICAL_GRINDING"),
                    confidence=0.5,
                )
            )
    elif family_hint == TURNING and axis_profile and axis_profile.subtype == AXIS_SHORT_RING and explicit_surface_grinding:
        candidates.append(
            Candidate(
                op_code="finish_grinding",
                strength=GEOMETRY,
                rule_code="AXIS_SHORT_RING_EXPLICIT_GRINDING",
                message="Short ring or washer has grinding evidence; add finish grinding candidate.",
                source=source_ref("system", rule_code="AXIS_SHORT_RING_EXPLICIT_GRINDING"),
                confidence=0.56,
                requires_review=True,
                review_reason="Confirm grinding face count and tolerance.",
            )
        )

    tool_steel_risk = contains_any(material_normalized, TOOL_STEEL_KEYWORDS)
    material_thermal_risk = match_material_code(
        material_normalized, THERMAL_DISTORTION_MATERIALS
    )
    has_heat = bool((parsed.requirements.get("heat_treatment") or {}).get("required")) or contains_any(
        tech_text, HEAT_TREATMENT_KEYWORDS
    )

    if family_hint == TURNING:
        explicit_stress_relief = contains_any(tech_text, ("去应力", "时效", "stress relief", "stress-relief"))
        heat = parsed.requirements.get("heat_treatment") or {}
        heat_text = normalize_text(f"{heat.get('raw_text') or ''} {tech_text}")
        hardening_heat = contains_any(heat_text, ("淬火", "hrc", "quench", "hardening"))
        high_deformation_axis = (
            bool(axis_profile)
            and axis_profile.subtype == AXIS_SLENDER_OR_ROLLER
            and (axis_profile.slenderness or 0.0) >= 15.0
            and has_heat
            and hardening_heat
        )
        trigger_stress = explicit_stress_relief or tool_steel_risk or high_deformation_axis
    else:
        trigger_stress = (
            contains_any(tech_text, STRAIGHTENING_KEYWORDS)
            or tool_steel_risk
            or (material_thermal_risk and has_heat)
            or is_long_plate_steel  # 仅钢长板因几何触发去应力；铝长板不去应力。
        )
    if trigger_stress:
        candidates.append(
            Candidate(
                op_code="stress_relief",
                strength=TECH_CONDITIONAL,
                rule_code="STRESS_RELIEF",
                message="Material, geometry, or heat-treatment risk suggests stress relief.",
                source=source_ref("system", rule_code="STRESS_RELIEF"),
                confidence=0.55,
                requires_review=True,
                review_reason="Confirm whether stress relief is required.",
            )
        )

    if is_long_plate:
        candidates.append(
            Candidate(
                op_code="straightening",
                strength=TECH_CONDITIONAL,
                rule_code="STRAIGHTENING",
                message="Long large-plate geometry may deform; add straightening candidate.",
                source=source_ref("system", rule_code="STRAIGHTENING"),
                confidence=0.5,
                requires_review=True,
                review_reason="Confirm whether straightening is required.",
            )
        )

    # 铝长板：用防变形支撑替代去应力（铝不做去应力热处理），并标复核。
    if is_long_plate_aluminum:
        candidates.append(
            Candidate(
                op_code="support_anti_deformation",
                strength=TECH_CONDITIONAL,
                rule_code="ALUMINUM_LONG_PLATE_SUPPORT",
                message="Aluminum long plate is deformation-prone; add anti-deformation support instead of stress relief.",
                source=source_ref("system", rule_code="ALUMINUM_LONG_PLATE_SUPPORT"),
                confidence=0.5,
                requires_review=True,
                review_reason="Confirm anti-deformation fixturing for the aluminum long plate.",
            )
        )


def _add_long_strip_boundary_review(
    candidates: list[Candidate],
    parsed: ParsedPart,
    material_normalized: str,
    family_hint: str | None = None,
) -> None:
    if family_hint != LARGE_PLATE:
        return
    if not contains_any(material_normalized, ("6061", "6063", "7075", "aluminum", "aluminium")):
        return
    bbox = parsed.geometry.get("bounding_box") or {}
    dims = sorted(
        value
        for value in (
            numeric_value(bbox.get("length")),
            numeric_value(bbox.get("width")),
            numeric_value(bbox.get("height")),
            numeric_value(bbox.get("thickness")),
        )
        if value and value > 0
    )
    if len(dims) < 3:
        return
    is_narrow_strip = dims[-1] >= 4 * dims[1] and dims[1] <= 60 and dims[0] <= 20
    if not is_narrow_strip:
        return
    candidates.append(
        Candidate(
            op_code="long_strip_boundary_review",
            strength=TECH_CONDITIONAL,
            rule_code=LONG_STRIP_BOUNDARY_REVIEW,
            message="Narrow aluminum strip was classified as large plate; review route boundary.",
            source=source_ref("system", rule_code=LONG_STRIP_BOUNDARY_REVIEW),
            confidence=0.5,
            requires_review=True,
            review_reason="Confirm whether the part should follow long-strip machining instead of large-plate routing.",
            review_code=LONG_STRIP_BOUNDARY_REVIEW,
            review_only=True,
        )
    )


def _add_detailing_evidence(
    candidates: list[Candidate],
    parsed: ParsedPart,
    tech_text: str,
    material_normalized: str,
    holes: list[dict[str, Any]],
    family_hint: str | None = None,
    axis_profile: AxisProfile | None = None,
) -> None:
    surface_ops = _strong_surface_ops(parsed, family_hint)
    has_precision = any(is_precision_hole(hole) for hole in holes)
    # 受阳极膜厚影响的"配合精孔"（H7/配合孔/铰孔），用于收紧表处后铰孔触发。
    has_fit_precision = any(_is_fit_precision_hole(hole) for hole in holes)
    has_thread = any(is_thread_hole(hole) for hole in holes)
    heat = parsed.requirements.get("heat_treatment") or {}
    heat_text = normalize_text(f"{heat.get('raw_text') or ''} {tech_text}")

    _add_surface_chain_detailing(
        candidates,
        parsed,
        surface_ops=surface_ops,
        has_precision=has_precision,
        has_fit_precision=has_fit_precision,
        has_thread=has_thread,
        family_hint=family_hint,
        axis_profile=axis_profile,
    )
    _add_precision_hole_detailing(candidates, holes, has_precision=has_precision)
    _add_machining_detailing(
        candidates,
        parsed,
        holes,
        family_hint=family_hint,
        has_precision=has_precision,
        has_thread=has_thread,
    )
    _add_heat_detailing(candidates, heat, heat_text)
    _add_shaft_straightness_detailing(
        candidates,
        parsed,
        tech_text,
        family_hint=family_hint,
        axis_profile=axis_profile,
    )


def _strong_surface_ops(parsed: ParsedPart, family_hint: str | None) -> set[str]:
    surface = parsed.requirements.get("surface_treatment") or {}
    if not surface.get("required"):
        return set()
    return set(surface_treatment_operation_codes(surface, material=parsed.material, family=family_hint))


def _add_surface_chain_detailing(
    candidates: list[Candidate],
    parsed: ParsedPart,
    *,
    surface_ops: set[str],
    has_precision: bool,
    has_fit_precision: bool,
    has_thread: bool,
    family_hint: str | None,
    axis_profile: AxisProfile | None,
) -> None:
    if not surface_ops:
        return
    surface = parsed.requirements.get("surface_treatment") or {}
    source = surface.get("source") or source_ref("system", rule_code="DETAIL_SURFACE_CHAIN")

    if surface_ops & {"hard_chrome", "chemical_nickel", "clear_anodizing", "hard_anodizing", "color_anodizing"}:
        _append_detail_candidate(
            candidates,
            "pre_plating_cleaning",
            "DETAIL_PRE_PLATING_CLEANING",
            source,
            review=False,
        )

    if "hard_chrome" in surface_ops:
        if _axis_hard_chrome_needs_masking(parsed, has_precision, has_thread, axis_profile):
            _append_detail_candidate(candidates, "hard_chrome_masking", "DETAIL_HARD_CHROME_MASKING", source)
        elif family_hint == TURNING:
            candidates.append(
                Candidate(
                    op_code="hard_chrome_masking",
                    strength=TECH_CONDITIONAL,
                    rule_code="DETAIL_HARD_CHROME_MASKING_REVIEW",
                    message="Hard chrome masking may be needed, but local plating evidence is not explicit.",
                    source=source,
                    confidence=0.45,
                    requires_review=True,
                    review_reason="Confirm whether any non-plated surfaces, threads, or fitting holes require masking.",
                    review_code="HARD_CHROME_MASKING_REVIEW",
                    review_only=True,
                )
            )
        _append_detail_candidate(candidates, "dehydrogenation_bake", "DETAIL_HARD_CHROME_DEHYDROGENATION", source)
        _append_detail_candidate(candidates, "post_chrome_inspection", "DETAIL_HARD_CHROME_INSPECTION", source, review=False)
        if family_hint == TURNING or has_precision:
            _append_detail_candidate(candidates, "post_chrome_polishing", "DETAIL_HARD_CHROME_POLISHING", source)

    if surface_ops & {"clear_anodizing", "hard_anodizing", "color_anodizing"}:
        _append_detail_candidate(candidates, "anodize_masking", "DETAIL_ANODIZE_MASKING", source)
        # 仅"会因阳极膜厚改变配合的精孔"(H7/配合孔)才后铰；普通公差不触发。
        if has_fit_precision:
            _append_detail_candidate(candidates, "post_anodize_reaming", "DETAIL_POST_ANODIZE_REAMING", source)

    if has_precision and surface_ops & {
        "hard_chrome",
        "chemical_nickel",
        "clear_anodizing",
        "hard_anodizing",
        "color_anodizing",
    }:
        _append_detail_candidate(candidates, "post_surface_precision_hole_check", "DETAIL_POST_SURFACE_HOLE_CHECK", source)

    if has_thread and surface_ops:
        _append_detail_candidate(candidates, "thread_chasing", "DETAIL_POST_SURFACE_THREAD_CHASING", source)

    _append_detail_candidate(candidates, "coating_thickness_inspection", "DETAIL_COATING_THICKNESS_INSPECTION", source)
    _append_detail_candidate(candidates, "surface_inspection", "DETAIL_SURFACE_INSPECTION", source, review=False)


def _add_precision_hole_detailing(
    candidates: list[Candidate],
    holes: list[dict[str, Any]],
    *,
    has_precision: bool,
) -> None:
    if not has_precision:
        return
    source = source_ref("step", rule_code="DETAIL_PRECISION_HOLE")
    prefers_reaming = any(_precision_hole_prefers_reaming(hole) for hole in holes)
    _append_detail_candidate(
        candidates,
        "reaming" if prefers_reaming else "precision_hole",
        "DETAIL_PRECISION_HOLE",
        source,
    )
    _append_detail_candidate(
        candidates,
        "precision_hole_inspection",
        "DETAIL_PRECISION_HOLE_INSPECTION",
        source,
        review=False,
    )


def _add_machining_detailing(
    candidates: list[Candidate],
    parsed: ParsedPart,
    holes: list[dict[str, Any]],
    *,
    family_hint: str | None,
    has_precision: bool,
    has_thread: bool,
) -> None:
    """Expand machining-family facts into explicit shop-floor operations.

    The generic MACHINING skeleton deliberately stays compact.  This function is
    the family-local expansion layer for square/block/plate machining so the
    other families keep their existing route behavior.
    """

    if family_hint != MACHINING:
        return

    hole_profile = _machining_hole_profile(holes)
    source = source_ref("system", rule_code="DETAIL_MACHINING_PROFILE")

    if hole_profile["has_through"]:
        _append_detail_candidate(candidates, "drilling_through", "DETAIL_MACHINING_THROUGH_HOLE", source)
    if hole_profile["has_blind"]:
        _append_detail_candidate(candidates, "drilling_blind", "DETAIL_MACHINING_BLIND_HOLE", source)
    if hole_profile["has_thread_through"]:
        _append_detail_candidate(candidates, "tapping_through", "DETAIL_MACHINING_THROUGH_TAPPING", source)
    if hole_profile["has_thread_blind"]:
        _append_detail_candidate(candidates, "blind_tapping", "DETAIL_MACHINING_BLIND_TAPPING", source)

    if has_precision and not any(candidate.op_code == "precision_hole" for candidate in candidates):
        _append_detail_candidate(candidates, "precision_hole", "DETAIL_MACHINING_PRECISION_HOLE", source)

    if _machining_needs_profile_milling(parsed):
        _append_detail_candidate(candidates, "profile_milling", "DETAIL_MACHINING_PROFILE_MILLING", source)

    if has_thread:
        _append_detail_candidate(
            candidates,
            "thread_inspection",
            "DETAIL_MACHINING_THREAD_INSPECTION",
            source,
            review=False,
        )

    if _machining_needs_in_process_inspection(parsed, holes, has_precision, has_thread):
        _append_detail_candidate(
            candidates,
            "in_process_inspection",
            "DETAIL_MACHINING_IN_PROCESS_INSPECTION",
            source,
            review=False,
        )


def _machining_hole_profile(holes: list[dict[str, Any]]) -> dict[str, bool]:
    profile = {
        "has_through": False,
        "has_blind": False,
        "has_thread_through": False,
        "has_thread_blind": False,
    }
    for hole in holes:
        hole_type = str(hole.get("hole_type") or "")
        text = _hole_text(hole)
        through = _hole_is_through(hole, text)
        blind = _hole_is_blind(hole, text)
        thread = is_thread_hole(hole) or has_thread_callout(text)
        profile["has_through"] = profile["has_through"] or through
        profile["has_blind"] = profile["has_blind"] or blind
        if thread:
            profile["has_thread_through"] = profile["has_thread_through"] or through
            profile["has_thread_blind"] = profile["has_thread_blind"] or blind or hole_type == "thread_candidate"
    return profile


def _hole_is_through(hole: dict[str, Any], text: str) -> bool:
    if hole.get("through") is True:
        return True
    if str(hole.get("hole_type") or "") == "through":
        return True
    return contains_any(text, ("完全贯穿", "贯穿", "通孔", "through"))


def _hole_is_blind(hole: dict[str, Any], text: str) -> bool:
    if hole.get("through") is False:
        return True
    if str(hole.get("hole_type") or "") == "blind":
        return True
    return contains_any(text, ("盲孔", "盲牙", "blind"))


def _machining_needs_profile_milling(parsed: ParsedPart) -> bool:
    part_type = parsed.geometry_part_type or ""
    if part_type not in {
        "plate",
        "thin_plate",
        "block",
        "simple_block",
        "complex_block",
        "precision_block",
        "long_bar",
        "small_irregular",
        "complex",
        "unknown",
    }:
        return False
    features = parsed.features
    complexity = features.get("complexity") or {}
    profile = parsed.geometry.get("profile_summary") or {}
    if any(
        int_value(profile.get(key)) or 0
        for key in (
            "outer_arc_count",
            "slot_candidate_count",
            "inner_profile_count",
            "circular_inner_profile_count",
        )
    ):
        return True
    if (int_value(complexity.get("edge_count")) or 0) >= 20:
        return True
    if (int_value(complexity.get("face_count")) or 0) >= 12:
        return True
    return bool(features.get("slots") or features.get("pockets"))


def _machining_needs_in_process_inspection(
    parsed: ParsedPart,
    holes: list[dict[str, Any]],
    has_precision: bool,
    has_thread: bool,
) -> bool:
    hole_total = sum(int_value(hole.get("count")) or 0 for hole in holes)
    if hole_total >= 6 or has_precision or has_thread:
        return True
    texts = []
    features = parsed.features
    texts.extend(str(item.get("raw_text") or "") for item in features.get("precision_requirements") or [])
    reqs = parsed.requirements
    texts.extend(str(item.get("raw_text") or "") for item in technical_requirement_items(reqs))
    text = normalize_text(" ".join(texts))
    return contains_any(text, ("±0.05", "±0.02", "+0.02", "+0.025", "h7", "h6", "ra0.8"))


def _precision_hole_prefers_reaming(hole: dict[str, Any]) -> bool:
    text = _hole_text(hole).lower()
    return "h7" in text or "ream" in text or "reaming" in text


def _is_fit_precision_hole(hole: dict[str, Any]) -> bool:
    """受阳极膜厚影响的配合精孔：H7/H6/G6 等配合公差或铰孔/配合孔/精孔。

    precision_candidate 类型本身即来自配合公差标注（H7 等），且该类型能存活到 fusion 之后；
    普通 ±0.1/±0.2 边缘公差不属于此列。
    """

    if not isinstance(hole, dict):
        return False
    if str(hole.get("hole_type") or "") == "precision_candidate":
        return True
    if not is_precision_hole(hole):
        return False
    text = _hole_text(hole).lower()
    return contains_any(
        text,
        ("h7", "h6", "h8", "g6", "g7", "f7", "fit", "fitting", "ream", "reaming", "配合", "铰", "精孔"),
    )


def _axis_hard_chrome_needs_masking(
    parsed: ParsedPart,
    has_precision: bool,
    has_thread: bool,
    axis_profile: AxisProfile | None,
) -> bool:
    if axis_profile is None:
        return True
    if axis_profile.surface_scope_confidence > 0:
        return True
    if has_thread or has_precision:
        return True
    surface = parsed.requirements.get("surface_treatment") or {}
    text = normalize_text(
        " ".join(str(surface.get(key) or "") for key in ("raw_text", "standard_code"))
    )
    return contains_any(text, SURFACE_LOCAL_SCOPE_KEYWORDS)


def _add_heat_detailing(
    candidates: list[Candidate],
    heat: dict[str, Any],
    heat_text: str,
) -> None:
    if not heat.get("required") and not contains_any(heat_text, HEAT_TREATMENT_KEYWORDS):
        return
    if not HARDNESS_PATTERN.search(heat_text):
        return
    _append_detail_candidate(
        candidates,
        "hardness_inspection",
        "DETAIL_HARDNESS_INSPECTION",
        heat.get("source") or source_ref("system", rule_code="DETAIL_HARDNESS_INSPECTION"),
        review=False,
    )


def _add_shaft_straightness_detailing(
    candidates: list[Candidate],
    parsed: ParsedPart,
    tech_text: str,
    *,
    family_hint: str | None,
    axis_profile: AxisProfile | None,
) -> None:
    if family_hint != TURNING:
        return
    if axis_profile and axis_profile.subtype == AXIS_SHORT_RING:
        return
    dims = _axis_dimensions(parsed.geometry)
    longest = dims[-1] if dims else 0.0
    slenderness = axis_profile.slenderness if axis_profile else _axis_slenderness(dims)
    explicit_straightness = contains_any(tech_text, STRAIGHTENING_KEYWORDS + AXIS_STRAIGHTNESS_KEYWORDS)
    support_bending_text = contains_any(tech_text, AXIS_SUPPORT_BENDING_KEYWORDS)
    has_heat = bool((parsed.requirements.get("heat_treatment") or {}).get("required")) or contains_any(
        tech_text, HEAT_TREATMENT_KEYWORDS
    )
    surface = parsed.requirements.get("surface_treatment") or {}
    surface_text = normalize_text(
        " ".join(str(surface.get(key) or "") for key in ("raw_text", "standard_code"))
    )
    has_hard_chrome = contains_any(surface_text, ("镀硬铬", "硬铬", "hard_chrome", "hard chrome"))
    definitely_slender = longest >= 200 and slenderness is not None and slenderness >= 15.0
    borderline_slender = (
        longest >= 200
        and slenderness is not None
        and 12.0 <= slenderness < 15.0
        and (explicit_straightness or support_bending_text or has_heat or has_hard_chrome)
    )
    if not (definitely_slender or borderline_slender or explicit_straightness):
        return
    _append_detail_candidate(
        candidates,
        "straightening",
        "DETAIL_SHAFT_STRAIGHTENING",
        source_ref("system", rule_code="DETAIL_SHAFT_STRAIGHTENING"),
        review=borderline_slender or explicit_straightness,
    )


def _append_detail_candidate(
    candidates: list[Candidate],
    op_code: str,
    rule_code: str,
    source: dict[str, Any],
    *,
    review: bool = True,
) -> None:
    candidates.append(
        Candidate(
            op_code=op_code,
            strength=FIELD,
            rule_code=rule_code,
            message=f"Detailing evidence adds {op_code}.",
            source=source,
            confidence=0.62,
            requires_review=review,
            review_reason="Detailing candidate; confirm before final quotation." if review else None,
        )
    )


def _add_deburr_evidence(
    candidates: list[Candidate], requirements: dict[str, Any], tech_text: str
) -> None:
    if (requirements.get("deburring") or {}).get("required") or contains_any(
        tech_text, DEBURR_KEYWORDS + EDGE_BREAK_KEYWORDS
    ):
        candidates.append(
            Candidate(
                op_code="deburr",
                strength=TECH_REQUIRED,
                rule_code="DEBURR_REQUIRED",
                message="Deburring or edge-break requirement detected; add deburr operation.",
                source=source_ref("system", rule_code="DEBURR_REQUIRED"),
                confidence=0.72,
            )
        )


def _classify_sentence(raw: Any) -> str:
    """Classify technical requirement text as required, conditional, or instructional."""

    text = str(raw or "").strip()
    if not text:
        return "instructional"
    if any(marker in text for marker in INSTRUCTIONAL_MARKERS):
        return "instructional"
    if any(marker in text for marker in CONDITIONAL_MARKERS):
        return "conditional"
    return "required"
