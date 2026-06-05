from __future__ import annotations

import json
from pathlib import Path
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

OPERATION_CODE_LABELS = {
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
}

QUANTITY_TYPE_LABELS = {
    "gross_weight": "毛重/净重",
    "cut_area": "下料面积",
    "hole_count": "孔数量",
    "counterbore_count": "沉孔数量",
    "thread_count": "螺纹数量",
    "precision_hole_count": "精孔数量",
    "estimated_hours": "估算工时",
    "grinding_area": "磨削面积",
    "heat_weight": "热处理重量",
    "surface_area": "表面积",
    "deburr_complexity": "去毛刺复杂度",
    "inspection_count": "检验数量",
    "manual_quantity": "人工工程量",
}

HOLE_TYPE_LABELS = {
    "through": "通孔",
    "blind": "盲孔",
    "counterbore": "沉孔",
    "countersink": "沉头孔",
    "threaded": "螺纹孔",
    "precision": "精孔",
}

UNIT_LABELS = {
    "lot": "批",
    "kg": "kg",
    "g": "g",
    "hour": "小时",
    "pcs": "件",
    "mm2": "mm²",
    "m2": "m²",
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

SOURCE_TYPE_LABELS = {
    "pdf": "PDF",
    "step": "STEP",
    "ai": "AI",
    "system": "系统",
    "manual": "人工",
    "rule": "规则",
    "price_rule": "价格规则",
    "mock_placeholder": "占位数据",
}

ERROR_CODE_LABELS = {
    "TASK_ID_REQUIRED": "任务ID必填",
    "QUOTE_REQUIRED": "请先生成报价",
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
        self.base_url_input = QLineEdit("http://127.0.0.1:8000")
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
        self.price_button = QPushButton("生成核价")
        self.export_button = QPushButton("导出 JSON")

        self.upload_pdf_button.clicked.connect(lambda: self.upload_file("pdf"))
        self.upload_step_button.clicked.connect(lambda: self.upload_file("step"))
        self.upload_attachment_button.clicked.connect(
            lambda: self.upload_file("attachment")
        )
        self.parse_button.clicked.connect(self.parse_task)
        self.price_button.clicked.connect(self.price_task)
        self.export_button.clicked.connect(self.export_quote)

        for button in (
            self.upload_pdf_button,
            self.upload_step_button,
            self.upload_attachment_button,
            self.parse_button,
            self.price_button,
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
        self.risk_tab = self._build_risk_tab()
        self.tabs.addTab(self.files_tab, "文件")
        self.tabs.addTab(self.feature_tab, "零件特征")
        self.tabs.addTab(self.quote_tab, "报价")
        self.tabs.addTab(self.risk_tab, "风险")
        root_layout.addWidget(self.tabs, 1)

        self.setCentralWidget(root)
        self.statusBar().showMessage("就绪")

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
        self.parse_pdf_checkbox.setChecked(True)
        self.parse_step_checkbox.setChecked(True)
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
        self.pdf_fields_table = QTableWidget(0, 5)
        self.pdf_fields_table.setHorizontalHeaderLabels(
            ["字段", "抽取值", "置信度", "方法", "证据"]
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
        self.confirm_risk_button = QPushButton("确认选中风险")
        self.final_quote_button = QPushButton("设置最终报价")
        self.confirm_quote_button = QPushButton("确认报价")
        self.refresh_quote_button.clicked.connect(self.refresh_quote_result)
        self.override_item_button.clicked.connect(self.open_item_override_dialog)
        self.quantity_override_button.clicked.connect(self.open_quantity_override_dialog)
        self.confirm_risk_button.clicked.connect(self.open_risk_confirmation_dialog)
        self.final_quote_button.clicked.connect(self.open_final_quote_dialog)
        self.confirm_quote_button.clicked.connect(self.open_confirm_quote_dialog)
        actions.addWidget(self.refresh_quote_button)
        actions.addWidget(self.override_item_button)
        actions.addWidget(self.quantity_override_button)
        actions.addWidget(self.confirm_risk_button)
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
        self.quote_risk_surcharge_value = value_label()
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
        summary.addRow("风险加价", self.quote_risk_surcharge_value)
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
        review_layout.addWidget(QLabel("报价风险"))
        self.quote_risk_table = QTableWidget(0, 6)
        self.quote_risk_table.setHorizontalHeaderLabels(
            ["编码", "等级", "说明", "需复核", "确认状态", "证据"]
        )
        configure_table(self.quote_risk_table)
        review_layout.addWidget(self.quote_risk_table)

        review_layout.addWidget(QLabel("人工修改记录"))
        self.manual_override_table = QTableWidget(0, 7)
        self.manual_override_table.setHorizontalHeaderLabels(
            ["对象", "字段", "旧值", "新值", "原因", "操作人", "时间"]
        )
        configure_table(self.manual_override_table)
        review_layout.addWidget(self.manual_override_table)
        quote_pages.addTab(review_page, "风险/人工修改")

        layout.addWidget(quote_pages, 1)
        self._sync_quote_actions(None)
        return widget

    def _build_risk_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.risk_table = QTableWidget(0, 5)
        self.risk_table.setHorizontalHeaderLabels(
            ["编码", "等级", "说明", "需复核", "证据"]
        )
        configure_table(self.risk_table)
        layout.addWidget(self.risk_table)
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
                use_ai=True,
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
        if self.current_quote_id:
            response = QMessageBox.question(
                self,
                "生成新报价",
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
            result = self.api.price_task(self._task_id())
            self.current_quote_id = result["quote_id"]
            self._render_quote_bundle(result)
            self._load_task()
            self.tabs.setCurrentWidget(self.quote_tab)
            self.statusBar().showMessage("报价已生成，正在显示报价页。")

        self._run_action("生成核价", action)

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
        row = self.quote_risk_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "请选择风险", "请先选中一条报价风险。")
            return

        risk_code_cell = self.quote_risk_table.item(row, 0)
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
            risk_message=str(risk.get("message") or ""),
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
        self._render_risks(risks)

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
                item.get("uploaded_at"),
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

        self.feature_parser_source_value.setText(parser_source_text(parse_result))
        self.feature_material_value.setText(
            join_present(
                [
                    material.get("standard_code"),
                    material.get("standard_name"),
                    f"原文：{material.get('raw_text')}"
                    if material.get("raw_text")
                    else None,
                    source_summary(material.get("source")),
                ]
            )
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
            join_present(
                [
                    geometry.get("part_type"),
                    confidence_text(geometry.get("part_type_confidence")),
                ]
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
                item["method"],
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
                item.get("depth"),
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

    def _render_risks(self, risks: list[dict[str, Any]]) -> None:
        self.risk_table.setRowCount(len(risks))
        for row, item in enumerate(risks):
            values = [
                item.get("code"),
                label_for(RISK_LEVEL_LABELS, item.get("level")),
                item.get("message"),
                yes_no(item.get("requires_review")),
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
                operation_text(item.get("operation_code")),
                item.get("operation_code"),
                trigger_reason_summary(item.get("trigger_reasons")),
                confidence_text(item.get("confidence")),
                yes_no(item.get("requires_review")),
                item.get("review_reason"),
                item.get("explanation"),
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
                item.get("formula"),
                basis_summary(item.get("basis")),
                yes_no(item.get("requires_review")),
                item.get("review_reason"),
            ]
            for column, value in enumerate(values):
                self.quantity_result_table.setItem(row, column, table_item(value))

    def _render_quote(self, quote_result: dict[str, Any] | None) -> None:
        if not quote_result:
            self._clear_quote()
            return

        self.current_quote_result = quote_result
        self.current_quote_id = quote_result.get("quote_id")
        items = quote_result.get("items") or []
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
                join_present(
                    [
                        item.get("formula"),
                        price_source_summary(item.get("price_source")),
                    ]
                ),
            ]
            for column, value in enumerate(values):
                self.quote_table.setItem(row, column, table_item(value))

        summary = quote_result.get("summary") or {}
        final_confirmed_amount = summary.get("final_confirmed_amount")

        self.quote_id_value.setText(str(quote_result.get("quote_id") or "-"))
        self.quote_status_value.setText(label_for(STATUS_LABELS, quote_result.get("status")))
        self.quote_currency_value.setText(str(quote_result.get("currency") or "-"))
        self.quote_version_value.setText(str(quote_result.get("price_version") or "-"))
        self.quote_priced_at_value.setText(str(quote_result.get("priced_at") or "-"))
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
        self.quote_risk_surcharge_value.setText(
            money_text(summary.get("risk_surcharge_amount"))
        )
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
        self._render_quote_risks(quote_result)
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
            self.quote_risk_surcharge_value,
            self.quote_system_calculated_value,
            self.quote_initial_value,
            self.quote_manual_adjustment_value,
        ):
            label.setText("-")
        self.quote_final_confirmed_input.setText("-")
        self.process_route_table.setRowCount(0)
        self.quantity_result_table.setRowCount(0)
        self.quote_table.setRowCount(0)
        self.quote_risk_table.setRowCount(0)
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

    def _render_quote_risks(self, quote_result: dict[str, Any]) -> None:
        risks = quote_result.get("risks") or []
        self.quote_risk_table.setRowCount(len(risks))
        for row, item in enumerate(risks):
            confirmed = risk_confirmed(quote_result, item)
            values = [
                item.get("code"),
                label_for(RISK_LEVEL_LABELS, item.get("level")),
                item.get("message"),
                yes_no(item.get("requires_review")),
                "已确认" if confirmed else "待确认" if item.get("requires_review") else "-",
                evidence_summary(item.get("evidence")),
            ]
            for column, value in enumerate(values):
                self.quote_risk_table.setItem(row, column, table_item(value))

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
                item.get("created_at"),
            ]
            for column, value in enumerate(values):
                self.manual_override_table.setItem(row, column, table_item(value))

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

        rows.append(
            {
                "label": PDF_FIELD_LABELS.get(field, field),
                "value": pdf_value_text(value),
                "confidence": confidence,
                "method": method or "-",
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


def parser_source_text(parse_result: dict[str, Any] | None) -> str:
    if not parse_result:
        return "-"

    parts = []
    pdf_result = parse_result.get("pdf_extract_result")
    step_result = parse_result.get("step_feature_result")

    if isinstance(pdf_result, dict):
        parser_name = pdf_result.get("parser_name") or "mock_pdf_parser"
        text_layer = pdf_result.get("text_layer") or {}
        text_layer_text = (
            f"text layer {text_layer.get('page_count')}页/{text_layer.get('block_count')}块"
            if text_layer.get("available")
            else None
        )
        parts.append(
            join_present(
                [
                    f"PDF：{parser_name}",
                    pdf_result.get("file_id"),
                    text_layer_text,
                ],
                " / ",
            )
        )
    else:
        parts.append("PDF：未解析")

    if isinstance(step_result, dict):
        parts.append(
            join_present(
                [
                    f"STEP：{step_result.get('parser_name') or 'mock_step_parser'}",
                    step_result.get("file_id"),
                ],
                " / ",
            )
        )
    else:
        parts.append("STEP：未解析")

    fallback_codes = [
        risk.get("code")
        for risk in parse_result.get("risks") or []
        if risk.get("code") == "PARSER_FALLBACK_USED"
    ]
    if fallback_codes:
        parts.append("注意：真实解析失败，已 fallback mock")

    return "；".join(parts)


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


def measured_value_text(value: dict[str, Any] | None) -> str:
    if not value:
        return "-"

    number = value.get("value")
    unit = value.get("unit")
    if number is None:
        return "-"
    return join_present([number, unit], " ")


def requirement_text(requirement: dict[str, Any] | None) -> str:
    if not requirement:
        return "-"

    return join_present(
        [
            "需要" if requirement.get("required") else "不需要",
            requirement.get("standard_code"),
            f"原文：{requirement.get('raw_text')}"
            if requirement.get("raw_text")
            else None,
            confidence_text(requirement.get("confidence")),
            source_summary(requirement.get("source")),
        ]
    )


def confidence_text(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def evidence_summary(evidence: Any) -> str:
    if not evidence:
        return "-"
    if isinstance(evidence, dict):
        return source_summary(evidence)
    if isinstance(evidence, list):
        return "; ".join(source_summary(item) for item in evidence)
    return str(evidence)


def trigger_reason_summary(reasons: Any) -> str:
    if not reasons:
        return "-"
    if not isinstance(reasons, list):
        return str(reasons)

    parts = []
    for reason in reasons:
        if not isinstance(reason, dict):
            parts.append(str(reason))
            continue
        parts.append(
            join_present(
                [
                    reason.get("rule_code"),
                    reason.get("message"),
                    source_summary(reason.get("source")),
                ],
                " / ",
            )
        )
    return "; ".join(parts) if parts else "-"


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
        value = join_present(
            [
                item.get("value"),
                label_for(UNIT_LABELS, item.get("unit"))
                if item.get("unit")
                else None,
            ],
            " ",
        )
        parts.append(
            join_present(
                [
                    item.get("name"),
                    value if value != "-" else None,
                    source_summary(item.get("source")),
                ],
                " / ",
            )
        )
    return "; ".join(parts) if parts else "-"


def source_summary(source: dict[str, Any] | None) -> str:
    if not source:
        return "-"

    location = join_present(
        [
            label_for(SOURCE_TYPE_LABELS, source.get("source_type")),
            source.get("file_id"),
            f"第 {source.get('page')} 页" if source.get("page") else None,
            source.get("location"),
        ],
        " / ",
    )
    raw_text = source.get("raw_text")
    rule_code = source.get("rule_code")
    extras = join_present(
        [
            f"原文：{raw_text}" if raw_text else None,
            f"规则：{rule_code}" if rule_code else None,
        ],
        " / ",
    )
    if extras == "-":
        return location
    return f"{location} ({extras})"


def price_source_summary(source: dict[str, Any] | None) -> str:
    if not source:
        return "-"

    return join_present(
        [
            label_for(SOURCE_TYPE_LABELS, source.get("source_type")),
            source.get("source_id"),
            source.get("rule_id"),
            source.get("version"),
        ],
        " / ",
    )


def money_text(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)
