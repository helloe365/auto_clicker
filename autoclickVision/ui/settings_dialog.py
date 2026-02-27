"""
Settings Dialog
Allows configuring matcher parameters, click behaviour, webhook
notifications, screenshot archiving, and failure-rate alerting.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """Modal dialog for application-wide settings."""

    def __init__(self, current: Dict[str, Any], parent=None):
        """
        Args:
            current: Dict of current settings values.  Expected keys::

                grayscale       (bool)
                multi_scale     (bool)
                scale_min       (float)
                scale_max       (float)
                scale_step      (float)
                use_bezier      (bool)
                use_directinput (bool)
                archive_screenshots (bool)
                failure_rate_threshold (float)
                failure_rate_window    (int)
                webhooks        (list[dict])  [{name, url}, …]
                stop_after_consecutive_failures (int)  0 = disabled
                stop_after_duration_minutes     (int)  0 = disabled
        """
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)
        self._current = current
        self._build_ui()
        self._load(current)

    # ═════════════════════════════════════════════════════════════
    # Build UI
    # ═════════════════════════════════════════════════════════════

    def _build_ui(self):
        root = QVBoxLayout(self)
        tabs = QTabWidget()

        # ── Matcher tab ─────────────────────────────────────────
        matcher_page = QWidget()
        ml = QFormLayout(matcher_page)

        self._chk_grayscale = QCheckBox("Grayscale matching")
        ml.addRow(self._chk_grayscale)

        self._chk_multi_scale = QCheckBox("Multi-scale matching")
        ml.addRow(self._chk_multi_scale)

        self._spin_scale_min = QDoubleSpinBox()
        self._spin_scale_min.setRange(0.1, 2.0)
        self._spin_scale_min.setSingleStep(0.05)
        ml.addRow("Scale min:", self._spin_scale_min)

        self._spin_scale_max = QDoubleSpinBox()
        self._spin_scale_max.setRange(0.1, 3.0)
        self._spin_scale_max.setSingleStep(0.05)
        ml.addRow("Scale max:", self._spin_scale_max)

        self._spin_scale_step = QDoubleSpinBox()
        self._spin_scale_step.setRange(0.01, 0.5)
        self._spin_scale_step.setSingleStep(0.01)
        ml.addRow("Scale step:", self._spin_scale_step)

        tabs.addTab(matcher_page, "Matcher")

        # ── Click tab ───────────────────────────────────────────
        click_page = QWidget()
        cl = QFormLayout(click_page)

        self._chk_bezier = QCheckBox("Bézier curve mouse movement")
        cl.addRow(self._chk_bezier)

        self._chk_directinput = QCheckBox("PyDirectInput mode (fullscreen games)")
        cl.addRow(self._chk_directinput)

        tabs.addTab(click_page, "Click")

        # ── Notifications tab ───────────────────────────────────
        notify_page = QWidget()
        nl = QVBoxLayout(notify_page)

        # Failure rate
        fr_group = QGroupBox("Failure-Rate Alert")
        frl = QFormLayout()
        self._spin_fr_threshold = QDoubleSpinBox()
        self._spin_fr_threshold.setRange(0.0, 1.0)
        self._spin_fr_threshold.setSingleStep(0.05)
        frl.addRow("Threshold:", self._spin_fr_threshold)

        self._spin_fr_window = QSpinBox()
        self._spin_fr_window.setRange(5, 200)
        frl.addRow("Window size:", self._spin_fr_window)
        fr_group.setLayout(frl)
        nl.addWidget(fr_group)

        # Webhook table
        wh_group = QGroupBox("Webhooks (Telegram / DingTalk / Slack)")
        whl = QVBoxLayout()
        self._webhook_table = QTableWidget(0, 2)
        self._webhook_table.setHorizontalHeaderLabels(["Name", "URL"])
        self._webhook_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch,
        )
        whl.addWidget(self._webhook_table)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Add")
        btn_add.clicked.connect(self._on_add_webhook)
        btn_remove = QPushButton("– Remove")
        btn_remove.clicked.connect(self._on_remove_webhook)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_remove)
        btn_row.addStretch()
        whl.addLayout(btn_row)
        wh_group.setLayout(whl)
        nl.addWidget(wh_group)
        nl.addStretch()

        tabs.addTab(notify_page, "Notifications")

        # ── Screenshot tab ──────────────────────────────────────
        ss_page = QWidget()
        sl = QFormLayout(ss_page)

        self._chk_archive = QCheckBox("Archive failure screenshots to logs/screenshots/")
        sl.addRow(self._chk_archive)

        tabs.addTab(ss_page, "Screenshots")

        # ── Stop Conditions tab ─────────────────────────────────
        stop_page = QWidget()
        stl = QFormLayout(stop_page)

        self._spin_stop_failures = QSpinBox()
        self._spin_stop_failures.setRange(0, 9999)
        self._spin_stop_failures.setSpecialValueText("Disabled")
        stl.addRow("Stop after N consecutive failures:", self._spin_stop_failures)

        self._spin_stop_duration = QSpinBox()
        self._spin_stop_duration.setRange(0, 99999)
        self._spin_stop_duration.setSuffix(" min")
        self._spin_stop_duration.setSpecialValueText("Disabled")
        stl.addRow("Stop after duration:", self._spin_stop_duration)

        tabs.addTab(stop_page, "Stop Conditions")

        root.addWidget(tabs)

        # ── Dialog buttons ──────────────────────────────────────
        bbox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        root.addWidget(bbox)

    # ═════════════════════════════════════════════════════════════
    # Webhook helpers
    # ═════════════════════════════════════════════════════════════

    def _on_add_webhook(self):
        row = self._webhook_table.rowCount()
        self._webhook_table.insertRow(row)
        self._webhook_table.setItem(row, 0, QTableWidgetItem(""))
        self._webhook_table.setItem(row, 1, QTableWidgetItem(""))

    def _on_remove_webhook(self):
        row = self._webhook_table.currentRow()
        if row >= 0:
            self._webhook_table.removeRow(row)

    # ═════════════════════════════════════════════════════════════
    # Load / collect
    # ═════════════════════════════════════════════════════════════

    def _load(self, s: Dict[str, Any]):
        self._chk_grayscale.setChecked(s.get("grayscale", False))
        self._chk_multi_scale.setChecked(s.get("multi_scale", False))
        self._spin_scale_min.setValue(s.get("scale_min", 0.7))
        self._spin_scale_max.setValue(s.get("scale_max", 1.3))
        self._spin_scale_step.setValue(s.get("scale_step", 0.05))
        self._chk_bezier.setChecked(s.get("use_bezier", False))
        self._chk_directinput.setChecked(s.get("use_directinput", False))
        self._chk_archive.setChecked(s.get("archive_screenshots", True))
        self._spin_fr_threshold.setValue(s.get("failure_rate_threshold", 0.5))
        self._spin_fr_window.setValue(s.get("failure_rate_window", 20))
        self._spin_stop_failures.setValue(s.get("stop_after_consecutive_failures", 0))
        self._spin_stop_duration.setValue(s.get("stop_after_duration_minutes", 0))

        for wh in s.get("webhooks", []):
            row = self._webhook_table.rowCount()
            self._webhook_table.insertRow(row)
            self._webhook_table.setItem(row, 0, QTableWidgetItem(wh.get("name", "")))
            self._webhook_table.setItem(row, 1, QTableWidgetItem(wh.get("url", "")))

    def get_settings(self) -> Dict[str, Any]:
        """Collect all settings from the dialog widgets."""
        webhooks: List[Dict[str, str]] = []
        for r in range(self._webhook_table.rowCount()):
            name_item = self._webhook_table.item(r, 0)
            url_item = self._webhook_table.item(r, 1)
            name = name_item.text().strip() if name_item else ""
            url = url_item.text().strip() if url_item else ""
            if name and url:
                webhooks.append({"name": name, "url": url})

        return {
            "grayscale": self._chk_grayscale.isChecked(),
            "multi_scale": self._chk_multi_scale.isChecked(),
            "scale_min": self._spin_scale_min.value(),
            "scale_max": self._spin_scale_max.value(),
            "scale_step": self._spin_scale_step.value(),
            "use_bezier": self._chk_bezier.isChecked(),
            "use_directinput": self._chk_directinput.isChecked(),
            "archive_screenshots": self._chk_archive.isChecked(),
            "failure_rate_threshold": self._spin_fr_threshold.value(),
            "failure_rate_window": self._spin_fr_window.value(),
            "webhooks": webhooks,
            "stop_after_consecutive_failures": self._spin_stop_failures.value(),
            "stop_after_duration_minutes": self._spin_stop_duration.value(),
        }
