from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from client.views.main_window import (
    MainWindow,
    QUANTITY_TYPE_LABELS,
    label_for,
    quantity_formula_text,
    review_reason_text,
    route_text,
)


class MainWindowTests(unittest.TestCase):
    def test_base_url_input_matches_client_default(self) -> None:
        app = QApplication.instance() or QApplication([])
        with patch.object(MainWindow, "refresh_task_list", return_value=None):
            window = MainWindow()
        self.assertEqual(window.api.base_url, "http://127.0.0.1:8000")
        self.assertEqual(window.base_url_input.text(), "http://127.0.0.1:8000")
        window.close()

    def test_quote_detail_english_fields_are_shown_in_chinese(self) -> None:
        self.assertEqual(label_for(QUANTITY_TYPE_LABELS, "material_weight"), "材料重量")
        self.assertEqual(
            route_text("机加/方件族 backbone route is required."),
            "机加/方件族基础工艺路线为必需项。",
        )
        self.assertEqual(
            route_text("Detailing evidence adds drilling."),
            "明细证据加入钻孔工序。",
        )
        self.assertEqual(
            route_text("Counterbore feature detected; add counterbore operation."),
            "检测到圆柱沉孔特征，加入圆柱沉孔工序。",
        )
        self.assertEqual(
            quantity_formula_text(
                "Gross weight is unavailable; use STEP/PDF measured weight for material pricing."
            ),
            "无法计算毛坯重量，使用 STEP/PDF 标注重量作为材料计价重量",
        )
        self.assertEqual(
            review_reason_text(
                "Gross weight is unavailable because material density is missing; "
                "STEP/PDF measured weight is used for material pricing."
            ),
            "材料密度缺失导致无法计算毛坯重量，已使用 STEP/PDF 标注重量作为材料计价重量，需复核。",
        )
        self.assertEqual(
            review_reason_text(
                "Bounding box or material density is missing; gross weight cannot be calculated."
            ),
            "包络尺寸或材料密度缺失，无法计算毛坯重量。",
        )


if __name__ == "__main__":
    unittest.main()
