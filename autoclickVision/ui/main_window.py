"""
Main Window
Top-level PyQt6 window that ties the toolbar, button editor, sequence editor,
log viewer, status bar, progress bar, system-tray icon, and global hotkeys together.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import keyboard
import numpy as np
from PyQt6.QtCore import QTimer, Qt, pyqtSignal, QObject
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QStatusBar,
    QSystemTrayIcon,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..config.config_manager import ConfigManager
from ..core.capture import ScreenCapture
from ..core.clicker import Clicker
from ..core.matcher import ImageMatcher
from ..core.scheduler import RunStats, SequenceScheduler, TaskConfig, TaskState
from ..core.watchdog import Watchdog
from .button_editor import ButtonEditor
from .log_viewer import LogViewer
from .sequence_editor import SequenceEditor

logger = logging.getLogger(__name__)

_LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
_SCREENSHOTS_DIR = _LOGS_DIR / "screenshots"
_SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────
# Signal bridge: scheduler callbacks → Qt thread
# ──────────────────────────────────────────────────────────────────

class _SignalBridge(QObject):
    log_signal = pyqtSignal(str)
    state_signal = pyqtSignal(str)
    stats_signal = pyqtSignal(object)
    failure_screenshot_signal = pyqtSignal(object, str)


# ──────────────────────────────────────────────────────────────────
# Main Window
# ──────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    """Application main window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoClick Vision")
        self.setMinimumSize(960, 640)

        # ── Core components ──────────────────────────────────────
        self.capture = ScreenCapture()
        self.matcher = ImageMatcher()
        self.clicker = Clicker()
        self.config_mgr = ConfigManager(auto_save=False)
        self.config_mgr.new_task()

        # Signal bridge
        self._bridge = _SignalBridge()
        self._bridge.log_signal.connect(self._on_log)
        self._bridge.state_signal.connect(self._on_state_change)
        self._bridge.stats_signal.connect(self._on_stats_update)
        self._bridge.failure_screenshot_signal.connect(self._on_failure_screenshot)

        self.scheduler = SequenceScheduler(
            capture=self.capture,
            matcher=self.matcher,
            clicker=self.clicker,
            on_log=lambda msg: self._bridge.log_signal.emit(msg),
            on_state_change=lambda s: self._bridge.state_signal.emit(s.value),
            on_stats_update=lambda s: self._bridge.stats_signal.emit(s),
            on_failure_screenshot=lambda img, tag: self._bridge.failure_screenshot_signal.emit(img, tag),
        )

        self.watchdog = Watchdog(
            on_freeze=self._on_watchdog_freeze,
            on_inactivity=self._on_watchdog_inactivity,
            on_exception=self._on_watchdog_exception,
        )

        # ── Build UI ─────────────────────────────────────────────
        self._build_toolbar()
        self._build_central()
        self._build_statusbar()
        self._build_tray_icon()
        self._register_hotkeys()

    # ═════════════════════════════════════════════════════════════
    # UI construction
    # ═════════════════════════════════════════════════════════════

    def _build_toolbar(self):
        tb = QToolBar("Main Toolbar")
        tb.setMovable(False)
        self.addToolBar(tb)

        self._act_start = QAction("▶ Start", self)
        self._act_start.triggered.connect(self._on_start)
        tb.addAction(self._act_start)

        self._act_pause = QAction("⏸ Pause", self)
        self._act_pause.triggered.connect(self._on_pause)
        self._act_pause.setEnabled(False)
        tb.addAction(self._act_pause)

        self._act_stop = QAction("⏹ Stop", self)
        self._act_stop.triggered.connect(self._on_stop)
        self._act_stop.setEnabled(False)
        tb.addAction(self._act_stop)

        tb.addSeparator()

        act_open = QAction("📂 Open", self)
        act_open.triggered.connect(self._on_open_config)
        tb.addAction(act_open)

        act_save = QAction("💾 Save", self)
        act_save.triggered.connect(self._on_save_config)
        tb.addAction(act_save)

        act_save_as = QAction("📄 Save As…", self)
        act_save_as.triggered.connect(self._on_save_as_config)
        tb.addAction(act_save_as)

    def _build_central(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: tabs for Button editor + Sequence editor
        left_tabs = QTabWidget()
        self.button_editor = ButtonEditor(self.config_mgr, self.capture, self.matcher)
        self.sequence_editor = SequenceEditor(self.config_mgr)
        left_tabs.addTab(self.button_editor, "Buttons")
        left_tabs.addTab(self.sequence_editor, "Sequence")

        # Right: log viewer
        self.log_viewer = LogViewer()

        splitter.addWidget(left_tabs)
        splitter.addWidget(self.log_viewer)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        self.setCentralWidget(splitter)

    def _build_statusbar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)

        self._lbl_state = QLabel("Idle")
        self._lbl_step = QLabel("Step: –")
        self._lbl_round = QLabel("Round: –")
        self._lbl_elapsed = QLabel("Elapsed: 0s")
        self._progress = QProgressBar()
        self._progress.setMaximumWidth(200)
        self._progress.setValue(0)

        sb.addWidget(self._lbl_state)
        sb.addWidget(self._lbl_step)
        sb.addWidget(self._lbl_round)
        sb.addWidget(self._lbl_elapsed)
        sb.addPermanentWidget(self._progress)

    def _build_tray_icon(self):
        self._tray = QSystemTrayIcon(self)
        self._tray.setToolTip("AutoClick Vision")
        menu = QMenu()
        menu.addAction("Show").triggered.connect(self.showNormal)
        menu.addAction("Quit").triggered.connect(QApplication.quit)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        # Icon will be set only if an icon file exists
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
        if icon_path.exists():
            self._tray.setIcon(QIcon(str(icon_path)))
        self._tray.show()

    # ═════════════════════════════════════════════════════════════
    # Global hotkeys
    # ═════════════════════════════════════════════════════════════

    def _register_hotkeys(self):
        try:
            keyboard.add_hotkey("F9", self._on_start)
            keyboard.add_hotkey("F10", self._on_pause)
            keyboard.add_hotkey("F11", self._on_stop)
        except Exception as e:
            logger.warning("Could not register global hotkeys: %s", e)

    # ═════════════════════════════════════════════════════════════
    # Task control slots
    # ═════════════════════════════════════════════════════════════

    def _build_task_config(self) -> TaskConfig:
        """Collect the current UI state into a TaskConfig."""
        task = self.config_mgr.task or TaskConfig()
        task.buttons = self.button_editor.get_button_configs()
        task.steps = self.sequence_editor.get_step_configs()
        seq_settings = self.sequence_editor.get_loop_settings()
        task.loop_count = seq_settings.get("loop_count", 50)
        task.round_interval = seq_settings.get("round_interval", 10.0)
        task.scheduled_start = seq_settings.get("scheduled_start")
        # Apply matcher settings
        self.matcher.grayscale = False
        self.matcher.multi_scale = False
        return task

    def _on_start(self):
        if self.scheduler.state == TaskState.PAUSED:
            self.scheduler.resume()
            return
        task = self._build_task_config()
        if not task.steps:
            QMessageBox.warning(self, "No Steps", "Please add at least one step to the sequence.")
            return
        self.scheduler.start(task)
        self.watchdog.start()
        self._act_start.setEnabled(False)
        self._act_pause.setEnabled(True)
        self._act_stop.setEnabled(True)

    def _on_pause(self):
        if self.scheduler.state == TaskState.RUNNING:
            self.scheduler.pause()
        elif self.scheduler.state == TaskState.PAUSED:
            self.scheduler.resume()

    def _on_stop(self):
        self.scheduler.stop()
        self.watchdog.stop()
        self._act_start.setEnabled(True)
        self._act_pause.setEnabled(False)
        self._act_stop.setEnabled(False)

    # ═════════════════════════════════════════════════════════════
    # Config I/O slots
    # ═════════════════════════════════════════════════════════════

    def _on_open_config(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Config", "", "Config Files (*.json *.yaml *.yml)"
        )
        if path:
            try:
                task = self.config_mgr.load(path)
                self.button_editor.load_from_task(task)
                self.sequence_editor.load_from_task(task)
                self.log_viewer.append_log(f"Config loaded: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _on_save_config(self):
        try:
            self.config_mgr.set_task(self._build_task_config())
            if self.config_mgr.current_path:
                self.config_mgr.save()
                self.log_viewer.append_log(f"Config saved: {self.config_mgr.current_path}")
            else:
                self._on_save_as_config()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_save_as_config(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Config As", "", "JSON (*.json);;YAML (*.yaml)"
        )
        if path:
            try:
                self.config_mgr.set_task(self._build_task_config())
                self.config_mgr.save(path)
                self.log_viewer.append_log(f"Config saved: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    # ═════════════════════════════════════════════════════════════
    # Scheduler callbacks (arrive on Qt thread via signal bridge)
    # ═════════════════════════════════════════════════════════════

    def _on_log(self, msg: str):
        self.log_viewer.append_log(msg)
        self.watchdog.heartbeat()
        self.watchdog.report_activity()

    def _on_state_change(self, state_value: str):
        state = TaskState(state_value)
        self._lbl_state.setText(state.value.capitalize())
        if state in (TaskState.FINISHED, TaskState.STOPPED, TaskState.ERROR):
            self._act_start.setEnabled(True)
            self._act_pause.setEnabled(False)
            self._act_stop.setEnabled(False)
            self.watchdog.stop()
            if state == TaskState.FINISHED:
                self._tray.showMessage("AutoClick Vision", "Task finished!", QSystemTrayIcon.MessageIcon.Information)
            elif state == TaskState.ERROR:
                self._tray.showMessage("AutoClick Vision", "Task error!", QSystemTrayIcon.MessageIcon.Critical)
        elif state == TaskState.PAUSED:
            self._act_start.setEnabled(True)
            self._act_pause.setEnabled(True)

    def _on_stats_update(self, stats: RunStats):
        self._lbl_step.setText(f"Step: {stats.current_step}/{stats.total_steps}")
        total = stats.total_rounds if stats.total_rounds > 0 else "∞"
        self._lbl_round.setText(f"Round: {stats.rounds_completed}/{total}")
        mins, secs = divmod(int(stats.elapsed), 60)
        self._lbl_elapsed.setText(f"Elapsed: {mins}m {secs}s")
        if stats.total_rounds > 0:
            pct = int(stats.rounds_completed / stats.total_rounds * 100)
            self._progress.setValue(pct)
        else:
            self._progress.setValue(0)

    def _on_failure_screenshot(self, image: np.ndarray, tag: str):
        """Save a failure screenshot and pass it to the log viewer."""
        import cv2
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{ts}_{tag}.png"
        fpath = _SCREENSHOTS_DIR / fname
        cv2.imwrite(str(fpath), image)
        self.log_viewer.add_screenshot(str(fpath), tag)

    # ═════════════════════════════════════════════════════════════
    # Watchdog callbacks (may come from background thread)
    # ═════════════════════════════════════════════════════════════

    def _on_watchdog_freeze(self):
        self._bridge.log_signal.emit("[WATCHDOG] ⚠ Freeze detected — consider restarting")
        self._tray.showMessage("AutoClick Vision", "Watchdog: freeze detected!", QSystemTrayIcon.MessageIcon.Warning)

    def _on_watchdog_inactivity(self):
        self._bridge.log_signal.emit("[WATCHDOG] ⚠ Prolonged screen inactivity")

    def _on_watchdog_exception(self, exc: Exception):
        self._bridge.log_signal.emit(f"[WATCHDOG] ✖ Exception: {exc}")

    # ═════════════════════════════════════════════════════════════
    # Tray / close overrides
    # ═════════════════════════════════════════════════════════════

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def closeEvent(self, event):
        """Minimize to tray instead of closing."""
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "AutoClick Vision",
            "Running in background. Double-click tray icon to restore.",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )
