"""
Log Viewer Panel
Real-time scrolling log output, failure screenshot thumbnails,
per-round execution summaries, and log export (TXT / CSV).
"""

from __future__ import annotations

import csv
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class LogViewer(QWidget):
    """Panel showing real-time logs, screenshots on failure, and export controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_lines: List[str] = []
        self._screenshots: List[Tuple[str, str]] = []  # (path, tag)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Top: log text
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(self._text.font())
        self._text.setStyleSheet("QTextEdit { font-family: Consolas, monospace; font-size: 12px; }")
        splitter.addWidget(self._text)

        # Bottom: screenshot list
        self._screenshot_list = QListWidget()
        self._screenshot_list.setMaximumHeight(150)
        self._screenshot_list.setIconSize(self._screenshot_list.iconSize())
        self._screenshot_list.itemDoubleClicked.connect(self._on_screenshot_double_click)
        splitter.addWidget(self._screenshot_list)

        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

        # Controls
        btn_row = QHBoxLayout()
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self.clear_log)
        btn_export_txt = QPushButton("Export TXT")
        btn_export_txt.clicked.connect(self._on_export_txt)
        btn_export_csv = QPushButton("Export CSV")
        btn_export_csv.clicked.connect(self._on_export_csv)
        btn_row.addWidget(btn_clear)
        btn_row.addWidget(btn_export_txt)
        btn_row.addWidget(btn_export_csv)
        btn_row.addStretch()
        root.addLayout(btn_row)

    # ═════════════════════════════════════════════════════════════
    # Log management
    # ═════════════════════════════════════════════════════════════

    def append_log(self, msg: str):
        self._log_lines.append(msg)
        self._text.append(msg)
        # Auto-scroll
        sb = self._text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear_log(self):
        self._log_lines.clear()
        self._text.clear()
        self._screenshots.clear()
        self._screenshot_list.clear()

    # ═════════════════════════════════════════════════════════════
    # Screenshots
    # ═════════════════════════════════════════════════════════════

    def add_screenshot(self, path: str, tag: str):
        self._screenshots.append((path, tag))
        item = QListWidgetItem()
        item.setText(f"[{tag}] {Path(path).name}")
        item.setData(Qt.ItemDataRole.UserRole, path)
        # Try to set a small icon
        if os.path.isfile(path):
            pm = QPixmap(path).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio)
            from PyQt6.QtGui import QIcon
            item.setIcon(QIcon(pm))
        self._screenshot_list.addItem(item)

    def _on_screenshot_double_click(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.isfile(path):
            dlg = QDialog(self)
            dlg.setWindowTitle("Screenshot")
            dlg.resize(800, 600)
            lbl = QLabel()
            pm = QPixmap(path).scaled(780, 580, Qt.AspectRatioMode.KeepAspectRatio)
            lbl.setPixmap(pm)
            layout = QVBoxLayout(dlg)
            layout.addWidget(lbl)
            dlg.exec()

    # ═════════════════════════════════════════════════════════════
    # Export
    # ═════════════════════════════════════════════════════════════

    def _on_export_txt(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Log", "", "Text Files (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(self._log_lines))

    def _on_export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Log", "", "CSV Files (*.csv)")
        if path:
            with open(path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["line", "message"])
                for i, line in enumerate(self._log_lines, 1):
                    writer.writerow([i, line])
