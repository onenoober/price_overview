from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from .mock_parser import (
    build_mock_pdf_extract_result,
    build_mock_step_feature_result,
    risk_item,
    source_ref,
)
from .storage import REPO_ROOT


ParserMode = Literal["mock", "auto", "real"]

PDF_FIELD_KEYS = (
    "drawing_no",
    "part_name",
    "revision",
    "material_raw",
    "weight_raw",
    "scale",
    "heat_treatment_raw",
    "surface_treatment_raw",
)

PDF_FIELD_PATTERNS = {
    "drawing_no": (
        r"(?:图号|图紙番号|图纸编号|物件料号|Drawing\s*(?:No\.?|Number)|DWG\.?\s*NO\.?|Part\s*No\.?|零件图号|件号|编号)\s*[:：#]?\s*(?P<value>[A-Za-z0-9][A-Za-z0-9_.\-\/#]{1,40})",
    ),
    "part_name": (
        r"(?:零件名称|零件名|品名|Part\s*Name|Description)\s*[:：]?\s*(?P<value>[^\r\n]{1,80})",
    ),
    "revision": (
        r"(?:版本|版次|修订|Revision|Rev\.?)\s*[:：]?\s*(?P<value>[A-Za-z0-9_.\-]{1,20})",
    ),
    "material_raw": (
        r"(?:材料|材质|Material|Mat\.?)\s*[:：]?\s*(?P<value>[A-Za-z0-9\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff+\-_.\/# ]{1,50})",
        r"\b(?P<value>SUS\s*304|SUS304|S45C|SKD11|AL\s*6061|AL6061|A6061|6061(?:-T6)?|45#|Q235|POM|PEEK|H59)\b",
    ),
    "weight_raw": (
        r"(?:重量|净重|单重|Weight|WT\.?)\s*[:：]?\s*(?P<value>\d+(?:[.,]\d+)?\s*(?:kg|kgs|g|KG|G|千克|克))",
    ),
    "scale": (
        r"(?:比例|Scale)\s*[:：]?\s*(?P<value>\d+(?:\.\d+)?\s*[:：]\s*\d+(?:\.\d+)?|NTS|n\.?t\.?s\.?)",
    ),
    "heat_treatment_raw": (
        r"(?:热处理|Heat\s*Treatment)\s*[:：]?\s*(?P<value>[^\r\n]{1,80})",
    ),
    "surface_treatment_raw": (
        r"(?:表面处理|表面要求|Surface\s*Treatment|Finish|Plating)\s*[:：]?\s*(?P<value>[^\r\n]{1,80})",
    ),
}

PDF_TITLE_FIELD_LABELS = {
    "drawing_no": ("图号", "图纸编号", "物件料号", "料号", "件号", "Drawing No", "Part No"),
    "part_name": ("零件名称", "零件名", "品名", "Part Name", "Description"),
    "revision": ("版本", "版 本", "版次", "修订", "Revision", "Rev"),
    "material_raw": ("材料", "材质", "Material", "Mat"),
    "weight_raw": ("重量", "重量(Kg)", "重量(KG)", "Weight", "WT"),
    "scale": ("比例", "比 例", "Scale"),
    "heat_treatment_raw": ("热处理", "Heat Treatment"),
    "surface_treatment_raw": ("表面处理", "表面 处理", "表面", "Surface Treatment", "Finish", "Plating"),
}

TOLERANCE_PATTERN = re.compile(
    r"(?:±|\+/-)\s*\d+(?:\.\d+)?|\b[HEG]\d\b|\bIT\d+\b",
    re.IGNORECASE,
)
ROUGHNESS_PATTERN = re.compile(r"\bR[az]\s*\d+(?:\.\d+)?\b", re.IGNORECASE)
TECHNICAL_REQUIREMENT_KEYWORDS = (
    "技术要求",
    "technical requirement",
    "remove burr",
    "去毛刺",
    "毛刺",
    "锐边",
    "倒角",
    "未注",
    "表面处理",
    "heat treatment",
    "surface treatment",
)


class ParserError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or []
        super().__init__(message)


@dataclass(frozen=True)
class ExtractedPdfField:
    value: str | None
    evidence: dict[str, Any]
    confidence: float
    extract_method: str


class PdfParser(Protocol):
    parser_name: str

    def parse(
        self,
        *,
        task: dict[str, Any],
        pdf_file: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class StepParser(Protocol):
    parser_name: str

    def parse(
        self,
        *,
        task: dict[str, Any],
        step_file: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class MockPdfParser:
    parser_name = "mock_pdf_parser"

    def parse(
        self,
        *,
        task: dict[str, Any],
        pdf_file: dict[str, Any],
    ) -> dict[str, Any]:
        return build_mock_pdf_extract_result(task, pdf_file)


class MockStepParser:
    parser_name = "mock_step_parser"

    def parse(
        self,
        *,
        task: dict[str, Any],
        step_file: dict[str, Any],
    ) -> dict[str, Any]:
        return build_mock_step_feature_result(task, step_file)


class RealPdfParser:
    parser_name = "real_pdf_text_parser"

    def parse(
        self,
        *,
        task: dict[str, Any],
        pdf_file: dict[str, Any],
    ) -> dict[str, Any]:
        pdf_path = resolve_file_path(pdf_file)
        if not pdf_path.exists():
            raise ParserError(
                "PDF_FILE_NOT_FOUND",
                "PDF 文件不存在，无法解析",
                details=[
                    {
                        "field": "storage_path",
                        "message": pdf_file.get("storage_path", ""),
                    }
                ],
            )

        fitz = load_pymupdf()
        pages: list[dict[str, Any]] = []
        blocks: list[dict[str, Any]] = []

        try:
            with fitz.open(pdf_path) as document:
                if document.page_count == 0:
                    raise ParserError(
                        "PDF_PAGE_EMPTY",
                        "PDF 没有可读取页面",
                        details=[{"field": "file_id", "message": pdf_file["file_id"]}],
                    )

                for page_index, page in enumerate(document, start=1):
                    page_text = normalize_text(page.get_text("text") or "")
                    page_blocks = extract_text_blocks(page, page_index)
                    pages.append(
                        {
                            "page": page_index,
                            "text": page_text,
                            "block_count": len(page_blocks),
                        }
                    )
                    blocks.extend(page_blocks)
        except ParserError:
            raise
        except Exception as exc:
            raise ParserError(
                "PDF_READ_FAILED",
                f"PDF 文件读取失败：{exc}",
                details=[
                    {
                        "field": "storage_path",
                        "message": pdf_file.get("storage_path", ""),
                    }
                ],
            ) from exc

        full_text = normalize_text("\n".join(page["text"] for page in pages))
        if not full_text:
            raise ParserError(
                "PDF_TEXT_LAYER_EMPTY",
                "PDF 未检测到可读取文本层，第一阶段暂不做 OCR",
                details=[{"field": "file_id", "message": pdf_file["file_id"]}],
            )

        fields = extract_pdf_fields(pdf_file, blocks, full_text)
        tolerance_matches = collect_pattern_matches(
            pdf_file=pdf_file,
            blocks=blocks,
            pattern=TOLERANCE_PATTERN,
        )
        roughness_matches = collect_pattern_matches(
            pdf_file=pdf_file,
            blocks=blocks,
            pattern=ROUGHNESS_PATTERN,
        )
        technical_requirement_matches = extract_technical_requirements(
            pdf_file=pdf_file,
            blocks=blocks,
        )
        technical_requirements = [
            item["text"] for item in technical_requirement_matches
        ]
        weight_value, weight_unit = parse_weight(fields["weight_raw"].value)

        risks = build_pdf_risks(
            pdf_file=pdf_file,
            fields=fields,
            tolerance_matches=tolerance_matches,
            roughness_matches=roughness_matches,
        )

        return {
            "schema_version": "1.0",
            "task_id": task["task_id"],
            "file_id": pdf_file["file_id"],
            "parser_name": self.parser_name,
            "text_layer": {
                "available": True,
                "page_count": len(pages),
                "block_count": len(blocks),
            },
            "drawing_no": fields["drawing_no"].value,
            "part_name": fields["part_name"].value,
            "revision": fields["revision"].value,
            "material_raw": fields["material_raw"].value,
            "weight_raw": fields["weight_raw"].value,
            "weight_value": weight_value,
            "weight_unit": weight_unit,
            "scale": fields["scale"].value,
            "heat_treatment_raw": fields["heat_treatment_raw"].value,
            "surface_treatment_raw": fields["surface_treatment_raw"].value,
            "tolerance_texts": [item["text"] for item in tolerance_matches],
            "roughness_texts": [item["text"] for item in roughness_matches],
            "technical_requirements": technical_requirements,
            "tolerance_evidence": [item["evidence"] for item in tolerance_matches],
            "roughness_evidence": [item["evidence"] for item in roughness_matches],
            "technical_requirement_evidence": [
                item["evidence"] for item in technical_requirement_matches
            ],
            "field_evidence": {
                key: field.evidence for key, field in fields.items()
            },
            "field_confidence": {
                key: field.confidence for key, field in fields.items()
            },
            "extract_method": {
                key: field.extract_method for key, field in fields.items()
            },
            "field_details": build_pdf_field_details(
                fields=fields,
                weight_value=weight_value,
                weight_unit=weight_unit,
                tolerance_matches=tolerance_matches,
                roughness_matches=roughness_matches,
                technical_requirement_matches=technical_requirement_matches,
            ),
            "text_pages": pages,
            "text_blocks": blocks,
            "risks": risks,
        }


class RealStepParser:
    parser_name = "real_step_geometry_parser"

    def parse(
        self,
        *,
        task: dict[str, Any],
        step_file: dict[str, Any],
    ) -> dict[str, Any]:
        raise ParserError(
            "STEP_PARSER_NOT_IMPLEMENTED",
            "真实 STEP geometry parser 尚未接入",
            details=[{"field": "file_id", "message": step_file["file_id"]}],
        )


@dataclass
class ParserService:
    mode: ParserMode
    pdf_parser: PdfParser
    step_parser: StepParser
    fallback_pdf_parser: PdfParser
    fallback_step_parser: StepParser

    def parse_pdf(
        self,
        *,
        task: dict[str, Any],
        pdf_file: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        return self._parse_with_mode(
            parser=self.pdf_parser,
            fallback_parser=self.fallback_pdf_parser,
            parser_kind="PDF",
            task=task,
            file_record=pdf_file,
        )

    def parse_step(
        self,
        *,
        task: dict[str, Any],
        step_file: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        return self._parse_with_mode(
            parser=self.step_parser,
            fallback_parser=self.fallback_step_parser,
            parser_kind="STEP",
            task=task,
            file_record=step_file,
        )

    def _parse_with_mode(
        self,
        *,
        parser: PdfParser | StepParser,
        fallback_parser: PdfParser | StepParser,
        parser_kind: str,
        task: dict[str, Any],
        file_record: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        if self.mode == "mock":
            return run_parser(parser, task=task, file_record=file_record), []

        try:
            return run_parser(parser, task=task, file_record=file_record), []
        except Exception as exc:
            parser_error = normalize_parser_exception(
                parser_kind=parser_kind,
                parser_name=parser.parser_name,
                exc=exc,
            )
            if self.mode == "auto":
                fallback_result = run_parser(
                    fallback_parser,
                    task=task,
                    file_record=file_record,
                )
                return fallback_result, [
                    parser_fallback_risk(
                        parser_kind=parser_kind,
                        file_record=file_record,
                        parser_name=parser.parser_name,
                        fallback_parser_name=fallback_parser.parser_name,
                        error=parser_error,
                    )
                ]

            return None, [
                parser_failed_risk(
                    parser_kind=parser_kind,
                    file_record=file_record,
                    parser_name=parser.parser_name,
                    error=parser_error,
                )
            ]


def run_parser(
    parser: PdfParser | StepParser,
    *,
    task: dict[str, Any],
    file_record: dict[str, Any],
) -> dict[str, Any]:
    if file_record["file_type"] == "pdf":
        return parser.parse(task=task, pdf_file=file_record)  # type: ignore[arg-type]
    return parser.parse(task=task, step_file=file_record)  # type: ignore[arg-type]


def load_pymupdf() -> Any:
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ParserError(
            "PYMUPDF_NOT_INSTALLED",
            "PyMuPDF 未安装，无法执行真实 PDF text layer 解析",
            details=[
                {
                    "field": "dependency",
                    "message": "Install backend/requirements.txt",
                }
            ],
        ) from exc

    return fitz


def resolve_file_path(file_record: dict[str, Any]) -> Path:
    storage_path = Path(file_record["storage_path"])
    if storage_path.is_absolute():
        return storage_path
    return REPO_ROOT / storage_path


def extract_text_blocks(page: Any, page_number: int) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    text_dict = page.get_text("dict") or {}
    block_index = 0
    for parent_block_index, block in enumerate(text_dict.get("blocks", [])):
        if block.get("type") != 0:
            continue

        for line in block.get("lines", []):
            text = normalize_text(
                "".join(span.get("text", "") for span in line.get("spans", []))
            )
            if not text:
                continue

            bbox = [round(float(value), 2) for value in line.get("bbox", [])]
            if len(bbox) != 4:
                continue

            blocks.append(
                {
                    "page": page_number,
                    "parent_block_index": parent_block_index,
                    "block_index": block_index,
                    "bbox": bbox,
                    "text": text,
                }
            )
            block_index += 1
    return blocks


def normalize_text(value: str) -> str:
    lines = []
    for line in value.replace("\u3000", " ").splitlines():
        cleaned = " ".join(line.strip().split())
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def extract_pdf_fields(
    pdf_file: dict[str, Any],
    blocks: list[dict[str, Any]],
    full_text: str,
) -> dict[str, ExtractedPdfField]:
    fields: dict[str, ExtractedPdfField] = {}
    for field_key in PDF_FIELD_KEYS:
        fields[field_key] = find_pdf_field(
            field_key=field_key,
            pdf_file=pdf_file,
            blocks=blocks,
            full_text=full_text,
        )
    return fields


def find_pdf_field(
    *,
    field_key: str,
    pdf_file: dict[str, Any],
    blocks: list[dict[str, Any]],
    full_text: str,
) -> ExtractedPdfField:
    patterns = PDF_FIELD_PATTERNS[field_key]

    for pattern in patterns:
        compiled = re.compile(pattern, re.IGNORECASE)
        for block in blocks:
            for line in block["text"].splitlines():
                match = compiled.search(line)
                if not match:
                    continue

                value = clean_field_value(match.group("value"), field_key)
                if not value:
                    continue

                return ExtractedPdfField(
                    value=value,
                    evidence=source_ref(
                        "pdf",
                        file_id=pdf_file["file_id"],
                        page=block["page"],
                        location=block_location(block),
                        raw_text=value,
                        rule_code=f"PDF_TEXT_REGEX:{field_key}",
                    ),
                    confidence=0.82,
                    extract_method="text_layer_regex",
                )

    title_field = find_title_block_field(
        field_key=field_key,
        pdf_file=pdf_file,
        blocks=blocks,
    )
    if title_field.value:
        return title_field

    for pattern in patterns:
        compiled = re.compile(pattern, re.IGNORECASE)
        match = compiled.search(full_text)
        if match:
            value = clean_field_value(match.group("value"), field_key)
            if value:
                return ExtractedPdfField(
                    value=value,
                    evidence=source_ref(
                        "pdf",
                        file_id=pdf_file["file_id"],
                        raw_text=value,
                        rule_code=f"PDF_TEXT_REGEX:{field_key}",
                    ),
                    confidence=0.65,
                    extract_method="text_layer_regex_full_text",
                )

    return ExtractedPdfField(
        value=None,
        evidence=source_ref(
            "pdf",
            file_id=pdf_file["file_id"],
            raw_text=None,
            rule_code=f"PDF_FIELD_NOT_FOUND:{field_key}",
        ),
        confidence=0.0,
        extract_method="not_found",
    )


def find_title_block_field(
    *,
    field_key: str,
    pdf_file: dict[str, Any],
    blocks: list[dict[str, Any]],
) -> ExtractedPdfField:
    if field_key == "part_name":
        inferred = infer_title_block_part_name(pdf_file, blocks)
        if inferred.value:
            return inferred

    label_block = find_label_block(blocks, PDF_TITLE_FIELD_LABELS[field_key])
    if label_block is None:
        return empty_title_block_field(pdf_file, field_key)

    value_block = find_adjacent_value_block(label_block, blocks)
    if value_block is None:
        return empty_title_block_field(pdf_file, field_key)

    value = clean_field_value(value_block["text"], field_key)
    if field_key == "weight_raw" and value:
        value = normalize_title_block_weight(value, label_block["text"])
    if not value:
        return empty_title_block_field(pdf_file, field_key)

    return ExtractedPdfField(
        value=value,
        evidence=source_ref(
            "pdf",
            file_id=pdf_file["file_id"],
            page=value_block["page"],
            location=block_location(value_block),
            raw_text=value,
            rule_code=f"PDF_TEXT_TITLE_BLOCK:{field_key}",
        ),
        confidence=0.78,
        extract_method="text_layer_title_block",
    )


def empty_title_block_field(
    pdf_file: dict[str, Any],
    field_key: str,
) -> ExtractedPdfField:
    return ExtractedPdfField(
        value=None,
        evidence=source_ref(
            "pdf",
            file_id=pdf_file["file_id"],
            raw_text=None,
            rule_code=f"PDF_TITLE_BLOCK_FIELD_NOT_FOUND:{field_key}",
        ),
        confidence=0.0,
        extract_method="not_found",
    )


def find_label_block(
    blocks: list[dict[str, Any]],
    labels: tuple[str, ...],
) -> dict[str, Any] | None:
    normalized_labels = [normalize_label(label) for label in labels]
    matches = []
    for block in blocks:
        normalized_text = normalize_label(block["text"])
        match_score = 0
        for label in normalized_labels:
            if normalized_text == label:
                match_score = max(match_score, 2)
            elif label in normalized_text:
                match_score = max(match_score, 1)
        if match_score:
            matches.append((match_score, block))

    if not matches:
        return None

    return max(matches, key=lambda item: (item[0], item[1]["bbox"][1], item[1]["bbox"][0]))[1]


def find_adjacent_value_block(
    label_block: dict[str, Any],
    blocks: list[dict[str, Any]],
) -> dict[str, Any] | None:
    label_bbox = label_block["bbox"]
    label_center_y = (label_bbox[1] + label_bbox[3]) / 2
    label_height = max(label_bbox[3] - label_bbox[1], 1)
    candidates: list[tuple[float, dict[str, Any]]] = []

    for block in blocks:
        if block is label_block or block["page"] != label_block["page"]:
            continue

        bbox = block["bbox"]
        if bbox[0] < label_bbox[2] - 4:
            continue

        horizontal_distance = bbox[0] - label_bbox[2]
        if horizontal_distance > 220:
            continue

        center_y = (bbox[1] + bbox[3]) / 2
        center_distance = abs(center_y - label_center_y)
        vertical_overlap = min(label_bbox[3], bbox[3]) - max(label_bbox[1], bbox[1])
        if vertical_overlap < 0 and center_distance > max(label_height, 14):
            continue

        if looks_like_title_label(block["text"]):
            continue

        score = horizontal_distance + center_distance * 1.5
        candidates.append((score, block))

    if not candidates:
        return None

    return min(candidates, key=lambda item: item[0])[1]


def infer_title_block_part_name(
    pdf_file: dict[str, Any],
    blocks: list[dict[str, Any]],
) -> ExtractedPdfField:
    max_x = max((block["bbox"][2] for block in blocks), default=0)
    max_y = max((block["bbox"][3] for block in blocks), default=0)
    candidates: list[tuple[int, float, dict[str, Any]]] = []

    for block in blocks:
        bbox = block["bbox"]
        text = " ".join(block["text"].split())
        if bbox[0] < max_x * 0.55 or bbox[1] < max_y * 0.86:
            continue
        if not re.search(r"[\u4e00-\u9fff]", text):
            continue
        if looks_like_title_label(text) or looks_like_non_part_name(text):
            continue

        candidates.append((len(text), bbox[0], block))

    if not candidates:
        return empty_title_block_field(pdf_file, "part_name")

    block = max(candidates, key=lambda item: (item[0], -item[1]))[2]
    value = clean_field_value(block["text"], "part_name")
    if not value:
        return empty_title_block_field(pdf_file, "part_name")

    return ExtractedPdfField(
        value=value,
        evidence=source_ref(
            "pdf",
            file_id=pdf_file["file_id"],
            page=block["page"],
            location=block_location(block),
            raw_text=value,
            rule_code="PDF_TEXT_TITLE_BLOCK:part_name",
        ),
        confidence=0.62,
        extract_method="text_layer_title_block_inferred",
    )


def normalize_label(value: str) -> str:
    return re.sub(r"[\s:：()（）._\-]+", "", value).lower()


def looks_like_title_label(value: str) -> bool:
    normalized = normalize_label(value)
    labels = [
        label
        for label_group in PDF_TITLE_FIELD_LABELS.values()
        for label in label_group
    ]
    return any(normalize_label(label) == normalized for label in labels)


def looks_like_non_part_name(value: str) -> bool:
    normalized = normalize_label(value)
    if re.fullmatch(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", value.strip()):
        return True
    if re.fullmatch(r"[A-Za-z0-9_.\-/#]+", value.strip()):
        return True
    excluded_fragments = (
        "科技",
        "有限公司",
        "Focusight",
        "Technology",
        "黄天星",
        "化学镍",
        "淬火",
        "方件类",
        "设计",
        "审核",
        "批准",
    )
    return any(normalize_label(fragment) in normalized for fragment in excluded_fragments)


def normalize_title_block_weight(value: str, label_text: str) -> str:
    if re.search(r"(kg|kgs|g|千克|克)", value, re.IGNORECASE):
        return value
    if re.search(r"kg", label_text, re.IGNORECASE):
        return f"{value} kg"
    if "克" in label_text:
        return f"{value} g"
    return value


def clean_field_value(value: str, field_key: str) -> str | None:
    cleaned = " ".join(value.replace("\u3000", " ").strip().split())
    cleaned = cleaned.strip(" :：;；,，")
    if not cleaned:
        return None

    next_label_pattern = re.compile(
        r"\s+(?:图号|零件名称|零件名|品名|材料|材质|重量|净重|单重|比例|版本|版次|"
        r"热处理|表面处理|Drawing|Part\s*Name|Description|Material|Mat\.?|"
        r"Weight|Scale|Revision|Rev\.?|Heat\s*Treatment|Surface\s*Treatment|"
        r"Finish|Plating)\s*[:：]?",
        re.IGNORECASE,
    )
    label_match = next_label_pattern.search(cleaned)
    if label_match:
        cleaned = cleaned[: label_match.start()].strip(" :：;；,，")

    if field_key == "material_raw":
        cleaned = re.sub(r"\s+", "", cleaned.upper())
    elif field_key == "weight_raw":
        cleaned = cleaned.replace(",", ".")
    elif field_key == "scale":
        cleaned = re.sub(r"\s+", "", cleaned.upper())

    return cleaned or None


def block_location(block: dict[str, Any]) -> str:
    bbox = ",".join(str(value) for value in block["bbox"])
    return f"page_{block['page']}_block_{block['block_index']}:{bbox}"


def collect_pattern_matches(
    *,
    pdf_file: dict[str, Any],
    blocks: list[dict[str, Any]],
    pattern: re.Pattern[str],
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    for block in blocks:
        for match in pattern.finditer(block["text"]):
            text = " ".join(match.group(0).split())
            normalized = text.upper().replace(" ", "")
            if normalized in seen:
                continue
            seen.add(normalized)
            matches.append(
                {
                    "text": text,
                    "evidence": source_ref(
                        "pdf",
                        file_id=pdf_file["file_id"],
                        page=block["page"],
                        location=block_location(block),
                        raw_text=text,
                        rule_code="PDF_TEXT_REGEX",
                    ),
                }
            )
    return matches


def extract_technical_requirements(
    *,
    pdf_file: dict[str, Any],
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    requirements: list[dict[str, Any]] = []
    seen: set[str] = set()
    requirement_parent_blocks: set[int] = {
        int(block["parent_block_index"])
        for block in blocks
        if any(
            keyword.lower() in block["text"].lower()
            for keyword in ("技术要求", "technical requirement")
        )
    }
    for block in blocks:
        for line in block["text"].splitlines():
            normalized = line.lower()

            starts_section = any(
                keyword.lower() in normalized
                for keyword in ("技术要求", "technical requirement")
            )
            looks_keyword_requirement = any(
                keyword.lower() in normalized
                for keyword in TECHNICAL_REQUIREMENT_KEYWORDS
            )
            same_requirement_block = (
                int(block.get("parent_block_index", -1)) in requirement_parent_blocks
            )

            if not (
                starts_section
                or looks_keyword_requirement
                or same_requirement_block
            ):
                continue

            cleaned = line.strip(" -:：;；")
            if not cleaned or cleaned in seen:
                continue

            seen.add(cleaned)
            requirements.append(
                {
                    "text": cleaned,
                    "evidence": source_ref(
                        "pdf",
                        file_id=pdf_file["file_id"],
                        page=block["page"],
                        location=block_location(block),
                        raw_text=cleaned,
                        rule_code="PDF_TEXT_TECHNICAL_REQUIREMENT",
                    ),
                }
            )
            if len(requirements) >= 20:
                return requirements

    return requirements


def build_pdf_field_details(
    *,
    fields: dict[str, ExtractedPdfField],
    weight_value: float | None,
    weight_unit: str | None,
    tolerance_matches: list[dict[str, Any]],
    roughness_matches: list[dict[str, Any]],
    technical_requirement_matches: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    details = {
        key: {
            "raw_text": field.value,
            "value": field.value,
            "confidence": field.confidence,
            "extract_method": field.extract_method,
            "evidence": field.evidence,
        }
        for key, field in fields.items()
    }
    details["weight_value"] = {
        "raw_text": fields["weight_raw"].value,
        "value": weight_value,
        "confidence": fields["weight_raw"].confidence if weight_value is not None else 0,
        "extract_method": fields["weight_raw"].extract_method,
        "evidence": fields["weight_raw"].evidence,
    }
    details["weight_unit"] = {
        "raw_text": fields["weight_raw"].value,
        "value": weight_unit,
        "confidence": fields["weight_raw"].confidence if weight_unit else 0,
        "extract_method": fields["weight_raw"].extract_method,
        "evidence": fields["weight_raw"].evidence,
    }
    details["tolerance_texts"] = {
        "raw_text": "; ".join(item["text"] for item in tolerance_matches) or None,
        "value": [item["text"] for item in tolerance_matches],
        "confidence": 0.78 if tolerance_matches else 0,
        "extract_method": "text_layer_regex",
        "evidence": [item["evidence"] for item in tolerance_matches],
    }
    details["roughness_texts"] = {
        "raw_text": "; ".join(item["text"] for item in roughness_matches) or None,
        "value": [item["text"] for item in roughness_matches],
        "confidence": 0.78 if roughness_matches else 0,
        "extract_method": "text_layer_regex",
        "evidence": [item["evidence"] for item in roughness_matches],
    }
    details["technical_requirements"] = {
        "raw_text": "\n".join(item["text"] for item in technical_requirement_matches)
        or None,
        "value": [item["text"] for item in technical_requirement_matches],
        "confidence": 0.72 if technical_requirement_matches else 0,
        "extract_method": "text_layer_keyword",
        "evidence": [item["evidence"] for item in technical_requirement_matches],
    }
    return details


def parse_weight(weight_raw: str | None) -> tuple[float | None, str | None]:
    if not weight_raw:
        return None, None

    match = re.search(
        r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>kgs?|g|千克|克)",
        weight_raw,
        re.IGNORECASE,
    )
    if not match:
        return None, None

    value = float(match.group("value").replace(",", "."))
    unit_text = match.group("unit").lower()
    if unit_text in {"kg", "kgs", "千克"}:
        return value, "kg"
    return value, "g"


def build_pdf_risks(
    *,
    pdf_file: dict[str, Any],
    fields: dict[str, ExtractedPdfField],
    tolerance_matches: list[dict[str, Any]],
    roughness_matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []

    for field_key in (
        "drawing_no",
        "part_name",
        "material_raw",
        "weight_raw",
    ):
        field = fields[field_key]
        if field.value:
            continue

        risks.append(
            risk_item(
                "LOW_CONFIDENCE_FIELD",
                "warning",
                f"PDF text layer 未能稳定抽取字段：{field_key}",
                "pdf_parser",
                True,
                [field.evidence],
            )
        )

    precision_evidence = [
        item["evidence"]
        for item in tolerance_matches + roughness_matches
        if is_high_precision_text(item["text"])
    ]
    if precision_evidence:
        risks.append(
            risk_item(
                "HIGH_PRECISION_REQUIREMENT",
                "warning",
                "PDF text layer 检测到高精度或高表面要求，需人工确认。",
                "pdf_parser",
                True,
                precision_evidence,
            )
        )

    if not risks:
        return []

    return risks


def is_high_precision_text(value: str) -> bool:
    normalized = value.upper().replace(" ", "")
    if re.fullmatch(r"[HEG]\d", normalized):
        return True
    if normalized.startswith("RA"):
        try:
            return float(normalized[2:]) <= 0.8
        except ValueError:
            return True
    tolerance_match = re.search(r"(?:±|\+/-)(\d+(?:\.\d+)?)", normalized)
    if tolerance_match:
        return float(tolerance_match.group(1)) <= 0.01
    return False


def build_parser_service(mode: str | None = None) -> ParserService:
    parser_mode = normalize_parser_mode(
        mode or os.getenv("PRICE_PARSER_MODE") or "auto"
    )
    mock_pdf_parser = MockPdfParser()
    mock_step_parser = MockStepParser()

    if parser_mode == "mock":
        pdf_parser: PdfParser = mock_pdf_parser
        step_parser: StepParser = mock_step_parser
    else:
        pdf_parser = RealPdfParser()
        step_parser = RealStepParser()

    return ParserService(
        mode=parser_mode,
        pdf_parser=pdf_parser,
        step_parser=step_parser,
        fallback_pdf_parser=mock_pdf_parser,
        fallback_step_parser=mock_step_parser,
    )


def normalize_parser_mode(value: str) -> ParserMode:
    normalized = value.strip().lower()
    if normalized in {"mock", "auto", "real"}:
        return normalized  # type: ignore[return-value]
    return "mock"


def normalize_parser_exception(
    *,
    parser_kind: str,
    parser_name: str,
    exc: Exception,
) -> ParserError:
    if isinstance(exc, ParserError):
        return exc

    return ParserError(
        f"{parser_kind}_PARSER_EXCEPTION",
        f"{parser_name} 解析异常：{exc}",
        details=[
            {
                "field": "exception_type",
                "message": exc.__class__.__name__,
            }
        ],
    )


def parser_fallback_risk(
    *,
    parser_kind: str,
    file_record: dict[str, Any],
    parser_name: str,
    fallback_parser_name: str,
    error: ParserError,
) -> dict[str, Any]:
    return risk_item(
        "PARSER_FALLBACK_USED",
        "warning",
        (
            f"{parser_kind} 真实解析失败，已使用 fallback parser。"
            f"真实解析器：{parser_name}；fallback：{fallback_parser_name}；"
            f"原因：{error.message}"
        ),
        "parser_service",
        True,
        [
            source_ref(
                "system",
                file_id=file_record["file_id"],
                raw_text=error.message,
                rule_code=error.code,
            )
        ],
    )


def parser_failed_risk(
    *,
    parser_kind: str,
    file_record: dict[str, Any],
    parser_name: str,
    error: ParserError,
) -> dict[str, Any]:
    return risk_item(
        f"{parser_kind}_PARSE_FAILED",
        "blocking",
        (
            f"{parser_kind} 真实解析失败，未使用 mock fallback。"
            f"解析器：{parser_name}；原因：{error.message}"
        ),
        "parser_service",
        True,
        [
            source_ref(
                "system",
                file_id=file_record["file_id"],
                raw_text=error.message,
                rule_code=error.code,
            )
        ],
    )
