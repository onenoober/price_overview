from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Any

from .storage import REPO_ROOT


SPREADSHEET_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
KG_PER_MM3_PER_G_CM3 = 1 / 1_000_000
MATERIAL_DENSITY_RULE_CODE = "MATERIAL_DENSITY_ARCHIVE"


@dataclass(frozen=True)
class MaterialDensityMatch:
    raw_text: str
    material_name: str
    density_g_cm3: float
    density_kg_mm3: float
    archive_file: str

    def to_step_density(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "material_name": self.material_name,
            "density_g_cm3": self.density_g_cm3,
            "density_kg_mm3": self.density_kg_mm3,
            "density_unit": "kg/mm3",
            "source": self.source_ref(),
        }

    def source_ref(self) -> dict[str, Any]:
        return {
            "source_type": "price_rule",
            "location": self.archive_file,
            "raw_text": (
                f"{self.material_name}; density={self.density_g_cm3} g/cm3"
            ),
            "rule_code": MATERIAL_DENSITY_RULE_CODE,
        }


@dataclass(frozen=True)
class MaterialArchiveRecord:
    material_name: str
    spec: str
    unit: str
    unit_price: float | None
    density_g_cm3: float
    archive_file: str


def lookup_material_density(raw_text: Any) -> MaterialDensityMatch | None:
    normalized = normalize_material_key(raw_text)
    if not normalized:
        return None

    for record in material_archive_records():
        if normalized in material_aliases(record.material_name):
            return MaterialDensityMatch(
                raw_text=str(raw_text).strip(),
                material_name=record.material_name,
                density_g_cm3=record.density_g_cm3,
                density_kg_mm3=record.density_g_cm3 * KG_PER_MM3_PER_G_CM3,
                archive_file=record.archive_file,
            )
    return None


@lru_cache(maxsize=1)
def material_archive_records() -> tuple[MaterialArchiveRecord, ...]:
    records: list[MaterialArchiveRecord] = []
    for path in sorted(REPO_ROOT.glob("*.xlsx"), key=lambda item: item.name):
        rows = read_first_sheet_rows(path)
        if len(rows) < 3 or len(rows[1]) < 5:
            continue
        if rows[1][4] != "\u5bc6\u5ea6":
            continue
        for row in rows[2:]:
            if len(row) < 5 or not row[0] or not row[4]:
                continue
            density = parse_float(row[4])
            if density is None:
                continue
            records.append(
                MaterialArchiveRecord(
                    material_name=row[0],
                    spec=row[1] if len(row) > 1 else "",
                    unit=row[2] if len(row) > 2 else "",
                    unit_price=parse_float(row[3] if len(row) > 3 else None),
                    density_g_cm3=density,
                    archive_file=path.name,
                )
            )
    return tuple(records)


def material_aliases(material_name: str) -> set[str]:
    normalized = normalize_material_key(material_name)
    aliases = {normalized}
    if normalized.endswith("#"):
        aliases.add(normalized[:-1])
    if normalized.startswith("AL") and len(normalized) > 2:
        aliases.add(normalized[2:])
    if normalized == "45#":
        aliases.add("45")
        aliases.add("S45C")
    return {alias for alias in aliases if alias}


def normalize_material_key(value: Any) -> str:
    if value in (None, ""):
        return ""
    text = str(value).strip().upper()
    text = text.replace("\uff03", "#")
    text = re.sub(r"[\s_\-]+", "", text)
    for suffix in ("\u94a2", "\u677f", "\u6750"):
        text = text.removesuffix(suffix)
    return text


def parse_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def read_first_sheet_rows(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as workbook:
        shared_strings = read_shared_strings(workbook)
        sheet_path = first_sheet_path(workbook)
        root = ET.fromstring(workbook.read(sheet_path))
        rows: list[list[str]] = []
        max_cols = 0
        for row in root.findall(".//a:sheetData/a:row", SPREADSHEET_NS):
            values: list[str] = []
            for cell in row.findall("a:c", SPREADSHEET_NS):
                index = column_index(cell.attrib.get("r", "A1"))
                while len(values) <= index:
                    values.append("")
                values[index] = cell_value(cell, shared_strings)
            if any(value.strip() for value in values):
                max_cols = max(max_cols, len(values))
                rows.append(values)
        for row in rows:
            while len(row) < max_cols:
                row.append("")
        return rows


def read_shared_strings(workbook: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []
    root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    return [
        "".join(text.text or "" for text in item.findall(".//a:t", SPREADSHEET_NS))
        for item in root.findall("a:si", SPREADSHEET_NS)
    ]


def first_sheet_path(workbook: zipfile.ZipFile) -> str:
    workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
    rel_root = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rel_root.findall("rel:Relationship", REL_NS)
    }
    sheet = workbook_root.find("a:sheets/a:sheet", SPREADSHEET_NS)
    if sheet is None:
        raise ValueError("Workbook does not contain a sheet.")
    rel_id = sheet.attrib[
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    ]
    target = rel_map[rel_id]
    if target.startswith("xl/"):
        return target
    return "xl/" + target.lstrip("/")


def cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(
            text.text or "" for text in cell.findall(".//a:t", SPREADSHEET_NS)
        ).strip()

    value = cell.find("a:v", SPREADSHEET_NS)
    if value is None:
        return ""
    raw_value = value.text or ""
    if cell_type == "s":
        try:
            return shared_strings[int(raw_value)].strip()
        except (IndexError, ValueError):
            return raw_value.strip()
    return raw_value.strip()


def column_index(cell_ref: str) -> int:
    value = 0
    for char in "".join(char for char in cell_ref if char.isalpha()):
        value = value * 26 + ord(char.upper()) - ord("A") + 1
    return max(0, value - 1)
