"""L6 · 风险与复核旁路 (Risk & Review).

集中处理所有风险信号，升级为复核项，**绝不回写主路线增加工序**。本模块只定义复核码与
构造助手；具体何时抛出由各层调用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# 复核码（方案 §L6 清单）。布尔为是否阻断。
CATEGORY_GEOMETRY_CONFLICT_REVIEW = "CATEGORY_GEOMETRY_CONFLICT_REVIEW"
LOW_CONFIDENCE_CATEGORY_REVIEW = "LOW_CONFIDENCE_CATEGORY_REVIEW"
HOLE_MISMATCH_REVIEW = "HOLE_MISMATCH_REVIEW"
WEIGHT_CONFLICT_REVIEW = "WEIGHT_CONFLICT_REVIEW"
SURFACE_TREATMENT_UNVERIFIED = "SURFACE_TREATMENT_UNVERIFIED"
FORBIDDEN_OP_TRIGGERED_REVIEW = "FORBIDDEN_OP_TRIGGERED_REVIEW"
SEQUENCE_CONFLICT_REVIEW = "SEQUENCE_CONFLICT_REVIEW"
WELDING_CONDITIONAL_TEXT = "WELDING_CONDITIONAL_TEXT"
LONG_STRIP_BOUNDARY_REVIEW = "LONG_STRIP_BOUNDARY_REVIEW"
SHAFT_SURFACE_REVIEW = "SHAFT_SURFACE_REVIEW"

BLOCKING_CODES = {LOW_CONFIDENCE_CATEGORY_REVIEW}


@dataclass(frozen=True)
class Review:
    code: str
    message: str
    source_layer: str
    evidence: dict[str, Any] | None = None
    blocking: bool = False

    def to_risk(self) -> dict[str, Any]:
        from backend.app.process_recognition import risk_item, system_source

        return risk_item(
            self.code,
            "warning",
            self.message,
            "route_engine",
            self.blocking,
            [self.evidence] if isinstance(self.evidence, dict) else [system_source(self.code)],
        )


def make_review(
    code: str,
    message: str,
    source_layer: str,
    *,
    evidence: dict[str, Any] | None = None,
    blocking: bool | None = None,
) -> Review:
    is_blocking = code in BLOCKING_CODES if blocking is None else blocking
    return Review(
        code=code,
        message=message,
        source_layer=source_layer,
        evidence=evidence,
        blocking=is_blocking,
    )
