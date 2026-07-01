"""L2 · 骨架层 / RouteProfile (Skeleton).

给每个工艺族一条**基线骨架路线**（必经主工序 + 顺序）。路线从骨架出发增减，而不是从空集
疯狂追加（铁律 B）。〔条件工序〕不在骨架里，由 L3 证据 + L4 矩阵决定是否插入。
"""

from __future__ import annotations

from .families import LARGE_PLATE, MACHINING, SHEET_METAL, TURNING


# 仅"必经"工序进骨架；方括号条件工序留给证据层。
SKELETONS: dict[str, tuple[str, ...]] = {
    SHEET_METAL: (
        # 折弯不再默认必经：纯平板/托板不应有 bending，由 L3 证据触发（见
        # evidence._add_bending_evidence）。
        "raw_material_check",
        "laser_cut_blank",
        "deburr",
        "inspection",
        "protective_packaging",
    ),
    TURNING: (
        "raw_material_check",
        "saw_cut",
        "turning",
        "deburr",
        "inspection",
        "protective_packaging",
    ),
    LARGE_PLATE: (
        "raw_material_check",
        "large_plate_roughing",
        "large_plate_finishing",
        "flatness_inspection",
        "protective_packaging",
    ),
    MACHINING: (
        "raw_material_check",
        "saw_cut",
        "fixture_setup",
        "cnc_rough_milling",
        "cnc_finish_milling",
        "deburr",
        "inspection",
        "protective_packaging",
    ),
}


def skeleton_for(family: str) -> tuple[str, ...]:
    return SKELETONS[family]
