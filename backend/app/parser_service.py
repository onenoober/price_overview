from __future__ import annotations

import base64
import json
import os
import re
import sys
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Callable, Literal, Protocol

import httpx
from jsonschema import ValidationError, validate

from .part_feature_builder import (
    risk_item,
    source_ref,
)
from .storage import REPO_ROOT


ParserMode = Literal["auto", "real"]
PdfVisionMode = Literal["off", "fallback", "low_confidence", "always"]

PDF_FIELD_KEYS = (
    "drawing_no",
    "part_name",
    "part_type_raw",
    "revision",
    "material_raw",
    "weight_raw",
    "scale",
    "heat_treatment_raw",
    "surface_treatment_raw",
)

PDF_FIELD_PATTERNS = {
    "drawing_no": (
        r"(?:图号|图紙番号|图纸编号|物件料号|Drawing[ \t]*(?:No\.?|Number)|DWG\.?[ \t]*NO\.?|Part[ \t]*No\.?|零件图号|件号|编号)[ \t]*[:：#]?[ \t]*(?P<value>[A-Za-z0-9][A-Za-z0-9_.\-\/#]{1,40})",
    ),
    "part_name": (
        r"(?:零件名称|零件名|品名|Part[ \t]*Name|Description)[ \t]*[:：]?[ \t]*(?P<value>[^\r\n]{1,80})",
    ),
    "part_type_raw": (
        r"(?:零件类型|零件类别|物件类型|Part[ \t]*Type|Part[ \t]*Category)[ \t]*[:：]?[ \t]*(?P<value>[\u4e00-\u9fffA-Za-z0-9_\- ]{1,30})",
    ),
    "revision": (
        r"(?:版本|版次|修订|Revision|Rev\.?)[ \t]*[:：]?[ \t]*(?P<value>[A-Za-z0-9_.\-]{1,20})",
    ),
    "material_raw": (
        r"(?:材料|材质|Material|Mat\.?)[ \t]*[:：]?[ \t]*(?P<value>[A-Za-z0-9\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff+\-_.\/# ]{1,50})",
        r"\b(?P<value>SUS\s*304|SUS304|S45C|SKD11|AL\s*6061|AL6061|A6061|6061(?:-T6)?|45#|Q235|POM|PEEK|H59)\b",
    ),
    "weight_raw": (
        r"(?:重量|净重|单重|Weight|WT\.?)[ \t]*[:：]?[ \t]*(?P<value>\d+(?:[.,]\d+)?[ \t]*(?:kg|kgs|g|KG|G|千克|克))",
    ),
    "scale": (
        r"(?:比例|Scale)[ \t]*[:：]?[ \t]*(?P<value>\d+(?:\.\d+)?[ \t]*[:：][ \t]*\d+(?:\.\d+)?|NTS|n\.?t\.?s\.?)",
    ),
    "heat_treatment_raw": (
        r"(?:热处理|Heat[ \t]*Treatment)[ \t]*[:：]?[ \t]*(?P<value>[^\r\n]{1,80})",
    ),
    "surface_treatment_raw": (
        r"(?:表面处理|表面要求|Surface[ \t]*Treatment|Finish|Plating)[ \t]*[:：]?[ \t]*(?P<value>[^\r\n]{1,80})",
    ),
}

PDF_TITLE_FIELD_LABELS = {
    "drawing_no": ("图号", "图纸编号", "物件料号", "料号", "件号", "Drawing No", "Part No"),
    "part_name": ("零件名称", "零件名", "品名", "Part Name", "Description"),
    "part_type_raw": ("零件类型", "零件类别", "物件类型", "Part Type", "Part Category"),
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
HOLE_COUNT_DIAMETER_PATTERN = re.compile(
    r"(?P<count>\d+)\s*(?:x|X|×|\*)\s*"
    r"(?:[ΦφØø⌀∅]\s*)?(?P<diameter>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
HOLE_THREAD_PATTERN = re.compile(
    r"(?:(?P<count>\d+)\s*(?:x|X|×|\*)\s*)?"
    r"(?P<thread>M\s*(?P<diameter>\d+(?:\.\d+)?)(?:\s*(?:x|X|×)\s*\d+(?:\.\d+)?)?)",
    re.IGNORECASE,
)
HOLE_DEPTH_PATTERN = re.compile(
    r"(?:深|depth|dp)\s*(?P<depth>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
HOLE_COUNTERBORE_PATTERN = re.compile(
    r"(?:⌴|⎴|凵|沉孔|锪孔|counterbore|c[\s/-]*bore|cb)\s*"
    r"(?:[ΦφØø⌀∅]\s*)?(?P<diameter>\d+(?:\.\d+)?)"
    r"(?:\s*(?:深|depth|dp)\s*(?P<depth>\d+(?:\.\d+)?))?",
    re.IGNORECASE,
)
HOLE_COUNTERSINK_PATTERN = re.compile(
    r"(?:⌵|沉头|沉頭|锥沉|countersink|c[\s/-]*sink|csk)\s*"
    r"(?:[ΦφØø⌀∅]\s*)?(?P<diameter>\d+(?:\.\d+)?)"
    r"(?:\s*(?:深|depth|dp)\s*(?P<depth>\d+(?:\.\d+)?))?"
    r"(?:\s*(?P<angle>\d+(?:\.\d+)?)\s*[°度])?",
    re.IGNORECASE,
)
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
LOW_CONFIDENCE_THRESHOLD = 0.7
FIELD_CONFLICT_THRESHOLD = 0.08
MAX_FIELD_CANDIDATES = 5


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
    candidates: list[dict[str, Any]] = dataclass_field(default_factory=list)


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
        material_density: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


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
                "PDF 未检测到可读取文本层，可使用多模态图像解析或转人工",
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
        hole_annotation_matches = collect_hole_annotation_matches(
            pdf_file=pdf_file,
            blocks=blocks,
        )
        return build_pdf_extract_result(
            task=task,
            pdf_file=pdf_file,
            parser_name=self.parser_name,
            fields=fields,
            tolerance_matches=tolerance_matches,
            roughness_matches=roughness_matches,
            technical_requirement_matches=technical_requirement_matches,
            hole_annotation_matches=hole_annotation_matches,
            text_layer={
                "available": True,
                "page_count": len(pages),
                "block_count": len(blocks),
            },
            text_pages=pages,
            text_blocks=blocks,
        )


@dataclass(frozen=True)
class PdfVisionConfig:
    api_key: str
    model: str
    base_url: str
    api_mode: str
    timeout_seconds: float
    dpi: int
    max_pages: int
    detail: str


class VisionAssistedPdfParser:
    parser_name = "real_pdf_vision_assisted_parser"

    def __init__(
        self,
        *,
        text_parser: PdfParser | None = None,
        vision_parser: PdfParser | None = None,
    ) -> None:
        self.text_parser = text_parser or RealPdfParser()
        self.vision_parser = vision_parser or RealPdfVisionParser()

    def parse(
        self,
        *,
        task: dict[str, Any],
        pdf_file: dict[str, Any],
    ) -> dict[str, Any]:
        vision_mode = pdf_vision_mode()
        if vision_mode == "always":
            return self.vision_parser.parse(task=task, pdf_file=pdf_file)

        try:
            text_result = self.text_parser.parse(task=task, pdf_file=pdf_file)
        except ParserError:
            if vision_mode in {"fallback", "low_confidence"}:
                return self.vision_parser.parse(task=task, pdf_file=pdf_file)
            raise

        if vision_mode != "low_confidence" or not pdf_result_needs_vision(text_result):
            return text_result

        try:
            vision_result = self.vision_parser.parse(task=task, pdf_file=pdf_file)
        except Exception as exc:
            text_result.setdefault("risks", []).append(
                pdf_vision_unavailable_risk(pdf_file, exc)
            )
            return text_result

        return merge_pdf_vision_result(text_result, vision_result, self.parser_name)


class RealPdfVisionParser:
    parser_name = "real_pdf_vision_parser"

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

        config = build_pdf_vision_config()
        rendered_pages = render_pdf_pages_for_vision(pdf_path, config)
        if not rendered_pages:
            raise ParserError(
                "PDF_VISION_PAGE_EMPTY",
                "PDF 未渲染出可供多模态模型识别的页面",
                details=[{"field": "file_id", "message": pdf_file["file_id"]}],
            )

        content = request_pdf_vision_content(
            config=config,
            task=task,
            pdf_file=pdf_file,
            rendered_pages=rendered_pages,
        )
        fields = vision_content_to_fields(pdf_file, content)
        tolerance_matches = vision_content_to_matches(
            pdf_file=pdf_file,
            content=content,
            list_key="tolerance_texts",
            rule_code="PDF_VISION:TOLERANCE",
        )
        roughness_matches = vision_content_to_matches(
            pdf_file=pdf_file,
            content=content,
            list_key="roughness_texts",
            rule_code="PDF_VISION:ROUGHNESS",
        )
        technical_requirement_matches = vision_content_to_matches(
            pdf_file=pdf_file,
            content=content,
            list_key="technical_requirements",
            rule_code="PDF_VISION:TECHNICAL_REQUIREMENT",
        )
        hole_annotation_matches = vision_content_to_hole_annotations(
            pdf_file=pdf_file,
            content=content,
        )

        return build_pdf_extract_result(
            task=task,
            pdf_file=pdf_file,
            parser_name=self.parser_name,
            fields=fields,
            tolerance_matches=tolerance_matches,
            roughness_matches=roughness_matches,
            technical_requirement_matches=technical_requirement_matches,
            hole_annotation_matches=hole_annotation_matches,
            text_layer={
                "available": False,
                "page_count": len(rendered_pages),
                "block_count": 0,
            },
            text_pages=[],
            text_blocks=[],
            vision={
                "available": True,
                "model": config.model,
                "api_mode": config.api_mode,
                "page_count": len(rendered_pages),
                "pages": [
                    {
                        "page": item["page"],
                        "width": item["width"],
                        "height": item["height"],
                        "dpi": item["dpi"],
                    }
                    for item in rendered_pages
                ],
                "notes": content.get("notes"),
                "confidence": bounded_pdf_confidence(content.get("confidence")),
            },
        )


class RealStepParser:
    parser_name = "real_step_geometry_parser"

    def parse(
        self,
        *,
        task: dict[str, Any],
        step_file: dict[str, Any],
        material_density: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        step_path = resolve_file_path(step_file)
        if not step_path.exists():
            raise ParserError(
                "STEP_FILE_NOT_FOUND",
                "STEP 文件不存在，无法解析",
                details=[
                    {
                        "field": "storage_path",
                        "message": step_file.get("storage_path", ""),
                    }
                ],
            )

        parse_step_file = load_standalone_step_parser()
        density = optional_float_env("PRICE_STEP_DENSITY")
        density_unit = normalize_step_density_unit(
            os.getenv("PRICE_STEP_DENSITY_UNIT") or "kg/mm3"
        )
        density_source = None
        if material_density:
            density = material_density.get("density_kg_mm3")
            density_unit = "kg/mm3"
            density_source = material_density.get("source")

        result = parse_step_file(
            step_path,
            task_id=task["task_id"],
            file_id=step_file["file_id"],
            density=density,
            density_unit=density_unit,
            backend=normalize_step_backend(
                os.getenv("PRICE_STEP_PARSER_BACKEND") or "auto"
            ),
        )
        if density_source and result.get("net_weight"):
            result["net_weight"]["density_source"] = density_source
        raise_for_step_parse_failure(result, step_file)
        result["parser_name"] = self.parser_name
        result["file_name"] = step_file.get("filename")
        return result


@dataclass
class ParserService:
    mode: ParserMode
    pdf_parser: PdfParser
    step_parser: StepParser

    def parse_pdf(
        self,
        *,
        task: dict[str, Any],
        pdf_file: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        return self._parse_with_mode(
            parser=self.pdf_parser,
            parser_kind="PDF",
            task=task,
            file_record=pdf_file,
        )

    def parse_step(
        self,
        *,
        task: dict[str, Any],
        step_file: dict[str, Any],
        material_density: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        try:
            if material_density is None:
                return self._parse_with_mode(
                    parser=self.step_parser,
                    parser_kind="STEP",
                    task=task,
                    file_record=step_file,
                )
            return (
                self.step_parser.parse(
                    task=task,
                    step_file=step_file,
                    material_density=material_density,
                ),
                [],
            )
        except Exception as exc:
            parser_error = normalize_parser_exception(
                parser_kind="STEP",
                parser_name=self.step_parser.parser_name,
                exc=exc,
            )
            return None, [
                parser_failed_risk(
                    parser_kind="STEP",
                    file_record=step_file,
                    parser_name=self.step_parser.parser_name,
                    error=parser_error,
                )
            ]

    def _parse_with_mode(
        self,
        *,
        parser: PdfParser | StepParser,
        parser_kind: str,
        task: dict[str, Any],
        file_record: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        try:
            return run_parser(parser, task=task, file_record=file_record), []
        except Exception as exc:
            parser_error = normalize_parser_exception(
                parser_kind=parser_kind,
                parser_name=parser.parser_name,
                exc=exc,
            )
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


def load_standalone_step_parser() -> Callable[..., dict[str, Any]]:
    try:
        from standalone_step_parser.step_parser import parse_step_file

        return parse_step_file
    except ImportError as first_error:
        standalone_root = REPO_ROOT / "standalone_step_parser"
        if standalone_root.exists() and str(standalone_root) not in sys.path:
            sys.path.insert(0, str(standalone_root))

        try:
            from step_parser import parse_step_file

            return parse_step_file
        except ImportError as second_error:
            raise ParserError(
                "STEP_PARSER_IMPORT_FAILED",
                "无法加载 standalone STEP parser，请确认 standalone_step_parser 存在且依赖已安装",
                details=[
                    {
                        "field": "import_error",
                        "message": str(second_error or first_error),
                    }
                ],
            ) from second_error


def raise_for_step_parse_failure(
    result: dict[str, Any],
    step_file: dict[str, Any],
) -> None:
    for risk in result.get("geometry_risks") or []:
        if risk.get("code") not in {"MISSING_STEP", "STEP_PARSE_FAILED"}:
            continue
        raise ParserError(
            str(risk.get("code") or "STEP_PARSE_FAILED"),
            str(risk.get("message") or "STEP 真实解析失败"),
            details=[
                {
                    "field": "file_id",
                    "message": step_file["file_id"],
                }
            ],
        )


def normalize_step_backend(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"auto", "pythonocc", "cadquery"}:
        return normalized
    return "auto"


def normalize_step_density_unit(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"kg/mm3", "g/cm3"}:
        return normalized
    return "kg/mm3"


def optional_float_env(name: str) -> float | None:
    value = os.getenv(name)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ParserError(
            "INVALID_STEP_DENSITY",
            f"{name} 必须是数字",
            details=[{"field": name, "message": value}],
        ) from exc


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


def pdf_vision_mode() -> PdfVisionMode:
    raw_value = os.getenv("PRICE_PDF_VISION_MODE", "fallback")
    normalized = raw_value.strip().lower()
    if normalized in {"off", "fallback", "low_confidence", "always"}:
        return normalized  # type: ignore[return-value]
    return "fallback"


def build_pdf_vision_config() -> PdfVisionConfig:
    api_key = (
        os.getenv("PRICE_PDF_VISION_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("PRICE_AI_API_KEY")
        or os.getenv("LLM_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
    )
    if not api_key:
        raise ParserError(
            "PDF_VISION_NOT_CONFIGURED",
            "多模态 PDF 图像解析未配置 API key",
            details=[
                {
                    "field": "api_key",
                    "message": (
                        "Set PRICE_PDF_VISION_API_KEY, OPENAI_API_KEY, "
                        "PRICE_AI_API_KEY, LLM_API_KEY, or DASHSCOPE_API_KEY"
                    ),
                }
            ],
        )

    base_url = (
        os.getenv("PRICE_PDF_VISION_BASE_URL")
        or os.getenv("PRICE_AI_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("LLM_BASE_URL")
        or "https://api.openai.com/v1"
    )
    api_mode = (
        os.getenv("PRICE_PDF_VISION_API_MODE")
        or os.getenv("PRICE_AI_API_MODE")
        or os.getenv("LLM_API_MODE")
        or infer_pdf_vision_api_mode(base_url)
    ).strip().lower()
    if api_mode not in {"responses", "chat_completions"}:
        api_mode = "chat_completions"

    return PdfVisionConfig(
        api_key=api_key,
        model=(
            os.getenv("PRICE_PDF_VISION_MODEL")
            or os.getenv("PRICE_AI_MODEL")
            or os.getenv("OPENAI_MODEL")
            or os.getenv("LLM_MODEL")
            or "gpt-5.5"
        ),
        base_url=base_url,
        api_mode=api_mode,
        timeout_seconds=float_env(
            "PRICE_PDF_VISION_TIMEOUT_SECONDS",
            float_env("PRICE_AI_TIMEOUT_SECONDS", 90.0),
        ),
        dpi=int_env("PRICE_PDF_VISION_DPI", 120),
        max_pages=max(1, int_env("PRICE_PDF_VISION_MAX_PAGES", 2)),
        detail=os.getenv("PRICE_PDF_VISION_DETAIL", "high").strip() or "high",
    )


def infer_pdf_vision_api_mode(base_url: str) -> str:
    normalized = base_url.lower()
    if "dashscope" in normalized or "compatible-mode" in normalized:
        return "chat_completions"
    return "responses"


def int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def render_pdf_pages_for_vision(
    pdf_path: Path,
    config: PdfVisionConfig,
) -> list[dict[str, Any]]:
    fitz = load_pymupdf()
    rendered_pages: list[dict[str, Any]] = []
    try:
        with fitz.open(pdf_path) as document:
            if document.page_count == 0:
                raise ParserError(
                    "PDF_PAGE_EMPTY",
                    "PDF 没有可读取页面",
                    details=[{"field": "storage_path", "message": str(pdf_path)}],
                )
            for page_index, page in enumerate(document, start=1):
                if page_index > config.max_pages:
                    break
                pixmap = page.get_pixmap(dpi=config.dpi, alpha=False)
                image_bytes = pixmap.tobytes("png")
                rendered_pages.append(
                    {
                        "page": page_index,
                        "width": pixmap.width,
                        "height": pixmap.height,
                        "dpi": config.dpi,
                        "data_url": (
                            "data:image/png;base64,"
                            + base64.b64encode(image_bytes).decode("ascii")
                        ),
                    }
                )
    except ParserError:
        raise
    except Exception as exc:
        raise ParserError(
            "PDF_VISION_RENDER_FAILED",
            f"PDF 页面渲染为图像失败：{exc}",
            details=[{"field": "storage_path", "message": str(pdf_path)}],
        ) from exc
    return rendered_pages


def request_pdf_vision_content(
    *,
    config: PdfVisionConfig,
    task: dict[str, Any],
    pdf_file: dict[str, Any],
    rendered_pages: list[dict[str, Any]],
) -> dict[str, Any]:
    schema = pdf_vision_extract_schema()
    system_prompt = (
        "You extract machining drawing fields from PDF page images. Use only text "
        "and markings visible in the supplied images. Do not infer missing material, "
        "weight, treatments, tolerances, revision, or hole notes. Return JSON only."
    )
    user_text = json.dumps(
        {
            "task_id": task["task_id"],
            "file_id": pdf_file["file_id"],
            "file_name": pdf_file.get("filename"),
            "required_fields": list(PDF_FIELD_KEYS)
            + [
                "weight_value",
                "weight_unit",
                "tolerance_texts",
                "roughness_texts",
                "technical_requirements",
                "hole_annotations",
            ],
            "instructions": (
                "Return raw drawing text exactly as visible where possible. "
                "Use null and confidence 0 when a field is not visible. "
                "Use location values such as title_block, technical_requirements, "
                "annotation, leader_note, revision_table, or page_image. "
                "For hole_annotations, extract visible callouts such as "
                "4 x Φ9 完全贯穿, ⌴ Φ15 深9, M6, H7, countersink, or counterbore; "
                "do not infer holes that are not explicitly annotated."
            ),
            "schema": schema,
        },
        ensure_ascii=False,
    )
    if config.api_mode == "chat_completions":
        payload = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        *[
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": item["data_url"],
                                    "detail": config.detail,
                                },
                            }
                            for item in rendered_pages
                        ],
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
        }
        response_payload = post_pdf_vision_json(
            config,
            config.base_url.rstrip("/") + "/chat/completions",
            payload,
        )
        response_text = extract_chat_completion_text(response_payload)
    else:
        payload = {
            "model": config.model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": user_text},
                        *[
                            {
                                "type": "input_image",
                                "image_url": item["data_url"],
                            }
                            for item in rendered_pages
                        ],
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "pdf_vision_extract",
                    "schema": schema,
                    "strict": True,
                }
            },
        }
        response_payload = post_pdf_vision_json(
            config,
            config.base_url.rstrip("/") + "/responses",
            payload,
        )
        response_text = extract_response_text(response_payload)

    try:
        content = json.loads(strip_json_code_fence(response_text))
    except json.JSONDecodeError as exc:
        raise ParserError(
            "PDF_VISION_RESPONSE_INVALID_JSON",
            "多模态模型返回内容不是合法 JSON",
            details=[{"field": "response", "message": response_text[:500]}],
        ) from exc
    if not isinstance(content, dict):
        raise ParserError(
            "PDF_VISION_RESPONSE_INVALID_SCHEMA",
            "多模态模型返回 JSON 必须是对象",
            details=[{"field": "response_type", "message": type(content).__name__}],
        )
    validate_pdf_vision_content(content, schema)
    return content


def post_pdf_vision_json(
    config: PdfVisionConfig,
    url: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=config.timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
    except httpx.RequestError as exc:
        raise ParserError(
            "PDF_VISION_REQUEST_FAILED",
            f"多模态模型请求失败：{exc}",
            details=[{"field": "url", "message": url}],
        ) from exc
    if response.status_code >= 400:
        raise ParserError(
            "PDF_VISION_REQUEST_FAILED",
            f"多模态模型请求失败，HTTP {response.status_code}",
            details=[{"field": "response", "message": response.text[:500]}],
        )
    try:
        return response.json()
    except ValueError as exc:
        raise ParserError(
            "PDF_VISION_RESPONSE_NOT_JSON",
            "多模态模型 HTTP 响应不是 JSON",
            details=[{"field": "response", "message": response.text[:500]}],
        ) from exc


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
        raise ParserError(
            "PDF_VISION_RESPONSE_EMPTY",
            "多模态模型响应不包含文本内容",
        )
    return response_text


def extract_chat_completion_text(response_payload: dict[str, Any]) -> str:
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ParserError(
            "PDF_VISION_RESPONSE_EMPTY",
            "多模态模型响应不包含 choices",
        )
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ParserError(
            "PDF_VISION_RESPONSE_INVALID_SCHEMA",
            "多模态模型 choice 必须是对象",
        )
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ParserError(
            "PDF_VISION_RESPONSE_INVALID_SCHEMA",
            "多模态模型 choice 不包含 message",
        )
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(
            item.get("text", "") for item in content if isinstance(item, dict)
        )
    if not isinstance(content, str) or not content.strip():
        raise ParserError(
            "PDF_VISION_RESPONSE_EMPTY",
            "多模态模型 message 不包含文本内容",
        )
    return content


def strip_json_code_fence(value: str) -> str:
    stripped = value.strip()
    if not stripped.startswith("```"):
        return stripped
    stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def validate_pdf_vision_content(
    content: dict[str, Any],
    schema: dict[str, Any],
) -> None:
    try:
        validate(instance=content, schema=schema)
    except ValidationError as exc:
        path = ".".join(str(item) for item in exc.path) or "$"
        raise ParserError(
            "PDF_VISION_RESPONSE_INVALID_SCHEMA",
            "多模态模型返回 JSON 不符合 PDF 解析结构",
            details=[
                {
                    "field": path,
                    "message": exc.message,
                }
            ],
        ) from exc


def pdf_vision_extract_schema() -> dict[str, Any]:
    field_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "value",
            "raw_text",
            "page",
            "location",
            "confidence",
            "evidence_summary",
        ],
        "properties": {
            "value": nullable_string_schema(),
            "raw_text": nullable_string_schema(),
            "page": nullable_integer_schema(),
            "location": nullable_string_schema(),
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence_summary": {"type": "string"},
        },
    }
    list_item_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "text",
            "page",
            "location",
            "confidence",
            "evidence_summary",
        ],
        "properties": {
            "text": {"type": "string"},
            "page": nullable_integer_schema(),
            "location": nullable_string_schema(),
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence_summary": {"type": "string"},
        },
    }
    hole_annotation_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "hole_type",
            "count",
            "diameter",
            "depth",
            "through",
            "counterbore_diameter",
            "counterbore_depth",
            "countersink_diameter",
            "countersink_depth",
            "countersink_angle",
            "raw_text",
            "page",
            "location",
            "confidence",
            "evidence_summary",
        ],
        "properties": {
            "hole_type": {
                "type": "string",
                "enum": [
                    "through",
                    "blind",
                    "counterbore",
                    "countersink",
                    "thread_candidate",
                    "precision_candidate",
                ],
            },
            "count": nullable_integer_schema(),
            "diameter": nullable_number_schema(),
            "depth": nullable_number_schema(),
            "through": {"type": ["boolean", "null"]},
            "counterbore_diameter": nullable_number_schema(),
            "counterbore_depth": nullable_number_schema(),
            "countersink_diameter": nullable_number_schema(),
            "countersink_depth": nullable_number_schema(),
            "countersink_angle": nullable_number_schema(),
            "raw_text": nullable_string_schema(),
            "page": nullable_integer_schema(),
            "location": nullable_string_schema(),
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence_summary": {"type": "string"},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "fields",
            "weight_value",
            "weight_unit",
            "tolerance_texts",
            "roughness_texts",
            "technical_requirements",
            "hole_annotations",
            "notes",
            "confidence",
        ],
        "properties": {
            "fields": {
                "type": "object",
                "additionalProperties": False,
                "required": list(PDF_FIELD_KEYS),
                "properties": {key: field_schema for key in PDF_FIELD_KEYS},
            },
            "weight_value": nullable_number_schema(),
            "weight_unit": nullable_string_schema(),
            "tolerance_texts": {"type": "array", "items": list_item_schema},
            "roughness_texts": {"type": "array", "items": list_item_schema},
            "technical_requirements": {"type": "array", "items": list_item_schema},
            "hole_annotations": {"type": "array", "items": hole_annotation_schema},
            "notes": nullable_string_schema(),
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }


def nullable_string_schema() -> dict[str, Any]:
    return {"type": ["string", "null"]}


def nullable_number_schema() -> dict[str, Any]:
    return {"type": ["number", "null"]}


def nullable_integer_schema() -> dict[str, Any]:
    return {"type": ["integer", "null"]}


def vision_content_to_fields(
    pdf_file: dict[str, Any],
    content: dict[str, Any],
) -> dict[str, ExtractedPdfField]:
    raw_fields = content.get("fields") if isinstance(content.get("fields"), dict) else {}
    fields: dict[str, ExtractedPdfField] = {}
    for field_key in PDF_FIELD_KEYS:
        item = raw_fields.get(field_key) if isinstance(raw_fields, dict) else None
        if not isinstance(item, dict):
            fields[field_key] = empty_vision_field(pdf_file, field_key)
            continue

        raw_text = vision_field_raw_text(field_key, item, content)
        value = clean_field_value(raw_text or "", field_key) if raw_text else None
        confidence = bounded_pdf_confidence(item.get("confidence")) if value else 0.0
        if not value:
            fields[field_key] = empty_vision_field(pdf_file, field_key)
            continue

        evidence = source_ref(
            "pdf",
            file_id=pdf_file["file_id"],
            page=integer_or_none(item.get("page")),
            location=string_or_none(item.get("location")) or "page_image",
            raw_text=raw_text,
            rule_code=f"PDF_VISION:{field_key}",
        )
        candidate = pdf_field_candidate(
            field_key=field_key,
            value=value,
            confidence=confidence,
            extract_method="vision_model",
            evidence=evidence,
        )
        fields[field_key] = ExtractedPdfField(
            value=value,
            evidence=evidence,
            confidence=confidence,
            extract_method="vision_model",
            candidates=[candidate],
        )
    return fields


def vision_field_raw_text(
    field_key: str,
    item: dict[str, Any],
    content: dict[str, Any],
) -> str | None:
    raw_text = string_or_none(item.get("raw_text")) or string_or_none(
        item.get("value")
    )
    if field_key != "weight_raw":
        return raw_text
    if not raw_text:
        weight_value = number_or_none(content.get("weight_value"))
        unit = string_or_none(content.get("weight_unit"))
        if weight_value is not None and unit:
            return f"{weight_value:g} {unit}"
        return None
    if parse_weight(raw_text) != (None, None):
        return raw_text

    unit = string_or_none(content.get("weight_unit"))
    if unit and re.search(r"\d", raw_text):
        return f"{raw_text} {unit}"
    return raw_text


def empty_vision_field(
    pdf_file: dict[str, Any],
    field_key: str,
) -> ExtractedPdfField:
    return ExtractedPdfField(
        value=None,
        evidence=source_ref(
            "pdf",
            file_id=pdf_file["file_id"],
            location="page_image",
            raw_text=None,
            rule_code=f"PDF_VISION_FIELD_NOT_FOUND:{field_key}",
        ),
        confidence=0.0,
        extract_method="vision_model_not_found",
        candidates=[],
    )


def vision_content_to_matches(
    *,
    pdf_file: dict[str, Any],
    content: dict[str, Any],
    list_key: str,
    rule_code: str,
) -> list[dict[str, Any]]:
    raw_items = content.get(list_key)
    if not isinstance(raw_items, list):
        return []

    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_items:
        if isinstance(item, str):
            text = normalize_text(item)
            page = None
            location = "page_image"
            confidence = 0.6
        elif isinstance(item, dict):
            text = normalize_text(str(item.get("text") or ""))
            page = integer_or_none(item.get("page"))
            location = string_or_none(item.get("location")) or "page_image"
            confidence = bounded_pdf_confidence(item.get("confidence"), default=0.6)
        else:
            continue
        if not text:
            continue
        normalized = normalize_candidate_value(text)
        if normalized in seen:
            continue
        seen.add(normalized)
        evidence = source_ref(
            "pdf",
            file_id=pdf_file["file_id"],
            page=page,
            location=location,
            raw_text=text,
            rule_code=rule_code,
        )
        matches.append(
            {
                "text": text,
                "confidence": confidence,
                "extract_method": "vision_model",
                "evidence": evidence,
            }
        )
    return matches


def vision_content_to_hole_annotations(
    *,
    pdf_file: dict[str, Any],
    content: dict[str, Any],
) -> list[dict[str, Any]]:
    raw_items = content.get("hole_annotations")
    if not isinstance(raw_items, list):
        return []

    annotations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        raw_text = normalize_text(str(item.get("raw_text") or ""))
        hole_type = normalize_hole_type(item.get("hole_type"))
        count = integer_or_none(item.get("count")) or 1
        diameter = number_or_none(item.get("diameter"))
        evidence = source_ref(
            "pdf",
            file_id=pdf_file["file_id"],
            page=integer_or_none(item.get("page")),
            location=string_or_none(item.get("location")) or "page_image",
            raw_text=raw_text or None,
            rule_code="PDF_VISION:HOLE_ANNOTATION",
        )
        annotation = hole_annotation_item(
            hole_type=hole_type,
            diameter=diameter,
            depth=number_or_none(item.get("depth")),
            count=count,
            confidence=bounded_pdf_confidence(item.get("confidence"), default=0.72),
            evidence=evidence,
            raw_text=raw_text,
            through=item.get("through") if isinstance(item.get("through"), bool) else None,
            counterbore_diameter=number_or_none(item.get("counterbore_diameter")),
            counterbore_depth=number_or_none(item.get("counterbore_depth")),
            countersink_diameter=number_or_none(item.get("countersink_diameter")),
            countersink_depth=number_or_none(item.get("countersink_depth")),
            countersink_angle=number_or_none(item.get("countersink_angle")),
            extract_method="vision_model",
        )
        key = hole_annotation_key(annotation)
        if key in seen:
            continue
        seen.add(key)
        annotations.append(annotation)
    return annotations


def build_pdf_extract_result(
    *,
    task: dict[str, Any],
    pdf_file: dict[str, Any],
    parser_name: str,
    fields: dict[str, ExtractedPdfField],
    tolerance_matches: list[dict[str, Any]],
    roughness_matches: list[dict[str, Any]],
    technical_requirement_matches: list[dict[str, Any]],
    hole_annotation_matches: list[dict[str, Any]],
    text_layer: dict[str, Any],
    text_pages: list[dict[str, Any]],
    text_blocks: list[dict[str, Any]],
    vision: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    result = {
        "schema_version": "1.0",
        "task_id": task["task_id"],
        "file_id": pdf_file["file_id"],
        "file_name": pdf_file.get("filename"),
        "parser_name": parser_name,
        "text_layer": text_layer,
        "drawing_no": fields["drawing_no"].value,
        "part_name": fields["part_name"].value,
        "part_type_raw": fields["part_type_raw"].value,
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
        "hole_annotations": hole_annotation_matches,
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
        "field_candidates": {
            key: field.candidates for key, field in fields.items()
        },
        "field_details": build_pdf_field_details(
            fields=fields,
            weight_value=weight_value,
            weight_unit=weight_unit,
            tolerance_matches=tolerance_matches,
            roughness_matches=roughness_matches,
            technical_requirement_matches=technical_requirement_matches,
            hole_annotation_matches=hole_annotation_matches,
        ),
        "text_pages": text_pages,
        "text_blocks": text_blocks,
        "risks": risks,
    }
    if vision is not None:
        result["vision"] = vision
    return result


def pdf_result_needs_vision(pdf_result: dict[str, Any]) -> bool:
    field_confidence = pdf_result.get("field_confidence") or {}
    for field_key in ("drawing_no", "part_name", "material_raw", "weight_raw"):
        if not pdf_result.get(field_key):
            return True
        if bounded_pdf_confidence(field_confidence.get(field_key), default=0.0) < (
            LOW_CONFIDENCE_THRESHOLD
        ):
            return True
    return False


def merge_pdf_vision_result(
    text_result: dict[str, Any],
    vision_result: dict[str, Any],
    parser_name: str,
) -> dict[str, Any]:
    merged = dict(text_result)
    merged["parser_name"] = parser_name
    merged["parser_chain"] = [
        text_result.get("parser_name"),
        vision_result.get("parser_name"),
    ]
    merged["vision"] = vision_result.get("vision")
    field_confidence = dict(text_result.get("field_confidence") or {})
    field_evidence = dict(text_result.get("field_evidence") or {})
    extract_method = dict(text_result.get("extract_method") or {})
    field_candidates = dict(text_result.get("field_candidates") or {})
    field_details = dict(text_result.get("field_details") or {})

    for field_key in PDF_FIELD_KEYS:
        text_confidence = bounded_pdf_confidence(
            field_confidence.get(field_key),
            default=0.0,
        )
        vision_confidence = bounded_pdf_confidence(
            (vision_result.get("field_confidence") or {}).get(field_key),
            default=0.0,
        )
        vision_value = vision_result.get(field_key)
        if not vision_value:
            continue
        if (
            not text_result.get(field_key)
            or text_confidence < LOW_CONFIDENCE_THRESHOLD
            or vision_confidence > text_confidence + 0.05
        ):
            merged[field_key] = vision_value
            field_confidence[field_key] = vision_confidence
            field_evidence[field_key] = (
                vision_result.get("field_evidence") or {}
            ).get(field_key)
            extract_method[field_key] = (
                vision_result.get("extract_method") or {}
            ).get(field_key)
            field_candidates[field_key] = (
                vision_result.get("field_candidates") or {}
            ).get(field_key, [])
            if field_key in (vision_result.get("field_details") or {}):
                field_details[field_key] = vision_result["field_details"][field_key]
            if field_key == "weight_raw":
                merged["weight_value"] = vision_result.get("weight_value")
                merged["weight_unit"] = vision_result.get("weight_unit")
                for detail_key in ("weight_value", "weight_unit"):
                    if detail_key in (vision_result.get("field_details") or {}):
                        field_details[detail_key] = vision_result["field_details"][
                            detail_key
                        ]

    for values_key, evidence_key, detail_key in (
        ("tolerance_texts", "tolerance_evidence", "tolerance_texts"),
        ("roughness_texts", "roughness_evidence", "roughness_texts"),
        (
            "technical_requirements",
            "technical_requirement_evidence",
            "technical_requirements",
        ),
    ):
        merged_values, merged_evidence = merge_pdf_text_lists(
            text_result.get(values_key) or [],
            text_result.get(evidence_key) or [],
            vision_result.get(values_key) or [],
            vision_result.get(evidence_key) or [],
        )
        merged[values_key] = merged_values
        merged[evidence_key] = merged_evidence
        if not text_result.get(values_key) and detail_key in (
            vision_result.get("field_details") or {}
        ):
            field_details[detail_key] = vision_result["field_details"][detail_key]

    merged["hole_annotations"] = merge_pdf_hole_annotations(
        text_result.get("hole_annotations") or [],
        vision_result.get("hole_annotations") or [],
    )
    if not text_result.get("hole_annotations") and "hole_annotations" in (
        vision_result.get("field_details") or {}
    ):
        field_details["hole_annotations"] = vision_result["field_details"][
            "hole_annotations"
        ]

    merged["field_confidence"] = field_confidence
    merged["field_evidence"] = field_evidence
    merged["extract_method"] = extract_method
    merged["field_candidates"] = field_candidates
    merged["field_details"] = field_details
    merged["risks"] = dedupe_risks(
        (text_result.get("risks") or []) + (vision_result.get("risks") or [])
    )
    return merged


def merge_pdf_text_lists(
    text_values: list[Any],
    text_evidence: list[Any],
    vision_values: list[Any],
    vision_evidence: list[Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    values: list[str] = []
    evidences: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source_values, source_evidence in (
        (text_values, text_evidence),
        (vision_values, vision_evidence),
    ):
        for index, value in enumerate(source_values):
            text = normalize_text(str(value or ""))
            key = normalize_candidate_value(text)
            if not text or key in seen:
                continue
            seen.add(key)
            values.append(text)
            evidence = (
                source_evidence[index]
                if index < len(source_evidence) and isinstance(source_evidence[index], dict)
                else source_ref("pdf", raw_text=text)
            )
            evidences.append(evidence)
    return values, evidences


def merge_pdf_hole_annotations(
    text_annotations: list[Any],
    vision_annotations: list[Any],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for annotations in (text_annotations, vision_annotations):
        for annotation in annotations:
            if not isinstance(annotation, dict):
                continue
            key = hole_annotation_key(annotation)
            if key in seen:
                continue
            seen.add(key)
            merged.append(annotation)
    return merged


def dedupe_risks(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result = []
    for risk in risks:
        code = str(risk.get("code") or "")
        message = str(risk.get("message") or "")
        key = (code, message)
        if key in seen:
            continue
        seen.add(key)
        result.append(risk)
    return result


def pdf_vision_unavailable_risk(
    pdf_file: dict[str, Any],
    exc: Exception,
) -> dict[str, Any]:
    parser_error = exc if isinstance(exc, ParserError) else None
    return risk_item(
        "PDF_VISION_UNAVAILABLE",
        "warning",
        f"多模态 PDF 图像解析不可用，已保留 text layer 解析结果：{exc}",
        "pdf_parser",
        True,
        [
            source_ref(
                "system",
                file_id=pdf_file["file_id"],
                raw_text=str(exc),
                rule_code=parser_error.code if parser_error else "PDF_VISION_ERROR",
            )
        ],
    )


def string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def integer_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        integer = int(value)
    except (TypeError, ValueError):
        return None
    return integer if integer > 0 else None


def number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def bounded_pdf_confidence(value: Any, *, default: float = 0.5) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return max(0.0, min(1.0, confidence))


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
    candidates = collect_pdf_field_candidates(
        field_key=field_key,
        pdf_file=pdf_file,
        blocks=blocks,
        full_text=full_text,
    )
    if candidates:
        selected = candidates[0]
        return ExtractedPdfField(
            value=selected["value"],
            evidence=selected["evidence"],
            confidence=selected["confidence"],
            extract_method=selected["extract_method"],
            candidates=candidates,
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
        candidates=[],
    )


def collect_pdf_field_candidates(
    *,
    field_key: str,
    pdf_file: dict[str, Any],
    blocks: list[dict[str, Any]],
    full_text: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
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

                candidates.append(
                    pdf_field_candidate(
                        field_key=field_key,
                        value=value,
                        confidence=0.82,
                        extract_method="text_layer_regex",
                        evidence=source_ref(
                            "pdf",
                            file_id=pdf_file["file_id"],
                            page=block["page"],
                            location=block_location(block),
                            raw_text=value,
                            rule_code=f"PDF_TEXT_REGEX:{field_key}",
                        ),
                    )
                )

    title_field = find_title_block_field(
        field_key=field_key,
        pdf_file=pdf_file,
        blocks=blocks,
    )
    if title_field.value:
        candidates.append(
            pdf_field_candidate(
                field_key=field_key,
                value=title_field.value,
                confidence=title_field.confidence,
                extract_method=title_field.extract_method,
                evidence=title_field.evidence,
            )
        )

    for pattern in patterns:
        compiled = re.compile(pattern, re.IGNORECASE)
        match = compiled.search(full_text)
        if match:
            value = clean_field_value(match.group("value"), field_key)
            if value:
                candidates.append(
                    pdf_field_candidate(
                        field_key=field_key,
                        value=value,
                        confidence=0.65,
                        extract_method="text_layer_regex_full_text",
                        evidence=source_ref(
                            "pdf",
                            file_id=pdf_file["file_id"],
                            raw_text=value,
                            rule_code=f"PDF_TEXT_REGEX:{field_key}",
                        ),
                    ),
                )

    return ranked_unique_candidates(candidates)


def pdf_field_candidate(
    *,
    field_key: str,
    value: str,
    confidence: float,
    extract_method: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "field_name": field_key,
        "value": value,
        "raw_text": evidence.get("raw_text") or value,
        "confidence": confidence,
        "extract_method": extract_method,
        "evidence": evidence,
        "evidence_detail": evidence_with_metadata(
            evidence,
            confidence=confidence,
            extract_method=extract_method,
        ),
    }


def ranked_unique_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = normalize_candidate_value(candidate.get("value"))
        existing = unique.get(key)
        if existing is None or candidate["confidence"] > existing["confidence"]:
            unique[key] = candidate
    return sorted(
        unique.values(),
        key=lambda item: (-float(item.get("confidence") or 0), str(item.get("value") or "")),
    )[:MAX_FIELD_CANDIDATES]


def normalize_candidate_value(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def evidence_with_metadata(
    evidence: dict[str, Any],
    *,
    confidence: float,
    extract_method: str,
) -> dict[str, Any]:
    return {
        **evidence,
        "confidence": confidence,
        "extract_method": extract_method,
    }


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
        r"\s+(?:图号|图纸编号|物件料号|零件名称|零件名|品名|零件类型|零件类别|物件类型|材料|材质|重量|净重|单重|比例|版本|版次|"
        r"热处理|表面处理|Drawing|Part\s*Name|Part\s*Type|Part\s*Category|Description|Material|Mat\.?|"
        r"Weight|Scale|Revision|Rev\.?|Heat\s*Treatment|Surface\s*Treatment|"
        r"Finish|Plating)\s*[:：]?",
        re.IGNORECASE,
    )
    label_match = next_label_pattern.search(cleaned)
    if label_match:
        cleaned = cleaned[: label_match.start()].strip(" :：;；,，")
    if not cleaned or looks_like_title_label(cleaned):
        return None

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


def collect_hole_annotation_matches(
    *,
    pdf_file: dict[str, Any],
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    annotations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for context_blocks in hole_annotation_context_blocks(blocks):
        annotation = parse_hole_annotation_context(
            pdf_file=pdf_file,
            blocks=context_blocks,
        )
        if annotation is None:
            continue
        key = hole_annotation_key(annotation)
        if key in seen:
            continue
        seen.add(key)
        annotations.append(annotation)
    return annotations


def hole_annotation_context_blocks(
    blocks: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    ordered_blocks = sorted(
        blocks,
        key=lambda item: (
            int(item.get("page") or 0),
            int(item.get("parent_block_index", item.get("block_index") or 0)),
            float((item.get("bbox") or [0, 0, 0, 0])[1]),
            float((item.get("bbox") or [0, 0, 0, 0])[0]),
            int(item.get("block_index") or 0),
        ),
    )
    contexts: list[list[dict[str, Any]]] = []
    for index, block in enumerate(ordered_blocks):
        text = normalize_hole_note_text(str(block.get("text") or ""))
        next_texts = [
            normalize_hole_note_text(str(item.get("text") or ""))
            for item in ordered_blocks[index + 1 : index + 4]
        ]
        if not hole_text_starts_annotation(text, next_texts):
            continue
        context = [block]
        for next_block in ordered_blocks[index + 1 : index + 7]:
            if not hole_blocks_are_adjacent(block, next_block):
                break
            next_text = normalize_hole_note_text(str(next_block.get("text") or ""))
            if hole_text_starts_annotation(next_text, []) and len(context) > 1:
                break
            if hole_text_has_secondary_signal(next_text) or hole_text_has_numeric_note_signal(next_text):
                context.append(next_block)
        contexts.append(context)
    return contexts


def hole_blocks_are_adjacent(
    current: dict[str, Any],
    candidate: dict[str, Any],
) -> bool:
    if current.get("page") != candidate.get("page"):
        return False
    current_parent = current.get("parent_block_index")
    candidate_parent = candidate.get("parent_block_index")
    if current_parent is not None and candidate_parent is not None:
        if current_parent == candidate_parent:
            return True
        current_bbox = current.get("bbox") or [0, 0, 0, 0]
        candidate_bbox = candidate.get("bbox") or [0, 0, 0, 0]
        try:
            vertical_gap = abs(float(candidate_bbox[1]) - float(current_bbox[1]))
            horizontal_gap = abs(float(candidate_bbox[0]) - float(current_bbox[0]))
            return vertical_gap <= 24 and horizontal_gap <= 90
        except (TypeError, ValueError, IndexError):
            return False
    current_bbox = current.get("bbox") or [0, 0, 0, 0]
    candidate_bbox = candidate.get("bbox") or [0, 0, 0, 0]
    try:
        return abs(float(candidate_bbox[1]) - float(current_bbox[1])) <= 24
    except (TypeError, ValueError, IndexError):
        return False


def parse_hole_annotation_context(
    *,
    pdf_file: dict[str, Any],
    blocks: list[dict[str, Any]],
) -> dict[str, Any] | None:
    lines = [
        normalize_hole_note_text(str(block.get("text") or ""))
        for block in blocks
        if normalize_hole_note_text(str(block.get("text") or ""))
    ]
    if not lines:
        return None
    raw_text = "; ".join(lines)
    combined_text = " ".join(lines)
    main_line = next((line for line in lines if hole_text_has_main_signal(line)), combined_text)
    main_match = HOLE_COUNT_DIAMETER_PATTERN.search(main_line)
    thread_match = HOLE_THREAD_PATTERN.search(main_line)
    if main_match is None and thread_match is None:
        return None

    count = integer_or_none(
        (thread_match.group("count") if thread_match else None)
        or (main_match.group("count") if main_match else None)
    ) or 1
    diameter = number_or_none(
        (thread_match.group("diameter") if thread_match else None)
        or (main_match.group("diameter") if main_match else None)
    )
    through = hole_text_has_through_signal(raw_text)
    tail_numbers = hole_tail_numbers(combined_text, main_match, thread_match)
    main_depth = None if through else first_hole_depth(main_line)
    if main_depth is None and not through and tail_numbers:
        main_depth = tail_numbers[0]
        tail_numbers = tail_numbers[1:]
    counterbore = HOLE_COUNTERBORE_PATTERN.search(raw_text)
    countersink = HOLE_COUNTERSINK_PATTERN.search(raw_text)
    fallback_counterbore_diameter, fallback_counterbore_depth = infer_counterbore_from_tail_numbers(
        tail_numbers,
        diameter,
    )

    hole_type = "through" if through else "blind" if main_depth is not None else "through"
    if counterbore or fallback_counterbore_diameter is not None:
        hole_type = "counterbore"
    elif countersink:
        hole_type = "countersink"
    if thread_match or re.search(r"攻牙|螺纹|螺絲|thread", raw_text, re.IGNORECASE):
        hole_type = "thread_candidate"
    elif hole_text_has_precision_signal(raw_text):
        hole_type = "precision_candidate"

    first_block = blocks[0]
    evidence = source_ref(
        "pdf",
        file_id=pdf_file["file_id"],
        page=integer_or_none(first_block.get("page")),
        location=block_location(first_block),
        raw_text=raw_text,
        rule_code="PDF_TEXT_HOLE_ANNOTATION",
    )
    confidence = 0.88
    if len(blocks) > 1:
        confidence = 0.9
    if hole_type in {"thread_candidate", "precision_candidate"}:
        confidence = 0.82

    return hole_annotation_item(
        hole_type=hole_type,
        diameter=diameter,
        depth=main_depth,
        count=count,
        confidence=confidence,
        evidence=evidence,
        raw_text=raw_text,
        through=through,
        counterbore_diameter=number_or_none(counterbore.group("diameter")) if counterbore else fallback_counterbore_diameter,
        counterbore_depth=number_or_none(counterbore.group("depth")) if counterbore else fallback_counterbore_depth,
        countersink_diameter=number_or_none(countersink.group("diameter")) if countersink else None,
        countersink_depth=number_or_none(countersink.group("depth")) if countersink else None,
        countersink_angle=number_or_none(countersink.group("angle")) if countersink else None,
        extract_method="text_layer_regex",
    )


def normalize_hole_note_text(value: str) -> str:
    text = normalize_text(value)
    replacements = {
        "×": "x",
        "＊": "*",
        "Ø": "Φ",
        "ø": "Φ",
        "φ": "Φ",
        "⌀": "Φ",
        "∅": "Φ",
        "完全穿透": "完全贯穿",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return " ".join(text.split())


def hole_text_starts_annotation(text: str, next_texts: list[str]) -> bool:
    if hole_text_has_main_signal(text):
        return True
    if not hole_text_is_count_prefix(text):
        return False
    return any(hole_text_has_numeric_note_signal(next_text) for next_text in next_texts)


def hole_text_is_count_prefix(text: str) -> bool:
    return bool(re.fullmatch(r"\d+\s*(?:x|X|\*)", text.strip()))


def hole_text_has_main_signal(text: str) -> bool:
    return bool(
        HOLE_COUNT_DIAMETER_PATTERN.search(text)
        or HOLE_THREAD_PATTERN.search(text)
    )


def hole_text_has_secondary_signal(text: str) -> bool:
    return bool(
        HOLE_COUNTERBORE_PATTERN.search(text)
        or HOLE_COUNTERSINK_PATTERN.search(text)
        or hole_text_has_through_signal(text)
        or HOLE_DEPTH_PATTERN.search(text)
    )


def hole_text_has_numeric_note_signal(text: str) -> bool:
    if not re.search(r"\d", text):
        return False
    return bool(
        re.fullmatch(r"\d+(?:\.\d+)?(?:\s*\S{0,4})?", text)
        or re.search(r"\d+(?:\.\d+)?\s*(?:完全贯穿|贯穿|通孔|反面)", text, re.IGNORECASE)
    )


def hole_text_has_through_signal(text: str) -> bool:
    return bool(re.search(r"完全贯穿|贯穿|通孔|through|thru", text, re.IGNORECASE))


def hole_text_has_precision_signal(text: str) -> bool:
    return bool(
        re.search(r"\b[HEG]\d\b|铰孔|精孔|配合孔|精密孔", text, re.IGNORECASE)
        or is_high_precision_text(text)
    )


def first_hole_depth(text: str) -> float | None:
    match = HOLE_DEPTH_PATTERN.search(text)
    return number_or_none(match.group("depth")) if match else None


def hole_tail_numbers(
    text: str,
    main_match: re.Match[str] | None,
    thread_match: re.Match[str] | None,
) -> list[float]:
    consumed_end = 0
    if main_match is not None:
        consumed_end = max(consumed_end, main_match.end())
    if thread_match is not None:
        consumed_end = max(consumed_end, thread_match.end())
    tail_text = text[consumed_end:]
    return [
        float(match.group(0))
        for match in re.finditer(r"\d+(?:\.\d+)?", tail_text)
    ]


def infer_counterbore_from_tail_numbers(
    numbers: list[float],
    base_diameter: float | None,
) -> tuple[float | None, float | None]:
    if len(numbers) < 2:
        return None, None
    counterbore_diameter = numbers[0]
    counterbore_depth = numbers[1]
    if base_diameter is not None and counterbore_diameter <= base_diameter:
        return None, None
    return counterbore_diameter, counterbore_depth


def normalize_hole_type(value: Any) -> str:
    text = str(value or "").strip()
    if text in {
        "through",
        "blind",
        "counterbore",
        "countersink",
        "thread_candidate",
        "precision_candidate",
    }:
        return text
    return "through"


def hole_annotation_item(
    *,
    hole_type: str,
    diameter: float | None,
    depth: float | None,
    count: int,
    confidence: float,
    evidence: dict[str, Any],
    raw_text: str,
    through: bool | None,
    counterbore_diameter: float | None,
    counterbore_depth: float | None,
    countersink_diameter: float | None,
    countersink_depth: float | None,
    countersink_angle: float | None,
    extract_method: str,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "hole_type": normalize_hole_type(hole_type),
        "diameter": diameter,
        "depth": depth,
        "count": max(1, int(count)),
        "confidence": bounded_pdf_confidence(confidence),
        "evidence": [evidence],
        "raw_text": raw_text,
        "through": through,
        "extract_method": extract_method,
    }
    optional_values = {
        "counterbore_diameter": counterbore_diameter,
        "counterbore_depth": counterbore_depth,
        "countersink_diameter": countersink_diameter,
        "countersink_depth": countersink_depth,
        "countersink_angle": countersink_angle,
    }
    item.update({key: value for key, value in optional_values.items() if value is not None})
    return item


def hole_annotation_key(item: dict[str, Any]) -> str:
    parts = [
        item.get("hole_type"),
        item.get("count"),
        rounded_key_number(item.get("diameter")),
        rounded_key_number(item.get("depth")),
        rounded_key_number(item.get("counterbore_diameter")),
        rounded_key_number(item.get("counterbore_depth")),
        rounded_key_number(item.get("countersink_diameter")),
        rounded_key_number(item.get("countersink_depth")),
        rounded_key_number(item.get("countersink_angle")),
        normalize_candidate_value(item.get("raw_text")),
    ]
    return "|".join(str(part) for part in parts)


def rounded_key_number(value: Any) -> str:
    number = number_or_none(value)
    return "" if number is None else f"{number:.3f}"


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
    hole_annotation_matches: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    tolerance_method = aggregate_match_method(tolerance_matches, "text_layer_regex")
    roughness_method = aggregate_match_method(roughness_matches, "text_layer_regex")
    technical_method = aggregate_match_method(
        technical_requirement_matches,
        "text_layer_keyword",
    )
    details = {
        key: {
            "raw_text": field.value,
            "value": field.value,
            "confidence": field.confidence,
            "extract_method": field.extract_method,
            "evidence": field.evidence,
            "evidence_detail": evidence_with_metadata(
                field.evidence,
                confidence=field.confidence,
                extract_method=field.extract_method,
            ),
            "candidates": field.candidates,
        }
        for key, field in fields.items()
    }
    details["weight_value"] = {
        "raw_text": fields["weight_raw"].value,
        "value": weight_value,
        "confidence": fields["weight_raw"].confidence if weight_value is not None else 0,
        "extract_method": fields["weight_raw"].extract_method,
        "evidence": fields["weight_raw"].evidence,
        "evidence_detail": evidence_with_metadata(
            fields["weight_raw"].evidence,
            confidence=fields["weight_raw"].confidence if weight_value is not None else 0,
            extract_method=fields["weight_raw"].extract_method,
        ),
        "candidates": fields["weight_raw"].candidates,
    }
    details["weight_unit"] = {
        "raw_text": fields["weight_raw"].value,
        "value": weight_unit,
        "confidence": fields["weight_raw"].confidence if weight_unit else 0,
        "extract_method": fields["weight_raw"].extract_method,
        "evidence": fields["weight_raw"].evidence,
        "evidence_detail": evidence_with_metadata(
            fields["weight_raw"].evidence,
            confidence=fields["weight_raw"].confidence if weight_unit else 0,
            extract_method=fields["weight_raw"].extract_method,
        ),
        "candidates": fields["weight_raw"].candidates,
    }
    details["tolerance_texts"] = {
        "raw_text": "; ".join(item["text"] for item in tolerance_matches) or None,
        "value": [item["text"] for item in tolerance_matches],
        "confidence": 0.78 if tolerance_matches else 0,
        "extract_method": tolerance_method,
        "evidence": [item["evidence"] for item in tolerance_matches],
        "evidence_detail": [
            evidence_with_metadata(
                item["evidence"],
                confidence=match_confidence(item, 0.78),
                extract_method=match_extract_method(item, "text_layer_regex"),
            )
            for item in tolerance_matches
        ],
        "candidates": [
            pdf_field_candidate(
                field_key="tolerance_texts",
                value=item["text"],
                confidence=match_confidence(item, 0.78),
                extract_method=match_extract_method(item, "text_layer_regex"),
                evidence=item["evidence"],
            )
            for item in tolerance_matches
        ],
    }
    details["roughness_texts"] = {
        "raw_text": "; ".join(item["text"] for item in roughness_matches) or None,
        "value": [item["text"] for item in roughness_matches],
        "confidence": 0.78 if roughness_matches else 0,
        "extract_method": roughness_method,
        "evidence": [item["evidence"] for item in roughness_matches],
        "evidence_detail": [
            evidence_with_metadata(
                item["evidence"],
                confidence=match_confidence(item, 0.78),
                extract_method=match_extract_method(item, "text_layer_regex"),
            )
            for item in roughness_matches
        ],
        "candidates": [
            pdf_field_candidate(
                field_key="roughness_texts",
                value=item["text"],
                confidence=match_confidence(item, 0.78),
                extract_method=match_extract_method(item, "text_layer_regex"),
                evidence=item["evidence"],
            )
            for item in roughness_matches
        ],
    }
    details["technical_requirements"] = {
        "raw_text": "\n".join(item["text"] for item in technical_requirement_matches)
        or None,
        "value": [item["text"] for item in technical_requirement_matches],
        "confidence": 0.72 if technical_requirement_matches else 0,
        "extract_method": technical_method,
        "evidence": [item["evidence"] for item in technical_requirement_matches],
        "evidence_detail": [
            evidence_with_metadata(
                item["evidence"],
                confidence=match_confidence(item, 0.72),
                extract_method=match_extract_method(item, "text_layer_keyword"),
            )
            for item in technical_requirement_matches
        ],
        "candidates": [
            pdf_field_candidate(
                field_key="technical_requirements",
                value=item["text"],
                confidence=match_confidence(item, 0.72),
                extract_method=match_extract_method(item, "text_layer_keyword"),
                evidence=item["evidence"],
            )
            for item in technical_requirement_matches
        ],
    }
    details["hole_annotations"] = {
        "raw_text": "\n".join(
            str(item.get("raw_text") or "") for item in hole_annotation_matches
        )
        or None,
        "value": hole_annotation_matches,
        "confidence": (
            max(float(item.get("confidence") or 0) for item in hole_annotation_matches)
            if hole_annotation_matches
            else 0
        ),
        "extract_method": aggregate_match_method(
            hole_annotation_matches,
            "text_layer_regex",
        ),
        "evidence": [
            evidence
            for item in hole_annotation_matches
            for evidence in item.get("evidence", [])
            if isinstance(evidence, dict)
        ],
        "evidence_detail": [
            evidence_with_metadata(
                evidence,
                confidence=float(item.get("confidence") or 0),
                extract_method=str(item.get("extract_method") or "text_layer_regex"),
            )
            for item in hole_annotation_matches
            for evidence in item.get("evidence", [])
            if isinstance(evidence, dict)
        ],
        "candidates": [
            pdf_field_candidate(
                field_key="hole_annotations",
                value=str(item.get("raw_text") or item.get("hole_type") or ""),
                confidence=float(item.get("confidence") or 0),
                extract_method=str(item.get("extract_method") or "text_layer_regex"),
                evidence=(item.get("evidence") or [source_ref("pdf")])[0],
            )
            for item in hole_annotation_matches
            if item.get("raw_text") or item.get("hole_type")
        ],
    }
    return details


def match_confidence(item: dict[str, Any], default: float) -> float:
    return bounded_pdf_confidence(item.get("confidence"), default=default)


def match_extract_method(item: dict[str, Any], default: str) -> str:
    method = item.get("extract_method")
    return method if isinstance(method, str) and method else default


def aggregate_match_method(matches: list[dict[str, Any]], default: str) -> str:
    methods = {match_extract_method(item, default) for item in matches}
    if not methods:
        return default
    if len(methods) == 1:
        return next(iter(methods))
    return "mixed"


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
        if field.value and field.confidence >= LOW_CONFIDENCE_THRESHOLD:
            continue

        risks.append(
            risk_item(
                "LOW_CONFIDENCE_FIELD",
                "warning",
                low_confidence_message(field_key, field),
                "pdf_parser",
                True,
                [field.evidence],
            )
        )

    for field_key, field in fields.items():
        if not candidate_values_conflict(field.candidates):
            continue
        risks.append(
            risk_item(
                "FIELD_CONFLICT",
                "warning",
                f"PDF 字段存在多个相近候选：{field_key}",
                "pdf_parser",
                True,
                field_conflict_evidence(field),
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
                "PDF 解析检测到高精度或高表面要求，需人工确认。",
                "pdf_parser",
                True,
                precision_evidence,
            )
        )

    if not risks:
        return []

    return risks


def low_confidence_message(field_key: str, field: ExtractedPdfField) -> str:
    if not field.value:
        return f"PDF 解析未能稳定抽取字段：{field_key}"
    return (
        f"PDF 字段置信度低于阈值：{field_key}；"
        f"当前值：{field.value}；置信度：{field.confidence:.2f}"
    )


def candidate_values_conflict(candidates: list[dict[str, Any]]) -> bool:
    if len(candidates) < 2:
        return False

    top = candidates[0]
    second = candidates[1]
    top_value = normalize_candidate_value(top.get("value"))
    second_value = normalize_candidate_value(second.get("value"))
    if not top_value or not second_value or top_value == second_value:
        return False

    top_confidence = float(top.get("confidence") or 0)
    second_confidence = float(second.get("confidence") or 0)
    return abs(top_confidence - second_confidence) <= FIELD_CONFLICT_THRESHOLD


def field_conflict_evidence(field: ExtractedPdfField) -> list[dict[str, Any]]:
    evidences: list[dict[str, Any]] = []
    for candidate in field.candidates[:2]:
        evidence = candidate.get("evidence")
        if isinstance(evidence, dict):
            evidences.append(evidence)
    return evidences or [field.evidence]


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

    return ParserService(
        mode=parser_mode,
        pdf_parser=VisionAssistedPdfParser(),
        step_parser=RealStepParser(),
    )


def normalize_parser_mode(value: str) -> ParserMode:
    normalized = value.strip().lower()
    if normalized in {"auto", "real"}:
        return normalized  # type: ignore[return-value]
    return "auto"


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
            f"{parser_kind} 真实解析失败，未生成替代解析结果。"
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
