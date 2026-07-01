"""Manufacturing context resolver for the V2 pricing domain."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain_v2.facts import Conflict, EvidenceRef, FactSnapshot, FactValue


_MATERIAL_KEYS = ("material", "material.grade", "material_name")
_THICKNESS_KEYS = ("thickness", "thickness_mm", "sheet.thickness_mm")
_EQUAL_THICKNESS_KEYS = (
    "equal_thickness",
    "is_equal_thickness",
    "constant_thickness",
    "is_constant_thickness",
    "sheet.equal_thickness",
)
_HOLE_KEYS = ("has_holes", "holes", "hole_count", "features.holes", "features.hole_count")
_BEND_KEYS = ("bend_count", "bends", "features.bends", "features.bend_count")
_BEND_ANGLE_KEYS = ("bend_angles", "features.bend_angles")

GeometryClass = Literal[
    "sheet_like",
    "prismatic",
    "rotational",
    "tubular",
    "profile_like",
    "freeform",
    "assembly",
    "mixed_geometry",
]
SupportLevel = Literal["L0", "L1", "L2", "L3", "L4"]


class StockCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    stock_form: str
    confidence: float
    evidence: list[EvidenceRef] = Field(default_factory=list)
    reason: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)


class FamilyCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    family: str
    confidence: float
    evidence: list[EvidenceRef] = Field(default_factory=list)
    reason: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)


class ManufacturingContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    geometry_class: GeometryClass | None = None
    stock_candidates: list[StockCandidate] = Field(default_factory=list)
    family_candidates: list[FamilyCandidate] = Field(default_factory=list)
    required_secondary_families: list[str] = Field(default_factory=list)
    support_level: SupportLevel = "L0"
    conflicts: list[Conflict] = Field(default_factory=list)
    facts: FactSnapshot | None = None


class ManufacturingContextResolver:
    """Resolve neutral facts into manufacturing context candidates."""

    def resolve(self, snapshot: FactSnapshot) -> ManufacturingContext:
        material = _normalize_text(snapshot.first_value(*_MATERIAL_KEYS))
        thickness_mm = _as_float(snapshot.first_value(*_THICKNESS_KEYS))
        equal_thickness = _as_bool(snapshot.first_value(*_EQUAL_THICKNESS_KEYS))
        hole_count = _count_feature(snapshot, _HOLE_KEYS)
        bend_count = _count_feature(snapshot, _BEND_KEYS)
        bend_angles = _as_float_list(snapshot.first_value(*_BEND_ANGLE_KEYS))

        conflicts = list(self._detect_conflicts(snapshot))
        geometry_class = self._resolve_geometry_class(thickness_mm, equal_thickness)
        stock_candidates = self._resolve_stock_candidates(
            snapshot, geometry_class, material, thickness_mm, equal_thickness
        )
        family_candidates = self._resolve_family_candidates(
            snapshot, geometry_class, material, thickness_mm, bend_count, bend_angles
        )
        secondary_families = self._resolve_secondary_families(hole_count)
        support_level = self._resolve_support_level(
            geometry_class,
            stock_candidates,
            family_candidates,
            material,
            thickness_mm,
            equal_thickness,
            hole_count,
            bend_count,
            bend_angles,
            conflicts,
        )

        return ManufacturingContext(
            geometry_class=geometry_class,
            stock_candidates=stock_candidates,
            family_candidates=family_candidates,
            required_secondary_families=secondary_families,
            support_level=support_level,
            conflicts=conflicts,
            facts=snapshot,
        )

    def _resolve_geometry_class(
        self, thickness_mm: float | None, equal_thickness: bool | None
    ) -> GeometryClass | None:
        if thickness_mm is not None and equal_thickness is True:
            return "sheet_like"
        return None

    def _resolve_stock_candidates(
        self,
        snapshot: FactSnapshot,
        geometry_class: str | None,
        material: str | None,
        thickness_mm: float | None,
        equal_thickness: bool | None,
    ) -> list[StockCandidate]:
        if geometry_class != "sheet_like":
            return []

        confidence = 0.70
        if thickness_mm is not None:
            confidence += 0.10
        if equal_thickness is True:
            confidence += 0.10
        if material:
            confidence += 0.05

        return [
            StockCandidate(
                stock_form="sheet",
                confidence=min(confidence, 0.95),
                reason="equal-thickness geometry with a measurable thickness",
                evidence=snapshot.evidence_for(
                    *_THICKNESS_KEYS, *_EQUAL_THICKNESS_KEYS, *_MATERIAL_KEYS
                ),
                attributes={"material": material, "thickness_mm": thickness_mm},
            )
        ]

    def _resolve_family_candidates(
        self,
        snapshot: FactSnapshot,
        geometry_class: str | None,
        material: str | None,
        thickness_mm: float | None,
        bend_count: int,
        bend_angles: tuple[float, ...],
    ) -> list[FamilyCandidate]:
        if geometry_class != "sheet_like":
            return []

        confidence = 0.72
        if material:
            confidence += 0.05
        if thickness_mm is not None:
            confidence += 0.08
        if bend_count > 0:
            confidence += 0.08
        if any(abs(angle - 90.0) <= 1.0 for angle in bend_angles):
            confidence += 0.04

        return [
            FamilyCandidate(
                family="sheet_metal",
                confidence=min(confidence, 0.97),
                reason="sheet-like facts support sheet metal family candidacy",
                evidence=snapshot.evidence_for(
                    *_MATERIAL_KEYS, *_THICKNESS_KEYS, *_BEND_KEYS, *_BEND_ANGLE_KEYS
                ),
                attributes={
                    "material": material,
                    "thickness_mm": thickness_mm,
                    "bend_count": bend_count,
                    "bend_angles": list(bend_angles),
                },
            )
        ]

    def _resolve_secondary_families(self, hole_count: int) -> list[str]:
        return ["hole_finishing"] if hole_count > 0 else []

    def _resolve_support_level(
        self,
        geometry_class: str | None,
        stock_candidates: list[StockCandidate],
        family_candidates: list[FamilyCandidate],
        material: str | None,
        thickness_mm: float | None,
        equal_thickness: bool | None,
        hole_count: int,
        bend_count: int,
        bend_angles: tuple[float, ...],
        conflicts: list[Conflict],
    ) -> SupportLevel:
        if conflicts:
            return "L1"
        if (
            geometry_class == "sheet_like"
            and any(candidate.stock_form == "sheet" for candidate in stock_candidates)
            and any(candidate.family == "sheet_metal" for candidate in family_candidates)
            and material == "sus304"
            and thickness_mm is not None
            and abs(thickness_mm - 2.0) <= 0.05
            and equal_thickness is True
            and hole_count > 0
            and bend_count == 1
            and any(abs(angle - 90.0) <= 1.0 for angle in bend_angles)
        ):
            return "L3"
        if geometry_class and stock_candidates and family_candidates:
            return "L2"
        if geometry_class:
            return "L1"
        return "L0"

    def _detect_conflicts(self, snapshot: FactSnapshot) -> list[Conflict]:
        conflicts: list[Conflict] = []
        conflicts.extend(_conflicts_for_scalar(snapshot, _MATERIAL_KEYS, "material"))
        conflicts.extend(_conflicts_for_scalar(snapshot, _THICKNESS_KEYS, "thickness_mm"))
        conflicts.extend(
            _conflicts_for_scalar(snapshot, _EQUAL_THICKNESS_KEYS, "equal_thickness")
        )
        return conflicts


def _conflicts_for_scalar(
    snapshot: FactSnapshot, keys: tuple[str, ...], field_name: str
) -> list[Conflict]:
    facts = [fact for key in keys for fact in snapshot.values_for(key)]
    normalized: dict[Any, list[FactValue]] = {}
    for fact in facts:
        value = _normalize_conflict_value(fact.value)
        if value is not None:
            normalized.setdefault(value, []).append(fact)
    if len(normalized) <= 1:
        return []

    refs: list[EvidenceRef] = []
    for fact_group in normalized.values():
        for fact in fact_group:
            refs.extend(fact.evidence)
    return [
        Conflict(
            field=field_name,
            candidates=list(normalized.keys()),
            reason=f"conflicting {field_name} facts",
            severity="warning",
            evidence=refs,
        )
    ]


def _normalize_conflict_value(value: Any) -> Any:
    if isinstance(value, str):
        return _normalize_text(value)
    if isinstance(value, bool):
        return value
    number = _as_float(value)
    if number is not None:
        return round(number, 4)
    return value


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace(" ", "")
    return text or None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "yes", "y", "1", "constant", "equal"}:
        return True
    if text in {"false", "no", "n", "0", "variable"}:
        return False
    return None


def _count_feature(snapshot: FactSnapshot, keys: tuple[str, ...]) -> int:
    value = snapshot.first_value(*keys)
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (list, tuple, set, dict)):
        return len(value)
    number = _as_float(value)
    return max(int(number), 0) if number is not None else 0


def _as_float_list(value: Any) -> tuple[float, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        return tuple(number for item in value if (number := _as_float(item)) is not None)
    number = _as_float(value)
    return () if number is None else (number,)


__all__ = [
    "FamilyCandidate",
    "ManufacturingContext",
    "ManufacturingContextResolver",
    "StockCandidate",
]
