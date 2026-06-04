from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Protocol


CHINA_TZ = timezone(timedelta(hours=8))


class AiAssistanceService(Protocol):
    def normalize_material(
        self,
        *,
        task_id: str,
        raw_text: str | None,
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ...

    def normalize_surface_treatment(
        self,
        *,
        task_id: str,
        raw_text: str | None,
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ...

    def explain_risk(
        self,
        *,
        task_id: str,
        risk: dict[str, Any],
    ) -> dict[str, Any]:
        ...

    def explain_operation(
        self,
        *,
        task_id: str,
        operation: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class MockAiAssistanceService:
    model_name = "mock-ai-assistance"
    prompt_version = "mock-v1"

    def normalize_material(
        self,
        *,
        task_id: str,
        raw_text: str | None,
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        normalized = normalize_key(raw_text)

        if normalized in {"sus304", "sus_304"}:
            content = {
                "raw_text": raw_text,
                "standard_code": "SUS304",
                "standard_name": "SUS304 stainless steel",
                "density": 7.93,
                "density_unit": "g/cm3",
                "match_reason": "Mock exact match for SUS304 material text.",
            }
            confidence = 0.9
        elif normalized == "skd11":
            content = {
                "raw_text": raw_text,
                "standard_code": "SKD11",
                "standard_name": "SKD11 tool steel",
                "density": 7.85,
                "density_unit": "g/cm3",
                "match_reason": "Mock material dictionary match for SKD11.",
            }
            confidence = 0.88
        elif normalized in {"s45c", "45#"}:
            content = {
                "raw_text": raw_text,
                "standard_code": "S45C",
                "standard_name": "S45C carbon steel",
                "density": 7.85,
                "density_unit": "g/cm3",
                "match_reason": "Mock material dictionary match for S45C.",
            }
            confidence = 0.86
        elif normalized in {"al6061", "6061", "6061_t6", "al6061_t6"}:
            content = {
                "raw_text": raw_text,
                "standard_code": "AL6061",
                "standard_name": "6061 aluminum alloy",
                "density": 2.7,
                "density_unit": "g/cm3",
                "match_reason": "Mock material dictionary match for AL6061.",
            }
            confidence = 0.86
        else:
            content = {
                "raw_text": raw_text,
                "standard_code": None,
                "standard_name": None,
                "density": None,
                "density_unit": None,
                "match_reason": "No mock material match. Keep raw evidence for review.",
            }
            confidence = 0.0 if not raw_text else 0.35

        return build_ai_output(
            task_id=task_id,
            input_type="field_text",
            output_type="normalization",
            content=content,
            confidence=confidence,
            evidence=evidence,
            model_name=self.model_name,
            prompt_version=self.prompt_version,
        )

    def normalize_surface_treatment(
        self,
        *,
        task_id: str,
        raw_text: str | None,
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        normalized = normalize_key(raw_text)

        if normalized in {
            "chemical_nickel_plating",
            "镀化学镍",
            "化学镍",
            "化学镀镍",
            "electroless_nickel_plating",
        }:
            content = {
                "raw_text": raw_text,
                "standard_code": "CHEMICAL_NICKEL_PLATING",
                "standard_name": "Chemical nickel plating",
                "match_reason": "Mock exact match for surface treatment text.",
            }
            confidence = 0.82
        else:
            content = {
                "raw_text": raw_text,
                "standard_code": None,
                "standard_name": None,
                "match_reason": "No mock surface treatment match. Keep raw evidence for review.",
            }
            confidence = 0.0 if not raw_text else 0.35

        return build_ai_output(
            task_id=task_id,
            input_type="field_text",
            output_type="normalization",
            content=content,
            confidence=confidence,
            evidence=evidence,
            model_name=self.model_name,
            prompt_version=self.prompt_version,
        )

    def explain_risk(
        self,
        *,
        task_id: str,
        risk: dict[str, Any],
    ) -> dict[str, Any]:
        content = {
            "risk_code": risk.get("code"),
            "risk_level": risk.get("level"),
            "original_message": risk.get("message"),
            "explanation": (
                "Mock explanation only. Please review the structured risk evidence "
                "before confirming the quote."
            ),
            "requires_review": risk.get("requires_review"),
        }

        return build_ai_output(
            task_id=task_id,
            input_type="risk_item",
            output_type="risk_suggestion",
            content=content,
            confidence=0.75,
            evidence=risk.get("evidence", []),
            model_name=self.model_name,
            prompt_version=self.prompt_version,
        )

    def explain_operation(
        self,
        *,
        task_id: str,
        operation: dict[str, Any],
    ) -> dict[str, Any]:
        content = {
            "operation_code": operation.get("operation_code"),
            "operation_name": operation.get("operation_name"),
            "trigger_reasons": operation.get("trigger_reasons", []),
            "explanation": (
                "Mock explanation only. This does not add, remove, reorder, "
                "or change operation confidence."
            ),
        }

        return build_ai_output(
            task_id=task_id,
            input_type="rule_result",
            output_type="explanation",
            content=content,
            confidence=0.75,
            evidence=operation.get("evidence", []),
            model_name=self.model_name,
            prompt_version=self.prompt_version,
        )


def build_ai_output(
    *,
    task_id: str,
    input_type: str,
    output_type: str,
    content: dict[str, Any],
    confidence: float,
    evidence: list[dict[str, Any]],
    model_name: str,
    prompt_version: str,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "input_type": input_type,
        "output_type": output_type,
        "content": content,
        "confidence": confidence,
        "evidence": evidence,
        "model_name": model_name,
        "prompt_version": prompt_version,
        "created_at": now_iso(),
    }


def normalize_key(value: str | None) -> str:
    if not value:
        return ""
    return "_".join(value.strip().lower().replace("/", " ").split())


def now_iso() -> str:
    return datetime.now(CHINA_TZ).isoformat(timespec="seconds")
