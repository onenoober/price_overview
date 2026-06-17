from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Callable

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from client.api_client import ApiError, PriceOverviewClient


FILE_TYPE_LABELS = {
    "pdf": "PDF 图纸",
    "step": "STEP 模型",
    "attachment": "附件",
}

STATUS_LABELS = {
    "draft": "草稿",
    "uploaded": "已上传",
    "parsed": "已解析",
    "priced": "已核价",
    "pending_review": "待审核",
    "confirmed": "已确认",
    "voided": "已作废",
}

FILE_STATUS_LABELS = {
    "uploaded": "已上传",
    "invalid": "无效",
    "deleted": "已删除",
}

FILE_PARSE_STATUS_LABELS = {
    "not_parsed": "未解析",
    "parsed": "已解析",
    "failed": "解析失败",
    "skipped": "已跳过",
}

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

RISK_LEVEL_LABELS = {
    "info": "提示",
    "warning": "警告",
    "error": "错误",
    "blocking": "阻断",
}

ITEM_TYPE_LABELS = {
    "material": "材料",
    "process": "工序",
    "surface_treatment": "表面处理",
    "management_fee": "管理费",
    "tax": "税费",
    "risk_surcharge": "风险加价",
    "other": "其他",
}

CURRENCY_LABELS = {
    "CNY": "人民币",
}

ROUTE_RULE_LABELS = {
    "MATERIAL_PRESENT": "检测到材料，需要材料准备",
    "MATERIAL_MISSING": "未检测到材料，需要人工确认",
    "BASE_CUTTING": "基础工艺包含下料",
    "BASE_CNC": "基础工艺包含 CNC 加工",
    "HOLE_THROUGH": "检测到通孔",
    "HOLE_COUNTERBORE": "检测到沉孔",
    "HOLE_THREAD_CANDIDATE": "检测到螺纹孔候选",
    "HOLE_PRECISION_CANDIDATE": "检测到精孔候选",
    "ROUGHNESS_GRINDING": "检测到表面粗糙度要求",
    "HEAT_TREATMENT_REQUIRED": "检测到热处理要求",
    "SURFACE_TREATMENT_REQUIRED": "检测到表面处理要求",
    "DEBURRING_REQUIRED": "检测到去毛刺要求",
    "BASE_INSPECTION": "基础报价包含检验",
    "BASE_PACKAGING": "基础报价包含包装",
    "INHERITED_REVIEW_RISK": "解析或特征融合存在需复核风险",
}

ROUTE_TEXT_LABELS = {
    "Material prep is required for quoting.": "材料报价需要先确认材料准备。",
    "Material is missing.": "缺少材料信息。",
    "First-pass route includes blank cutting.": "初版工艺路线包含下料。",
    "First-pass route includes CNC machining.": "初版工艺路线包含 CNC 加工。",
    "CNC routing is a first-pass bridge rule and should be replaced by A.": "CNC 工艺为系统初版过渡规则，需由工艺人员复核或替换。",
    "Thread holes are candidates and need manual or A-side confirmation.": "螺纹孔为候选结果，需要人工或工艺侧确认。",
    "Precision holes are candidates and need manual or A-side confirmation.": "精孔为候选结果，需要人工或工艺侧确认。",
    "Roughness-to-grinding mapping is a first-pass candidate.": "磨削工艺由粗糙度规则初步推断，需要复核。",
    "Detected deburring requirement.": "检测到去毛刺要求。",
    "First-pass quote includes inspection.": "初版报价包含检验。",
    "First-pass quote includes packaging.": "初版报价包含包装。",
    "Parsing or feature fusion produced review risks.": "解析或特征融合产生了需复核风险。",
    "Inherited parse/fusion risks require review before formal quoting.": "继承了解析或特征融合风险，正式报价前需要复核。",
}

OPERATION_CODE_LABELS = {
    "review_drawing": "审图/3D确认",
    "material_prepare": "备料",
    "saw_cut": "锯切下料",
    "wire_cut_blank": "线割开料",
    "surface_grinding_rough": "平面粗磨",
    "cnc_milling": "CNC铣削",
    "drilling": "钻孔",
    "countersink": "沉孔/沉头孔",
    "tapping": "攻牙",
    "precision_hole": "精孔加工",
    "wire_cut_profile": "线切割外形",
    "heat_treatment": "热处理",
    "straightening": "校平/校直",
    "finish_grinding": "精磨",
    "deburr": "去毛刺",
    "pre_plating_cleaning": "镀前清洗",
    "chemical_nickel": "化学镍",
    "post_plating_inspection": "镀后检验",
    "inspection": "终检",
    "protective_packaging": "防划伤包装",
    "turning": "车削",
    "cylindrical_grinding": "圆磨",
    "laser_cut": "激光切割",
    "edm": "放电加工",
    "unmapped_operation": "未登记工序",
    "manual_review": "人工复核",
    "MATERIAL_PREP": "材料准备",
    "CUTTING": "下料",
    "CNC": "CNC 加工",
    "DRILLING": "钻孔",
    "COUNTERBORE": "沉孔",
    "TAPPING": "攻牙",
    "PRECISION_HOLE": "精孔",
    "WIRE_CUTTING": "线切割",
    "GRINDING": "磨削",
    "HEAT_TREATMENT": "热处理",
    "CHEMICAL_PLATING": "化学镀",
    "DEBURRING": "去毛刺",
    "INSPECTION": "检验",
    "PACKAGING": "包装",
    "MANUAL_REVIEW": "人工复核",
    "UNMAPPED_OPERATION": "未登记工序",
    "CUSTOM_OPERATION": "自定义工序",
}

QUANTITY_TYPE_LABELS = {
    "gross_weight": "毛坯重量",
    "cut_area": "下料面积",
    "cut_count": "下料件数/刀数",
    "hole_count": "孔数量",
    "counterbore_count": "沉孔数量",
    "thread_count": "螺纹数量",
    "precision_hole_count": "精孔数量",
    "estimated_hours": "估算工时",
    "grinding_area": "磨削面积",
    "heat_weight": "热处理重量",
    "surface_area": "表面积",
    "surface_weight": "表面处理重量",
    "deburr_complexity": "去毛刺复杂度",
    "deburr_count": "去毛刺件数",
    "inspection_count": "检验数量",
    "manual_quantity": "人工工程量",
}

QUANTITY_FORMULA_LABELS = {
    "length_mm * width_mm * height_mm * density_kg_per_mm3.": "毛坯长 × 毛坯宽 × 毛坯厚 × 材料密度",
    "length * width from bounding box.": "包络长 × 包络宽",
    "Requires machining parameters such as removal rate or cycle-time rule; not inferred from complexity alone.": "需要去除率、装夹或节拍规则；不只按复杂度估算",
    "First-pass saw-cut count uses part.quantity; real knife count and nesting need review.": "第一版按零件数量估算下料刀数，实际刀数和排版需复核",
    "cut_length_mm * material_thickness_mm.": "切割长度 × 材料厚度",
    "outer_profile_length_mm * material_thickness_mm.": "外轮廓长度 × 材料厚度",
    "grinding_face_count * grinding_face_area_mm2.": "磨削面数 × 单面磨削面积",
    "Prefer calculated gross_weight; fallback to STEP/PDF measured weight when gross weight is unavailable.": "优先使用毛坯重量；缺失时使用 STEP/PDF 重量并复核",
    "Convert STEP surface_area to m2.": "STEP 表面积换算为平方米",
    "Convert STEP surface_area to m2 for chemical nickel surface treatment pricing.": "STEP 表面积换算为平方米，作为化学镍表面处理计价工程量",
    "STEP surface_area converted to m2, used as chemical nickel surface treatment quantity.": "STEP 表面积换算为平方米，作为化学镍表面处理计价工程量",
    "Prefer STEP/PDF net weight; fallback to calculated gross weight for first-pass surface treatment pricing.": "优先使用 STEP/PDF 净重；缺失时用毛坯重量作为表面处理重量并复核",
    "Prefer STEP complexity_score; fallback to STEP edge_count when complexity_score is unavailable.": "优先使用 STEP 复杂度评分；缺失时用边数量待确认",
    "part.quantity with STEP complexity_score or edge_count as review basis.": "按零件数量计去毛刺，复杂度评分或边数量作为复核依据",
    "part.quantity.": "零件数量",
    "part.quantity for protective packaging pieces.": "零件数量",
    "Sum detected hole candidates by operation type.": "按孔类型汇总识别到的孔数量",
}

QUOTE_FORMULA_LABELS = {
    "A_BASIC_CORE_FIRST_PASS": "系统首版核价规则",
    "max(quantity * unit_price, minimum_charge)": "按华南工序标准：max(工程量 × 单价，起步价)",
    "quantity * unit_price": "工程量 × 单价",
}

REVIEW_REASON_LABELS = {
    "Drawing requires 3D confirmation.": "图纸技术要求说明未标注尺寸参见 3D，正式报价前需审图/3D确认。",
    "Material is missing.": "材料信息缺失。",
    "Bounding box is missing for process recognition.": "缺少包络尺寸，无法完整识别工艺路线。",
    "Part type is missing.": "零件类型缺失。",
    "Small irregular blanking method needs confirmation.": "小型异形件下料方式需确认。",
    "Wire-cut profile is a candidate and needs process confirmation.": "线切割轮廓为候选工序，需工艺确认。",
    "Thin-part grinding requirement needs confirmation.": "薄片件磨削需求需确认。",
    "Thin-part straightening is a candidate and needs confirmation.": "薄片件校平/校直为候选工序，需确认。",
    "Slot candidates may need wire cutting confirmation.": "槽特征可能需要线切割，需确认。",
    "Small-radius machining method needs confirmation.": "小 R 加工方式需确认。",
    "High complexity may need wire cutting confirmation.": "复杂度较高，可能需要线切割，需确认。",
    "Thread callout pilot drilling needs confirmation.": "螺纹标注对应的底孔钻孔需确认。",
    "Thread callout needs tapping confirmation.": "螺纹标注对应的攻牙工序需确认。",
    "Straightening requirement needs process confirmation.": "校平/校直要求需工艺确认。",
    "Precision technical requirement needs process confirmation.": "精度技术要求需工艺确认。",
    "Grinding requirement needs process confirmation.": "磨削要求需工艺确认。",
    "Surface treatment is not mapped to a supported process.": "表面处理未映射到当前支持的工序，需人工确认。",
    "Inherited parse/fusion risks require review before formal quoting.": "解析或特征融合存在风险，正式报价前需人工复核。",
    "Shaft parts are outside MVP auto-quote scope.": "轴类零件暂不在当前自动报价范围内。",
    "Complex parts are outside MVP auto-quote scope.": "复杂零件暂不在当前自动报价范围内。",
    "Weldments are outside MVP auto-quote scope.": "焊接件暂不在当前自动报价范围内。",
    "Assemblies are outside MVP auto-quote scope.": "装配件暂不在当前自动报价范围内。",
    "Heat-treated thin parts may need straightening.": "薄片件热处理后可能需要校平/校直。",
    "Heat-treated thin parts may need finish grinding.": "薄片件热处理后可能需要精磨。",
    "Part quantity is missing.": "零件数量缺失。",
    "Part quantity is missing; saw-cut count needs manual input.": "零件数量缺失，锯切下料数量需人工输入。",
    "Wire-cut outer profile length or material thickness is missing.": "线切割外轮廓长度或材料厚度缺失。",
    "Hole type is a candidate or low-confidence and needs confirmation.": "孔类型为候选或置信度较低，需确认。",
}

PRICE_SOURCE_ID_LABELS = {
    "a_basic_core_bridge": "系统首版核价规则",
    "south_china_process_standard": "华南工序计价标准表",
    "surface_treatment_price_standard": "表面处理价格标准",
}

PRICE_RULE_LABELS = {
    "A_BASIC_CORE_FIRST_PASS": "系统首版核价规则",
    "SEARXNG_MATERIAL_PRICE_SEARCH": "材料实时行情搜索",
    "TAVILY_GPT_MATERIAL_PRICE_SEARCH": "材料实时行情搜索",
    "TAVILY_GPT_SURFACE_TREATMENT_PRICE_SEARCH": "表面处理市场价搜索",
    "GPT_SURFACE_TREATMENT_PRICE_ESTIMATE": "表面处理AI估算价",
    "SOUTH_CHINA_SAW_CUT": "锯切下料标准",
    "SOUTH_CHINA_CNC_MILLING": "CNC铣削标准",
    "SOUTH_CHINA_SURFACE_GRINDING": "平面磨标准",
    "SOUTH_CHINA_FINISH_GRINDING": "精磨标准",
    "SOUTH_CHINA_DRILLING": "钻孔标准",
    "SOUTH_CHINA_COUNTERSINK": "沉孔标准",
    "SOUTH_CHINA_TAPPING": "攻牙标准",
    "SOUTH_CHINA_PRECISION_HOLE": "精孔标准",
    "SOUTH_CHINA_WIRE_CUT_BLANK": "线割开料标准",
    "SOUTH_CHINA_WIRE_CUT_PROFILE": "线切割标准",
    "SOUTH_CHINA_HEAT_TREATMENT": "热处理标准",
    "SOUTH_CHINA_DEBURR": "去毛刺标准",
    "SOUTH_CHINA_INSPECTION_PACKAGING": "检验包装标准",
    "SOUTH_CHINA_CHEMICAL_NICKEL": "化学镍标准",
}

QUANTITY_BASIS_LABELS = {
    "bounding_box": "包络尺寸",
    "material": "材料",
    "density": "材料密度",
    "density_kg_per_mm3": "材料密度",
    "bounding_box_volume": "包络体积",
    "part_volume": "STEP 实体体积",
    "face_count": "面数量",
    "edge_count": "边数量",
    "complexity_score": "复杂度评分",
    "cut_length": "切割长度",
    "outer_profile_length": "外轮廓长度",
    "material_thickness": "材料厚度",
    "grinding_face_count": "磨削面数",
    "major_face_area": "主要平面面积",
    "gross_weight": "毛坯重量",
    "fallback_weight": "STEP/PDF 重量",
    "surface_area": "STEP 表面积",
    "surface_area_m2": "表面积",
    "surface_treatment": "表面处理要求",
    "part_quantity": "零件数量",
    "drilling": "钻孔数量",
    "countersink": "沉孔/沉头孔数量",
    "tapping": "攻牙数量",
    "precision_hole": "精孔数量",
}

QUANTITY_RULE_LABELS = {
    "GROSS_WEIGHT_BBOX": "毛坯重量包络尺寸",
    "CUT_AREA": "下料面积包络尺寸",
    "CNC_ESTIMATE:BBOX_VOLUME": "CNC 包络体积依据",
    "CNC_ESTIMATE:FACE_COUNT": "CNC 面数量依据",
    "CNC_ESTIMATE:EDGE_COUNT": "CNC 边数量依据",
    "CNC_ESTIMATE:COMPLEXITY_SCORE": "CNC 复杂度依据",
    "HEAT_TREATMENT:GROSS_WEIGHT": "热处理毛坯重量",
    "QUANTITY_LOW_CONFIDENCE_HOLE_COUNT": "低置信度孔数量",
    "INSPECTION": "检验数量",
    "PACKAGING": "包装数量",
    "DEBURRING:COMPLEXITY_SCORE": "去毛刺复杂度评分",
    "DEBURRING:EDGE_COUNT": "去毛刺边数量",
}

HOLE_TYPE_LABELS = {
    "through": "通孔",
    "blind": "盲孔",
    "counterbore": "沉孔",
    "countersink": "沉头孔",
    "threaded": "螺纹孔",
    "precision": "精孔",
    "thread_candidate": "螺纹孔候选",
    "precision_candidate": "精孔候选",
}

PART_TYPE_LABELS = {
    "thin_plate": "薄片件",
    "plate": "板件",
    "block": "方件/块件",
    "small_irregular": "异形小件",
    "shaft": "轴类件",
    "complex": "复杂件",
}

UNIT_LABELS = {
    "lot": "批",
    "kg": "kg",
    "g": "g",
    "hour": "小时",
    "pcs": "件",
    "mm": "mm",
    "mm2": "mm²",
    "mm3": "mm³",
    "m2": "m²",
    "kg/mm3": "kg/mm³",
    "kg/mm^3": "kg/mm³",
    "score": "分",
}

TARGET_TYPE_LABELS = {
    "operation": "工艺路线",
    "quantity": "工程量",
    "quote_item": "报价明细",
    "quote_summary": "报价汇总",
    "risk": "风险",
}

FIELD_LABELS = {
    "add": "新增",
    "delete": "删除",
    "sequence": "顺序",
    "operation": "工序",
    "operation_code": "工序编码",
    "amount": "金额",
    "final_amount": "最终金额",
    "unit_price": "单价",
    "value": "工程量值",
    "confirmed": "确认",
    "explanation": "说明",
    "final_confirmed_amount": "最终确认价",
}

PDF_FIELD_LABELS = {
    "drawing_no": "图号",
    "part_name": "零件名称",
    "part_type_raw": "零件类型",
    "revision": "版本",
    "material_raw": "材料原文",
    "weight_raw": "重量原文",
    "weight_value": "重量数值",
    "weight_unit": "重量单位",
    "scale": "比例",
    "heat_treatment_raw": "热处理原文",
    "surface_treatment_raw": "表面处理原文",
    "tolerance_texts": "公差文本",
    "roughness_texts": "粗糙度文本",
    "technical_requirements": "技术要求",
}

PDF_REQUIRED_FIELDS = [
    "drawing_no",
    "part_name",
    "part_type_raw",
    "revision",
    "material_raw",
    "weight_raw",
    "weight_value",
    "weight_unit",
    "scale",
    "heat_treatment_raw",
    "surface_treatment_raw",
    "tolerance_texts",
    "roughness_texts",
    "technical_requirements",
]

PDF_EXTRACT_METHOD_LABELS = {
    "text_layer_title_block": "标题栏识别",
    "text_layer_title_block_inferred": "标题栏推断",
    "text_layer_regex": "文本规则匹配",
    "text_layer_regex_full_text": "全文规则匹配",
    "text_layer_keyword": "关键词识别",
    "vision_model": "AI 图像识别",
    "not_found": "未找到",
}

SOURCE_TYPE_LABELS = {
    "pdf": "PDF",
    "step": "STEP",
    "ai": "AI",
    "system": "系统",
    "manual": "人工",
    "rule": "规则",
    "price_rule": "价格规则",
    "market_search": "市场搜索",
    "ai_estimate": "AI估算价",
    "legacy_placeholder": "历史占位数据",
}

SOURCE_LOCATION_LABELS = {
    "title_block": "标题栏",
    "technical_requirements": "技术要求区",
    "tolerance": "公差标注",
    "roughness": "粗糙度标注",
    "page_image": "页面图像",
    "material": "材料字段",
    "surface": "表面处理字段",
    "heat_treatment": "热处理字段",
    "part_type": "零件类型字段",
}

AI_INPUT_TYPE_LABELS = {
    "pdf_text": "PDF 文本",
    "field_text": "字段文本",
    "step_geometry": "STEP 几何",
    "fusion_feature": "融合特征",
    "rule_result": "规则结果",
    "risk_item": "风险项",
    "override_history": "修改记录",
}

AI_OUTPUT_TYPE_LABELS = {
    "field_candidate": "字段候选",
    "normalization": "归一结果",
    "part_type_classification": "零件类型识别",
    "process_route_suggestion": "工艺路线建议",
    "explanation": "解释",
    "risk_suggestion": "风险建议",
    "analysis": "分析",
}

AI_RISK_SUMMARY_LABELS = {
    "MISSING_STEP": ("缺少 STEP 文件", "请上传 STEP 文件，或确认仅使用当前资料继续。"),
    "MISSING_PDF": ("缺少 PDF 图纸", "请上传 PDF 图纸，或确认仅使用当前资料继续。"),
    "HIGH_PRECISION_REQUIREMENT": (
        "检测到高精度或高表面要求",
        "请核对图纸标注，并确认加工和检验要求。",
    ),
    "WEIGHT_MISMATCH": (
        "重量偏差需复核",
        "请核对 PDF 重量、STEP 理论净重、材料密度、单位和文件版本。",
    ),
    "LOW_CONFIDENCE_FIELD": (
        "字段置信度低",
        "请按 PDF 原文复核关键字段，不要直接采用低置信度结果。",
    ),
    "HIGH_RISK_GEOMETRY": (
        "高风险几何",
        "请结合 STEP 几何确认加工难度、夹持、刀具可达性和是否需要人工报价。",
    ),
    "UNKNOWN_MATERIAL": ("材料需确认", "请按图纸原文确认材料牌号。"),
    "UNKNOWN_SURFACE_TREATMENT": (
        "表面处理需确认",
        "请按图纸原文确认表面处理要求。",
    ),
    "PROCESS_ROUTE_REQUIRES_REVIEW": (
        "工艺路线需要复核",
        "请检查需复核工序、规则命中原因和待确认标记。",
    ),
    "MISSING_PRICE_OR_QUANTITY": (
        "价格或工程量缺失",
        "请补录单价或工程量后再确认报价。",
    ),
}

RISK_MESSAGE_LABELS = {
    "MISSING_STEP": "缺少 STEP 模型文件，当前只能基于已上传资料继续，需上传 STEP 或人工确认。",
    "MISSING_PDF": "缺少 PDF 图纸文件，当前只能基于已上传资料继续，需上传 PDF 或人工确认。",
    "HIGH_PRECISION_REQUIREMENT": "检测到高精度公差或高表面要求，需人工确认加工和检验要求。",
    "UNKNOWN_MATERIAL": "材料原文需要人工确认材料牌号。",
    "UNKNOWN_SURFACE_TREATMENT": "表面处理原文需要人工确认表面处理要求。",
    "PROCESS_ROUTE_REQUIRES_REVIEW": "工艺路线包含需复核项，需人工确认。",
    "MISSING_PRICE_OR_QUANTITY": "存在工序缺少单价或工程量，需补录后复核报价。",
    "QUANTITY_WEIGHT_MISSING": "未找到可用材料重量，材料和热处理工程量需人工复核。",
    "WEIGHT_MISMATCH": "PDF 标注重量与 STEP 理论重量偏差较大，需人工确认。",
    "PDF_STEP_PART_TYPE_CONFLICT": "PDF 和 STEP 零件类型判断不一致，已保留候选，需人工确认。",
    "PDF_STEP_HOLE_TYPE_MISMATCH": "PDF 孔类型标注与 STEP 孔候选类型不一致，需人工确认。",
    "PDF_STEP_HOLE_DIMENSION_MISMATCH": "PDF 孔尺寸标注与 STEP 孔候选尺寸不一致，需人工确认。",
    "LOW_CONFIDENCE_FIELD": "PDF 字段抽取不稳定，需人工核对图纸字段。",
    "FIELD_CONFLICT": "PDF 字段存在多个相近候选，需人工确认最终取值。",
    "PARSER_FALLBACK_USED": "真实解析失败，历史记录曾使用备用解析结果，需人工复核。",
    "PDF_VISION_UNAVAILABLE": "PDF 图像解析不可用，已保留文本层解析结果，需人工复核。",
    "STEP_PARSE_FAILED": "STEP 模型解析失败，需检查文件或转人工处理。",
}

RISK_MESSAGE_TEXT_LABELS = {
    "Multiple solids/shells/compounds detected; assembly or multi-body STEP should be reviewed.": "STEP 检测到多个实体、壳体或组合体，可能是装配件或多实体模型，需人工复核。",
    "High freeform BSPLINE geometry ratio should be reviewed.": "STEP 自由曲面比例较高，需人工复核加工难度。",
    "High geometry complexity should be reviewed.": "STEP 几何复杂度较高，需人工复核加工难度。",
    "Thin-wall candidate detected from bounding box proportions.": "根据包络尺寸比例检测到薄壁候选，需人工复核。",
    "Long thin geometry may require support/cantilever review.": "细长结构可能需要支撑或悬臂加工复核。",
}

RISK_MESSAGE_PATTERNS = (
    (
        re.compile(r"Part type candidate (\w+) should be reviewed before automatic pricing\."),
        lambda match: (
            f"STEP 零件类型候选为 {part_type_label(match.group(1))}，自动报价前需人工复核。"
        ),
    ),
    (
        re.compile(r"Small radius features detected:\s*(\d+)\."),
        lambda match: f"STEP 检测到小半径特征 {match.group(1)} 处，需人工复核加工方式。",
    ),
    (
        re.compile(r"Narrow slot candidates detected:\s*(\d+)\."),
        lambda match: f"STEP 检测到窄槽候选 {match.group(1)} 处，需人工复核加工方式。",
    ),
    (
        re.compile(r"Deep hole candidates detected:\s*(\d+)\."),
        lambda match: f"STEP 检测到深孔候选 {match.group(1)} 处，需人工复核加工方式。",
    ),
    (
        re.compile(r"STEP parsing failed:\s*(.+)"),
        lambda match: f"STEP 解析失败：{match.group(1)}",
    ),
)

ERROR_CODE_LABELS = {
    "TASK_ID_REQUIRED": "任务ID必填",
    "QUOTE_REQUIRED": "请先生成报价",
    "REQUEST_TIMEOUT": "请求超时",
    "NETWORK_ERROR": "网络错误",
    "INVALID_RESPONSE": "响应格式错误",
    "INVALID_JSON": "JSON 格式错误",
    "API_ERROR": "接口错误",
    "HTTP_ERROR": "请求失败",
    "TASK_ALREADY_EXISTS": "任务已存在",
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.api = PriceOverviewClient()
        self.current_task_id: str | None = None
        self.current_quote_id: str | None = None
        self.current_process_route: dict[str, Any] | None = None
        self.current_quantity_result: dict[str, Any] | None = None
        self.current_quote_result: dict[str, Any] | None = None
        self._files: list[dict[str, Any]] = []
        self._parse_result_file_ids: set[str] = set()

        self.setWindowTitle("报价核对工作台")
        self.resize(1180, 760)
        self._build_ui()
        QTimer.singleShot(0, self.refresh_task_list)

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)

        toolbar = QHBoxLayout()
        self.base_url_input = QLineEdit("http://127.0.0.1:8017")
        self.task_id_input = QLineEdit()
        self.task_id_input.setPlaceholderText("请选择或新建任务")
        self.task_combo = QComboBox()
        self.task_combo.addItem("手动输入任务ID", None)
        self.task_combo.setMinimumWidth(320)
        self.task_id_input.setMinimumWidth(180)
        refresh_tasks_button = QPushButton("刷新任务")
        new_task_button = QPushButton("新建任务")
        load_button = QPushButton("加载")
        self.task_combo.currentIndexChanged.connect(self.select_task_from_combo)
        refresh_tasks_button.clicked.connect(self.refresh_task_list)
        new_task_button.clicked.connect(self.open_create_task_dialog)
        load_button.clicked.connect(self.load_task)

        toolbar.addWidget(QLabel("后端地址"))
        toolbar.addWidget(self.base_url_input, 2)
        toolbar.addWidget(QLabel("任务"))
        toolbar.addWidget(self.task_combo, 2)
        toolbar.addWidget(QLabel("任务ID"))
        toolbar.addWidget(self.task_id_input, 1)
        toolbar.addWidget(refresh_tasks_button)
        toolbar.addWidget(new_task_button)
        toolbar.addWidget(load_button)
        root_layout.addLayout(toolbar)

        actions = QHBoxLayout()
        self.upload_pdf_button = QPushButton("上传 PDF")
        self.upload_step_button = QPushButton("上传 STEP")
        self.upload_attachment_button = QPushButton("上传附件")
        self.parse_button = QPushButton("解析文件")
        self.price_button = QPushButton("规则核价")
        self.ai_price_button = QPushButton("AI 工艺核价")
        self.price_button.setToolTip("按规则快速生成核价。")
        self.ai_price_button.setToolTip("调用 AI 生成工艺路线，可能较慢，失败时会提示原因。")
        self.export_button = QPushButton("导出 JSON")

        self.upload_pdf_button.clicked.connect(lambda: self.upload_file("pdf"))
        self.upload_step_button.clicked.connect(lambda: self.upload_file("step"))
        self.upload_attachment_button.clicked.connect(
            lambda: self.upload_file("attachment")
        )
        self.parse_button.clicked.connect(self.parse_task)
        self.price_button.clicked.connect(self.price_task)
        self.ai_price_button.clicked.connect(self.price_task_with_ai)
        self.export_button.clicked.connect(self.export_quote)

        for button in (
            self.upload_pdf_button,
            self.upload_step_button,
            self.upload_attachment_button,
            self.parse_button,
            self.price_button,
            self.ai_price_button,
            self.export_button,
        ):
            actions.addWidget(button)
        actions.addStretch(1)
        root_layout.addLayout(actions)

        summary = QFormLayout()
        self.task_status_value = QLabel("-")
        self.latest_quote_value = QLabel("-")
        self.risk_count_value = QLabel("0")
        self.initial_quote_value = QLabel("-")
        self.final_quote_value = QLabel("-")

        summary.addRow("任务状态", self.task_status_value)
        summary.addRow("最新报价ID", self.latest_quote_value)
        summary.addRow("风险数量", self.risk_count_value)
        summary.addRow("初始报价", self.initial_quote_value)
        summary.addRow("最终报价", self.final_quote_value)
        root_layout.addLayout(summary)

        self.tabs = QTabWidget()
        self.files_tab = self._build_files_tab()
        self.feature_tab = self._build_feature_tab()
        self.quote_tab = self._build_quote_tab()
        self.ai_tab = self._build_ai_tab()
        self.risk_tab = self._build_risk_tab()
        self.tabs.addTab(self.files_tab, "文件")
        self.tabs.addTab(self.feature_tab, "零件特征")
        self.tabs.addTab(self.quote_tab, "报价")
        self.tabs.addTab(self.risk_tab, "风险")
        self.tabs.addTab(self.ai_tab, "AI 建议")
        root_layout.addWidget(self.tabs, 1)

        self.setCentralWidget(root)
        self.statusBar().showMessage("就绪")
        self.rule_price_timeout = 120.0
        self.ai_price_timeout = 100.0

    def _build_files_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        upload_controls = QHBoxLayout()
        self.file_type_combo = QComboBox()
        for file_type in ("pdf", "step", "attachment"):
            self.file_type_combo.addItem(FILE_TYPE_LABELS[file_type], file_type)
        self.file_path_input = QLineEdit()
        self.file_path_input.setReadOnly(True)
        self.uploaded_by_input = QLineEdit("user_001")
        browse_button = QPushButton("浏览")
        upload_button = QPushButton("上传")
        refresh_button = QPushButton("刷新")
        invalidate_button = QPushButton("标记失效")
        delete_button = QPushButton("删除选中文件")

        browse_button.clicked.connect(self.select_upload_file)
        upload_button.clicked.connect(self.upload_selected_file)
        refresh_button.clicked.connect(self.load_task)
        invalidate_button.clicked.connect(self.invalidate_selected_file)
        delete_button.clicked.connect(self.delete_selected_file)

        upload_controls.addWidget(QLabel("文件类型"))
        upload_controls.addWidget(self.file_type_combo)
        upload_controls.addWidget(QLabel("本地文件"))
        upload_controls.addWidget(self.file_path_input, 2)
        upload_controls.addWidget(browse_button)
        upload_controls.addWidget(QLabel("上传人"))
        upload_controls.addWidget(self.uploaded_by_input)
        upload_controls.addWidget(upload_button)
        upload_controls.addWidget(refresh_button)
        upload_controls.addWidget(invalidate_button)
        upload_controls.addWidget(delete_button)
        layout.addLayout(upload_controls)

        parse_controls = QHBoxLayout()
        self.parse_pdf_checkbox = QCheckBox("解析 PDF")
        self.parse_step_checkbox = QCheckBox("解析 STEP")
        self.parse_ai_checkbox = QCheckBox("AI 建议")
        self.parse_pdf_checkbox.setChecked(True)
        self.parse_step_checkbox.setChecked(True)
        self.parse_ai_checkbox.setChecked(False)
        self.parse_pdf_combo = QComboBox()
        self.parse_step_combo = QComboBox()
        self.parse_pdf_combo.addItem("自动选择最新有效文件", None)
        self.parse_step_combo.addItem("自动选择最新有效文件", None)
        self.parse_selection_hint = QLabel()
        self.parse_selection_hint.setWordWrap(True)
        self.parse_pdf_combo.currentIndexChanged.connect(self._update_parse_selection_hint)
        self.parse_step_combo.currentIndexChanged.connect(self._update_parse_selection_hint)
        self.parse_pdf_checkbox.stateChanged.connect(self._update_parse_selection_hint)
        self.parse_step_checkbox.stateChanged.connect(self._update_parse_selection_hint)
        parse_controls.addWidget(self.parse_pdf_checkbox)
        parse_controls.addWidget(self.parse_pdf_combo, 1)
        parse_controls.addWidget(self.parse_step_checkbox)
        parse_controls.addWidget(self.parse_step_combo, 1)
        parse_controls.addWidget(self.parse_ai_checkbox)
        parse_controls.addWidget(self.parse_selection_hint, 2)
        parse_controls.addStretch(1)
        layout.addLayout(parse_controls)

        self.files_table = QTableWidget(0, 11)
        self.files_table.setHorizontalHeaderLabels(
            [
                "文件ID",
                "文件名",
                "文件类型",
                "版本",
                "状态",
                "解析状态",
                "本次选择",
                "结果来源",
                "上传时间",
                "上传人",
                "存储路径",
            ]
        )
        configure_table(self.files_table)
        self.files_table.itemSelectionChanged.connect(
            self.sync_parse_selection_from_file_table
        )
        header = self.files_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(10, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.files_table)
        self._update_parse_selection_hint()
        return widget

    def _build_feature_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        actions = QHBoxLayout()
        refresh_button = QPushButton("刷新解析结果")
        refresh_button.clicked.connect(self.refresh_parse_result)
        actions.addWidget(refresh_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        summary = QFormLayout()
        self.feature_parser_source_value = value_label()
        self.feature_material_value = value_label()
        self.feature_material_confidence_value = value_label()
        self.feature_dimensions_value = value_label()
        self.feature_volume_value = value_label()
        self.feature_weight_value = value_label()
        self.feature_surface_value = value_label()
        self.feature_heat_value = value_label()
        self.feature_part_type_value = value_label()

        summary.addRow("解析来源", self.feature_parser_source_value)
        summary.addRow("材料", self.feature_material_value)
        summary.addRow("材料置信度", self.feature_material_confidence_value)
        summary.addRow("包络尺寸", self.feature_dimensions_value)
        summary.addRow("体积/表面积", self.feature_volume_value)
        summary.addRow("重量", self.feature_weight_value)
        summary.addRow("表面处理", self.feature_surface_value)
        summary.addRow("热处理", self.feature_heat_value)
        summary.addRow("零件类型", self.feature_part_type_value)
        layout.addLayout(summary)

        layout.addWidget(QLabel("PDF抽取字段"))
        self.pdf_fields_table = QTableWidget(0, 6)
        self.pdf_fields_table.setHorizontalHeaderLabels(
            ["字段", "抽取值", "置信度", "方法", "候选", "证据"]
        )
        configure_table(self.pdf_fields_table)
        layout.addWidget(self.pdf_fields_table)

        layout.addWidget(QLabel("孔特征"))
        self.holes_table = QTableWidget(0, 6)
        self.holes_table.setHorizontalHeaderLabels(
            ["类型", "数量", "直径", "深度", "置信度", "证据"]
        )
        configure_table(self.holes_table)
        layout.addWidget(self.holes_table)

        layout.addWidget(QLabel("精度要求"))
        self.precision_table = QTableWidget(0, 4)
        self.precision_table.setHorizontalHeaderLabels(
            ["要求", "类型", "置信度", "证据"]
        )
        configure_table(self.precision_table)
        layout.addWidget(self.precision_table)
        return widget

    def _build_quote_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        actions = QHBoxLayout()
        self.refresh_quote_button = QPushButton("刷新报价")
        self.override_item_button = QPushButton("修改选中明细")
        self.quantity_override_button = QPushButton("修改选中工程量")
        self.final_quote_button = QPushButton("设置最终报价")
        self.confirm_quote_button = QPushButton("确认报价")
        self.refresh_quote_button.clicked.connect(self.refresh_quote_result)
        self.override_item_button.clicked.connect(self.open_item_override_dialog)
        self.quantity_override_button.clicked.connect(self.open_quantity_override_dialog)
        self.final_quote_button.clicked.connect(self.open_final_quote_dialog)
        self.confirm_quote_button.clicked.connect(self.open_confirm_quote_dialog)
        actions.addWidget(self.refresh_quote_button)
        actions.addWidget(self.override_item_button)
        actions.addWidget(self.quantity_override_button)
        actions.addWidget(self.final_quote_button)
        actions.addWidget(self.confirm_quote_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        summary = QFormLayout()
        self.quote_id_value = value_label()
        self.quote_status_value = value_label()
        self.quote_currency_value = value_label()
        self.quote_version_value = value_label()
        self.quote_priced_at_value = value_label()
        self.quote_material_amount_value = value_label()
        self.quote_process_amount_value = value_label()
        self.quote_surface_amount_value = value_label()
        self.quote_management_fee_value = value_label()
        self.quote_tax_amount_value = value_label()
        self.quote_system_calculated_value = value_label()
        self.quote_initial_value = value_label()
        self.quote_manual_adjustment_value = value_label()
        self.quote_final_confirmed_input = QLineEdit()
        self.quote_final_confirmed_input.setReadOnly(True)

        summary.addRow("报价ID", self.quote_id_value)
        summary.addRow("状态", self.quote_status_value)
        summary.addRow("币种", self.quote_currency_value)
        summary.addRow("价格版本", self.quote_version_value)
        summary.addRow("核价时间", self.quote_priced_at_value)
        summary.addRow("材料费", self.quote_material_amount_value)
        summary.addRow("工序费", self.quote_process_amount_value)
        summary.addRow("表面处理费", self.quote_surface_amount_value)
        summary.addRow("管理费", self.quote_management_fee_value)
        summary.addRow("税费", self.quote_tax_amount_value)
        summary.addRow("系统计算价", self.quote_system_calculated_value)
        summary.addRow("初始报价", self.quote_initial_value)
        summary.addRow("人工调整", self.quote_manual_adjustment_value)
        summary.addRow("最终确认价", self.quote_final_confirmed_input)
        layout.addLayout(summary)

        quote_pages = QTabWidget()

        process_page = QWidget()
        process_layout = QVBoxLayout(process_page)

        process_actions = QHBoxLayout()
        self.add_operation_button = QPushButton("新增工序")
        self.edit_operation_button = QPushButton("修改选中工序")
        self.delete_operation_button = QPushButton("删除选中工序")
        self.reorder_operation_button = QPushButton("调整顺序")
        self.add_operation_button.clicked.connect(self.open_add_operation_dialog)
        self.edit_operation_button.clicked.connect(self.open_edit_operation_dialog)
        self.delete_operation_button.clicked.connect(self.open_delete_operation_dialog)
        self.reorder_operation_button.clicked.connect(self.open_operation_sequence_dialog)
        process_actions.addWidget(self.add_operation_button)
        process_actions.addWidget(self.edit_operation_button)
        process_actions.addWidget(self.delete_operation_button)
        process_actions.addWidget(self.reorder_operation_button)
        process_actions.addStretch(1)
        process_layout.addLayout(process_actions)

        self.process_route_table = QTableWidget(0, 9)
        self.process_route_table.setHorizontalHeaderLabels(
            [
                "工序ID",
                "序号",
                "工序",
                "工序编码",
                "触发原因",
                "置信度",
                "需复核",
                "复核原因",
                "说明",
            ]
        )
        configure_table(self.process_route_table)
        self.process_route_table.setColumnHidden(0, True)
        process_layout.addWidget(self.process_route_table)
        quote_pages.addTab(process_page, "工艺路线")

        quantity_page = QWidget()
        quantity_layout = QVBoxLayout(quantity_page)
        self.quantity_result_table = QTableWidget(0, 9)
        self.quantity_result_table.setHorizontalHeaderLabels(
            ["工程量ID", "工序", "类型", "值", "单位", "公式", "依据", "需复核", "复核原因"]
        )
        configure_table(self.quantity_result_table)
        quantity_layout.addWidget(self.quantity_result_table)
        quote_pages.addTab(quantity_page, "工程量")

        quote_items_page = QWidget()
        quote_items_layout = QVBoxLayout(quote_items_page)
        self.quote_table = QTableWidget(0, 11)
        self.quote_table.setHorizontalHeaderLabels(
            [
                "明细ID",
                "类型",
                "工序",
                "数量",
                "单位",
                "单价",
                "金额",
                "系统金额",
                "最终金额",
                "需复核",
                "公式/来源",
            ]
        )
        configure_table(self.quote_table)
        quote_items_layout.addWidget(self.quote_table)
        quote_pages.addTab(quote_items_page, "报价明细")

        review_page = QWidget()
        review_layout = QVBoxLayout(review_page)
        self.manual_override_table = QTableWidget(0, 7)
        self.manual_override_table.setHorizontalHeaderLabels(
            ["对象", "字段", "旧值", "新值", "原因", "操作人", "时间"]
        )
        configure_table(self.manual_override_table)
        review_layout.addWidget(self.manual_override_table)
        quote_pages.addTab(review_page, "人工修改")

        layout.addWidget(quote_pages, 1)
        self._sync_quote_actions(None)
        return widget

    def _build_risk_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        actions = QHBoxLayout()
        self.confirm_risk_button = QPushButton("确认选中风险")
        self.confirm_risk_button.clicked.connect(self.open_risk_confirmation_dialog)
        actions.addWidget(self.confirm_risk_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.risk_table = QTableWidget(0, 6)
        self.risk_table.setHorizontalHeaderLabels(
            ["编码", "等级", "说明", "需复核", "确认状态", "证据"]
        )
        configure_table(self.risk_table)
        layout.addWidget(self.risk_table)
        return widget

    def _build_ai_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.ai_status_label = QLabel("本次未启用 AI 建议或暂无需要 AI 解释的内容。")
        self.ai_status_label.setWordWrap(True)
        layout.addWidget(self.ai_status_label)
        self.ai_output_table = QTableWidget(0, 8)
        self.ai_output_table.setHorizontalHeaderLabels(
            [
                "输入类型",
                "输出类型",
                "结果摘要",
                "置信度",
                "模型",
                "提示词版本",
                "生成时间",
                "证据",
            ]
        )
        configure_table(self.ai_output_table)
        header = self.ai_output_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.ai_output_table)
        return widget

    def load_task(self) -> None:
        self._run_action("加载任务", self._load_task)

    def refresh_task_list(self) -> None:
        self._run_action("刷新任务列表", self._refresh_task_list)

    def select_task_from_combo(self, _index: int | None = None) -> None:
        if not hasattr(self, "task_combo"):
            return
        task_id = self.task_combo.currentData()
        if task_id:
            self.task_id_input.setText(str(task_id))
            if self.current_task_id != str(task_id):
                self.load_task()

    def open_create_task_dialog(self) -> None:
        dialog = CreateTaskDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        payload = dialog.payload()

        def action() -> None:
            self.api.base_url = self.base_url_input.text().strip().rstrip("/")
            task = self.api.create_task(**payload)
            self.task_id_input.setText(task["task_id"])
            self._refresh_task_list(selected_task_id=task["task_id"])
            self._load_task()
            self.tabs.setCurrentWidget(self.files_tab)
            self.statusBar().showMessage(
                f"任务 {task['task_id']} 已创建，可以上传真实 PDF。"
            )

        self._run_action("新建任务", action)

    def select_upload_file(self) -> None:
        file_type = self._selected_file_type()
        filters = {
            "pdf": "PDF 文件 (*.pdf)",
            "step": "STEP 文件 (*.step *.stp)",
            "attachment": "所有文件 (*.*)",
        }
        selected, _ = QFileDialog.getOpenFileName(
            self,
            f"选择{FILE_TYPE_LABELS.get(file_type, file_type)}",
            "",
            filters[file_type],
        )
        if selected:
            self.file_path_input.setText(selected)

    def upload_selected_file(self) -> None:
        selected = self.file_path_input.text().strip()
        if not selected:
            QMessageBox.warning(self, "文件必填", "请先选择一个文件。")
            return

        file_type = self._selected_file_type()
        uploaded_by = self.uploaded_by_input.text().strip() or "user_001"

        def action() -> None:
            task_id = self._task_id()
            self.api.upload_file(
                task_id,
                file_type,
                Path(selected),
                uploaded_by=uploaded_by,
            )
            self.file_path_input.clear()
            self._load_task()
            self.tabs.setCurrentWidget(self.files_tab)
            self.statusBar().showMessage("文件已上传并刷新文件列表。")

        self._run_action(f"上传 {FILE_TYPE_LABELS.get(file_type, file_type)}", action)

    def upload_file(self, file_type: str) -> None:
        filters = {
            "pdf": "PDF 文件 (*.pdf)",
            "step": "STEP 文件 (*.step *.stp)",
            "attachment": "所有文件 (*.*)",
        }
        selected, _ = QFileDialog.getOpenFileName(
            self,
            f"选择{FILE_TYPE_LABELS.get(file_type, file_type)}",
            "",
            filters[file_type],
        )
        if not selected:
            return

        def action() -> None:
            task_id = self._task_id()
            uploaded_by = self.uploaded_by_input.text().strip() or "user_001"
            self.api.upload_file(
                task_id,
                file_type,
                Path(selected),
                uploaded_by=uploaded_by,
            )
            self._load_task()
            self.tabs.setCurrentWidget(self.files_tab)
            self.statusBar().showMessage("文件已上传并刷新文件列表。")

        self._run_action(f"上传 {FILE_TYPE_LABELS.get(file_type, file_type)}", action)

    def invalidate_selected_file(self) -> None:
        file_id = self._selected_file_id_or_warn()
        if not file_id:
            return

        response = QMessageBox.question(
            self,
            "标记文件失效",
            f"确定将文件 {file_id} 标记为失效吗？失效文件不会再参与解析。",
        )
        if response != QMessageBox.StandardButton.Yes:
            return

        def action() -> None:
            self.api.invalidate_file(self._task_id(), file_id)
            self._load_task()
            self.tabs.setCurrentWidget(self.files_tab)
            self.statusBar().showMessage("文件已标记为失效。")

        self._run_action("标记文件失效", action)

    def delete_selected_file(self) -> None:
        file_id = self._selected_file_id_or_warn()
        if not file_id:
            return

        response = QMessageBox.question(
            self,
            "删除文件",
            f"确定删除文件 {file_id} 吗？这里会逻辑删除，不会物理移除历史文件。",
        )
        if response != QMessageBox.StandardButton.Yes:
            return

        def action() -> None:
            self.api.delete_file(self._task_id(), file_id)
            self._load_task()
            self.tabs.setCurrentWidget(self.files_tab)
            self.statusBar().showMessage("文件已删除。")

        self._run_action("删除文件", action)

    def parse_task(self) -> None:
        if not self.parse_pdf_checkbox.isChecked() and not self.parse_step_checkbox.isChecked():
            QMessageBox.warning(self, "请选择解析输入", "请至少勾选 PDF 或 STEP 中的一项。")
            return

        def action() -> None:
            task_id = self._task_id()
            self.api.parse_task(
                task_id,
                parse_pdf=self.parse_pdf_checkbox.isChecked(),
                parse_step=self.parse_step_checkbox.isChecked(),
                use_ai=self.parse_ai_checkbox.isChecked(),
                pdf_file_id=(
                    self._selected_parse_file_id(self.parse_pdf_combo)
                    if self.parse_pdf_checkbox.isChecked()
                    else None
                ),
                step_file_id=(
                    self._selected_parse_file_id(self.parse_step_combo)
                    if self.parse_step_checkbox.isChecked()
                    else None
                ),
            )
            self.api.get_parse_result(task_id)
            self._load_task()
            self.tabs.setCurrentWidget(self.feature_tab)
            self.statusBar().showMessage("解析完成，正在显示零件特征。")

        self._run_action("解析任务", action)

    def refresh_parse_result(self) -> None:
        def action() -> None:
            parse_result = self.api.get_parse_result(self._task_id())
            self._render_part_feature(parse_result)
            self._render_risks(parse_result.get("risks") or [])

        self._run_action("刷新解析结果", action)

    def price_task(self) -> None:
        self._price_task(
            title="生成规则核价",
            action_label="生成规则核价",
            use_ai=False,
            use_market_price_search=False,
            process_route_mode="rule",
            request_timeout=self.rule_price_timeout,
        )

    def price_task_with_ai(self) -> None:
        self._price_task(
            title="生成 AI 工艺核价",
            action_label="生成 AI 工艺核价",
            use_ai=True,
            use_market_price_search=False,
            process_route_mode="ai_autonomous",
            request_timeout=self.ai_price_timeout,
        )

    def _price_task(
        self,
        *,
        title: str,
        action_label: str,
        use_ai: bool,
        use_market_price_search: bool,
        process_route_mode: str,
        request_timeout: float | None,
    ) -> None:
        if self.current_quote_id:
            response = QMessageBox.question(
                self,
                title,
                (
                    "再次核价会生成新的报价ID，当前报价上的人工修改不会复制过去。\n\n"
                    f"当前报价：{self.current_quote_id}\n\n"
                    "是否继续？"
                ),
            )
            if response != QMessageBox.StandardButton.Yes:
                self.statusBar().showMessage("生成核价已取消。")
                return

        def action() -> None:
            result = self.api.price_task(
                self._task_id(),
                use_ai=use_ai,
                use_market_price_search=use_market_price_search,
                process_route_mode=process_route_mode,
                timeout=request_timeout,
            )
            self.current_quote_id = result["quote_id"]
            self._render_quote_bundle(result)
            self._load_task()
            self.tabs.setCurrentWidget(self.quote_tab)
            self.statusBar().showMessage("报价已生成，正在显示报价页。")

        self._run_action(action_label, action)

    def refresh_quote_result(self) -> None:
        def action() -> None:
            quote_id = self.current_quote_id
            if not quote_id:
                raise ApiError("QUOTE_REQUIRED", "请先生成或载入报价。")
            quote_bundle = self.api.get_quote_bundle(quote_id)
            self._render_quote_bundle(quote_bundle)

        self._run_action("刷新报价", action)

    def open_add_operation_dialog(self) -> None:
        quote_result = self._quote_result_or_warn()
        if quote_result is None:
            return
        process_route = self.current_process_route
        if not process_route:
            QMessageBox.warning(self, "无工艺路线", "当前报价没有可修改的工艺路线。")
            return

        operations = process_route.get("operations") or []
        dialog = OperationDialog(
            self,
            operation=None,
            max_sequence=len(operations) + 1,
            operator_id=self.uploaded_by_input.text().strip() or "user_001",
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.submit_manual_override(dialog.payload())

    def open_edit_operation_dialog(self) -> None:
        operation = self._selected_operation_or_warn()
        if operation is None:
            return

        operations = (self.current_process_route or {}).get("operations") or []
        dialog = OperationDialog(
            self,
            operation=operation,
            max_sequence=max(len(operations), 1),
            operator_id=self.uploaded_by_input.text().strip() or "user_001",
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.submit_manual_override(dialog.payload())

    def open_delete_operation_dialog(self) -> None:
        operation = self._selected_operation_or_warn()
        if operation is None:
            return

        dialog = DeleteOperationDialog(
            self,
            operation=operation,
            operator_id=self.uploaded_by_input.text().strip() or "user_001",
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.submit_manual_override(dialog.payload())

    def open_operation_sequence_dialog(self) -> None:
        operation = self._selected_operation_or_warn()
        if operation is None:
            return

        operations = (self.current_process_route or {}).get("operations") or []
        dialog = OperationSequenceDialog(
            self,
            operation=operation,
            max_sequence=max(len(operations), 1),
            operator_id=self.uploaded_by_input.text().strip() or "user_001",
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.submit_manual_override(dialog.payload())

    def open_item_override_dialog(self) -> None:
        quote_result = self._quote_result_or_warn()
        if quote_result is None:
            return
        row = self.quote_table.currentRow()
        if row < 0:
            QMessageBox.warning(
                self,
                "请选择明细",
                "请先选中一条报价明细。",
            )
            return

        item_id_cell = self.quote_table.item(row, 0)
        if item_id_cell is None:
            QMessageBox.warning(self, "请选择明细", "所选行没有明细ID。")
            return

        item = find_quote_item(quote_result, item_id_cell.text())
        if item is None:
            QMessageBox.warning(self, "明细未找到", "未找到对应的报价明细。")
            return

        dialog = ManualOverrideDialog(
            self,
            target_type="quote_item",
            target_id=item["item_id"],
            field_options=["amount", "final_amount", "unit_price", "explanation"],
            old_values={
                "amount": item.get("amount"),
                "final_amount": item.get("final_amount"),
                "unit_price": item.get("unit_price"),
                "explanation": item.get("explanation"),
            },
            operator_id=self.uploaded_by_input.text().strip() or "user_001",
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.submit_manual_override(dialog.payload())

    def open_quantity_override_dialog(self) -> None:
        quote_result = self._quote_result_or_warn()
        if quote_result is None:
            return
        quantity_result = self.current_quantity_result
        if not quantity_result:
            QMessageBox.warning(self, "无工程量", "当前报价没有可修改的工程量结果。")
            return
        row = self.quantity_result_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "请选择工程量", "请先选中一条工程量记录。")
            return

        quantity_id_cell = self.quantity_result_table.item(row, 0)
        if quantity_id_cell is None:
            QMessageBox.warning(self, "请选择工程量", "所选行没有工程量ID。")
            return

        quantity_item = find_quantity_item(quantity_result, quantity_id_cell.text())
        if quantity_item is None:
            QMessageBox.warning(self, "工程量未找到", "未找到对应的工程量记录。")
            return

        dialog = ManualOverrideDialog(
            self,
            target_type="quantity",
            target_id=quantity_item["quantity_id"],
            field_options=["value"],
            old_values={"value": quantity_item.get("value")},
            operator_id=self.uploaded_by_input.text().strip() or "user_001",
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.submit_manual_override(dialog.payload())

    def open_risk_confirmation_dialog(self) -> None:
        quote_result = self._quote_result_or_warn()
        if quote_result is None:
            return
        row = self.risk_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "请选择风险", "请先在风险页选中一条风险。")
            return

        risk_code_cell = self.risk_table.item(row, 0)
        if risk_code_cell is None:
            QMessageBox.warning(self, "请选择风险", "所选行没有风险编码。")
            return

        risk_code = risk_code_cell.text().strip()
        risk = find_risk(quote_result, risk_code)
        if risk is None:
            QMessageBox.warning(self, "风险未找到", "未找到对应的风险记录。")
            return
        if risk_confirmed(quote_result, risk):
            QMessageBox.information(self, "风险已确认", "该风险已经有确认记录。")
            return

        dialog = RiskConfirmDialog(
            self,
            risk_code=risk_code,
            risk_message=risk_message_text(risk),
            operator_id=self.uploaded_by_input.text().strip() or "user_001",
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.submit_manual_override(dialog.payload())

    def open_final_quote_dialog(self) -> None:
        quote_result = self._quote_result_or_warn()
        if quote_result is None:
            return
        summary = quote_result.get("summary") or {}
        dialog = ManualOverrideDialog(
            self,
            target_type="quote_summary",
            target_id="summary",
            field_options=["final_confirmed_amount"],
            old_values={
                "final_confirmed_amount": summary.get("final_confirmed_amount"),
            },
            operator_id=self.uploaded_by_input.text().strip() or "user_001",
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.submit_manual_override(dialog.payload())

    def open_confirm_quote_dialog(self) -> None:
        quote_result = self._quote_result_or_warn()
        if quote_result is None:
            return
        if quote_result.get("status") in {"confirmed", "voided"}:
            QMessageBox.warning(self, "报价只读", "已确认或作废的报价不可再次确认。")
            return

        blocking = blocking_review_risks(quote_result)
        if blocking:
            QMessageBox.warning(
                self,
                "存在阻断风险",
                "存在未确认的阻断风险，不能确认报价。\n\n"
                + "\n".join(risk.get("code") or "-" for risk in blocking),
            )
            return

        summary = quote_result.get("summary") or {}
        default_amount = first_number(
            summary.get("final_confirmed_amount"),
            summary.get("system_initial_quote"),
            summary.get("system_calculated_amount"),
            0,
        )
        dialog = ConfirmQuoteDialog(
            self,
            default_amount=default_amount,
            operator_id=self.uploaded_by_input.text().strip() or "user_001",
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.submit_confirm_quote(dialog.payload())

    def submit_confirm_quote(self, payload: dict[str, Any]) -> None:
        def action() -> None:
            quote_id = self.current_quote_id
            if not quote_id:
                raise ApiError("QUOTE_REQUIRED", "请先生成或载入报价。")
            self.api.confirm_quote(quote_id, **payload)
            quote_bundle = self.api.get_quote_bundle(quote_id)
            self._render_quote_bundle(quote_bundle)
            self._load_task()
            self.tabs.setCurrentWidget(self.quote_tab)
            message = "报价已确认，后续修改需要生成新报价。"
            self.statusBar().showMessage(message)
            QMessageBox.information(self, "报价已确认", message)

        self._run_action("确认报价", action)

    def submit_manual_override(self, payload: dict[str, Any]) -> None:
        def action() -> None:
            quote_id = self.current_quote_id
            if not quote_id:
                raise ApiError("QUOTE_REQUIRED", "请先生成或载入报价。")
            self.api.save_override(quote_id, payload)
            quote_bundle = self.api.get_quote_bundle(quote_id)
            self._render_quote_bundle(quote_bundle)
            self._load_task()
            self.tabs.setCurrentWidget(self.quote_tab)
            message = "人工修改已保存，正在显示报价页。"
            self.statusBar().showMessage(message)
            QMessageBox.information(self, "人工修改已保存", message)

        self._run_action("保存人工修改", action)

    def export_quote(self) -> None:
        def action() -> None:
            quote_id = self.current_quote_id
            if not quote_id:
                raise ApiError("QUOTE_REQUIRED", "请先生成或载入报价。")

            export_result = self.api.export_quote(quote_id)
            exported = self.api.download_export(export_result["export_id"])
            default_name = f"{export_result['export_id']}.json"
            selected, _ = QFileDialog.getSaveFileName(
                self,
                "保存导出文件",
                default_name,
                "JSON 文件 (*.json)",
            )
            if selected:
                selected_path = Path(selected)
                selected_path.write_text(
                    json.dumps(exported, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                self.tabs.setCurrentWidget(self.quote_tab)
                message = (
                    f"已导出 {export_result['export_id']} 到 "
                    f"{selected_path.resolve()}"
                )
                self.statusBar().showMessage(message)
                QMessageBox.information(self, "导出已保存", message)
            else:
                self.statusBar().showMessage("导出已取消。")

        self._run_action("导出报价", action)

    def _load_task(self) -> None:
        self.api.base_url = self.base_url_input.text().strip().rstrip("/")
        data = self.api.get_task(self._task_id())
        self.current_task_id = data["task_id"]
        self.current_quote_id = data.get("latest_quote_id")
        self._select_task_in_combo(self.current_task_id)
        self._render_task(data)

    def _refresh_task_list(self, selected_task_id: str | None = None) -> None:
        self.api.base_url = self.base_url_input.text().strip().rstrip("/")
        selected = (
            selected_task_id
            or self.current_task_id
            or self.task_combo.currentData()
            or self.task_id_input.text().strip()
        )
        tasks = self.api.list_tasks()
        selected_after_refresh = None

        self.task_combo.blockSignals(True)
        try:
            self.task_combo.clear()
            self.task_combo.addItem("手动输入任务ID", None)
            for task in tasks:
                label = task_combo_label(task)
                self.task_combo.addItem(label, task.get("task_id"))

            if selected:
                index = self.task_combo.findData(selected)
                if index >= 0:
                    self.task_combo.setCurrentIndex(index)
                    selected_after_refresh = str(selected)
            if selected_after_refresh is None and tasks:
                selected_after_refresh = str(tasks[0].get("task_id"))
                self.task_combo.setCurrentIndex(1)
        finally:
            self.task_combo.blockSignals(False)

        if selected_after_refresh:
            self.task_id_input.setText(selected_after_refresh)
            if self.current_task_id != selected_after_refresh:
                self._load_task()
        elif not selected:
            self.task_id_input.clear()

        self.statusBar().showMessage(f"已加载 {len(tasks)} 个任务。")

    def _select_task_in_combo(self, task_id: str) -> None:
        if not hasattr(self, "task_combo"):
            return
        index = self.task_combo.findData(task_id)
        if index < 0:
            return
        self.task_combo.blockSignals(True)
        try:
            self.task_combo.setCurrentIndex(index)
        finally:
            self.task_combo.blockSignals(False)

    def _quote_result_or_warn(self) -> dict[str, Any] | None:
        if not self.current_quote_result:
            QMessageBox.warning(
                self,
                "请先生成报价",
                "请先生成或载入报价。",
            )
            return None
        return self.current_quote_result

    def _selected_operation_or_warn(self) -> dict[str, Any] | None:
        if self._quote_result_or_warn() is None:
            return None

        process_route = self.current_process_route
        if not process_route:
            QMessageBox.warning(self, "无工艺路线", "当前报价没有可修改的工艺路线。")
            return None

        row = self.process_route_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "请选择工序", "请先选中一条工艺路线记录。")
            return None

        operation_id_cell = self.process_route_table.item(row, 0)
        if operation_id_cell is None or not operation_id_cell.text().strip():
            QMessageBox.warning(self, "请选择工序", "所选行没有工序ID。")
            return None

        operation = find_operation(process_route, operation_id_cell.text().strip())
        if operation is None:
            QMessageBox.warning(self, "工序未找到", "未找到对应的工艺路线记录。")
            return None
        return operation

    def _render_task(self, data: dict[str, Any]) -> None:
        self.task_status_value.setText(label_for(STATUS_LABELS, data.get("status")))
        self.latest_quote_value.setText(str(data.get("latest_quote_id") or "-"))

        risks = data.get("risks") or []
        self.risk_count_value.setText(str(len(risks)))
        self._render_risks(risks, data.get("latest_quote_result"))

        parse_result = data.get("parse_result")
        self._render_files(data.get("files") or [], parse_result)
        self._render_part_feature(parse_result)
        self._render_quote_bundle(
            {
                "process_route": data.get("latest_process_route"),
                "quantity_result": data.get("latest_quantity_result"),
                "quote_result": data.get("latest_quote_result"),
            }
        )
        self._render_ai_outputs(data.get("ai_outputs") or [])

    def _render_files(
        self,
        files: list[dict[str, Any]],
        parse_result: dict[str, Any] | None,
    ) -> None:
        self._files = files
        self._parse_result_file_ids = parse_file_ids(parse_result)
        self._populate_parse_file_combos(files)
        self.files_table.setRowCount(len(files))
        for row, item in enumerate(files):
            values = [
                item.get("file_id"),
                item.get("filename"),
                label_for(FILE_TYPE_LABELS, item.get("file_type")),
                item.get("version"),
                label_for(FILE_STATUS_LABELS, item.get("status")),
                label_for(FILE_PARSE_STATUS_LABELS, item.get("parse_status")),
                "-",
                yes_no(item.get("file_id") in self._parse_result_file_ids),
                datetime_text(item.get("uploaded_at")),
                item.get("uploaded_by"),
                item.get("storage_path"),
            ]
            for column, value in enumerate(values):
                self.files_table.setItem(row, column, table_item(value))
        self._refresh_file_choice_columns()

    def _render_part_feature(self, parse_result: dict[str, Any] | None) -> None:
        part_feature = (parse_result or {}).get("part_feature")
        if not part_feature:
            self._clear_part_feature()
            return

        material = part_feature.get("material") or {}
        geometry = part_feature.get("geometry") or {}
        features = part_feature.get("features") or {}
        requirements = part_feature.get("manufacturing_requirements") or {}
        surface = requirements.get("surface_treatment") or {}
        heat = requirements.get("heat_treatment") or {}

        self.feature_parser_source_value.setText(
            parser_source_text(parse_result, self._files)
        )
        self.feature_material_value.setText(
            material_feature_text(material)
        )
        self.feature_material_confidence_value.setText(
            confidence_text(material.get("confidence"))
        )
        self.feature_dimensions_value.setText(
            bounding_box_text(geometry.get("bounding_box"))
        )
        self.feature_volume_value.setText(
            join_present(
                [
                    f"体积：{measured_value_text(geometry.get('volume'))}",
                    f"表面积：{measured_value_text(geometry.get('surface_area'))}",
                ]
            )
        )
        self.feature_weight_value.setText(
            join_present(
                [
                    f"PDF重量：{measured_value_text(geometry.get('pdf_weight'))}",
                    f"STEP净重：{measured_value_text(geometry.get('step_net_weight'))}",
                ]
            )
        )
        self.feature_surface_value.setText(requirement_text(surface))
        self.feature_heat_value.setText(requirement_text(heat))
        self.feature_part_type_value.setText(
            part_type_text(
                geometry,
                (parse_result.get("pdf_extract_result") or {})
                if isinstance(parse_result, dict)
                else {},
            )
        )

        self._render_pdf_fields(parse_result.get("pdf_extract_result"))
        self._render_holes(features.get("holes") or [])
        self._render_precision(features.get("precision_requirements") or [])

    def _clear_part_feature(self) -> None:
        for label in (
            self.feature_parser_source_value,
            self.feature_material_value,
            self.feature_material_confidence_value,
            self.feature_dimensions_value,
            self.feature_volume_value,
            self.feature_weight_value,
            self.feature_surface_value,
            self.feature_heat_value,
            self.feature_part_type_value,
        ):
            label.setText("-")
        self.pdf_fields_table.setRowCount(0)
        self.holes_table.setRowCount(0)
        self.precision_table.setRowCount(0)

    def _render_pdf_fields(self, pdf_result: dict[str, Any] | None) -> None:
        rows = pdf_field_rows(pdf_result)
        self.pdf_fields_table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            values = [
                item["label"],
                item["value"],
                confidence_text(item["confidence"]),
                label_for(PDF_EXTRACT_METHOD_LABELS, item["method"]),
                item["candidates"],
                item["evidence"],
            ]
            for column, value in enumerate(values):
                self.pdf_fields_table.setItem(row, column, table_item(value))

    def _render_holes(self, holes: list[dict[str, Any]]) -> None:
        self.holes_table.setRowCount(len(holes))
        for row, item in enumerate(holes):
            values = [
                label_for(HOLE_TYPE_LABELS, item.get("hole_type")),
                item.get("count"),
                item.get("diameter"),
                hole_depth_text(item),
                confidence_text(item.get("confidence")),
                evidence_summary(item.get("evidence")),
            ]
            for column, value in enumerate(values):
                self.holes_table.setItem(row, column, table_item(value))

    def _render_precision(self, requirements: list[dict[str, Any]]) -> None:
        self.precision_table.setRowCount(len(requirements))
        for row, item in enumerate(requirements):
            values = [
                item.get("raw_text"),
                item.get("standard_type"),
                confidence_text(item.get("confidence")),
                source_summary(item.get("source")),
            ]
            for column, value in enumerate(values):
                self.precision_table.setItem(row, column, table_item(value))

    def _render_risks(
        self,
        risks: list[dict[str, Any]],
        quote_result: dict[str, Any] | None = None,
    ) -> None:
        self.risk_table.setRowCount(len(risks))
        for row, item in enumerate(risks):
            confirmed = (
                risk_confirmed(quote_result, item)
                if quote_result
                else False
            )
            values = [
                item.get("code"),
                label_for(RISK_LEVEL_LABELS, item.get("level")),
                risk_message_text(item),
                yes_no(item.get("requires_review")),
                "已确认" if confirmed else "待确认" if item.get("requires_review") else "-",
                evidence_summary(item.get("evidence")),
            ]
            for column, value in enumerate(values):
                self.risk_table.setItem(row, column, table_item(value))

    def _render_quote_bundle(self, bundle: dict[str, Any] | None) -> None:
        if not bundle or not bundle.get("quote_result"):
            self._clear_quote()
            return

        self._render_process_route(bundle.get("process_route"))
        self._render_quantity_result(bundle.get("quantity_result"))
        self._render_quote(bundle.get("quote_result"))

    def _render_process_route(self, process_route: dict[str, Any] | None) -> None:
        self.current_process_route = process_route
        operations = (process_route or {}).get("operations") or []
        self.process_route_table.setRowCount(len(operations))
        for row, item in enumerate(operations):
            values = [
                item.get("operation_id"),
                item.get("sequence"),
                operation_label(item),
                item.get("operation_code"),
                trigger_reason_summary(item.get("trigger_reasons")),
                confidence_text(item.get("confidence")),
                yes_no(item.get("requires_review")),
                review_reason_text(item.get("review_reason")),
                route_text(item.get("explanation")),
            ]
            for column, value in enumerate(values):
                self.process_route_table.setItem(row, column, table_item(value))

    def _render_quantity_result(self, quantity_result: dict[str, Any] | None) -> None:
        self.current_quantity_result = quantity_result
        items = (quantity_result or {}).get("items") or []
        self.quantity_result_table.setRowCount(len(items))
        for row, item in enumerate(items):
            values = [
                item.get("quantity_id"),
                operation_text(item.get("operation_code")),
                label_for(QUANTITY_TYPE_LABELS, item.get("quantity_type")),
                item.get("value"),
                label_for(UNIT_LABELS, item.get("unit")),
                quantity_formula_text(item.get("formula")),
                basis_summary(item.get("basis")),
                yes_no(item.get("requires_review")),
                review_reason_text(item.get("review_reason")),
            ]
            for column, value in enumerate(values):
                self.quantity_result_table.setItem(row, column, table_item(value))

    def _render_quote(self, quote_result: dict[str, Any] | None) -> None:
        if not quote_result:
            self._clear_quote()
            return

        self.current_quote_result = quote_result
        self.current_quote_id = quote_result.get("quote_id")
        items = [
            item
            for item in quote_result.get("items") or []
            if item.get("item_type") != "risk_surcharge"
        ]
        self.quote_table.setRowCount(len(items))
        for row, item in enumerate(items):
            values = [
                item.get("item_id"),
                label_for(ITEM_TYPE_LABELS, item.get("item_type")),
                operation_text(item.get("operation_code")),
                item.get("quantity"),
                label_for(UNIT_LABELS, item.get("unit")),
                item.get("unit_price"),
                item.get("amount"),
                item.get("system_amount"),
                item.get("final_amount"),
                yes_no(item.get("requires_review")),
                quote_formula_source_text(item),
            ]
            for column, value in enumerate(values):
                self.quote_table.setItem(row, column, table_item(value))

        summary = quote_result.get("summary") or {}
        final_confirmed_amount = summary.get("final_confirmed_amount")

        self.quote_id_value.setText(str(quote_result.get("quote_id") or "-"))
        self.quote_status_value.setText(label_for(STATUS_LABELS, quote_result.get("status")))
        self.quote_currency_value.setText(
            label_for(CURRENCY_LABELS, quote_result.get("currency"))
        )
        self.quote_version_value.setText(str(quote_result.get("price_version") or "-"))
        self.quote_priced_at_value.setText(datetime_text(quote_result.get("priced_at")))
        self.quote_material_amount_value.setText(
            money_text(summary.get("material_amount"))
        )
        self.quote_process_amount_value.setText(
            money_text(summary.get("process_amount"))
        )
        self.quote_surface_amount_value.setText(
            money_text(summary.get("surface_treatment_amount"))
        )
        self.quote_management_fee_value.setText(
            money_text(summary.get("management_fee"))
        )
        self.quote_tax_amount_value.setText(money_text(summary.get("tax_amount")))
        self.quote_system_calculated_value.setText(
            money_text(summary.get("system_calculated_amount"))
        )
        self.quote_initial_value.setText(
            money_text(summary.get("system_initial_quote"))
        )
        self.quote_manual_adjustment_value.setText(
            money_text(summary.get("manual_adjustment_amount"))
        )
        self.quote_final_confirmed_input.setText(money_text(final_confirmed_amount))
        self.initial_quote_value.setText(money_text(summary.get("system_initial_quote")))
        self.final_quote_value.setText(money_text(final_confirmed_amount))
        self._render_risks(quote_result.get("risks") or [], quote_result)
        self._render_manual_overrides(quote_result.get("manual_overrides") or [])
        self._sync_quote_actions(quote_result)

    def _clear_quote(self) -> None:
        self.current_process_route = None
        self.current_quantity_result = None
        self.current_quote_result = None
        for label in (
            self.quote_id_value,
            self.quote_status_value,
            self.quote_currency_value,
            self.quote_version_value,
            self.quote_priced_at_value,
            self.quote_material_amount_value,
            self.quote_process_amount_value,
            self.quote_surface_amount_value,
            self.quote_management_fee_value,
            self.quote_tax_amount_value,
            self.quote_system_calculated_value,
            self.quote_initial_value,
            self.quote_manual_adjustment_value,
        ):
            label.setText("-")
        self.quote_final_confirmed_input.setText("-")
        self.process_route_table.setRowCount(0)
        self.quantity_result_table.setRowCount(0)
        self.quote_table.setRowCount(0)
        self.manual_override_table.setRowCount(0)
        self.initial_quote_value.setText("-")
        self.final_quote_value.setText("-")
        self._sync_quote_actions(None)

    def _sync_quote_actions(self, quote_result: dict[str, Any] | None) -> None:
        if not hasattr(self, "override_item_button"):
            return

        has_quote = bool(quote_result)
        status = (quote_result or {}).get("status")
        readonly = status in {"confirmed", "voided"}
        blocking = bool(blocking_review_risks(quote_result or {}))

        can_edit = has_quote and not readonly
        self.override_item_button.setEnabled(can_edit)
        self.quantity_override_button.setEnabled(can_edit)
        if hasattr(self, "confirm_risk_button"):
            self.confirm_risk_button.setEnabled(can_edit)
        self.final_quote_button.setEnabled(can_edit)
        self.add_operation_button.setEnabled(can_edit)
        self.edit_operation_button.setEnabled(can_edit)
        self.delete_operation_button.setEnabled(can_edit)
        self.reorder_operation_button.setEnabled(can_edit)
        self.confirm_quote_button.setEnabled(can_edit and not blocking)
        self.confirm_quote_button.setToolTip(
            "存在未确认的阻断风险，不能确认报价。"
            if has_quote and blocking
            else ""
        )
        if hasattr(self, "export_button"):
            self.export_button.setEnabled(has_quote)

    def _render_manual_overrides(self, overrides: list[dict[str, Any]]) -> None:
        self.manual_override_table.setRowCount(len(overrides))
        for row, item in enumerate(overrides):
            values = [
                join_present(
                    [
                        label_for(TARGET_TYPE_LABELS, item.get("target_type")),
                        item.get("target_id"),
                    ],
                    " / ",
                ),
                label_for(FIELD_LABELS, item.get("field")),
                override_value_text(item.get("old_value")),
                override_value_text(item.get("new_value")),
                item.get("reason"),
                item.get("operator_id"),
                datetime_text(item.get("created_at")),
            ]
            for column, value in enumerate(values):
                self.manual_override_table.setItem(row, column, table_item(value))

    def _render_ai_outputs(self, outputs: list[dict[str, Any]]) -> None:
        unavailable_outputs = [
            item for item in outputs if ai_output_unavailable(item)
        ]
        visible_outputs = [
            item for item in outputs if not ai_output_unavailable(item)
        ]
        self.ai_status_label.setText(
            ai_status_text(
                visible_count=len(visible_outputs),
                unavailable_outputs=unavailable_outputs,
            )
        )
        self.ai_output_table.setRowCount(len(visible_outputs))
        for row, item in enumerate(visible_outputs):
            values = [
                label_for(AI_INPUT_TYPE_LABELS, item.get("input_type")),
                label_for(AI_OUTPUT_TYPE_LABELS, item.get("output_type")),
                ai_output_summary(item),
                confidence_text(item.get("confidence")),
                item.get("model_name"),
                item.get("prompt_version"),
                datetime_text(item.get("created_at")),
                evidence_summary(item.get("evidence")),
            ]
            for column, value in enumerate(values):
                self.ai_output_table.setItem(row, column, table_item(value))

    def _selected_file_type(self) -> str:
        return str(self.file_type_combo.currentData() or "pdf")

    def _selected_parse_file_id(self, combo: QComboBox) -> str | None:
        value = combo.currentData()
        return str(value) if value else None

    def _selected_parse_file_ids(self) -> set[str]:
        file_ids: set[str] = set()
        pdf_file_id = self._effective_parse_file_id(
            "pdf",
            self.parse_pdf_checkbox,
            self.parse_pdf_combo,
        )
        step_file_id = self._effective_parse_file_id(
            "step",
            self.parse_step_checkbox,
            self.parse_step_combo,
        )
        if pdf_file_id:
            file_ids.add(pdf_file_id)
        if step_file_id:
            file_ids.add(step_file_id)
        return file_ids

    def _effective_parse_file_id(
        self,
        file_type: str,
        checkbox: QCheckBox,
        combo: QComboBox,
    ) -> str | None:
        if not checkbox.isChecked():
            return None

        selected_file_id = self._selected_parse_file_id(combo)
        if selected_file_id:
            return selected_file_id

        latest_file = latest_uploaded_file(self._files, file_type)
        return str(latest_file["file_id"]) if latest_file else None

    def _refresh_file_choice_columns(self) -> None:
        if not hasattr(self, "files_table"):
            return

        selected_file_ids = self._selected_parse_file_ids()
        for row, item in enumerate(self._files):
            if row >= self.files_table.rowCount():
                continue
            file_id = item.get("file_id")
            self.files_table.setItem(
                row,
                6,
                table_item(yes_no(file_id in selected_file_ids)),
            )
            self.files_table.setItem(
                row,
                7,
                table_item(yes_no(file_id in self._parse_result_file_ids)),
            )

    def _populate_parse_file_combos(self, files: list[dict[str, Any]]) -> None:
        self._populate_parse_file_combo(self.parse_pdf_combo, files, "pdf")
        self._populate_parse_file_combo(self.parse_step_combo, files, "step")
        self._update_parse_selection_hint()

    def _populate_parse_file_combo(
        self,
        combo: QComboBox,
        files: list[dict[str, Any]],
        file_type: str,
    ) -> None:
        current_file_id = combo.currentData()
        combo.clear()
        combo.addItem("自动选择最新有效文件", None)

        for item in files:
            if item.get("file_type") != file_type or item.get("status") != "uploaded":
                continue
            label = (
                f"v{item.get('version')} "
                f"{item.get('filename')} "
                f"({item.get('file_id')})"
            )
            combo.addItem(label, item.get("file_id"))

        if current_file_id:
            index = combo.findData(current_file_id)
            if index >= 0:
                combo.setCurrentIndex(index)

    def sync_parse_selection_from_file_table(self) -> None:
        row = self.files_table.currentRow()
        if row < 0 or row >= len(self._files):
            return

        file_record = self._files[row]
        file_type = file_record.get("file_type")
        if file_type not in {"pdf", "step"}:
            self.statusBar().showMessage("附件不参与解析。")
            return

        if file_record.get("status") != "uploaded":
            self.statusBar().showMessage("失效或删除的文件不能作为解析来源。")
            return

        combo = self.parse_pdf_combo if file_type == "pdf" else self.parse_step_combo
        index = combo.findData(file_record.get("file_id"))
        if index < 0:
            return

        combo.setCurrentIndex(index)
        self._update_parse_selection_hint()
        self.statusBar().showMessage(
            f"已选择 {FILE_TYPE_LABELS[file_type]} v{file_record.get('version')} "
            "作为解析来源。"
        )

    def _update_parse_selection_hint(self, _index: int | None = None) -> None:
        if not hasattr(self, "parse_selection_hint"):
            return

        pdf_text = self._parse_selection_text(
            "pdf",
            self.parse_pdf_checkbox,
            self.parse_pdf_combo,
        )
        step_text = self._parse_selection_text(
            "step",
            self.parse_step_checkbox,
            self.parse_step_combo,
        )
        self.parse_selection_hint.setText(
            f"将解析：PDF={pdf_text}；STEP={step_text}。勾选的输入会融合成零件特征。"
        )
        self._refresh_file_choice_columns()

    def _parse_selection_text(
        self,
        file_type: str,
        checkbox: QCheckBox,
        combo: QComboBox,
    ) -> str:
        if not checkbox.isChecked():
            return "不解析"

        selected_text = combo.currentText()
        if combo.currentData():
            return selected_text

        latest_file = latest_uploaded_file(self._files, file_type)
        if latest_file:
            return (
                "自动最新："
                f"v{latest_file.get('version')} "
                f"{latest_file.get('filename')} "
                f"({latest_file.get('file_id')})"
            )
        return "自动最新：当前无有效文件"

    def _selected_file_id_or_warn(self) -> str | None:
        row = self.files_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "请选择文件", "请先在文件表中选中一条文件记录。")
            return None

        file_id_cell = self.files_table.item(row, 0)
        if file_id_cell is None or not file_id_cell.text().strip():
            QMessageBox.warning(self, "请选择文件", "所选行没有文件ID。")
            return None

        return file_id_cell.text().strip()

    def _task_id(self) -> str:
        task_id = self.task_id_input.text().strip()
        if not task_id:
            raise ApiError("TASK_ID_REQUIRED", "任务ID不能为空。")
        return task_id

    def _run_action(self, label: str, action: Callable[[], None]) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.statusBar().showMessage(label)
        try:
            action()
        except ApiError as exc:
            QMessageBox.warning(self, label_for(ERROR_CODE_LABELS, exc.code), exc.message)
            self.statusBar().showMessage(exc.message)
        except Exception as exc:
            QMessageBox.critical(self, "错误", str(exc))
            self.statusBar().showMessage(str(exc))
        else:
            if self.statusBar().currentMessage() == label:
                self.statusBar().showMessage("完成")
        finally:
            QApplication.restoreOverrideCursor()


class ManualOverrideDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        *,
        target_type: str,
        target_id: str,
        field_options: list[str],
        old_values: dict[str, Any],
        operator_id: str,
    ) -> None:
        super().__init__(parent)
        self.target_type = target_type
        self.target_id = target_id
        self.old_values = old_values

        self.setWindowTitle("人工修改")
        self.resize(520, 320)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.target_type_input = QLineEdit(label_for(TARGET_TYPE_LABELS, target_type))
        self.target_type_input.setReadOnly(True)
        self.target_id_input = QLineEdit(target_id)
        self.target_id_input.setReadOnly(True)
        self.field_combo = QComboBox()
        for field in field_options:
            self.field_combo.addItem(label_for(FIELD_LABELS, field), field)
        self.old_value_input = QLineEdit()
        self.old_value_input.setReadOnly(True)
        self.new_value_input = QLineEdit()
        self.reason_input = QPlainTextEdit()
        self.reason_input.setFixedHeight(84)
        self.operator_input = QLineEdit(operator_id)

        self.field_combo.currentIndexChanged.connect(self._sync_old_value)
        self._sync_old_value()

        form.addRow("修改对象", self.target_type_input)
        form.addRow("对象ID", self.target_id_input)
        form.addRow("字段", self.field_combo)
        form.addRow("旧值", self.old_value_input)
        form.addRow("新值", self.new_value_input)
        form.addRow("原因", self.reason_input)
        form.addRow("操作人", self.operator_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setText("确定")
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button:
            cancel_button.setText("取消")
        layout.addWidget(buttons)

    def _sync_old_value(self, _index: int | None = None) -> None:
        field = self._current_field()
        self.old_value_input.setText(override_value_text(self.old_values.get(field)))

    def _current_field(self) -> str:
        return str(self.field_combo.currentData() or "")

    def accept(self) -> None:
        if not self.new_value_input.text().strip():
            QMessageBox.warning(self, "新值必填", "请填写新值。")
            return
        if not self.reason_input.toPlainText().strip():
            QMessageBox.warning(self, "原因必填", "请填写修改原因。")
            return
        if not self.operator_input.text().strip():
            QMessageBox.warning(self, "操作人必填", "请填写操作人。")
            return
        super().accept()

    def payload(self) -> dict[str, Any]:
        field = self._current_field()
        return {
            "target_type": self.target_type,
            "target_id": self.target_id,
            "field": field,
            "old_value": self.old_values.get(field),
            "new_value": self.new_value_input.text().strip(),
            "reason": self.reason_input.toPlainText().strip(),
            "operator_id": self.operator_input.text().strip(),
        }


class OperationDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        *,
        operation: dict[str, Any] | None,
        max_sequence: int,
        operator_id: str,
    ) -> None:
        super().__init__(parent)
        self.operation = operation

        self.setWindowTitle("修改工序" if operation else "新增工序")
        self.resize(560, 360)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.operation_combo = QComboBox()
        for operation_code, label in OPERATION_CODE_LABELS.items():
            self.operation_combo.addItem(f"{label} / {operation_code}", operation_code)

        self.sequence_input = QSpinBox()
        self.sequence_input.setRange(1, max(1, max_sequence))
        self.sequence_input.setValue(
            int(operation.get("sequence") or 1) if operation else max(1, max_sequence)
        )
        self.explanation_input = QPlainTextEdit()
        self.explanation_input.setFixedHeight(82)
        self.reason_input = QPlainTextEdit()
        self.reason_input.setFixedHeight(82)
        self.operator_input = QLineEdit(operator_id)

        if operation:
            operation_id_input = QLineEdit(str(operation.get("operation_id") or ""))
            operation_id_input.setReadOnly(True)
            form.addRow("工序ID", operation_id_input)
            index = self.operation_combo.findData(operation.get("operation_code"))
            if index >= 0:
                self.operation_combo.setCurrentIndex(index)
            self.sequence_input.setEnabled(False)
            self.explanation_input.setPlainText(str(operation.get("explanation") or ""))

        form.addRow("工序", self.operation_combo)
        form.addRow("插入顺序" if not operation else "当前顺序", self.sequence_input)
        form.addRow("说明", self.explanation_input)
        form.addRow("原因", self.reason_input)
        form.addRow("操作人", self.operator_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setText("保存")
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button:
            cancel_button.setText("取消")
        layout.addWidget(buttons)

    def accept(self) -> None:
        if not self._operation_code():
            QMessageBox.warning(self, "工序必填", "请选择工序。")
            return
        if not self.reason_input.toPlainText().strip():
            QMessageBox.warning(self, "原因必填", "请填写修改原因。")
            return
        if not self.operator_input.text().strip():
            QMessageBox.warning(self, "操作人必填", "请填写操作人。")
            return
        if self.operation:
            explanation = self.explanation_input.toPlainText().strip()
            if (
                self._operation_code() == self.operation.get("operation_code")
                and explanation == str(self.operation.get("explanation") or "")
            ):
                QMessageBox.warning(self, "没有修改", "请修改工序或说明后再保存。")
                return
        super().accept()

    def payload(self) -> dict[str, Any]:
        operation_code = self._operation_code()
        explanation = self.explanation_input.toPlainText().strip()
        if self.operation is None:
            return {
                "target_type": "operation",
                "target_id": "new_operation",
                "field": "add",
                "old_value": None,
                "new_value": {
                    "operation_code": operation_code,
                    "sequence": self.sequence_input.value(),
                    "explanation": explanation
                    or label_for(OPERATION_CODE_LABELS, operation_code),
                },
                "reason": self.reason_input.toPlainText().strip(),
                "operator_id": self.operator_input.text().strip(),
            }

        return {
            "target_type": "operation",
            "target_id": str(self.operation.get("operation_id") or ""),
            "field": "operation",
            "old_value": operation_summary(self.operation),
            "new_value": {
                "operation_code": operation_code,
                "explanation": explanation
                or str(self.operation.get("explanation") or ""),
            },
            "reason": self.reason_input.toPlainText().strip(),
            "operator_id": self.operator_input.text().strip(),
        }

    def _operation_code(self) -> str:
        return str(self.operation_combo.currentData() or "")


class DeleteOperationDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        *,
        operation: dict[str, Any],
        operator_id: str,
    ) -> None:
        super().__init__(parent)
        self.operation = operation
        self.setWindowTitle("删除工序")
        self.resize(520, 260)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.operation_input = QLineEdit(operation_summary(operation))
        self.operation_input.setReadOnly(True)
        self.reason_input = QPlainTextEdit()
        self.reason_input.setFixedHeight(84)
        self.operator_input = QLineEdit(operator_id)

        form.addRow("工序", self.operation_input)
        form.addRow("原因", self.reason_input)
        form.addRow("操作人", self.operator_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setText("删除")
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button:
            cancel_button.setText("取消")
        layout.addWidget(buttons)

    def accept(self) -> None:
        if not self.reason_input.toPlainText().strip():
            QMessageBox.warning(self, "原因必填", "请填写删除原因。")
            return
        if not self.operator_input.text().strip():
            QMessageBox.warning(self, "操作人必填", "请填写操作人。")
            return
        super().accept()

    def payload(self) -> dict[str, Any]:
        return {
            "target_type": "operation",
            "target_id": str(self.operation.get("operation_id") or ""),
            "field": "delete",
            "old_value": operation_summary(self.operation),
            "new_value": None,
            "reason": self.reason_input.toPlainText().strip(),
            "operator_id": self.operator_input.text().strip(),
        }


class OperationSequenceDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        *,
        operation: dict[str, Any],
        max_sequence: int,
        operator_id: str,
    ) -> None:
        super().__init__(parent)
        self.operation = operation
        self.old_sequence = int(operation.get("sequence") or 1)
        self.setWindowTitle("调整工序顺序")
        self.resize(520, 280)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.operation_input = QLineEdit(operation_summary(operation))
        self.operation_input.setReadOnly(True)
        self.sequence_input = QSpinBox()
        self.sequence_input.setRange(1, max(1, max_sequence))
        self.sequence_input.setValue(self.old_sequence)
        self.reason_input = QPlainTextEdit()
        self.reason_input.setFixedHeight(84)
        self.operator_input = QLineEdit(operator_id)

        form.addRow("工序", self.operation_input)
        form.addRow("新顺序", self.sequence_input)
        form.addRow("原因", self.reason_input)
        form.addRow("操作人", self.operator_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setText("保存")
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button:
            cancel_button.setText("取消")
        layout.addWidget(buttons)

    def accept(self) -> None:
        if self.sequence_input.value() == self.old_sequence:
            QMessageBox.warning(self, "顺序未变化", "请选择新的工序顺序。")
            return
        if not self.reason_input.toPlainText().strip():
            QMessageBox.warning(self, "原因必填", "请填写调整原因。")
            return
        if not self.operator_input.text().strip():
            QMessageBox.warning(self, "操作人必填", "请填写操作人。")
            return
        super().accept()

    def payload(self) -> dict[str, Any]:
        return {
            "target_type": "operation",
            "target_id": str(self.operation.get("operation_id") or ""),
            "field": "sequence",
            "old_value": self.old_sequence,
            "new_value": self.sequence_input.value(),
            "reason": self.reason_input.toPlainText().strip(),
            "operator_id": self.operator_input.text().strip(),
        }


class ConfirmQuoteDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        *,
        default_amount: float,
        operator_id: str,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("确认报价")
        self.resize(460, 260)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.amount_input = QLineEdit(f"{float(default_amount):.2f}")
        self.operator_input = QLineEdit(operator_id)
        self.note_input = QPlainTextEdit()
        self.note_input.setFixedHeight(90)

        form.addRow("最终确认价", self.amount_input)
        form.addRow("确认人", self.operator_input)
        form.addRow("确认说明", self.note_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setText("确认")
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button:
            cancel_button.setText("取消")
        layout.addWidget(buttons)

    def accept(self) -> None:
        try:
            amount = float(self.amount_input.text().strip())
        except ValueError:
            QMessageBox.warning(self, "金额不合法", "请填写合法的最终确认价。")
            return
        if amount < 0:
            QMessageBox.warning(self, "金额不合法", "最终确认价不能小于 0。")
            return
        if not self.operator_input.text().strip():
            QMessageBox.warning(self, "确认人必填", "请填写确认人。")
            return
        if not self.note_input.toPlainText().strip():
            QMessageBox.warning(self, "确认说明必填", "请填写确认说明。")
            return
        super().accept()

    def payload(self) -> dict[str, Any]:
        return {
            "confirmed_total_amount": float(self.amount_input.text().strip()),
            "confirmed_by": self.operator_input.text().strip(),
            "confirm_note": self.note_input.toPlainText().strip(),
        }


class RiskConfirmDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        *,
        risk_code: str,
        risk_message: str,
        operator_id: str,
    ) -> None:
        super().__init__(parent)
        self.risk_code = risk_code
        self.setWindowTitle("确认风险")
        self.resize(520, 280)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.risk_code_input = QLineEdit(risk_code)
        self.risk_code_input.setReadOnly(True)
        self.risk_message_input = QPlainTextEdit(risk_message)
        self.risk_message_input.setReadOnly(True)
        self.risk_message_input.setFixedHeight(70)
        self.reason_input = QPlainTextEdit()
        self.reason_input.setFixedHeight(80)
        self.operator_input = QLineEdit(operator_id)

        form.addRow("风险编码", self.risk_code_input)
        form.addRow("风险说明", self.risk_message_input)
        form.addRow("确认说明", self.reason_input)
        form.addRow("操作人", self.operator_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setText("确认风险")
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button:
            cancel_button.setText("取消")
        layout.addWidget(buttons)

    def accept(self) -> None:
        if not self.reason_input.toPlainText().strip():
            QMessageBox.warning(self, "确认说明必填", "请填写风险确认说明。")
            return
        if not self.operator_input.text().strip():
            QMessageBox.warning(self, "操作人必填", "请填写操作人。")
            return
        super().accept()

    def payload(self) -> dict[str, Any]:
        return {
            "target_type": "risk",
            "target_id": self.risk_code,
            "field": "confirmed",
            "old_value": False,
            "new_value": True,
            "reason": self.reason_input.toPlainText().strip(),
            "operator_id": self.operator_input.text().strip(),
        }


class CreateTaskDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("新建报价任务")
        self.resize(460, 220)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.customer_name_input = QLineEdit()
        self.part_name_input = QLineEdit()
        self.part_no_input = QLineEdit()
        self.quantity_input = QSpinBox()
        self.quantity_input.setRange(1, 1_000_000)
        self.quantity_input.setValue(1)
        self.task_id_input = QLineEdit()
        self.task_id_input.setPlaceholderText("留空则自动生成")

        form.addRow("客户名称", self.customer_name_input)
        form.addRow("零件名称", self.part_name_input)
        form.addRow("图号/零件号", self.part_no_input)
        form.addRow("数量", self.quantity_input)
        form.addRow("任务ID", self.task_id_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setText("创建")
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button:
            cancel_button.setText("取消")
        layout.addWidget(buttons)

    def accept(self) -> None:
        if not self.customer_name_input.text().strip():
            QMessageBox.warning(self, "客户名称必填", "请填写客户名称。")
            return
        if not self.part_name_input.text().strip():
            QMessageBox.warning(self, "零件名称必填", "请填写零件名称。")
            return
        super().accept()

    def payload(self) -> dict[str, Any]:
        task_id = self.task_id_input.text().strip()
        payload: dict[str, Any] = {
            "customer_name": self.customer_name_input.text().strip(),
            "part_name": self.part_name_input.text().strip(),
            "part_no": self.part_no_input.text().strip(),
            "quantity": self.quantity_input.value(),
        }
        if task_id:
            payload["task_id"] = task_id
        return payload


def table_item(value: Any) -> QTableWidgetItem:
    text = "-" if value is None else str(value)
    item = QTableWidgetItem(text)
    item.setToolTip(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def find_quote_item(
    quote_result: dict[str, Any],
    item_id: str,
) -> dict[str, Any] | None:
    for item in quote_result.get("items") or []:
        if item.get("item_id") == item_id:
            return item
    return None


def find_quantity_item(
    quantity_result: dict[str, Any],
    quantity_id: str,
) -> dict[str, Any] | None:
    for item in quantity_result.get("items") or []:
        if item.get("quantity_id") == quantity_id:
            return item
    return None


def find_operation(
    process_route: dict[str, Any],
    operation_id: str,
) -> dict[str, Any] | None:
    for item in process_route.get("operations") or []:
        if item.get("operation_id") == operation_id:
            return item
    return None


def find_risk(
    quote_result: dict[str, Any],
    risk_code: str,
) -> dict[str, Any] | None:
    for risk in quote_result.get("risks") or []:
        if str(risk.get("code") or "") == risk_code:
            return risk
    return None


def blocking_review_risks(quote_result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        risk
        for risk in quote_result.get("risks") or []
        if isinstance(risk, dict)
        and risk.get("level") == "blocking"
        and risk.get("requires_review")
        and not risk_confirmed(quote_result, risk)
    ]


def risk_confirmed(quote_result: dict[str, Any], risk: dict[str, Any]) -> bool:
    risk_code = str(risk.get("code") or "")
    for override in quote_result.get("manual_overrides") or []:
        if override.get("target_type") != "risk":
            continue
        if str(override.get("target_id") or "") != risk_code:
            continue
        if override.get("field") != "confirmed":
            continue
        if truthy_override_value(override.get("new_value")):
            return True
    return False


def truthy_override_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "是"}
    return bool(value)


def first_number(*values: Any) -> float:
    for value in values:
        if isinstance(value, bool) or value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def override_value_text(value: Any) -> str:
    if value is None:
        return "-"
    return str(value)


def label_for(labels: dict[str, str], value: Any) -> str:
    if value in (None, ""):
        return "-"
    text = str(value)
    return labels.get(text, text)


def yes_no(value: Any) -> str:
    return "是" if bool(value) else "否"


def operation_text(operation_code: Any) -> str:
    if operation_code in (None, ""):
        return "-"
    return join_present(
        [
            label_for(OPERATION_CODE_LABELS, operation_code),
            str(operation_code),
        ],
        " / ",
    )


def operation_label(operation: dict[str, Any] | None) -> str:
    if not isinstance(operation, dict):
        return "-"
    operation_code = operation.get("operation_code")
    if operation_code == "unmapped_operation":
        return route_text(operation.get("operation_name"))
    label = label_for(OPERATION_CODE_LABELS, operation_code)
    if label != "-":
        return label
    return route_text(operation.get("operation_name"))


def route_text(value: Any) -> str:
    if value in (None, ""):
        return "-"
    text = str(value).strip()
    if not text:
        return "-"
    if text in ROUTE_TEXT_LABELS:
        return ROUTE_TEXT_LABELS[text]

    counter_patterns = (
        (r"Detected through holes:\s*(\d+)\.", "检测到通孔：{} 个"),
        (r"Detected counterbores:\s*(\d+)\.", "检测到沉孔：{} 个"),
        (r"Detected thread hole candidates:\s*(\d+)\.", "检测到螺纹孔候选：{} 个"),
        (r"Detected precision hole candidates:\s*(\d+)\.", "检测到精孔候选：{} 个"),
    )
    for pattern, template in counter_patterns:
        match = re.fullmatch(pattern, text)
        if match:
            return template.format(match.group(1))

    surface_match = re.fullmatch(r"Detected surface treatment:\s*(.+)\.", text)
    if surface_match:
        return f"检测到表面处理：{surface_match.group(1)}"

    heat_match = re.fullmatch(r"Detected heat treatment:\s*(.+)\.", text)
    if heat_match:
        return f"检测到热处理：{heat_match.group(1)}"

    roughness_match = re.fullmatch(r"Detected roughness requirements:\s*(\d+)\.", text)
    if roughness_match:
        return f"检测到粗糙度要求：{roughness_match.group(1)} 项"

    return text


def risk_message_text(risk: dict[str, Any]) -> str:
    code = str(risk.get("code") or "")
    message = compact_text(risk.get("message"), limit=160)
    operation_code = risk_operation_code(risk)

    if code == "MISSING_PRICE_OR_QUANTITY" and operation_code:
        operation = label_for(OPERATION_CODE_LABELS, operation_code)
        return f"{operation}缺少单价或工程量，需补录后复核报价。"

    if code == "LOW_CONFIDENCE_FIELD":
        field_key = pdf_risk_field_key(message)
        field_label = label_for(PDF_FIELD_LABELS, field_key) if field_key else ""
        return (
            f"PDF 字段“{field_label}”抽取不稳定，需人工核对。"
            if field_label and field_label != "-"
            else RISK_MESSAGE_LABELS[code]
        )

    if code == "FIELD_CONFLICT":
        field_key = pdf_risk_field_key(message)
        field_label = label_for(PDF_FIELD_LABELS, field_key) if field_key else ""
        return (
            f"PDF 字段“{field_label}”存在多个相近候选，需人工确认最终取值。"
            if field_label and field_label != "-"
            else RISK_MESSAGE_LABELS[code]
        )

    translated_message = translated_risk_message(message)
    if translated_message != message:
        return translated_message

    if code in RISK_MESSAGE_LABELS and not has_cjk(message):
        return RISK_MESSAGE_LABELS[code]
    if message:
        return message
    return RISK_MESSAGE_LABELS.get(code, "-")


def translated_risk_message(message: str) -> str:
    if message in ("", "-"):
        return message
    if message in RISK_MESSAGE_TEXT_LABELS:
        return RISK_MESSAGE_TEXT_LABELS[message]
    for pattern, formatter in RISK_MESSAGE_PATTERNS:
        match = pattern.fullmatch(message)
        if match:
            return formatter(match)
    return message


def part_type_label(value: Any) -> str:
    text = str(value or "")
    return label_for(PART_TYPE_LABELS, text)


def pdf_risk_field_key(message: str) -> str:
    prefixes = (
        "PDF 字段置信度低于阈值：",
        "PDF text layer 未能稳定抽取字段：",
        "PDF 字段存在多个相近候选：",
    )
    for prefix in prefixes:
        if prefix in message:
            return message.split(prefix, 1)[1].split("；", 1)[0].strip()
    if "：" in message:
        return message.rsplit("：", 1)[-1].split("；", 1)[0].strip()
    return ""


def risk_operation_code(risk: dict[str, Any]) -> str | None:
    evidence = risk.get("evidence") or []
    if isinstance(evidence, dict):
        evidence = [evidence]

    for item in evidence:
        if not isinstance(item, dict):
            continue
        rule_code = str(item.get("rule_code") or "")
        if rule_code.startswith("MISSING_PRICE_OR_QUANTITY:"):
            return rule_code.split(":", 1)[1]

    message = str(risk.get("message") or "")
    marker = " is missing price or quantity"
    if marker in message:
        return message.split(marker, 1)[0].strip()
    return None


def operation_summary(operation: dict[str, Any]) -> str:
    return join_present(
        [
            f"#{operation.get('sequence')}",
            operation_text(operation.get("operation_code")),
            operation.get("operation_id"),
        ],
        " / ",
    )


def parse_file_ids(parse_result: dict[str, Any] | None) -> set[str]:
    file_ids: set[str] = set()
    for key in ("pdf_extract_result", "step_feature_result"):
        result = (parse_result or {}).get(key)
        if isinstance(result, dict) and result.get("file_id"):
            file_ids.add(str(result["file_id"]))
    return file_ids


def pdf_field_rows(pdf_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(pdf_result, dict):
        return []

    details = pdf_result.get("field_details") or {}
    confidences = pdf_result.get("field_confidence") or {}
    methods = pdf_result.get("extract_method") or {}
    evidences = pdf_result.get("field_evidence") or {}
    field_candidates = pdf_result.get("field_candidates") or {}
    rows = []

    for field in PDF_REQUIRED_FIELDS:
        detail = details.get(field) if isinstance(details, dict) else None
        value = (
            detail.get("value")
            if isinstance(detail, dict) and "value" in detail
            else pdf_result.get(field)
        )
        confidence = (
            detail.get("confidence")
            if isinstance(detail, dict) and "confidence" in detail
            else confidences.get(field)
        )
        method = (
            detail.get("extract_method")
            if isinstance(detail, dict)
            else methods.get(field)
        )
        evidence = (
            detail.get("evidence")
            if isinstance(detail, dict)
            else evidences.get(field)
        )
        candidates = (
            detail.get("candidates")
            if isinstance(detail, dict) and "candidates" in detail
            else field_candidates.get(field)
            if isinstance(field_candidates, dict)
            else []
        )

        rows.append(
            {
                "label": PDF_FIELD_LABELS.get(field, field),
                "value": pdf_value_text(value),
                "confidence": confidence,
                "method": method or "-",
                "candidates": pdf_candidates_text(candidates),
                "evidence": evidence_summary(
                    evidence if isinstance(evidence, list) else [evidence]
                    if evidence
                    else []
                ),
            }
        )

    return rows


def pdf_value_text(value: Any) -> str:
    if value in (None, ""):
        return "-"
    if isinstance(value, list):
        return "\n".join(str(item) for item in value) if value else "-"
    return str(value)


def pdf_candidates_text(candidates: Any) -> str:
    if not isinstance(candidates, list) or not candidates:
        return "-"

    parts = []
    for candidate in candidates[:3]:
        if not isinstance(candidate, dict):
            continue
        value = candidate.get("value", candidate.get("candidate_value"))
        if value in (None, ""):
            continue
        method = candidate.get("extract_method") or candidate.get("source") or "-"
        confidence = confidence_text(candidate.get("confidence"))
        parts.append(f"{compact_text(value, limit=36)}（置信度 {confidence} / {method}）")

    if not parts:
        return "-"

    extra = len(candidates) - len(parts)
    if extra > 0:
        parts.append(f"另有 {extra} 项")
    return "；".join(parts)


def parser_source_text(
    parse_result: dict[str, Any] | None,
    files: list[dict[str, Any]] | None = None,
) -> str:
    if not parse_result:
        return "-"

    parts = []
    pdf_result = parse_result.get("pdf_extract_result")
    step_result = parse_result.get("step_feature_result")
    file_names = file_name_lookup(files or [])

    if isinstance(pdf_result, dict):
        parts.append(f"PDF：{source_file_text(pdf_result, file_names)}")
    else:
        parts.append("PDF：未解析")

    if isinstance(step_result, dict):
        parts.append(f"STEP：{source_file_text(step_result, file_names)}")
    else:
        parts.append("STEP：未解析")

    fallback_codes = [
        risk.get("code")
        for risk in parse_result.get("risks") or []
        if risk.get("code") == "PARSER_FALLBACK_USED"
    ]
    if fallback_codes:
        parts.append("注意：历史记录包含备用解析结果")

    return "；".join(parts)


def file_name_lookup(files: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(item["file_id"]): str(item.get("filename") or "")
        for item in files
        if isinstance(item, dict) and item.get("file_id")
    }


def source_file_text(
    result: dict[str, Any],
    file_names: dict[str, str],
) -> str:
    file_id = result.get("file_id")
    file_name = (
        result.get("file_name")
        or result.get("filename")
        or file_names.get(str(file_id))
    )
    return join_present([file_id, file_name], " / ")


def latest_uploaded_file(
    files: list[dict[str, Any]],
    file_type: str,
) -> dict[str, Any] | None:
    candidates = [
        item
        for item in files
        if item.get("file_type") == file_type and item.get("status") == "uploaded"
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: int(item.get("version") or 0))


def task_combo_label(task: dict[str, Any]) -> str:
    return join_present(
        [
            task.get("task_id"),
            task.get("customer_name"),
            task.get("part_name"),
            label_for(STATUS_LABELS, task.get("status")),
        ],
        " | ",
    )


def value_label() -> QLabel:
    label = QLabel("-")
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def configure_table(table: QTableWidget) -> None:
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)


def join_present(values: list[Any], separator: str = " | ") -> str:
    parts = [str(value) for value in values if value not in (None, "")]
    return separator.join(parts) if parts else "-"


def bounding_box_text(bounding_box: dict[str, Any] | None) -> str:
    if not bounding_box:
        return "-"

    length = bounding_box.get("length")
    width = bounding_box.get("width")
    height = bounding_box.get("height")
    unit = bounding_box.get("unit") or ""
    if length is None or width is None or height is None:
        return "-"
    return f"长 {length} x 宽 {width} x 高 {height} {unit}".strip()


def part_type_text(geometry: dict[str, Any], pdf_result: dict[str, Any] | None = None) -> str:
    step_type = geometry.get("step_part_type")
    if step_type:
        return join_present(
            [
                step_part_type_text(geometry),
                pdf_category_text(geometry, pdf_result),
            ]
        )

    legacy_part_type = geometry.get("part_type")
    if legacy_part_type:
        return join_present(
            [
                f"STEP类型：{label_for(PART_TYPE_LABELS, legacy_part_type)}（{confidence_text(geometry.get('part_type_confidence'))}）",
                pdf_category_text(geometry, pdf_result),
            ]
        )

    explicit_pdf_type = geometry.get("pdf_part_type") or geometry.get("pdf_part_type_raw")
    if explicit_pdf_type:
        return join_present(
            [
                f"PDF类型：{explicit_pdf_type}",
                f"置信度 {confidence_text(geometry.get('pdf_part_type_confidence'))}",
            ]
        )

    pdf_category = geometry.get("pdf_part_category") or {}
    if isinstance(pdf_category, dict) and pdf_category.get("category_name"):
        return join_present(
            [
                f"PDF类型：{pdf_category.get('category_name')}",
                f"置信度 {confidence_text(pdf_category.get('confidence'))}",
            ]
        )

    raw_part_type = (pdf_result or {}).get("part_type_raw")
    if raw_part_type:
        return join_present(
            [
                f"PDF类型：{raw_part_type}",
                f"置信度 {confidence_text((pdf_result or {}).get('field_confidence', {}).get('part_type_raw'))}",
            ]
        )

    return "-"


def step_part_type_text(geometry: dict[str, Any]) -> str:
    step_type = geometry.get("step_part_type")
    specific_type = geometry.get("step_part_type_specific")
    label = label_for(PART_TYPE_LABELS, step_type)
    if specific_type:
        label = f"{label} / {specific_type}"
    return f"STEP类型：{label}（{confidence_text(geometry.get('step_part_type_confidence'))}）"


def pdf_category_text(geometry: dict[str, Any], pdf_result: dict[str, Any] | None = None) -> str | None:
    explicit_pdf_type = geometry.get("pdf_part_type") or geometry.get("pdf_part_type_raw")
    if explicit_pdf_type:
        return f"PDF类型：{explicit_pdf_type}"

    pdf_category = geometry.get("pdf_part_category") or {}
    if isinstance(pdf_category, dict) and pdf_category.get("category_name"):
        return f"PDF类型：{pdf_category.get('category_name')}"

    raw_part_type = (pdf_result or {}).get("part_type_raw")
    if raw_part_type:
        return f"PDF类型：{raw_part_type}"

    candidates = geometry.get("part_type_candidates") or []
    if not isinstance(candidates, list) or not candidates:
        candidates = []

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        source = candidate.get("source") or {}
        if not isinstance(source, dict):
            continue
        if source.get("source_type") != "pdf":
            continue
        label = str(source.get("raw_text") or candidate.get("reason") or "").strip()
        if label:
            return f"PDF类型：{label}"

    return None


def measured_value_text(value: dict[str, Any] | None) -> str:
    if not value:
        return "-"

    number = value.get("value")
    unit = value.get("unit")
    if number is None:
        return "-"
    return join_present([number, unit], " ")


def material_feature_text(material: dict[str, Any] | None) -> str:
    if not material:
        return "-"
    standard_name = material_display_name(material)
    return join_present(
        [
            f"原文：{material.get('raw_text')}" if material.get("raw_text") else None,
            f"名称：{standard_name}" if standard_name else None,
            material_density_text(material),
        ]
    )


def material_display_name(material: dict[str, Any]) -> str | None:
    return (
        material_chinese_name(
            material.get("standard_code"),
            material.get("raw_text"),
            material.get("standard_name"),
        )
        or material.get("standard_name")
    )


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
    return re.sub(r"[\s_\-/]+", "", str(value or "").upper().replace("＃", "#"))


def material_density_text(material: dict[str, Any]) -> str | None:
    density = material.get("density")
    if density is None:
        return None
    return "密度：" + join_present([density, material.get("density_unit")], " ")


def hole_depth_text(hole: dict[str, Any]) -> Any:
    if hole.get("through") is True:
        return "贯穿"
    return hole.get("depth")


def requirement_text(requirement: dict[str, Any] | None) -> str:
    if not requirement:
        return "-"

    has_raw_text = bool(requirement.get("raw_text"))
    is_required = bool(requirement.get("required"))
    return join_present(
        [
            "需要" if is_required else "不需要",
            f"原文：{requirement.get('raw_text')}"
            if has_raw_text
            else None,
            f"置信度 {confidence_text(requirement.get('confidence'))}"
            if (has_raw_text or is_required)
            and requirement.get("confidence") is not None
            else None,
        ]
    )


def confidence_text(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def datetime_text(value: Any) -> str:
    if value in (None, ""):
        return "-"

    text = str(value).strip()
    if not text:
        return "-"

    normalized = text.replace("T", " ")
    if normalized.endswith("Z"):
        normalized = normalized[:-1]

    for marker in ("+", "-"):
        marker_index = normalized.rfind(marker)
        if marker_index > 10:
            normalized = normalized[:marker_index]
            break

    if "." in normalized:
        normalized = normalized.split(".", 1)[0]
    return normalized.strip()


def evidence_summary(evidence: Any) -> str:
    if not evidence:
        return "-"
    if isinstance(evidence, dict):
        return source_summary(evidence)
    if isinstance(evidence, list):
        return "; ".join(source_summary(item) for item in evidence)
    return str(evidence)


def ai_output_summary(item: dict[str, Any]) -> str:
    content, wrapper_key = unwrap_ai_content(item.get("content"))
    if not isinstance(content, dict):
        return override_value_text(content)

    if content.get("available") is False:
        return join_present(
            [
                "AI不可用",
                content.get("error_message"),
                content.get("review_suggestion"),
            ],
            "；",
        )

    output_type = item.get("output_type")
    if output_type == "field_candidate":
        return ai_field_candidate_summary(content)
    if output_type == "normalization":
        return ai_normalization_summary(content, wrapper_key)
    if output_type == "risk_suggestion":
        return ai_risk_summary(content)
    if output_type == "explanation":
        return ai_operation_summary(content)
    if output_type == "analysis":
        return ai_analysis_summary(content)

    return ai_content_summary(content)


def ai_output_unavailable(item: dict[str, Any]) -> bool:
    content, _wrapper_key = unwrap_ai_content(item.get("content"))
    return isinstance(content, dict) and content.get("available") is False


def ai_status_text(
    *,
    visible_count: int,
    unavailable_outputs: list[dict[str, Any]],
) -> str:
    unavailable_count = len(unavailable_outputs)
    unavailable_reason = ai_unavailable_reason_text(unavailable_outputs)
    if visible_count > 0 and unavailable_count > 0:
        return (
            f"已生成 {visible_count} 条 AI 建议；另有 {unavailable_count} 条因{unavailable_reason}未生成，"
            "主流程未受影响。"
        )
    if visible_count > 0:
        return f"已生成 {visible_count} 条 AI 建议，仅供人工复核参考，不会改写报价结果。"
    if unavailable_count > 0:
        return (
            f"AI {unavailable_reason}，本次没有生成 AI 建议；解析、核价等主流程已继续，"
            "请按结构化字段、风险和报价依据人工复核。"
        )
    return "本次未启用 AI 建议，或当前没有需要 AI 解释的风险/候选内容。"


def ai_unavailable_reason_text(outputs: list[dict[str, Any]]) -> str:
    messages = []
    for output in outputs:
        content, _wrapper_key = unwrap_ai_content(output.get("content"))
        if isinstance(content, dict):
            messages.append(str(content.get("error_message") or ""))
        messages.append(str(output.get("model_name") or ""))
    text = "\n".join(messages).lower()
    if "429" in text or "rate limit" in text or "rate-limited" in text:
        return "服务限流"
    if "timed out" in text or "timeout" in text:
        return "请求超时"
    if "not configured" in text or "unconfigured" in text:
        return "未配置"
    return "当前不可用"


def unwrap_ai_content(content: Any) -> tuple[Any, str | None]:
    if not isinstance(content, dict):
        return content, None

    for key in (
        "material_normalization",
        "surface_treatment_normalization",
        "risk_explanation",
        "operation_explanation",
    ):
        value = content.get(key)
        if isinstance(value, dict):
            return value, key
    return content, None


def ai_normalization_summary(content: dict[str, Any], wrapper_key: str | None) -> str:
    if isinstance(content.get("requirements"), list):
        return ai_technical_requirement_summary(content)

    raw_text = content.get("raw_text")
    standard_code = content.get("standard_code")
    standard_name = content.get("standard_name")
    if wrapper_key == "surface_treatment_normalization" or (
        standard_code and "PLATING" in str(standard_code).upper()
    ):
        label = "表面处理归一"
    else:
        label = "材料归一"

    if standard_code or standard_name:
        result = join_present([standard_code, standard_name], " / ")
        return join_present(
            [
                f"{label}：原文“{raw_text}”",
                f"识别为 {result}",
                f"置信度 {confidence_text(content.get('confidence'))}",
            ],
            "；",
        )

    return join_present(
        [
            f"{label}：原文“{raw_text}”",
            "未能匹配到标准编码",
            "需要人工确认",
        ],
        "；",
    )


def ai_field_candidate_summary(content: dict[str, Any]) -> str:
    candidates = content.get("candidates") or []
    if not isinstance(candidates, list) or not candidates:
        return join_present(
            [
                "字段候选：无可用候选",
                content.get("notes"),
            ],
            "；",
        )

    parts = []
    for candidate in candidates[:4]:
        if not isinstance(candidate, dict):
            continue
        field_label = label_for(PDF_FIELD_LABELS, candidate.get("field_name"))
        value = compact_text(candidate.get("candidate_value"), limit=40)
        parts.append(
            join_present(
                [
                    field_label,
                    f"“{value}”" if value else None,
                    f"置信度 {confidence_text(candidate.get('confidence'))}",
                ],
                " ",
            )
        )
    extra = len(candidates) - len(parts)
    return join_present(
        [
            f"字段候选：{len(candidates)} 项",
            "；".join(parts),
            f"另有 {extra} 项" if extra > 0 else None,
            "需复核" if content.get("review_required") else None,
        ],
        "；",
    )


def ai_technical_requirement_summary(content: dict[str, Any]) -> str:
    requirements = content.get("requirements") or []
    if not isinstance(requirements, list) or not requirements:
        return join_present(
            [
                "技术要求归一：无候选结果",
                content.get("review_summary"),
            ],
            "；",
        )

    parts = []
    for item in requirements[:4]:
        if not isinstance(item, dict):
            continue
        raw_text = compact_text(item.get("raw_text"), limit=36)
        code = item.get("standard_code") or item.get("requirement_type")
        parts.append(
            join_present(
                [
                    f"原文“{raw_text}”" if raw_text else None,
                    f"候选 {code}" if code else None,
                    f"置信度 {confidence_text(item.get('confidence'))}",
                ],
                " ",
            )
        )
    extra = len(requirements) - len(parts)
    return join_present(
        [
            f"技术要求归一：{len(requirements)} 项候选",
            "；".join(parts),
            f"另有 {extra} 项" if extra > 0 else None,
            content.get("review_summary"),
        ],
        "；",
    )


def ai_risk_summary(content: dict[str, Any]) -> str:
    risk_code = str(content.get("risk_code") or "")
    risk_label, default_suggestion = AI_RISK_SUMMARY_LABELS.get(
        risk_code,
        (risk_code or "未命名风险", "请结合证据人工确认。"),
    )
    ai_suggestion = compact_text(content.get("review_suggestion"))
    explanation = compact_text(content.get("explanation"))
    suggestion = ai_suggestion if has_cjk(ai_suggestion) else default_suggestion
    return join_present(
        [
            f"风险：{risk_label}",
            f"编码：{risk_code}" if risk_code else None,
            f"说明：{explanation}" if has_cjk(explanation) else None,
            f"建议：{suggestion}",
        ],
        "；",
    )


def ai_operation_summary(content: dict[str, Any]) -> str:
    operation_code = content.get("operation_code")
    operation_label = label_for(OPERATION_CODE_LABELS, operation_code)
    explanation = compact_text(content.get("explanation"))
    suggestion = compact_text(content.get("review_suggestion"))
    if not has_cjk(explanation):
        explanation = "该工序由系统规则命中生成，需结合图纸和工艺路线复核。"
    if not has_cjk(suggestion):
        suggestion = "请结合规则命中原因确认该工序是否适用。"
    return join_present(
        [
            f"工序解释：{operation_label}",
            f"编码：{operation_code}" if operation_code else None,
            f"说明：{explanation}" if explanation else None,
            f"建议：{suggestion}" if suggestion else None,
        ],
        "；",
    )


def ai_analysis_summary(content: dict[str, Any]) -> str:
    override_count = content.get("override_count")
    categories = content.get("frequent_categories") or []
    if isinstance(categories, list):
        category_text = "、".join(
            label_for(TARGET_TYPE_LABELS, category) for category in categories[:4]
        )
    else:
        category_text = ""
    suggestions = content.get("suggestions") or []
    suggestion = ""
    if isinstance(suggestions, list) and suggestions:
        suggestion = compact_text(suggestions[0], limit=90)
    return join_present(
        [
            f"修改复盘：共 {override_count} 条人工修改" if override_count is not None else "修改复盘",
            f"高频对象：{category_text}" if category_text else None,
            compact_text(content.get("summary"), limit=120),
            f"建议：{suggestion}" if suggestion else None,
        ],
        "；",
    )


def compact_text(value: Any, limit: int = 120) -> str:
    if value in (None, ""):
        return ""
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def has_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def ai_content_summary(content: Any) -> str:
    if not isinstance(content, dict):
        return override_value_text(content)

    if content.get("available") is False:
        return join_present(
            [
                "AI不可用",
                content.get("error_message"),
                content.get("review_suggestion"),
            ]
        )

    parts = [
        content.get("standard_code"),
        content.get("standard_name"),
        content.get("risk_code"),
        content.get("operation_code"),
        content.get("explanation"),
        content.get("review_suggestion"),
        content.get("match_reason"),
    ]

    summary = join_present(parts)
    if summary != "-":
        return summary
    return json.dumps(content, ensure_ascii=False, default=str)


def trigger_reason_summary(reasons: Any) -> str:
    if not reasons:
        return "-"
    if not isinstance(reasons, list):
        return route_text(reasons)

    parts = []
    for reason in reasons:
        if not isinstance(reason, dict):
            parts.append(route_text(reason))
            continue
        rule_code = reason.get("rule_code")
        rule_text = route_rule_text(rule_code)
        message_text = route_text(reason.get("message"))
        if message_text != "-":
            parts.append(message_text)
            continue
        parts.append(
            join_present(
                [
                    rule_text,
                ],
                "：",
            )
        )
    return "; ".join(parts) if parts else "-"


def route_rule_text(rule_code: Any) -> str:
    if rule_code in (None, ""):
        return "-"
    text = str(rule_code)
    return ROUTE_RULE_LABELS.get(text, text)


def basis_summary(basis: Any) -> str:
    if not basis:
        return "-"
    if not isinstance(basis, list):
        return str(basis)

    parts = []
    for item in basis:
        if not isinstance(item, dict):
            parts.append(str(item))
            continue
        name = label_for(QUANTITY_BASIS_LABELS, item.get("name"))
        value = join_present(
            [
                item.get("value"),
                label_for(UNIT_LABELS, item.get("unit"))
                if item.get("unit")
                else None,
            ],
            " ",
        )
        label_value = f"{name}：{value}" if value != "-" else name
        source = quantity_basis_source_summary(item.get("source"))
        if source != "-":
            label_value = f"{label_value}（{source}）"
        parts.append(label_value)
    return "; ".join(parts) if parts else "-"


def quantity_formula_text(formula: Any) -> str:
    if formula in (None, ""):
        return "-"
    text = str(formula)
    return QUANTITY_FORMULA_LABELS.get(text, text)


def review_reason_text(reason: Any) -> str:
    if reason in (None, ""):
        return "-"
    text = str(reason)
    return REVIEW_REASON_LABELS.get(text, text)


def quote_formula_source_text(item: dict[str, Any]) -> str:
    return join_present(
        [
            quote_formula_text(item.get("formula")),
            price_source_summary(item.get("price_source")),
        ]
    )


def quote_formula_text(formula: Any) -> str:
    if formula in (None, ""):
        return "-"
    text = str(formula)
    return QUOTE_FORMULA_LABELS.get(text, quantity_formula_text(text))


def quantity_basis_source_summary(source: dict[str, Any] | None) -> str:
    if not source:
        return "-"

    parts = [
        label_for(SOURCE_TYPE_LABELS, source.get("source_type")),
        f"第 {source.get('page')} 页" if source.get("page") else None,
    ]
    raw_text = source.get("raw_text")
    rule_code = source.get("rule_code")
    if raw_text:
        parts.append(f"原文：{raw_text}")
    elif rule_code:
        parts.append(quantity_rule_text(rule_code))
    return join_present(parts, " / ")


def quantity_rule_text(rule_code: Any) -> str:
    if rule_code in (None, ""):
        return "-"
    text = str(rule_code)
    if text in QUANTITY_RULE_LABELS:
        return QUANTITY_RULE_LABELS[text]
    if text.startswith("WIRE_CUT:") and text.endswith(":CUT_LENGTH_MISSING"):
        return "线切割长度缺失"
    if text.startswith("WIRE_CUT:") and text.endswith(":OUTER_PROFILE_LENGTH"):
        return "线切割外轮廓长度"
    if text.startswith("WIRE_CUT:") and text.endswith(":THICKNESS"):
        return "线切割材料厚度"
    if text.startswith("GRINDING:") and text.endswith(":FACE_COUNT_MISSING"):
        return "磨削面数缺失"
    if text.startswith("GRINDING:") and text.endswith(":MAJOR_FACE_AREA"):
        return "磨削基准面积"
    return text


def source_summary(source: dict[str, Any] | None) -> str:
    if not source:
        return "-"

    source_type = label_for(SOURCE_TYPE_LABELS, source.get("source_type"))
    parts = [
        f"来源：{source_type}" if source_type != "-" else None,
        f"文件：{source.get('file_id')}" if source.get("file_id") else None,
        f"第 {source.get('page')} 页" if source.get("page") else None,
        f"位置：{source_location_text(source.get('location'))}"
        if source.get("location")
        else None,
    ]
    raw_text = source.get("raw_text")
    rule_code = source.get("rule_code")
    parts.extend(
        [
            f"原文：{raw_text}" if raw_text else None,
            f"规则：{source_rule_text(rule_code)}" if rule_code else None,
        ]
    )
    return join_present(parts, "；")


def source_location_text(location: Any) -> str:
    if location in (None, ""):
        return "-"
    text = str(location)
    if text in SOURCE_LOCATION_LABELS:
        return SOURCE_LOCATION_LABELS[text]
    block_match = re.fullmatch(
        r"page_(\d+)_block_(\d+)(?::(.+))?",
        text,
    )
    if block_match:
        suffix = f"（坐标：{block_match.group(3)}）" if block_match.group(3) else ""
        return f"第 {block_match.group(1)} 页文本块 {block_match.group(2)}{suffix}"
    return text


def source_rule_text(rule_code: Any) -> str:
    if rule_code in (None, ""):
        return "-"
    text = str(rule_code)
    if text in QUANTITY_RULE_LABELS:
        return QUANTITY_RULE_LABELS[text]
    if text in PRICE_RULE_LABELS:
        return PRICE_RULE_LABELS[text]
    if text in PDF_EXTRACT_METHOD_LABELS:
        return PDF_EXTRACT_METHOD_LABELS[text]
    if text in RISK_MESSAGE_LABELS:
        return RISK_MESSAGE_LABELS[text]
    if ":" in text:
        prefix, suffix = text.split(":", 1)
        prefix_label = source_rule_text(prefix)
        suffix_label = source_rule_suffix_text(suffix)
        return join_present([prefix_label, suffix_label], "：")
    return source_rule_suffix_text(text)


def source_rule_suffix_text(value: Any) -> str:
    text = str(value or "")
    if text in PDF_FIELD_LABELS:
        return PDF_FIELD_LABELS[text]
    if text in OPERATION_CODE_LABELS:
        return OPERATION_CODE_LABELS[text]
    if text in QUANTITY_RULE_LABELS:
        return QUANTITY_RULE_LABELS[text]
    labels = {
        "PDF_TEXT_TITLE_BLOCK": "PDF 标题栏识别",
        "PDF_TEXT_REGEX": "PDF 文本规则匹配",
        "PDF_FIELD_NOT_FOUND": "PDF 字段未找到",
        "PDF_TITLE_BLOCK_FIELD_NOT_FOUND": "PDF 标题栏字段未找到",
        "PDF_TEXT_HOLE_ANNOTATION": "PDF 孔标注识别",
        "PDF_TEXT_TECHNICAL_REQUIREMENT": "PDF 技术要求识别",
        "PDF_VISION": "PDF 图像识别",
        "PDF_VISION_FIELD_NOT_FOUND": "PDF 图像识别字段未找到",
        "PDF_VISION_ERROR": "PDF 图像识别错误",
        "STEP_HOLE_MATCH_CONTEXT": "STEP 孔匹配上下文",
        "STEP_AI_PART_TYPE_CLASSIFICATION": "AI STEP 零件类型识别",
        "STEP_RULE_PART_TYPE_CANDIDATE": "STEP 规则类型候选",
        "MISSING_PRICE_OR_QUANTITY": "缺少价格或工程量",
        "PROCESS_ROUTE_REQUIRES_REVIEW": "工艺路线需要复核",
        "MATERIAL_DENSITY_AI_NORMALIZATION": "AI 材料密度归一",
        "MATERIAL_DENSITY_MISSING": "材料密度缺失",
        "QUANTITY_DIMENSION_MISSING": "工程量尺寸缺失",
    }
    return labels.get(text, text)


def price_source_summary(source: dict[str, Any] | None) -> str:
    if not source:
        return "-"

    return join_present(
        [
            label_for(SOURCE_TYPE_LABELS, source.get("source_type")),
            price_source_id_text(source.get("source_id")),
            price_rule_text(source.get("rule_id")),
            price_version_text(source.get("version")),
        ],
        " / ",
    )


def price_source_id_text(source_id: Any) -> str:
    if source_id in (None, ""):
        return "-"
    text = str(source_id)
    if text in PRICE_SOURCE_ID_LABELS:
        return PRICE_SOURCE_ID_LABELS[text]
    if "south_china_process_standard" in text:
        return "华南工序计价标准表"
    if text.startswith("searxng_"):
        return "SearXNG 材料行情搜索"
    if text.startswith("tavily_gpt_"):
        return "Tavily + GPT 行情搜索"
    return text


def price_rule_text(rule_id: Any) -> str:
    if rule_id in (None, ""):
        return "-"
    text = str(rule_id)
    base, _, operation_code = text.partition(":")
    label = PRICE_RULE_LABELS.get(base)
    if not label and base.startswith("9A3_"):
        normalized_base = f"SOUTH_CHINA_{base.removeprefix('9A3_')}"
        label = PRICE_RULE_LABELS.get(normalized_base)
    if not label:
        return text
    operation = operation_text(operation_code) if operation_code else "-"
    if operation != "-":
        return f"{label}（{operation}）"
    return label


def price_version_text(version: Any) -> str:
    if version in (None, ""):
        return "-"
    text = str(version)
    if text == "a-basic-v1":
        return "基础版"
    if text == "south-china-process-standard-v1":
        return "华南工序标准 V1"
    if text.startswith("market-test"):
        return "市场价测试版本"
    return text


def money_text(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)
