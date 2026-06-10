from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class SourceRef:
    source_type: str = "step"
    file_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(frozen=True)
class MeasuredValue:
    value: float | None
    unit: str | None
    source: SourceRef

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "unit": self.unit, "source": self.source.to_dict()}


@dataclass(frozen=True)
class BoundingBox:
    length: float | None
    width: float | None
    height: float | None
    unit: str = "mm"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HoleCandidate:
    hole_type: str
    diameter: float | None
    depth: float | None
    count: int
    confidence: float
    evidence: list[SourceRef]
    counterbore_diameter: float | None = None
    counterbore_depth: float | None = None
    countersink_diameter: float | None = None
    countersink_depth: float | None = None
    countersink_angle: float | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "hole_type": self.hole_type,
            "diameter": self.diameter,
            "depth": self.depth,
            "count": self.count,
            "confidence": self.confidence,
            "evidence": [item.to_dict() for item in self.evidence],
        }
        optional_values = {
            "counterbore_diameter": self.counterbore_diameter,
            "counterbore_depth": self.counterbore_depth,
            "countersink_diameter": self.countersink_diameter,
            "countersink_depth": self.countersink_depth,
            "countersink_angle": self.countersink_angle,
        }
        result.update(
            {
                key: value
                for key, value in optional_values.items()
                if value is not None
            }
        )
        return result


@dataclass(frozen=True)
class RiskItem:
    code: str
    level: str
    message: str
    source: str
    requires_review: bool
    evidence: list[SourceRef]

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "level": self.level,
            "message": self.message,
            "source": self.source,
            "requires_review": self.requires_review,
            "evidence": [item.to_dict() for item in self.evidence],
        }
