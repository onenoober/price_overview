"""L0 · 解析与置信度层 (Parse & Confidence).

把生产链路里的 ``part_feature`` dict 整理成 ``ParsedPart``，并把"最可信的业务小类"
（PDF 标题栏 ``pdf_part_category``）单独抽出来带上置信度 —— 这是后续"信任业务小类、
几何降级"的前提。本层不做任何工艺决策。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BusinessClass:
    """业务小类（钣金类/圆件类/大板类/方件类...），来自 PDF 标题栏。"""

    category_name: str | None
    confidence: float
    source: dict[str, Any] | None
    compatible_part_types: tuple[str, ...] = ()
    raw_text: str | None = None

    @property
    def present(self) -> bool:
        return bool(self.category_name)


@dataclass(frozen=True)
class ParsedPart:
    """L0 输出。保留原始 ``part_feature`` 供下游证据层复用既有特征助手。"""

    part_feature: dict[str, Any]
    business_class: BusinessClass
    geometry: dict[str, Any]
    features: dict[str, Any]
    requirements: dict[str, Any]
    material: dict[str, Any]
    geometry_part_type: str | None
    assumptions: list[str] = field(default_factory=list)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_part_feature(part_feature: dict[str, Any]) -> ParsedPart:
    geometry = part_feature.get("geometry") or {}
    features = part_feature.get("features") or {}
    requirements = part_feature.get("manufacturing_requirements") or {}
    material = part_feature.get("material") or {}

    pdf_category = geometry.get("pdf_part_category") or {}
    business_class = BusinessClass(
        category_name=_clean(pdf_category.get("category_name")),
        confidence=_as_float(pdf_category.get("confidence")),
        source=pdf_category.get("source") if isinstance(pdf_category.get("source"), dict) else None,
        compatible_part_types=tuple(pdf_category.get("compatible_part_types") or ()),
        raw_text=_clean(pdf_category.get("raw_text")),
    )

    return ParsedPart(
        part_feature=part_feature,
        business_class=business_class,
        geometry=geometry,
        features=features,
        requirements=requirements,
        material=material,
        geometry_part_type=_clean(geometry.get("part_type")),
    )


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
