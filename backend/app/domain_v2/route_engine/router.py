"""L1 · 路由层 / 硬入口 (Router).

业务小类 → 工艺族（FAMILY）。这是**唯一**决定走哪条族路线的地方，也是修复钣金/轴类
8/16 灾难性偏离的单点。

铁律 A —— 几何不得覆盖业务小类：几何只能在族内选工序，不能换族；冲突时报
``CATEGORY_GEOMETRY_CONFLICT_REVIEW`` 并继续用小类的族。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .families import (
    CATEGORY_CONFIDENCE_THRESHOLD,
    CATEGORY_TO_FAMILY,
    FALLBACK_FAMILY,
    FAMILY_LABELS,
)
from .parsed_part import ParsedPart
from .reviews import (
    CATEGORY_GEOMETRY_CONFLICT_REVIEW,
    LOW_CONFIDENCE_CATEGORY_REVIEW,
    Review,
    make_review,
)


@dataclass(frozen=True)
class RoutingDecision:
    family: str
    business_category: str | None
    confidence: float
    reviews: list[Review] = field(default_factory=list)
    geometry_note: str | None = None

    @property
    def blocking(self) -> bool:
        return any(review.blocking for review in self.reviews)


def route_family(parsed: ParsedPart) -> RoutingDecision:
    business = parsed.business_class
    category = business.category_name

    # 小类缺失或不在映射表（型材/拼组等暂未建族）→ 保守机加 + 强制复核。
    if not category or category not in CATEGORY_TO_FAMILY:
        return RoutingDecision(
            family=FALLBACK_FAMILY,
            business_category=category,
            confidence=business.confidence,
            reviews=[
                make_review(
                    LOW_CONFIDENCE_CATEGORY_REVIEW,
                    f"业务小类缺失或未建族（{category or '无'}），保守按"
                    f"{FAMILY_LABELS[FALLBACK_FAMILY]}规划并强制复核。",
                    source_layer="L1",
                    evidence=business.source,
                )
            ],
        )

    # 小类存在但置信度低 → 降级机加 + 强制复核，不静默猜。
    if business.confidence < CATEGORY_CONFIDENCE_THRESHOLD:
        return RoutingDecision(
            family=FALLBACK_FAMILY,
            business_category=category,
            confidence=business.confidence,
            reviews=[
                make_review(
                    LOW_CONFIDENCE_CATEGORY_REVIEW,
                    f"业务小类“{category}”抽取置信度过低（{business.confidence:.2f}），"
                    f"保守按{FAMILY_LABELS[FALLBACK_FAMILY]}规划并强制复核。",
                    source_layer="L1",
                    evidence=business.source,
                )
            ],
        )

    # 小类明确且置信度达标 → 硬路由定族。几何意见仅作记录。
    family = CATEGORY_TO_FAMILY[category]
    reviews: list[Review] = []
    geometry_note: str | None = None

    if _geometry_conflicts(parsed):
        geometry_note = (
            f"业务小类“{category}”→{FAMILY_LABELS[family]}，"
            f"但 STEP 几何类型“{parsed.geometry_part_type}”不在兼容集，"
            f"几何仅作记录、不换族。"
        )
        reviews.append(
            make_review(
                CATEGORY_GEOMETRY_CONFLICT_REVIEW,
                geometry_note,
                source_layer="L1",
                evidence=business.source,
                blocking=False,
            )
        )

    return RoutingDecision(
        family=family,
        business_category=category,
        confidence=business.confidence,
        reviews=reviews,
        geometry_note=geometry_note,
    )


def _geometry_conflicts(parsed: ParsedPart) -> bool:
    """小类↔几何 part_type 是否明显冲突。复用 PDF 小类自带的兼容类型集。"""

    part_type = parsed.geometry_part_type
    compatible = parsed.business_class.compatible_part_types
    if not part_type or not compatible:
        return False
    return part_type not in compatible
