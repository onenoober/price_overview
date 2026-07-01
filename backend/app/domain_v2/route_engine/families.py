"""四个工艺族常量及段位顺序。"""

from __future__ import annotations


SHEET_METAL = "SHEET_METAL"
TURNING = "TURNING"
LARGE_PLATE = "LARGE_PLATE"
MACHINING = "MACHINING"

FAMILIES = (SHEET_METAL, TURNING, LARGE_PLATE, MACHINING)

FAMILY_LABELS = {
    SHEET_METAL: "钣金族",
    TURNING: "车削/轴类族",
    LARGE_PLATE: "大板族",
    MACHINING: "机加/方件族",
}

# L1 硬路由：业务小类(category_name) → 工艺族。几何不得参与换族（铁律 A）。
CATEGORY_TO_FAMILY = {
    "钣金类": SHEET_METAL,
    "焊接类": SHEET_METAL,
    "圆件类": TURNING,
    "大板类": LARGE_PLATE,
    "方件类": MACHINING,
}

# 业务小类置信度阈值。低于此值不直接进硬路由，降级机加 + 强制复核。
CATEGORY_CONFIDENCE_THRESHOLD = 0.6

# 兜底族（小类缺失/低置信时保守按机加，方案 §7）。
FALLBACK_FAMILY = MACHINING
