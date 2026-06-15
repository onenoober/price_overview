from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Protocol

import httpx


CHINA_TZ = timezone(timedelta(hours=8))
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-5.5"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 60.0
PDF_AI_MAX_FIELD_CANDIDATES = 3
PDF_AI_MAX_OUTPUT_CANDIDATES = 8
PDF_AI_MAX_EVIDENCE_ITEMS = 3
PDF_AI_MAX_TEXT_BLOCKS = 12
PDF_AI_MAX_TECHNICAL_REQUIREMENTS = 8
PDF_AI_REVIEW_CONFIDENCE_THRESHOLD = 0.75
PDF_AI_TEXT_LIMIT = 160
PDF_AI_LONG_TEXT_LIMIT = 360

RISK_EXPLANATION_GUIDANCE = {
    "WEIGHT_MISMATCH": {
        "name": "PDF 重量与 STEP 理论重量不一致",
        "why_review": (
            "PDF 标注重量和 STEP 根据体积、材料密度算出的理论净重偏差超过阈值，"
            "可能是材料、模型版本、图纸重量标注或单位换算不一致。"
        ),
        "review_focus": (
            "核对 PDF 重量、STEP 文件版本、材料密度来源、单位，以及是否存在模型缺失或图纸标注错误。"
        ),
    },
    "LOW_CONFIDENCE_FIELD": {
        "name": "PDF 关键字段置信度低",
        "why_review": (
            "PDF 字段抽取结果不稳定，可能来自标题栏识别不清、字段位置异常、候选值冲突或文本层缺失。"
        ),
        "review_focus": (
            "按图纸原文复核字段值，尤其是图号、零件名、材料和重量，不要直接采用低置信度结果。"
        ),
    },
    "HIGH_RISK_GEOMETRY": {
        "name": "STEP 几何存在高风险候选",
        "why_review": (
            "STEP 解析检测到复杂件、轴类件、小 R、窄槽、深孔、薄壁或长悬臂等加工风险候选。"
        ),
        "review_focus": (
            "结合 STEP 几何和图纸要求确认加工难度、夹持方式、刀具可达性、是否需要特殊工艺或人工报价。"
        ),
    },
}


class AiAssistanceService(Protocol):
    def extract_pdf_field_candidates(
        self,
        *,
        task_id: str,
        pdf_result: dict[str, Any],
    ) -> dict[str, Any]:
        ...

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

    def normalize_technical_requirements(
        self,
        *,
        task_id: str,
        technical_requirements: list[str],
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

    def analyze_override_history(
        self,
        *,
        task_id: str,
        overrides: list[dict[str, Any]],
        quote_result: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class AiAssistanceError(Exception):
    pass


@dataclass(frozen=True)
class OpenAiAssistanceConfig:
    api_key: str
    model: str = DEFAULT_OPENAI_MODEL
    base_url: str = DEFAULT_OPENAI_BASE_URL
    api_mode: str = "responses"
    timeout_seconds: float = DEFAULT_OPENAI_TIMEOUT_SECONDS
    stream: bool = False


class OpenAiAssistanceService:
    prompt_version = "b4-openai-v1"

    def __init__(self, config: OpenAiAssistanceConfig) -> None:
        self.config = config
        self.model_name = config.model

    def extract_pdf_field_candidates(
        self,
        *,
        task_id: str,
        pdf_result: dict[str, Any],
    ) -> dict[str, Any]:
        content = self._request_structured_content(
            schema_name="pdf_field_candidates",
            schema=pdf_field_candidates_schema(),
            system_prompt=(
                "You review extracted PDF text fields for a machining quote. "
                "Return field candidates only from the supplied parser result and "
                "evidence. Do not invent missing critical fields. Write human-readable "
                "reason and notes fields in Simplified Chinese. Return at most "
                f"{PDF_AI_MAX_OUTPUT_CANDIDATES} candidate items, prioritizing "
                "low-confidence, missing, conflicting, or multi-candidate fields. "
                "Return JSON only."
            ),
            user_payload=compact_pdf_field_candidate_payload(
                task_id=task_id,
                pdf_result=pdf_result,
            ),
        )
        return build_ai_output(
            task_id=task_id,
            input_type="pdf_text",
            output_type="field_candidate",
            content=content,
            confidence=bounded_confidence(
                content.get("confidence"),
                default=average_confidence(content.get("candidates") or []),
            ),
            evidence=pdf_evidence(pdf_result),
            model_name=self.model_name,
            prompt_version=self.prompt_version,
        )

    def normalize_material(
        self,
        *,
        task_id: str,
        raw_text: str | None,
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        content = self._request_structured_content(
            schema_name="material_normalization",
            schema=material_normalization_schema(),
            system_prompt=(
                "You normalize machining quote material text. Use only the provided "
                "raw text and evidence. Identify the standard material grade/name "
                "when the raw text is enough, including common steel, stainless "
                "steel, aluminum, copper, plastic, and tool-steel grades. Return a "
                "typical engineering density when the material grade is clear, "
                "prefer density_unit='g/cm3'. Do not invent a material or density "
                "when evidence is insufficient. Write human-readable match_reason "
                "in Simplified Chinese. Return JSON only."
            ),
            user_payload={
                "task_id": task_id,
                "raw_text": raw_text,
                "evidence": evidence,
                "density_unit_preference": "g/cm3",
                "examples": [
                    {"raw_text": "Q235A", "standard_code": "Q235A"},
                    {"raw_text": "45", "standard_code": "S45C"},
                    {"raw_text": "SUS304", "standard_code": "SUS304"},
                    {"raw_text": "6061-T6", "standard_code": "AL6061-T6"},
                ],
            },
        )
        return build_ai_output(
            task_id=task_id,
            input_type="field_text",
            output_type="normalization",
            content=content,
            confidence=bounded_confidence(content.get("confidence")),
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
        content = self._request_structured_content(
            schema_name="surface_treatment_normalization",
            schema=surface_treatment_normalization_schema(),
            system_prompt=(
                "You normalize machining quote surface-treatment text. Use only the "
                "provided raw text and evidence. Do not invent requirements. Write "
                "human-readable match_reason in Simplified Chinese. Return JSON only."
            ),
            user_payload={
                "task_id": task_id,
                "raw_text": raw_text,
                "evidence": evidence,
                "allowed_standard_codes": ["CHEMICAL_NICKEL_PLATING"],
            },
        )
        return build_ai_output(
            task_id=task_id,
            input_type="field_text",
            output_type="normalization",
            content=content,
            confidence=bounded_confidence(content.get("confidence")),
            evidence=evidence,
            model_name=self.model_name,
            prompt_version=self.prompt_version,
        )

    def normalize_technical_requirements(
        self,
        *,
        task_id: str,
        technical_requirements: list[str],
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        content = self._request_structured_content(
            schema_name="technical_requirement_normalization",
            schema=technical_requirement_normalization_schema(),
            system_prompt=(
                "You normalize machining drawing technical requirements. Use only "
                "the supplied requirement text and evidence. Output advisory "
                "candidates only; do not create binding process rules. Write "
                "human-readable match_reason and review_summary in Simplified "
                "Chinese. Return JSON only."
            ),
            user_payload={
                "task_id": task_id,
                "technical_requirements": technical_requirements,
                "evidence": evidence,
                "allowed_standard_codes": [
                    "DEBURR",
                    "HEAT_TREATMENT_REVIEW",
                    "ROUGHNESS_REVIEW",
                    "TOLERANCE_REVIEW",
                    "SURFACE_TREATMENT_REVIEW",
                    "INSPECTION_REVIEW",
                ],
            },
        )
        return build_ai_output(
            task_id=task_id,
            input_type="field_text",
            output_type="normalization",
            content=content,
            confidence=bounded_confidence(
                content.get("confidence"),
                default=average_confidence(content.get("requirements") or []),
            ),
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
        content = self._request_structured_content(
            schema_name="risk_explanation",
            schema=risk_explanation_schema(),
            system_prompt=(
                "You explain structured quote-review risks for a human reviewer. "
                "Do not change the risk code, risk level, or review requirement. "
                "Only explain why manual review is needed and what evidence should "
                "be checked. Do not suggest changing pricing results, risk levels, "
                "or rule outcomes. For WEIGHT_MISMATCH, LOW_CONFIDENCE_FIELD, and "
                "HIGH_RISK_GEOMETRY, follow the supplied guidance. Write explanation "
                "and review_suggestion in Simplified Chinese. "
                "Return JSON only."
            ),
            user_payload=compact_risk_explanation_payload(task_id, risk),
        )
        content = align_risk_explanation_content(content, risk)
        return build_ai_output(
            task_id=task_id,
            input_type="risk_item",
            output_type="risk_suggestion",
            content=content,
            confidence=bounded_confidence(content.get("confidence"), default=0.75),
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
        content = self._request_structured_content(
            schema_name="operation_explanation",
            schema=operation_explanation_schema(),
            system_prompt=(
                "You explain a generated process-route operation to a quote reviewer. "
                "Base the explanation only on the supplied rule result. Do not add, "
                "remove, reorder, or change operations or confidence. Write "
                "trigger_summary, explanation, and review_suggestion in Simplified "
                "Chinese. Return JSON only."
            ),
            user_payload={"task_id": task_id, "operation": operation},
        )
        return build_ai_output(
            task_id=task_id,
            input_type="rule_result",
            output_type="explanation",
            content=content,
            confidence=bounded_confidence(content.get("confidence"), default=0.75),
            evidence=operation.get("trigger_reasons", []),
            model_name=self.model_name,
            prompt_version=self.prompt_version,
        )

    def analyze_override_history(
        self,
        *,
        task_id: str,
        overrides: list[dict[str, Any]],
        quote_result: dict[str, Any],
    ) -> dict[str, Any]:
        content = self._request_structured_content(
            schema_name="override_history_analysis",
            schema=override_history_analysis_schema(),
            system_prompt=(
                "You summarize manual override history for quote process improvement. "
                "Do not change the quote, prices, rules, or approval status. Return "
                "advisory JSON only. Write summary, frequent_categories, and "
                "suggestions in Simplified Chinese."
            ),
            user_payload={
                "task_id": task_id,
                "quote_id": quote_result.get("quote_id"),
                "quote_status": quote_result.get("status"),
                "overrides": overrides,
                "summary": quote_result.get("summary"),
            },
        )
        return build_ai_output(
            task_id=task_id,
            input_type="override_history",
            output_type="analysis",
            content=content,
            confidence=bounded_confidence(content.get("confidence"), default=0.65),
            evidence=override_evidence(overrides),
            model_name=self.model_name,
            prompt_version=self.prompt_version,
        )

    def _request_structured_content(
        self,
        *,
        schema_name: str,
        schema: dict[str, Any],
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> dict[str, Any]:
        user_text = json.dumps(user_payload, ensure_ascii=False)
        if self.config.api_mode == "chat_completions":
            response_payload = self._create_chat_completion(
                {
                    "model": self.config.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": (
                                f"{user_text}\n\nReturn a JSON object matching this "
                                f"schema named {schema_name}:\n"
                                f"{json.dumps(schema, ensure_ascii=False)}\n\n"
                                "Return the object directly. Do not wrap it in a "
                                f"top-level property such as {schema_name}."
                            ),
                        },
                    ],
                    "response_format": {"type": "json_object"},
                }
            )
            response_text = extract_chat_completion_text(response_payload)
        else:
            response_payload = self._create_response(
                {
                    "model": self.config.model,
                    "input": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_text},
                    ],
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": schema_name,
                            "schema": schema,
                            "strict": True,
                        }
                    },
                }
            )
            response_text = extract_response_text(response_payload)
        try:
            content = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise AiAssistanceError("AI response was not valid JSON") from exc
        if not isinstance(content, dict):
            raise AiAssistanceError("AI response JSON must be an object")
        content = normalize_structured_content(schema_name, content)
        validate_structured_content(schema_name, schema, content)
        return content

    def _create_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = self.config.base_url.rstrip("/") + "/responses"
        return self._post_json(url, payload, response_kind="responses")

    def _create_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        return self._post_json(url, payload, response_kind="chat_completions")

    def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        response_kind: str,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        request_payload = dict(payload)
        if self.config.stream:
            request_payload["stream"] = True
        try:
            with httpx.Client(timeout=self.config.timeout_seconds) as client:
                if self.config.stream:
                    with client.stream(
                        "POST",
                        url,
                        headers=headers,
                        json=request_payload,
                    ) as response:
                        if response.status_code >= 400:
                            body = response.read().decode("utf-8", errors="replace")
                            raise AiAssistanceError(
                                f"AI request failed with status {response.status_code}: "
                                f"{body[:500]}"
                            )
                        response_text = collect_openai_stream_text(response.iter_lines())
                        return stream_text_payload(response_kind, response_text)

                response = client.post(url, headers=headers, json=request_payload)
        except httpx.RequestError as exc:
            raise AiAssistanceError(f"AI request failed: {exc}") from exc
        except ValueError as exc:
            raise AiAssistanceError(str(exc)) from exc

        if response.status_code >= 400:
            raise AiAssistanceError(
                f"AI request failed with status {response.status_code}: "
                f"{response.text[:500]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise AiAssistanceError("AI response was not JSON") from exc


class UnavailableOnErrorAiAssistanceService:
    def __init__(
        self,
        primary: AiAssistanceService,
    ) -> None:
        self.primary = primary

    def extract_pdf_field_candidates(
        self,
        *,
        task_id: str,
        pdf_result: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return self.primary.extract_pdf_field_candidates(
                task_id=task_id,
                pdf_result=pdf_result,
            )
        except Exception as exc:
            return unavailable_field_candidates_output(
                task_id=task_id,
                pdf_result=pdf_result,
                exc=exc,
            )

    def normalize_material(
        self,
        *,
        task_id: str,
        raw_text: str | None,
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            return self.primary.normalize_material(
                task_id=task_id,
                raw_text=raw_text,
                evidence=evidence,
            )
        except Exception as exc:
            return unavailable_normalization_output(
                task_id=task_id,
                raw_text=raw_text,
                evidence=evidence,
                exc=exc,
                content_extra={
                    "standard_code": None,
                    "standard_name": None,
                    "density": None,
                    "density_unit": None,
                    "match_reason": "AI provider unavailable; no material normalization generated.",
                },
            )

    def normalize_surface_treatment(
        self,
        *,
        task_id: str,
        raw_text: str | None,
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            return self.primary.normalize_surface_treatment(
                task_id=task_id,
                raw_text=raw_text,
                evidence=evidence,
            )
        except Exception as exc:
            return unavailable_normalization_output(
                task_id=task_id,
                raw_text=raw_text,
                evidence=evidence,
                exc=exc,
                content_extra={
                    "standard_code": None,
                    "standard_name": None,
                    "match_reason": "AI provider unavailable; no surface treatment normalization generated.",
                },
            )

    def normalize_technical_requirements(
        self,
        *,
        task_id: str,
        technical_requirements: list[str],
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            return self.primary.normalize_technical_requirements(
                task_id=task_id,
                technical_requirements=technical_requirements,
                evidence=evidence,
            )
        except Exception as exc:
            return unavailable_normalization_output(
                task_id=task_id,
                raw_text="\n".join(technical_requirements),
                evidence=evidence,
                exc=exc,
                content_extra={
                    "requirements": [],
                    "review_summary": (
                        "AI provider unavailable; no technical requirement "
                        "normalization generated."
                    ),
                },
            )

    def explain_risk(
        self,
        *,
        task_id: str,
        risk: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return self.primary.explain_risk(task_id=task_id, risk=risk)
        except Exception as exc:
            return unavailable_risk_output(task_id=task_id, risk=risk, exc=exc)

    def explain_operation(
        self,
        *,
        task_id: str,
        operation: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return self.primary.explain_operation(task_id=task_id, operation=operation)
        except Exception as exc:
            return unavailable_operation_output(
                task_id=task_id,
                operation=operation,
                exc=exc,
            )

    def analyze_override_history(
        self,
        *,
        task_id: str,
        overrides: list[dict[str, Any]],
        quote_result: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return self.primary.analyze_override_history(
                task_id=task_id,
                overrides=overrides,
                quote_result=quote_result,
            )
        except Exception as exc:
            return unavailable_analysis_output(
                task_id=task_id,
                overrides=overrides,
                quote_result=quote_result,
                exc=exc,
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


def build_ai_assistance_service() -> AiAssistanceService:
    provider = os.getenv("PRICE_AI_PROVIDER", "auto").strip().lower()

    api_key = (
        os.getenv("OPENAI_API_KEY")
        or os.getenv("PRICE_AI_API_KEY")
        or os.getenv("LLM_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
    )
    if not api_key:
        return UnconfiguredAiAssistanceService()

    if provider in {"", "disabled", "off"}:
        return UnconfiguredAiAssistanceService()

    if provider not in {"auto", "openai"}:
        return UnconfiguredAiAssistanceService()

    base_url = (
        os.getenv("PRICE_AI_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("LLM_BASE_URL")
        or DEFAULT_OPENAI_BASE_URL
    )
    api_mode = (
        os.getenv("PRICE_AI_API_MODE")
        or os.getenv("LLM_API_MODE")
        or infer_api_mode(base_url)
    )
    config = OpenAiAssistanceConfig(
        api_key=api_key,
        model=os.getenv("PRICE_AI_MODEL")
        or os.getenv("OPENAI_MODEL")
        or os.getenv("LLM_MODEL")
        or DEFAULT_OPENAI_MODEL,
        base_url=base_url,
        api_mode=api_mode,
        timeout_seconds=float(
            os.getenv("PRICE_AI_TIMEOUT_SECONDS", str(DEFAULT_OPENAI_TIMEOUT_SECONDS))
        ),
        stream=bool_env("PRICE_AI_STREAM", bool_env("LLM_STREAM", False)),
    )
    return UnavailableOnErrorAiAssistanceService(OpenAiAssistanceService(config))


class UnconfiguredAiAssistanceService:
    model_name = "ai-unconfigured"
    prompt_version = "b4-ai-unavailable-v1"

    def extract_pdf_field_candidates(
        self,
        *,
        task_id: str,
        pdf_result: dict[str, Any],
    ) -> dict[str, Any]:
        return unavailable_field_candidates_output(
            task_id=task_id,
            pdf_result=pdf_result,
            exc=AiAssistanceError("AI provider is not configured"),
        )

    def normalize_material(
        self,
        *,
        task_id: str,
        raw_text: str | None,
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return unavailable_normalization_output(
            task_id=task_id,
            raw_text=raw_text,
            evidence=evidence,
            exc=AiAssistanceError("AI provider is not configured"),
            content_extra={
                "standard_code": None,
                "standard_name": None,
                "density": None,
                "density_unit": None,
                "match_reason": "AI provider is not configured; no material normalization generated.",
            },
        )

    def normalize_surface_treatment(
        self,
        *,
        task_id: str,
        raw_text: str | None,
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return unavailable_normalization_output(
            task_id=task_id,
            raw_text=raw_text,
            evidence=evidence,
            exc=AiAssistanceError("AI provider is not configured"),
            content_extra={
                "standard_code": None,
                "standard_name": None,
                "match_reason": "AI provider is not configured; no surface treatment normalization generated.",
            },
        )

    def normalize_technical_requirements(
        self,
        *,
        task_id: str,
        technical_requirements: list[str],
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return unavailable_normalization_output(
            task_id=task_id,
            raw_text="\n".join(technical_requirements),
            evidence=evidence,
            exc=AiAssistanceError("AI provider is not configured"),
            content_extra={
                "requirements": [],
                "review_summary": (
                    "AI provider is not configured; no technical requirement "
                    "normalization generated."
                ),
            },
        )

    def explain_risk(
        self,
        *,
        task_id: str,
        risk: dict[str, Any],
    ) -> dict[str, Any]:
        return unavailable_risk_output(
            task_id=task_id,
            risk=risk,
            exc=AiAssistanceError("AI provider is not configured"),
        )

    def explain_operation(
        self,
        *,
        task_id: str,
        operation: dict[str, Any],
    ) -> dict[str, Any]:
        return unavailable_operation_output(
            task_id=task_id,
            operation=operation,
            exc=AiAssistanceError("AI provider is not configured"),
        )

    def analyze_override_history(
        self,
        *,
        task_id: str,
        overrides: list[dict[str, Any]],
        quote_result: dict[str, Any],
    ) -> dict[str, Any]:
        return unavailable_analysis_output(
            task_id=task_id,
            overrides=overrides,
            quote_result=quote_result,
            exc=AiAssistanceError("AI provider is not configured"),
        )


def unavailable_normalization_output(
    *,
    task_id: str,
    raw_text: str | None,
    evidence: list[dict[str, Any]],
    exc: Exception,
    content_extra: dict[str, Any],
) -> dict[str, Any]:
    content = {
        "raw_text": raw_text,
        "available": False,
        "error_message": str(exc),
        **content_extra,
    }
    return build_ai_output(
        task_id=task_id,
        input_type="field_text",
        output_type="normalization",
        content=content,
        confidence=0.0,
        evidence=evidence,
        model_name=ai_error_model_name(exc),
        prompt_version="b4-ai-unavailable-v1",
    )


def unavailable_field_candidates_output(
    *,
    task_id: str,
    pdf_result: dict[str, Any],
    exc: Exception,
) -> dict[str, Any]:
    return build_ai_output(
        task_id=task_id,
        input_type="pdf_text",
        output_type="field_candidate",
        content={
            "available": False,
            "error_message": str(exc),
            "candidates": [],
            "review_required": True,
            "notes": "AI provider unavailable; review parser field evidence directly.",
        },
        confidence=0.0,
        evidence=pdf_evidence(pdf_result),
        model_name=ai_error_model_name(exc),
        prompt_version="b4-ai-unavailable-v1",
    )


def unavailable_risk_output(
    *,
    task_id: str,
    risk: dict[str, Any],
    exc: Exception,
) -> dict[str, Any]:
    return build_ai_output(
        task_id=task_id,
        input_type="risk_item",
        output_type="risk_suggestion",
        content={
            "risk_code": risk.get("code"),
            "risk_level": risk.get("level"),
            "original_message": risk.get("message"),
            "available": False,
            "error_message": str(exc),
            "explanation": "",
            "review_suggestion": "AI 当前不可用，请直接按结构化风险证据进行人工复核。",
            "requires_review": bool(risk.get("requires_review")),
        },
        confidence=0.0,
        evidence=risk.get("evidence", []),
        model_name=ai_error_model_name(exc),
        prompt_version="b4-ai-unavailable-v1",
    )


def unavailable_operation_output(
    *,
    task_id: str,
    operation: dict[str, Any],
    exc: Exception,
) -> dict[str, Any]:
    return build_ai_output(
        task_id=task_id,
        input_type="rule_result",
        output_type="explanation",
        content={
            "operation_code": operation.get("operation_code"),
            "operation_name": operation.get("operation_name"),
            "available": False,
            "error_message": str(exc),
            "trigger_summary": "",
            "explanation": "",
            "review_suggestion": "AI provider unavailable; review the rule trigger reasons directly.",
            "preserves_rule_result": True,
        },
        confidence=0.0,
        evidence=operation.get("trigger_reasons", []),
        model_name=ai_error_model_name(exc),
        prompt_version="b4-ai-unavailable-v1",
    )


def unavailable_analysis_output(
    *,
    task_id: str,
    overrides: list[dict[str, Any]],
    quote_result: dict[str, Any],
    exc: Exception,
) -> dict[str, Any]:
    return build_ai_output(
        task_id=task_id,
        input_type="override_history",
        output_type="analysis",
        content={
            "available": False,
            "error_message": str(exc),
            "override_count": len(overrides),
            "target_type_counts": override_target_counts(overrides),
            "frequent_categories": [],
            "summary": "",
            "suggestions": [
                "AI provider unavailable; review manual override records directly."
            ],
            "quote_status": quote_result.get("status"),
            "confidence": 0.0,
        },
        confidence=0.0,
        evidence=override_evidence(overrides),
        model_name=ai_error_model_name(exc),
        prompt_version="b4-ai-unavailable-v1",
    )


def ai_error_model_name(exc: Exception) -> str:
    message = str(exc).lower()
    if (
        "json" in message
        or "schema" in message
        or "did not contain" in message
        or "must be an object" in message
    ):
        return "ai-format-error"
    return "ai-unavailable"


def infer_api_mode(base_url: str) -> str:
    normalized = base_url.lower()
    if "dashscope" in normalized or "compatible-mode" in normalized:
        return "chat_completions"
    return "responses"


def bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def stream_text_payload(response_kind: str, response_text: str) -> dict[str, Any]:
    if response_kind == "chat_completions":
        return {"choices": [{"message": {"content": response_text}}]}
    return {"output_text": response_text}


def collect_openai_stream_text(lines: Iterable[Any]) -> str:
    chunks: list[str] = []
    for raw_line in lines:
        line = decode_stream_line(raw_line)
        if not line or line.startswith(":"):
            continue
        if line.startswith("data:"):
            line = line[len("data:") :].strip()
        if line == "[DONE]":
            break
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        chunks.extend(stream_event_text_chunks(event))

    response_text = "".join(chunks).strip()
    if not response_text:
        raise ValueError("AI stream did not contain text content")
    return response_text


def decode_stream_line(raw_line: Any) -> str:
    if isinstance(raw_line, bytes):
        return raw_line.decode("utf-8", errors="replace").strip()
    return str(raw_line or "").strip()


def stream_event_text_chunks(event: dict[str, Any]) -> list[str]:
    chunks: list[str] = []
    choices = event.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0]
        if isinstance(choice, dict):
            delta = choice.get("delta") or {}
            message = choice.get("message") or {}
            if isinstance(delta, dict):
                chunks.extend(content_chunks(delta.get("content")))
            if isinstance(message, dict):
                chunks.extend(content_chunks(message.get("content")))

    event_type = event.get("type")
    delta = event.get("delta")
    if event_type in {"response.output_text.delta", "response.output_text.done"}:
        chunks.extend(content_chunks(delta))
    chunks.extend(content_chunks(event.get("output_text")))
    return chunks


def content_chunks(content: Any) -> list[str]:
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        return [
            str(item.get("text") or "")
            for item in content
            if isinstance(item, dict) and item.get("text")
        ]
    return []


def extract_response_text(response_payload: dict[str, Any]) -> str:
    output_text = response_payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    chunks: list[str] = []
    for item in response_payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    response_text = "".join(chunks).strip()
    if not response_text:
        raise AiAssistanceError("AI response did not contain output text")
    return response_text


def extract_chat_completion_text(response_payload: dict[str, Any]) -> str:
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AiAssistanceError("AI chat completion response did not contain choices")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise AiAssistanceError("AI chat completion choice was not an object")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise AiAssistanceError("AI chat completion choice did not contain a message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise AiAssistanceError("AI chat completion did not contain message content")
    return content


def bounded_confidence(value: Any, *, default: float = 0.5) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return max(0.0, min(1.0, confidence))


def normalize_structured_content(schema_name: str, content: dict[str, Any]) -> dict[str, Any]:
    if schema_name != "pdf_field_candidates":
        return content

    normalized = dict(content)
    candidates = normalized.get("candidates")
    if isinstance(candidates, list):
        normalized["candidates"] = [
            normalize_pdf_field_candidate(candidate)
            for candidate in candidates
            if isinstance(candidate, dict)
        ][:PDF_AI_MAX_OUTPUT_CANDIDATES]
    return normalized


def compact_risk_explanation_payload(
    task_id: str,
    risk: dict[str, Any],
) -> dict[str, Any]:
    risk_code = str(risk.get("code") or "")
    return {
        "task_id": task_id,
        "risk": {
            "code": risk.get("code"),
            "level": risk.get("level"),
            "message": risk.get("message"),
            "requires_review": bool(risk.get("requires_review")),
            "source": risk.get("source"),
            "evidence": compact_ai_evidence(risk.get("evidence")),
        },
        "guidance": RISK_EXPLANATION_GUIDANCE.get(risk_code),
        "constraints": {
            "must_preserve_risk_code": risk.get("code"),
            "must_preserve_risk_level": risk.get("level"),
            "must_preserve_requires_review": bool(risk.get("requires_review")),
            "explain_only_manual_review_reason": True,
            "do_not_change_pricing_or_rule_results": True,
        },
    }


def align_risk_explanation_content(
    content: dict[str, Any],
    risk: dict[str, Any],
) -> dict[str, Any]:
    aligned = dict(content)
    aligned["risk_code"] = risk.get("code")
    aligned["risk_level"] = risk.get("level")
    aligned["original_message"] = risk.get("message")
    aligned["requires_review"] = bool(risk.get("requires_review"))
    aligned["confidence"] = bounded_confidence(aligned.get("confidence"), default=0.75)

    if not str(aligned.get("explanation") or "").strip():
        guidance = RISK_EXPLANATION_GUIDANCE.get(str(risk.get("code") or ""))
        aligned["explanation"] = (
            guidance["why_review"]
            if guidance
            else "该风险由系统规则生成，需要结合结构化证据进行人工复核。"
        )
    if not str(aligned.get("review_suggestion") or "").strip():
        guidance = RISK_EXPLANATION_GUIDANCE.get(str(risk.get("code") or ""))
        aligned["review_suggestion"] = (
            guidance["review_focus"]
            if guidance
            else "请核对风险证据、图纸原文、STEP 结果和报价规则命中原因。"
        )
    return aligned


def normalize_pdf_field_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(candidate)
    if "candidate_value" not in normalized and "value" in normalized:
        normalized["candidate_value"] = normalized.get("value")

    value = normalized.get("candidate_value")
    if isinstance(value, dict):
        normalized["candidate_value"] = json.dumps(
            value,
            ensure_ascii=False,
            default=str,
        )
    elif isinstance(value, list):
        normalized["candidate_value"] = [
            item
            if item is None or isinstance(item, (str, int, float, bool))
            else json.dumps(item, ensure_ascii=False, default=str)
            for item in value
        ]

    normalized["field_name"] = str(normalized.get("field_name") or "")
    normalized["confidence"] = bounded_confidence(normalized.get("confidence"))
    normalized["reason"] = str(normalized.get("reason") or "")
    normalized["evidence_summary"] = str(normalized.get("evidence_summary") or "")
    return {
        key: normalized.get(key)
        for key in (
            "field_name",
            "candidate_value",
            "confidence",
            "reason",
            "evidence_summary",
        )
    }


def validate_structured_content(
    schema_name: str,
    schema: dict[str, Any],
    content: dict[str, Any],
) -> None:
    errors: list[str] = []
    validate_schema_value(content, schema, schema_name, errors)
    if errors:
        raise AiAssistanceError(
            f"AI response schema validation failed for {schema_name}: {errors[0]}"
        )


def validate_schema_value(
    value: Any,
    schema: dict[str, Any],
    path: str,
    errors: list[str],
) -> None:
    if errors:
        return

    expected_type = schema.get("type")
    if expected_type is not None and not schema_type_matches(value, expected_type):
        errors.append(f"{path} expected {expected_type}, got {type(value).__name__}")
        return

    if value is None:
        return

    if isinstance(value, dict):
        required = schema.get("required") or []
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key} is required")
                return

        properties = schema.get("properties") or {}
        additional_properties = schema.get("additionalProperties", True)
        if additional_properties is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}.{key} is not allowed")
                    return

        for key, property_schema in properties.items():
            if key in value:
                validate_schema_value(
                    value[key],
                    property_schema,
                    f"{path}.{key}",
                    errors,
                )
                if errors:
                    return

        if isinstance(additional_properties, dict):
            for key, item in value.items():
                if key in properties:
                    continue
                validate_schema_value(
                    item,
                    additional_properties,
                    f"{path}.{key}",
                    errors,
                )
                if errors:
                    return

    if isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                validate_schema_value(item, item_schema, f"{path}[{index}]", errors)
                if errors:
                    return

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            errors.append(f"{path} must be >= {minimum}")
            return
        if maximum is not None and value > maximum:
            errors.append(f"{path} must be <= {maximum}")


def schema_type_matches(value: Any, expected_type: Any) -> bool:
    if isinstance(expected_type, list):
        return any(schema_type_matches(value, item) for item in expected_type)
    if expected_type == "null":
        return value is None
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


def nullable_string_schema() -> dict[str, Any]:
    return {"type": ["string", "null"]}


def nullable_number_schema() -> dict[str, Any]:
    return {"type": ["number", "null"]}


def material_normalization_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "raw_text",
            "standard_code",
            "standard_name",
            "density",
            "density_unit",
            "match_reason",
            "confidence",
        ],
        "properties": {
            "raw_text": nullable_string_schema(),
            "standard_code": nullable_string_schema(),
            "standard_name": nullable_string_schema(),
            "density": nullable_number_schema(),
            "density_unit": nullable_string_schema(),
            "match_reason": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }


def surface_treatment_normalization_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "raw_text",
            "standard_code",
            "standard_name",
            "match_reason",
            "confidence",
        ],
        "properties": {
            "raw_text": nullable_string_schema(),
            "standard_code": nullable_string_schema(),
            "standard_name": nullable_string_schema(),
            "match_reason": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }


def pdf_field_candidates_schema() -> dict[str, Any]:
    candidate_value_schema = {
        "type": ["string", "number", "boolean", "array", "null"],
        "items": {"type": ["string", "number", "boolean", "null"]},
    }
    candidate_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "field_name",
            "candidate_value",
            "confidence",
            "reason",
            "evidence_summary",
        ],
        "properties": {
            "field_name": {"type": "string"},
            "candidate_value": candidate_value_schema,
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "reason": {"type": "string"},
            "evidence_summary": {"type": "string"},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["candidates", "review_required", "notes", "confidence"],
        "properties": {
            "candidates": {
                "type": "array",
                "items": candidate_schema,
                "maxItems": PDF_AI_MAX_OUTPUT_CANDIDATES,
            },
            "review_required": {"type": "boolean"},
            "notes": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }


def technical_requirement_normalization_schema() -> dict[str, Any]:
    requirement_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "raw_text",
            "standard_code",
            "requirement_type",
            "match_reason",
            "confidence",
            "requires_review",
        ],
        "properties": {
            "raw_text": {"type": "string"},
            "standard_code": nullable_string_schema(),
            "requirement_type": {"type": "string"},
            "match_reason": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "requires_review": {"type": "boolean"},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["requirements", "review_summary", "confidence"],
        "properties": {
            "requirements": {"type": "array", "items": requirement_schema},
            "review_summary": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }


def risk_explanation_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "risk_code",
            "risk_level",
            "original_message",
            "explanation",
            "review_suggestion",
            "requires_review",
            "confidence",
        ],
        "properties": {
            "risk_code": nullable_string_schema(),
            "risk_level": nullable_string_schema(),
            "original_message": nullable_string_schema(),
            "explanation": {"type": "string"},
            "review_suggestion": {"type": "string"},
            "requires_review": {"type": "boolean"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }


def operation_explanation_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "operation_code",
            "operation_name",
            "trigger_summary",
            "explanation",
            "review_suggestion",
            "preserves_rule_result",
            "confidence",
        ],
        "properties": {
            "operation_code": nullable_string_schema(),
            "operation_name": nullable_string_schema(),
            "trigger_summary": {"type": "string"},
            "explanation": {"type": "string"},
            "review_suggestion": {"type": "string"},
            "preserves_rule_result": {"type": "boolean"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }


def override_history_analysis_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "override_count",
            "target_type_counts",
            "frequent_categories",
            "summary",
            "suggestions",
            "quote_status",
            "confidence",
        ],
        "properties": {
            "override_count": {"type": "integer", "minimum": 0},
            "target_type_counts": {
                "type": "object",
                "additionalProperties": {"type": "integer", "minimum": 0},
            },
            "frequent_categories": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
            "suggestions": {"type": "array", "items": {"type": "string"}},
            "quote_status": nullable_string_schema(),
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }


def normalize_key(value: str | None) -> str:
    if not value:
        return ""
    return "_".join(value.strip().lower().replace("/", " ").split())


def average_confidence(items: Any, *, default: float = 0.5) -> float:
    if not isinstance(items, list) or not items:
        return default
    values = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            values.append(float(item.get("confidence")))
        except (TypeError, ValueError):
            continue
    if not values:
        return default
    return bounded_confidence(sum(values) / len(values), default=default)


def compact_pdf_field_candidate_payload(
    *,
    task_id: str,
    pdf_result: dict[str, Any],
) -> dict[str, Any]:
    review_fields = pdf_ai_review_fields(pdf_result)
    field_details = compact_pdf_field_details(
        pdf_result,
        review_fields=review_fields,
    )
    payload = {
        "task_id": task_id,
        "parser_name": pdf_result.get("parser_name"),
        "review_focus_fields": review_fields,
        "field_details": field_details,
        "technical_requirements": compact_ai_list(
            pdf_result.get("technical_requirements"),
            limit=PDF_AI_MAX_TECHNICAL_REQUIREMENTS,
            text_limit=PDF_AI_LONG_TEXT_LIMIT,
        ),
    }
    if not field_details:
        payload["field_evidence"] = compact_pdf_field_evidence(pdf_result)
        payload["field_confidence"] = pdf_result.get("field_confidence")
        payload["text_blocks_sample"] = compact_pdf_text_blocks(pdf_result)
    return payload


def compact_pdf_field_details(
    pdf_result: dict[str, Any],
    *,
    review_fields: list[str] | None = None,
) -> dict[str, Any]:
    field_details = pdf_result.get("field_details") or {}
    if not isinstance(field_details, dict):
        return {}

    focused_fields = set(review_fields or [])
    compact: dict[str, Any] = {}
    for field_name, detail in field_details.items():
        if not isinstance(detail, dict):
            continue
        if focused_fields and field_name not in focused_fields:
            continue

        compact_detail: dict[str, Any] = {}
        for key in ("raw_text", "value", "confidence", "extract_method"):
            if key in detail:
                compact_detail[key] = compact_ai_value(
                    detail.get(key),
                    text_limit=PDF_AI_LONG_TEXT_LIMIT,
                )

        evidence = compact_ai_evidence(detail.get("evidence"))
        if evidence:
            compact_detail["evidence"] = evidence

        candidates = compact_ai_candidates(detail.get("candidates"))
        if should_include_compact_candidates(detail, candidates):
            compact_detail["candidates"] = candidates

        compact[str(field_name)] = compact_detail

    return compact


def pdf_ai_review_fields(pdf_result: dict[str, Any]) -> list[str]:
    field_details = pdf_result.get("field_details") or {}
    if not isinstance(field_details, dict):
        return []

    review_fields = []
    for field_name, detail in field_details.items():
        if not isinstance(detail, dict):
            continue
        confidence = bounded_confidence(detail.get("confidence"), default=1.0)
        candidates = detail.get("candidates")
        if (
            pdf_ai_value_is_missing(detail.get("value"))
            or confidence < PDF_AI_REVIEW_CONFIDENCE_THRESHOLD
            or (isinstance(candidates, list) and len(candidates) > 1)
        ):
            review_fields.append(str(field_name))

    return review_fields


def pdf_ai_value_is_missing(value: Any) -> bool:
    return value in (None, "") or (isinstance(value, list) and not value)


def should_include_compact_candidates(
    detail: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> bool:
    raw_candidates = detail.get("candidates")
    if not candidates:
        return False
    if isinstance(raw_candidates, list) and len(raw_candidates) > 1:
        return True
    return detail.get("value") in (None, "", [])


def compact_pdf_field_evidence(pdf_result: dict[str, Any]) -> dict[str, Any]:
    field_evidence = pdf_result.get("field_evidence") or {}
    if not isinstance(field_evidence, dict):
        return {}
    return {
        str(field_name): evidence
        for field_name, evidence in (
            (field_name, compact_ai_evidence(value))
            for field_name, value in field_evidence.items()
        )
        if evidence
    }


def compact_pdf_text_blocks(pdf_result: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = pdf_result.get("text_blocks") or []
    if not isinstance(blocks, list):
        return []

    compact_blocks = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        text = block.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        compact_blocks.append(
            {
                "page": block.get("page"),
                "block_index": block.get("block_index"),
                "bbox": compact_ai_value(block.get("bbox"), list_limit=4),
                "text": truncate_ai_text(text, PDF_AI_TEXT_LIMIT),
            }
        )
        if len(compact_blocks) >= PDF_AI_MAX_TEXT_BLOCKS:
            break

    return compact_blocks


def compact_ai_candidates(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    compact_candidates = []
    for candidate in value:
        if not isinstance(candidate, dict):
            continue
        compact_candidate: dict[str, Any] = {}
        for key in ("field_name", "value", "raw_text", "confidence", "extract_method"):
            if key in candidate:
                compact_candidate[key] = compact_ai_value(
                    candidate.get(key),
                    text_limit=PDF_AI_TEXT_LIMIT,
                )
        evidence = compact_ai_evidence(candidate.get("evidence"), limit=1)
        if evidence:
            compact_candidate["evidence"] = evidence
        compact_candidates.append(compact_candidate)
        if len(compact_candidates) >= PDF_AI_MAX_FIELD_CANDIDATES:
            break

    return compact_candidates


def compact_ai_evidence(value: Any, *, limit: int = PDF_AI_MAX_EVIDENCE_ITEMS) -> Any:
    if isinstance(value, dict):
        return compact_ai_evidence_item(value)
    if not isinstance(value, list):
        return None

    compact_items = []
    for item in value:
        if not isinstance(item, dict):
            continue
        compact_items.append(compact_ai_evidence_item(item))
        if len(compact_items) >= limit:
            break
    return compact_items


def compact_ai_evidence_item(item: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = (
        "source_type",
        "file_id",
        "page",
        "location",
        "raw_text",
        "rule_code",
        "confidence",
        "extract_method",
    )
    return {
        key: compact_ai_value(item.get(key), text_limit=PDF_AI_TEXT_LIMIT)
        for key in allowed_keys
        if item.get(key) not in (None, "")
    }


def compact_ai_list(
    value: Any,
    *,
    limit: int,
    text_limit: int = PDF_AI_TEXT_LIMIT,
) -> list[Any]:
    if not isinstance(value, list):
        return []
    return [
        compact_ai_value(item, text_limit=text_limit)
        for item in value[:limit]
    ]


def compact_ai_value(
    value: Any,
    *,
    text_limit: int = PDF_AI_TEXT_LIMIT,
    list_limit: int = PDF_AI_MAX_EVIDENCE_ITEMS,
) -> Any:
    if isinstance(value, str):
        return truncate_ai_text(value, text_limit)
    if isinstance(value, list):
        return [
            compact_ai_value(item, text_limit=text_limit, list_limit=list_limit)
            for item in value[:list_limit]
        ]
    if isinstance(value, dict):
        return {
            str(key): compact_ai_value(
                nested,
                text_limit=text_limit,
                list_limit=list_limit,
            )
            for key, nested in value.items()
            if key != "evidence_detail"
        }
    return value


def truncate_ai_text(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def source_text(source: Any) -> str:
    if not isinstance(source, dict):
        return ""
    parts = [
        source.get("source_type"),
        f"file={source.get('file_id')}" if source.get("file_id") else None,
        f"page={source.get('page')}" if source.get("page") else None,
        source.get("location"),
        source.get("raw_text"),
        source.get("rule_code"),
    ]
    return " | ".join(str(part) for part in parts if part not in (None, ""))


def pdf_evidence(pdf_result: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = []
    field_evidence = pdf_result.get("field_evidence") or {}
    if isinstance(field_evidence, dict):
        evidence.extend(
            item for item in field_evidence.values() if isinstance(item, dict)
        )
    for key in (
        "tolerance_evidence",
        "roughness_evidence",
        "technical_requirement_evidence",
    ):
        values = pdf_result.get(key) or []
        if isinstance(values, list):
            evidence.extend(item for item in values if isinstance(item, dict))
    return evidence


def override_evidence(overrides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence = []
    for override in overrides:
        if not isinstance(override, dict):
            continue
        evidence.append(
            {
                "source_type": "manual",
                "file_id": None,
                "page": None,
                "location": override.get("target_type"),
                "raw_text": json.dumps(override, ensure_ascii=False, default=str),
                "rule_code": str(override.get("override_id") or "OVERRIDE_HISTORY"),
            }
        )
    return evidence


def override_target_counts(overrides: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for override in overrides:
        target_type = str(override.get("target_type") or "unknown")
        counts[target_type] = counts.get(target_type, 0) + 1
    return counts


def now_iso() -> str:
    return datetime.now(CHINA_TZ).isoformat(timespec="seconds")
