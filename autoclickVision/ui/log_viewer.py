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
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr

logger = logging.getLogger(__name__)


class LogViewer(QWidget):
    """Panel showing real-time logs, screenshots on failure, and export controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_lines: List[str] = []
        self._screenshots: List[Tuple[str, str]] = []  # (path, tag)
        self._round_summaries: List[Tuple[int, int, int, int]] = []  # (round, ok, fail, skip)
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

        # Middle: round summary table
        grp_summary = QGroupBox(tr("Round Summary"))
        sl = QVBoxLayout(grp_summary)
        self._summary_table = QTableWidget(0, 4)
        self._summary_table.setHorizontalHeaderLabels(
            [tr("Round"), tr("Success"), tr("Failure"), tr("Skipped")])
        self._summary_table.setMaximumHeight(140)
        self._summary_table.horizontalHeader().setStretchLastSection(True)
        sl.addWidget(self._summary_table)
        splitter.addWidget(grp_summary)

        # Bottom: screenshot list
        self._screenshot_list = QListWidget()
        self._screenshot_list.setMaximumHeight(150)
        self._screenshot_list.setIconSize(self._screenshot_list.iconSize())
        self._screenshot_list.itemDoubleClicked.connect(self._on_screenshot_double_click)
        splitter.addWidget(self._screenshot_list)

        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)
        root.addWidget(splitter)

        # Controls
        btn_row = QHBoxLayout()
        btn_clear = QPushButton(tr("Clear"))
        btn_clear.clicked.connect(self.clear_log)
        btn_export_txt = QPushButton(tr("Export TXT"))
        btn_export_txt.clicked.connect(self._on_export_txt)
        btn_export_csv = QPushButton(tr("Export CSV"))
        btn_export_csv.clicked.connect(self._on_export_csv)
        btn_history = QPushButton(tr("History"))
        btn_history.clicked.connect(self._on_browse_history)
        btn_row.addWidget(btn_clear)
        btn_row.addWidget(btn_export_txt)
        btn_row.addWidget(btn_export_csv)
        btn_row.addWidget(btn_history)
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
        self._round_summaries.clear()
        self._summary_table.setRowCount(0)

    # ═════════════════════════════════════════════════════════════
    # Round summaries
    # ═════════════════════════════════════════════════════════════

    def add_round_summary(self, round_num: int, success: int, failure: int, skipped: int):
        """Append a per-round summary row to the table."""
        self._round_summaries.append((round_num, success, failure, skipped))
        row = self._summary_table.rowCount()
        self._summary_table.insertRow(row)
        for col, val in enumerate([round_num, success, failure, skipped]):
            item = QTableWidgetItem(str(val))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._summary_table.setItem(row, col, item)
        # Auto-scroll to the newest row
        self._summary_table.scrollToBottom()

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
            dlg.setWindowTitle(tr("Screenshot"))
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
        path, _ = QFileDialog.getSaveFileName(self, tr("Export Log"), "", tr("Text Files (*.txt)"))
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(self._log_lines))

    def _on_export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("Export Log"), "", tr("CSV Files (*.csv)"))
        if path:
            with open(path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["line", "message"])
                for i, line in enumerate(self._log_lines, 1):
                    writer.writerow([i, line])

    # ═════════════════════════════════════════════════════════════
    # Historical run browser
    # ═════════════════════════════════════════════════════════════

    def _on_browse_history(self):
        """Open a dialog listing past log and crash files."""
        logs_dir = Path(__file__).resolve().parent.parent / "logs"
        if not logs_dir.exists():
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, tr("History"), tr("No log files found."))
            return

        log_files = sorted(logs_dir.glob("*.log"), reverse=True)
        if not log_files:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, tr("History"), tr("No log files found."))
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Historical Runs"))
        dlg.resize(700, 500)
        layout = QVBoxLayout(dlg)

        lbl = QLabel(f"Found {len(log_files)} log file(s) in {logs_dir}")
        layout.addWidget(lbl)

        file_list = QListWidget()
        for fp in log_files:
            file_list.addItem(fp.name)
        layout.addWidget(file_list)

        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setStyleSheet("QTextEdit { font-family: Consolas, monospace; font-size: 11px; }")
        layout.addWidget(preview)

        def _on_select():
            items = file_list.selectedItems()
            if not items:
                return
            fname = items[0].text()
            fpath = logs_dir / fname
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                preview.setPlainText(content)
            except Exception as e:
                preview.setPlainText(f"Error reading file: {e}")

        file_list.currentItemChanged.connect(lambda *_: _on_select())

        btn_row = QHBoxLayout()
        btn_close = QPushButton(tr("Close"))
        btn_close.clicked.connect(dlg.accept)
        btn_load = QPushButton(tr("Load into viewer"))
        def _load():
            text = preview.toPlainText()
            if text:
                self.clear_log()
                for line in text.splitlines():
                    self.append_log(line)
            dlg.accept()
        btn_load.clicked.connect(_load)
        btn_row.addWidget(btn_load)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        dlg.exec()
