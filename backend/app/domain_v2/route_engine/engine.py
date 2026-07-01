"""分层路线引擎编排 (L0→L6)。

``plan_route_v2`` 是新引擎的唯一入口，签名与旧 ``build_process_route`` 对齐，产出同构的路线
dict（``schema_version/operations/stage_route/risks/requires_review``），由 ``pricing_core``
按特性开关并行调用。
"""

from __future__ import annotations

from typing import Any

from backend.app.process_recognition import (
    OPERATION_STAGE_MAP,
    STAGE_DICTIONARY,
    add_operation,
    add_stage,
    finalize_route,
    finalize_stage_route,
    system_source,
)

from .assemble import AssembledRoute, assemble_route
from .evidence import collect_evidence
from .parsed_part import parse_part_feature
from .reviews import Review
from .router import RoutingDecision, route_family
from .skeleton import skeleton_for


def plan_route_v2(
    *,
    task_id: str,
    route_id: str,
    part_feature: dict[str, Any],
    inherited_risks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    parsed = parse_part_feature(part_feature)

    # L1 硬路由
    decision: RoutingDecision = route_family(parsed)
    family = decision.family

    # L2 骨架 + L3 证据 + L4 矩阵 + L5 装配
    skeleton = skeleton_for(family)
    candidates = collect_evidence(parsed, family_hint=decision.family)
    assembled: AssembledRoute = assemble_route(family, skeleton, candidates, parsed)

    operations = _build_operations(assembled)
    stage_route = _build_stage_route(operations, assembled)
    risks = _build_risks(decision, assembled)

    route = finalize_route(
        task_id=task_id,
        route_id=route_id,
        operations=operations,
        risks=risks,
        stage_route=stage_route,
        preserve_input_order=True,
    )
    route["family"] = family
    route["business_category"] = decision.business_category
    return route


def _build_operations(assembled: AssembledRoute) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    for spec in assembled.ops:
        add_operation(
            operations,
            operation_code=spec.op_code,
            rule_code=spec.rule_code,
            message=spec.message,
            source=spec.source,
            confidence=spec.confidence,
            requires_review=spec.requires_review,
            review_reason=spec.review_reason,
        )
    return operations


def _build_stage_route(
    operations: list[dict[str, Any]], assembled: AssembledRoute
) -> list[dict[str, Any]]:
    review_stage_codes = {
        OPERATION_STAGE_MAP.get(spec.op_code)
        for spec in assembled.ops
        if spec.requires_review
    }
    stages: list[dict[str, Any]] = []
    seen: set[str] = set()
    for operation in operations:
        stage_code = OPERATION_STAGE_MAP.get(str(operation.get("operation_code") or ""))
        if not stage_code or stage_code in seen:
            continue
        seen.add(stage_code)
        definition = STAGE_DICTIONARY.get(stage_code)
        add_stage(
            stages,
            stage_code,
            rule_code="ROUTE_ENGINE_STAGE",
            message=definition.description if definition else f"{stage_code} 阶段。",
            source=system_source("ROUTE_ENGINE_STAGE"),
            confidence=0.85,
            requires_review=stage_code in review_stage_codes,
        )
    return finalize_stage_route(stages)


def _build_risks(
    decision: RoutingDecision, assembled: AssembledRoute
) -> list[dict[str, Any]]:
    reviews: list[Review] = list(decision.reviews) + list(assembled.reviews)
    return [review.to_risk() for review in reviews]
