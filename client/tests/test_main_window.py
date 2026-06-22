from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from client.views.main_window import MainWindow


class MainWindowTests(unittest.TestCase):
    def test_base_url_input_matches_client_default(self) -> None:
        app = QApplication.instance() or QApplication([])
        with patch.object(MainWindow, "refresh_task_list", return_value=None):
            window = MainWindow()
        self.assertEqual(window.api.base_url, "http://127.0.0.1:8000")
        self.assertEqual(window.base_url_input.text(), "http://127.0.0.1:8000")
        window.close()


if __name__ == "__main__":
    unittest.main()
