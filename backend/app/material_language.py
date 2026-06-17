from __future__ import annotations

import re
from typing import Any


MATERIAL_CHINESE_NAMES = {
    "Q235A": "Q235A 碳素结构钢",
    "Q235": "Q235 碳素结构钢",
    "S45C": "45号钢",
    "45": "45号钢",
    "45#": "45号钢",
    "SUS304": "SUS304 不锈钢",
    "304": "SUS304 不锈钢",
    "SKD11": "SKD11 冷作模具钢",
    "DC53": "DC53 冷作模具钢",
    "CR12MOV": "Cr12MoV 冷作模具钢",
    "AL6061": "6061 铝合金",
    "AL6061T6": "6061-T6 铝合金",
    "6061": "6061 铝合金",
    "6061T6": "6061-T6 铝合金",
}


def normalize_material_normalization_content(content: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(content)
    chinese_name = material_chinese_name(
        normalized.get("standard_code"),
        normalized.get("raw_text"),
        normalized.get("standard_name"),
    )
    if chinese_name:
        normalized["standard_name"] = chinese_name
    return normalized


def normalize_part_feature_material(part_feature: dict[str, Any] | None) -> None:
    if not isinstance(part_feature, dict):
        return
    material = part_feature.get("material")
    if not isinstance(material, dict):
        return
    chinese_name = material_chinese_name(
        material.get("standard_code"),
        material.get("raw_text"),
        material.get("standard_name"),
    )
    if chinese_name:
        material["standard_name"] = chinese_name


def normalize_part_feature_material_density(
    part_feature: dict[str, Any] | None,
    pdf_result: dict[str, Any] | None = None,
    step_result: dict[str, Any] | None = None,
) -> None:
    if not isinstance(part_feature, dict):
        return
    material = part_feature.get("material")
    material_uses_legacy_density = (
        isinstance(material, dict)
        and is_legacy_builtin_density_source(material.get("source"))
    )
    if material_uses_legacy_density:
        material["standard_code"] = None
        material["density"] = None
        material["density_unit"] = None
        material["source"] = pdf_material_source(pdf_result, material.get("raw_text"))

    geometry = part_feature.get("geometry")
    if not isinstance(geometry, dict):
        return
    net_weight = geometry.get("step_net_weight")
    if not isinstance(net_weight, dict):
        return
    density_source = net_weight.get("density_source")
    step_net_weight = (step_result or {}).get("net_weight")
    step_density_source = (
        step_net_weight.get("density_source")
        if isinstance(step_net_weight, dict)
        else None
    )
    if (
        material_uses_legacy_density
        or is_legacy_builtin_density_source(density_source)
        or is_legacy_builtin_density_source(step_density_source)
    ):
        net_weight["value"] = None
        net_weight["unit"] = None
        net_weight["density"] = None
        net_weight["density_unit"] = None
        net_weight["density_source"] = None
        clear_step_net_weight(step_result)


def normalize_step_feature_material_density(step_result: dict[str, Any] | None) -> None:
    step_net_weight = (step_result or {}).get("net_weight")
    if not isinstance(step_net_weight, dict):
        return
    if is_legacy_builtin_density_source(step_net_weight.get("density_source")):
        clear_step_net_weight(step_result)


def clear_step_net_weight(step_result: dict[str, Any] | None) -> None:
    step_net_weight = (step_result or {}).get("net_weight")
    if not isinstance(step_net_weight, dict):
        return
    step_net_weight["value"] = None
    step_net_weight["unit"] = None
    step_net_weight["density"] = None
    step_net_weight["density_unit"] = None
    step_net_weight["density_source"] = None


def is_legacy_builtin_density_source(source: Any) -> bool:
    if not isinstance(source, dict):
        return False
    rule_code = str(source.get("rule_code") or "")
    return rule_code.startswith("MATERIAL_DENSITY_BUILTIN:")


def pdf_material_source(
    pdf_result: dict[str, Any] | None,
    raw_text: Any,
) -> dict[str, Any]:
    evidence = (pdf_result or {}).get("field_evidence") or {}
    material_evidence = evidence.get("material_raw") if isinstance(evidence, dict) else None
    if isinstance(material_evidence, dict):
        return material_evidence
    return {
        "source_type": "system",
        "file_id": None,
        "page": None,
        "location": None,
        "raw_text": raw_text,
        "rule_code": "LEGACY_MATERIAL_DENSITY_BUILTIN_REMOVED",
    }


def material_chinese_name(*values: Any) -> str | None:
    normalized_values = [normalize_material_key(value) for value in values if value]
    for key in normalized_values:
        if key in MATERIAL_CHINESE_NAMES:
            return MATERIAL_CHINESE_NAMES[key]
    for key in normalized_values:
        for material_key, name in MATERIAL_CHINESE_NAMES.items():
            if material_key and material_key in key:
                return name
    return None


def normalize_material_key(value: Any) -> str:
    text = str(value or "").upper().replace("＃", "#")
    text = re.sub(r"[\s_\-/]+", "", text)
    return text
