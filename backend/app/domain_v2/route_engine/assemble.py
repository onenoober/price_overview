"""L5 route assembly and ordering."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.app.part_feature_builder import source_ref
from backend.app.process_recognition import OPERATION_STAGE_MAP, STAGE_SEQUENCE

from .evidence import Candidate
from .families import FAMILY_LABELS
from .policy import (
    ALLOW,
    CONDITIONAL,
    CONDITIONAL_GEOMETRY,
    DENY,
    REQUIRED,
    policy,
)
from .reviews import FORBIDDEN_OP_TRIGGERED_REVIEW, Review, make_review


OP_WITHIN_STAGE_RANK = {
    "welding_prepare": 5,
    "fit_up": 8,
    "bending": 12,
    "sheet_metal_welding": 15,
    "weld_grinding": 20,
    "stress_relief": 10,
    "straightening": 20,
    "cnc_finish_milling": 30,
    "cylindrical_grinding": 40,
    "finish_grinding": 45,
    "reaming": 50,
    "precision_hole": 55,
    "hardness_inspection": 60,
    "in_process_inspection": 5,
    "thread_inspection": 10,
}


@dataclass(frozen=True)
class OpSpec:
    op_code: str
    status: str  # required | candidate
    rule_code: str
    message: str
    source: dict[str, Any]
    confidence: float
    requires_review: bool = False
    review_reason: str | None = None


@dataclass
class AssembledRoute:
    ops: list[OpSpec] = field(default_factory=list)
    reviews: list[Review] = field(default_factory=list)
    verified_candidate_count: int = 0


def assemble_route(
    family: str,
    skeleton: tuple[str, ...],
    candidates: list[Candidate],
    parsed: Any,
) -> AssembledRoute:
    label = FAMILY_LABELS.get(family, family)
    skeleton_set = set(skeleton)
    ops: list[OpSpec] = []
    reviews: list[Review] = []

    # L2 skeleton: always required.
    for op_code in skeleton:
        ops.append(
            OpSpec(
                op_code=op_code,
                status="required",
                rule_code=f"SKELETON_{family}",
                message=f"{label} backbone route is required.",
                source=source_ref("system", rule_code=f"SKELETON_{family}"),
                confidence=0.9,
            )
        )

    # Review-only candidates are never inserted into the route.
    for candidate in candidates:
        if candidate.review_only:
            reviews.extend(_candidate_reviews(candidate))

    routable = [candidate for candidate in candidates if not candidate.review_only]
    verified = 0
    for candidate in _dedupe(routable):
        op_code = candidate.op_code
        if op_code in skeleton_set:
            continue
        decision = policy(family, op_code)
        if decision in (REQUIRED, ALLOW, CONDITIONAL):
            ops.append(_candidate_to_spec(candidate))
            reviews.extend(_candidate_reviews(candidate))
            verified += 1
        elif decision == CONDITIONAL_GEOMETRY:
            if candidate.is_geometry:
                ops.append(_candidate_to_spec(candidate))
                reviews.extend(_candidate_reviews(candidate))
                verified += 1
        elif decision == DENY:
            reviews.append(
                make_review(
                    FORBIDDEN_OP_TRIGGERED_REVIEW,
                    f"Evidence triggered forbidden op `{op_code}` for {label} (source: {candidate.rule_code}); "
                    "it was blocked from the route and may indicate an upstream misclassification.",
                    source_layer="L4",
                    evidence=candidate.source,
                    blocking=False,
                )
            )

    ordered = _order_by_stage(ops, skeleton)
    return AssembledRoute(ops=ordered, reviews=reviews, verified_candidate_count=verified)


def _candidate_to_spec(candidate: Candidate) -> OpSpec:
    return OpSpec(
        op_code=candidate.op_code,
        status="candidate",
        rule_code=candidate.rule_code,
        message=candidate.message,
        source=candidate.source,
        confidence=candidate.confidence,
        requires_review=candidate.requires_review,
        review_reason=candidate.review_reason,
    )


def _candidate_reviews(candidate: Candidate) -> list[Review]:
    if candidate.review_code:
        return [
            make_review(
                candidate.review_code,
                candidate.review_reason or candidate.message,
                source_layer="L3",
                evidence=candidate.source,
            )
        ]
    return []


def _dedupe(candidates: list[Candidate]) -> list[Candidate]:
    """Keep the highest-confidence candidate per op while preserving first-seen order."""

    best: dict[str, Candidate] = {}
    order: list[str] = []
    for candidate in candidates:
        existing = best.get(candidate.op_code)
        if existing is None:
            best[candidate.op_code] = candidate
            order.append(candidate.op_code)
        elif candidate.confidence > existing.confidence:
            best[candidate.op_code] = candidate
    return [best[op_code] for op_code in order]


def _stage_index(op_code: str) -> int:
    stage_code = OPERATION_STAGE_MAP.get(op_code)
    if not stage_code:
        return len(STAGE_SEQUENCE)
    try:
        return STAGE_SEQUENCE.index(stage_code)
    except ValueError:
        return len(STAGE_SEQUENCE)


def _order_by_stage(ops: list[OpSpec], skeleton: tuple[str, ...]) -> list[OpSpec]:
    """Order by stage first, then by a small within-stage priority table."""

    skeleton_rank = {op_code: rank for rank, op_code in enumerate(skeleton)}

    def sort_key(item: tuple[int, OpSpec]) -> tuple[int, int, int, int]:
        index, spec = item
        stage = _stage_index(spec.op_code)
        within_stage = OP_WITHIN_STAGE_RANK.get(spec.op_code, 100)
        in_skeleton = skeleton_rank.get(spec.op_code)
        if in_skeleton is not None:
            return (stage, within_stage, 0, in_skeleton)
        return (stage, within_stage, 1, index)

    return [spec for _, spec in sorted(enumerate(ops), key=sort_key)]
