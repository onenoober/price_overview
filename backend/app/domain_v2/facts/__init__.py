"""Neutral V2 manufacturing fact models.

Facts describe what was observed or inferred. They do not decide how the part
should be manufactured.
"""

from __future__ import annotations

from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


FactStatus = Literal["observed", "inferred", "confirmed", "conflicted", "missing"]
EvidenceSource = Literal["pdf", "step", "user", "rule", "ai"]


class EvidenceRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_type: EvidenceSource
    source_file_id: str | None = None
    page: int | None = None
    bbox: list[float] | None = None
    cad_entity_id: str | None = None
    raw_text: str | None = None
    extractor_version: str = "unknown"


class FactValue(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    value: Any
    unit: str | None = None
    confidence: float = 1.0
    evidence: list[EvidenceRef] = Field(default_factory=list)
    status: FactStatus = "observed"

    @field_validator("key")
    @classmethod
    def key_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("FactValue.key must not be empty")
        return value

    @field_validator("confidence")
    @classmethod
    def confidence_must_be_unit_interval(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("FactValue.confidence must be between 0 and 1")
        return value


class Conflict(BaseModel):
    model_config = ConfigDict(frozen=True)

    field: str
    candidates: list[Any]
    reason: str
    severity: Literal["info", "warning", "blocking"] = "warning"
    evidence: list[EvidenceRef] = Field(default_factory=list)


class FactSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "2.0"
    snapshot_id: str | None = None
    part_identity: dict[str, FactValue] = Field(default_factory=dict)
    material_facts: dict[str, FactValue] = Field(default_factory=dict)
    geometry_facts: dict[str, FactValue] = Field(default_factory=dict)
    feature_facts: dict[str, FactValue] = Field(default_factory=dict)
    requirement_facts: dict[str, FactValue] = Field(default_factory=dict)
    order_context: dict[str, FactValue] = Field(default_factory=dict)
    conflicts: list[Conflict] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    facts: list[FactValue] = Field(default_factory=list)

    @classmethod
    def from_values(
        cls,
        values: Iterable[FactValue],
        *,
        snapshot_id: str | None = None,
        evidence: Iterable[EvidenceRef] | None = None,
    ) -> "FactSnapshot":
        return cls(
            snapshot_id=snapshot_id,
            facts=list(values),
            evidence=list(evidence or ()),
        )

    def values_for(self, key: str) -> list[FactValue]:
        return [fact for fact in self._all_facts() if fact.key == key]

    def first_value(self, *keys: str, default: Any = None) -> Any:
        fact = self.first_fact(*keys)
        return default if fact is None else fact.value

    def first_fact(self, *keys: str) -> FactValue | None:
        key_set = set(keys)
        return next((fact for fact in self._all_facts() if fact.key in key_set), None)

    def evidence_for(self, *keys: str) -> list[EvidenceRef]:
        refs: list[EvidenceRef] = []
        key_set = set(keys)
        for fact in self._all_facts():
            if fact.key in key_set:
                refs.extend(fact.evidence)
        return refs

    def _all_facts(self) -> list[FactValue]:
        facts = list(self.facts)
        for section in (
            self.part_identity,
            self.material_facts,
            self.geometry_facts,
            self.feature_facts,
            self.requirement_facts,
            self.order_context,
        ):
            facts.extend(section.values())
        return facts


__all__ = ["Conflict", "EvidenceRef", "FactSnapshot", "FactValue"]
