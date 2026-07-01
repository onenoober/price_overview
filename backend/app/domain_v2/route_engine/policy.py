"""L4 · 策略矩阵层 / 允许-禁止门 (Policy Matrix Gate).

用"小类 × 工序"矩阵过滤候选工序，把"只会加"变成"会挡"。逐字落方案 §3.1–3.4。

矩阵语义：
- ``R`` required —— 骨架必经（由 L2 保证，不在候选门里判）。
- ``A`` allow —— 有证据即可加入。
- ``C`` conditional —— 需要明确证据才加入，否则不加。
- ``CG`` conditional-geometry —— 需要**几何**证据才加入（大板的 edm/wire_cut/pocket）。
- ``D`` deny —— 硬禁止；被证据触发说明上游误判，报 FORBIDDEN_OP_TRIGGERED_REVIEW。
"""

from __future__ import annotations

from .families import LARGE_PLATE, MACHINING, SHEET_METAL, TURNING


ALLOW = "A"
DENY = "D"
CONDITIONAL = "C"
CONDITIONAL_GEOMETRY = "CG"
REQUIRED = "R"

# 默认策略：未列出的候选工序按 conditional（需证据）处理，防膨胀。
DEFAULT_POLICY = CONDITIONAL

# 表面处理 / 遮蔽相关工序（各族统一按 conditional 处理；钣金除外见矩阵）。
_SURFACE_OPS = (
    "powder_coating",
    "white_powder_coating",
    "powder_coating_texture",
    "chemical_nickel",
    "clear_anodizing",
    "hard_anodizing",
    "color_anodizing",
    "hard_chrome",
    "sand_blasting",
    "powder_masking",
    "anodize_masking",
    "hard_chrome_masking",
    "surface_masking",
    "pre_plating_cleaning",
)


def _with_surface(base: dict[str, str], policy: str) -> dict[str, str]:
    matrix = dict(base)
    for op in _SURFACE_OPS:
        matrix.setdefault(op, policy)
    return matrix


# 3.1 钣金 SHEET_METAL —— 机加/电火花/线切割/平面粗磨全部 D。
SHEET_METAL_MATRIX = _with_surface(
    {
        "raw_material_check": REQUIRED,
        "laser_cut_blank": REQUIRED,
        # 折弯改为条件工序：仅在 L3 折弯证据成立时加入（纯平板不加）。
        "bending": CONDITIONAL,
        "deburr": REQUIRED,
        "inspection": REQUIRED,
        "protective_packaging": REQUIRED,
        "sheet_metal_welding": CONDITIONAL,
        # 硬禁止（报告证据：钣金 4/4 被误加这些）。
        "cnc_rough_milling": DENY,
        "cnc_finish_milling": DENY,
        "cnc_milling": DENY,
        "profile_milling": DENY,
        "pocket_milling": DENY,
        "slot_milling": DENY,
        "step_milling": DENY,
        "edm": DENY,
        "wire_cut_profile": DENY,
        "surface_grinding_rough": DENY,
        "cylindrical_grinding": DENY,
        "finish_grinding": DENY,
        "saw_cut": DENY,
        "turning": DENY,
        "turning_rough": DENY,
        "turning_finish": DENY,
    },
    CONDITIONAL,
)

# 3.2 轴类 TURNING —— 必含车削主线；不以铣为主。
TURNING_MATRIX = _with_surface(
    {
        "raw_material_check": REQUIRED,
        "saw_cut": REQUIRED,
        "turning": REQUIRED,
        "deburr": REQUIRED,
        "inspection": REQUIRED,
        "protective_packaging": REQUIRED,
        "center_drilling": CONDITIONAL,
        "drilling": CONDITIONAL,
        "drilling_through": CONDITIONAL,
        "drilling_blind": CONDITIONAL,
        "tapping": CONDITIONAL,
        "counterbore": CONDITIONAL,
        "countersink": CONDITIONAL,
        "external_thread_turning": CONDITIONAL,
        "shaft_milling": CONDITIONAL,
        "keyway_milling": CONDITIONAL,
        "cross_drilling": CONDITIONAL,
        "grooving_turning": CONDITIONAL,
        "turning_finish": CONDITIONAL,
        "heat_treatment": CONDITIONAL,
        "stress_relief": CONDITIONAL,
        "straightening": CONDITIONAL,
        "cylindrical_grinding": CONDITIONAL,
        "finish_grinding": CONDITIONAL,
        # 硬禁止（报告证据：轴类缺车削主线 + 出现 cnc_*/edm/pocket）。
        "cnc_rough_milling": DENY,
        "cnc_finish_milling": DENY,
        "cnc_milling": DENY,
        "edm": DENY,
        "pocket_milling": DENY,
        "slot_milling": DENY,
        "profile_milling": DENY,
        "wire_cut_profile": DENY,
        "surface_grinding_rough": DENY,
    },
    CONDITIONAL,
)

# 3.3 大板 LARGE_PLATE —— 允许磨削；edm/wire_cut/pocket 改为需几何证据的 conditional。
LARGE_PLATE_MATRIX = _with_surface(
    {
        "raw_material_check": REQUIRED,
        "large_plate_roughing": REQUIRED,
        "large_plate_finishing": REQUIRED,
        "flatness_inspection": REQUIRED,
        "protective_packaging": REQUIRED,
        "surface_grinding_rough": ALLOW,
        "finish_grinding": ALLOW,
        "cylindrical_grinding": DENY,
        # 大板用自身的开粗/精加工，通用 CNC 铣视为冗余 → 拦截。
        "cnc_rough_milling": DENY,
        "cnc_finish_milling": DENY,
        "cnc_milling": DENY,
        "stress_relief": CONDITIONAL,
        "straightening": CONDITIONAL,
        "drilling": CONDITIONAL,
        "drilling_through": CONDITIONAL,
        "tapping": CONDITIONAL,
        "deburr": CONDITIONAL,
        "inspection": CONDITIONAL,
        # 默认不加，有明确几何证据才加。
        "edm": CONDITIONAL_GEOMETRY,
        "wire_cut_profile": CONDITIONAL_GEOMETRY,
        "pocket_milling": CONDITIONAL_GEOMETRY,
    },
    CONDITIONAL,
)

# 3.4 机加/方件 MACHINING —— 主线保留；软爪/防变形/粗磨/去应力/线切割降为条件候选。
MACHINING_MATRIX = _with_surface(
    {
        "raw_material_check": REQUIRED,
        "saw_cut": REQUIRED,
        "fixture_setup": REQUIRED,
        "cnc_rough_milling": REQUIRED,
        "cnc_finish_milling": REQUIRED,
        "deburr": REQUIRED,
        "inspection": REQUIRED,
        "protective_packaging": REQUIRED,
        "drilling": CONDITIONAL,
        "drilling_through": CONDITIONAL,
        "drilling_blind": CONDITIONAL,
        "tapping": CONDITIONAL,
        "tapping_through": CONDITIONAL,
        "blind_tapping": CONDITIONAL,
        "fine_thread_tapping": CONDITIONAL,
        "side_tapping": CONDITIONAL,
        "counterbore": CONDITIONAL,
        "countersink": CONDITIONAL,
        "profile_milling": CONDITIONAL,
        "slot_milling": CONDITIONAL,
        "pocket_milling": CONDITIONAL,
        "precision_hole": CONDITIONAL,
        "reaming": CONDITIONAL,
        "thread_inspection": CONDITIONAL,
        "in_process_inspection": CONDITIONAL,
        "heat_treatment": CONDITIONAL,
        "stress_relief": CONDITIONAL,
        "surface_grinding_rough": CONDITIONAL,
        "cylindrical_grinding": DENY,
        "wire_cut_profile": CONDITIONAL,
        "support_anti_deformation": CONDITIONAL,
        "soft_jaw_fixture": CONDITIONAL,
        "edm": CONDITIONAL,
    },
    CONDITIONAL,
)

MATRICES: dict[str, dict[str, str]] = {
    SHEET_METAL: SHEET_METAL_MATRIX,
    TURNING: TURNING_MATRIX,
    LARGE_PLATE: LARGE_PLATE_MATRIX,
    MACHINING: MACHINING_MATRIX,
}


def policy(family: str, op: str) -> str:
    """policy(family, op) -> A|D|C|CG|R。未登记的工序默认 conditional。"""

    return MATRICES.get(family, {}).get(op, DEFAULT_POLICY)
