from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProcessDefinition:
    process_code: str
    process_name: str
    process_type: str
    description: str
    sequence: int
    is_supported_in_mvp: bool
    requires_manual_confirm: bool
    auto_quote_enabled: bool
    quantity_type: str | None = None
    pricing_unit: str | None = None
    default_process_variant: str | None = None
    process_variants: tuple[str, ...] = ()
    first_pass_unit_price: float | None = None
    aliases: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "process_code": self.process_code,
            "process_name": self.process_name,
            "process_type": self.process_type,
            "description": self.description,
            "sequence": self.sequence,
            "is_supported_in_mvp": self.is_supported_in_mvp,
            "requires_manual_confirm": self.requires_manual_confirm,
            "auto_quote_enabled": self.auto_quote_enabled,
            "quantity_type": self.quantity_type,
            "pricing_unit": self.pricing_unit,
            "default_process_variant": self.default_process_variant,
            "process_variants": list(self.process_variants),
            "first_pass_unit_price": self.first_pass_unit_price,
            "aliases": list(self.aliases),
        }


PROCESS_DEFINITIONS: tuple[ProcessDefinition, ...] = (
    ProcessDefinition(
        "review_drawing",
        "审图/3D确认",
        "前处理",
        "确认 PDF、STEP、关键尺寸、公差和技术要求",
        10,
        True,
        True,
        False,
    ),
    ProcessDefinition(
        "material_prepare",
        "备料",
        "材料",
        "按材料和毛坯尺寸备料",
        20,
        True,
        False,
        True,
        quantity_type="gross_weight",
        pricing_unit="kg",
        aliases=("MATERIAL_PREP",),
    ),
    ProcessDefinition(
        "saw_cut",
        "锯切下料",
        "下料",
        "板料、棒料、块料初步开料",
        30,
        True,
        False,
        True,
        quantity_type="cut_count",
        pricing_unit="pcs",
        first_pass_unit_price=10.0,
        aliases=("CUTTING",),
    ),
    ProcessDefinition(
        "wire_cut_blank",
        "线割开料",
        "下料",
        "精密小件或硬料开料",
        40,
        True,
        True,
        False,
        quantity_type="cut_area",
        pricing_unit="mm2",
        aliases=("WIRE_CUT_BLANK",),
    ),
    ProcessDefinition(
        "surface_grinding_rough",
        "平面粗磨",
        "磨削",
        "建立基准、控制厚度和平面度",
        50,
        True,
        True,
        True,
        quantity_type="grinding_area",
        pricing_unit="hour",
        first_pass_unit_price=90.0,
    ),
    ProcessDefinition(
        "cnc_milling",
        "CNC铣削",
        "机加工",
        "粗铣、精铣、型腔、台阶面加工",
        60,
        True,
        True,
        True,
        quantity_type="estimated_hours",
        pricing_unit="hour",
        first_pass_unit_price=115.0,
        aliases=("CNC",),
    ),
    ProcessDefinition(
        "drilling",
        "钻孔",
        "孔加工",
        "普通通孔、盲孔底孔",
        70,
        True,
        False,
        True,
        quantity_type="hole_count",
        pricing_unit="hole",
        first_pass_unit_price=3.5,
        aliases=("DRILLING",),
    ),
    ProcessDefinition(
        "countersink",
        "沉孔/沉头孔",
        "孔加工",
        "沉孔、沉头孔、倒角孔",
        80,
        True,
        False,
        True,
        quantity_type="counterbore_count",
        pricing_unit="hole",
        first_pass_unit_price=10.0,
        aliases=("COUNTERBORE", "COUNTERSINK"),
    ),
    ProcessDefinition(
        "tapping",
        "攻牙",
        "孔加工",
        "螺纹孔加工",
        90,
        True,
        True,
        True,
        quantity_type="thread_count",
        pricing_unit="hole",
        first_pass_unit_price=10.0,
        aliases=("TAPPING",),
    ),
    ProcessDefinition(
        "wire_cut_profile",
        "线切割外形",
        "线切割",
        "异形外轮廓、内孔、窄槽加工",
        65,
        True,
        True,
        True,
        quantity_type="cut_area",
        pricing_unit="mm2",
        default_process_variant="medium_wire",
        process_variants=("fast_wire", "medium_wire", "slow_wire"),
        first_pass_unit_price=0.02,
        aliases=("WIRE_CUTTING",),
    ),
    ProcessDefinition(
        "heat_treatment",
        "热处理",
        "热处理",
        "淬火、调质、渗氮、真空热处理等",
        110,
        True,
        False,
        True,
        quantity_type="heat_weight",
        pricing_unit="kg",
        first_pass_unit_price=16.5,
        aliases=("HEAT_TREATMENT",),
    ),
    ProcessDefinition(
        "straightening",
        "校平/校直",
        "矫正",
        "薄片件、长条件热后矫正",
        120,
        True,
        True,
        False,
    ),
    ProcessDefinition(
        "finish_grinding",
        "精磨",
        "磨削",
        "热后精磨、厚度控制、平面度控制",
        130,
        True,
        True,
        True,
        quantity_type="grinding_area",
        pricing_unit="hour",
        first_pass_unit_price=90.0,
        aliases=("GRINDING",),
    ),
    ProcessDefinition(
        "precision_hole",
        "精孔加工",
        "精加工",
        "铰孔、镗孔、慢走丝修孔等",
        140,
        True,
        True,
        True,
        quantity_type="precision_hole_count",
        pricing_unit="hole",
        first_pass_unit_price=27.5,
        aliases=("PRECISION_HOLE",),
    ),
    ProcessDefinition(
        "deburr",
        "去毛刺",
        "后处理",
        "去毛刺、飞边、锐角倒钝",
        150,
        True,
        False,
        True,
        quantity_type="deburr_count",
        pricing_unit="pcs",
        first_pass_unit_price=12.5,
        aliases=("DEBURRING",),
    ),
    ProcessDefinition(
        "pre_plating_cleaning",
        "镀前清洗",
        "表处前处理",
        "除油、清洗、活化",
        160,
        True,
        False,
        False,
    ),
    ProcessDefinition(
        "chemical_nickel",
        "化学镍",
        "表面处理",
        "化学镀镍",
        170,
        True,
        False,
        True,
        quantity_type="surface_weight",
        pricing_unit="kg",
        aliases=("CHEMICAL_PLATING",),
    ),
    ProcessDefinition(
        "post_plating_inspection",
        "镀后检验",
        "检验",
        "镀层外观、膜厚、孔径复检",
        180,
        True,
        False,
        False,
    ),
    ProcessDefinition(
        "inspection",
        "终检",
        "检验",
        "尺寸、外观、硬度、关键孔检测",
        190,
        True,
        False,
        True,
        quantity_type="inspection_count",
        pricing_unit="pcs",
        first_pass_unit_price=17.5,
        aliases=("INSPECTION",),
    ),
    ProcessDefinition(
        "protective_packaging",
        "防划伤包装",
        "包装",
        "单件隔离、防弯曲、防碰伤包装",
        200,
        True,
        False,
        True,
        quantity_type="manual_quantity",
        pricing_unit="pcs",
        first_pass_unit_price=17.5,
        aliases=("PACKAGING",),
    ),
    ProcessDefinition(
        "turning",
        "车削",
        "预留/人工确认",
        "轴类件加工，第一版不自动报价",
        300,
        False,
        True,
        False,
        aliases=("TURNING",),
    ),
    ProcessDefinition(
        "cylindrical_grinding",
        "圆磨",
        "预留/人工确认",
        "轴类件精加工，第一版不自动报价",
        310,
        False,
        True,
        False,
        aliases=("CYLINDRICAL_GRINDING",),
    ),
    ProcessDefinition(
        "laser_cut",
        "激光切割",
        "预留/人工确认",
        "钣金切割，第一版不自动报价",
        320,
        False,
        True,
        False,
        aliases=("LASER_CUT",),
    ),
    ProcessDefinition(
        "edm",
        "放电加工",
        "预留/人工确认",
        "复杂型腔加工，第一版不自动报价",
        330,
        False,
        True,
        False,
        aliases=("EDM",),
    ),
    ProcessDefinition(
        "manual_review",
        "人工复核",
        "人工确认",
        "解析、工艺或报价风险需要人工确认",
        900,
        True,
        True,
        False,
        aliases=("MANUAL_REVIEW",),
    ),
)


PROCESS_DICTIONARY = {
    definition.process_code: definition for definition in PROCESS_DEFINITIONS
}
PROCESS_NAMES = {
    definition.process_code: definition.process_name
    for definition in PROCESS_DEFINITIONS
}
PROCESS_SEQUENCE = [
    definition.process_code
    for definition in sorted(PROCESS_DEFINITIONS, key=lambda item: item.sequence)
]
PROCESS_UNIT_PRICES = {
    definition.process_code: definition.first_pass_unit_price
    for definition in PROCESS_DEFINITIONS
    if definition.first_pass_unit_price is not None
}

_PROCESS_ALIASES = {
    alias.upper(): definition.process_code
    for definition in PROCESS_DEFINITIONS
    for alias in (definition.process_code, *definition.aliases)
}


def list_process_definitions() -> list[dict[str, Any]]:
    return [definition.to_dict() for definition in PROCESS_DEFINITIONS]


def normalize_process_code(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    return _PROCESS_ALIASES.get(text.upper())


def is_registered_process_code(value: Any) -> bool:
    return normalize_process_code(value) is not None


def get_process_definition(process_code: str) -> ProcessDefinition:
    normalized = normalize_process_code(process_code)
    if normalized is None:
        raise KeyError(process_code)
    return PROCESS_DICTIONARY[normalized]


def process_name_for_code(process_code: str) -> str:
    return get_process_definition(process_code).process_name


def process_sequence_index(process_code: str) -> int:
    return PROCESS_SEQUENCE.index(get_process_definition(process_code).process_code)
