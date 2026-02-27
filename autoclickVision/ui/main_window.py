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
from ..notifications import FailureRateMonitor, WebhookNotifier
from .button_editor import ButtonEditor
from .log_viewer import LogViewer
from .sequence_editor import SequenceEditor
from .settings_dialog import SettingsDialog

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
    tray_message_signal = pyqtSignal(str, str, int)  # title, message, icon_type


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

        # Application-wide settings
        self._settings: dict = {
            "grayscale": False,
            "multi_scale": False,
            "scale_min": 0.7,
            "scale_max": 1.3,
            "scale_step": 0.05,
            "use_bezier": False,
            "use_directinput": False,
            "archive_screenshots": True,
            "failure_rate_threshold": 0.5,
            "failure_rate_window": 20,
            "webhooks": [],
            "stop_after_consecutive_failures": 0,
            "stop_after_duration_minutes": 0,
        }

        # Webhook notifier
        self.webhook_notifier = WebhookNotifier()

        # Failure-rate monitor
        self.failure_monitor = FailureRateMonitor(
            threshold=0.5,
            window=20,
            on_alert=self._on_failure_rate_alert,
        )

        self._last_summary_round: int = 0

        # Signal bridge
        self._bridge = _SignalBridge()
        self._bridge.log_signal.connect(self._on_log)
        self._bridge.state_signal.connect(self._on_state_change)
        self._bridge.stats_signal.connect(self._on_stats_update)
        self._bridge.failure_screenshot_signal.connect(self._on_failure_screenshot)
        self._bridge.tray_message_signal.connect(self._on_tray_message)

        self.scheduler = SequenceScheduler(
            capture=self.capture,
            matcher=self.matcher,
            clicker=self.clicker,
            on_log=lambda msg: self._bridge.log_signal.emit(msg),
            on_state_change=lambda s: self._bridge.state_signal.emit(s.value),
            on_stats_update=lambda s: self._bridge.stats_signal.emit(s),
            on_failure_screenshot=lambda img, tag: self._bridge.failure_screenshot_signal.emit(img, tag),
            on_chain_task=self._on_chain_task,
            on_recognition_result=self._on_recognition_result,
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

        tb.addSeparator()

        act_settings = QAction("Settings", self)
        act_settings.triggered.connect(self._on_settings)
        tb.addAction(act_settings)

    def _build_central(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: tabs for Button editor + Sequence editor
        left_tabs = QTabWidget()
        self.button_editor = ButtonEditor(self.config_mgr, self.capture, self.matcher)
        self.sequence_editor = SequenceEditor(self.config_mgr)

        # Keep the shared task's button list in sync whenever buttons change
        self.button_editor.buttons_changed.connect(self._sync_buttons_to_task)

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
        # Load icon via QPixmap (more reliable than QIcon(path) for .ico)
        icon = self._load_app_icon()
        if not icon.isNull():
            self._tray.setIcon(icon)
            self.setWindowIcon(icon)
        self._tray.show()

    @staticmethod
    def _load_app_icon() -> QIcon:
        """Try several candidate paths and load via QPixmap for reliability."""
        from PyQt6.QtGui import QPixmap
        base = Path(__file__).resolve().parent.parent
        for rel in ("assets/icon.ico", "icon.ico", "assets/icon.png"):
            p = base / rel
            if p.exists():
                pm = QPixmap(str(p))
                if not pm.isNull():
                    return QIcon(pm)
        return QIcon()

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

    def _sync_buttons_to_task(self):
        """Push the button editor's current list into the shared task config
        so the sequence editor can see them immediately."""
        task = self.config_mgr.task
        if task is not None:
            task.buttons = self.button_editor.get_button_configs()

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
        # Apply matcher settings from the settings dialog
        self.matcher.grayscale = self._settings.get("grayscale", False)
        self.matcher.multi_scale = self._settings.get("multi_scale", False)
        self.matcher.scale_range = (
            self._settings.get("scale_min", 0.7),
            self._settings.get("scale_max", 1.3),
        )
        self.matcher.scale_step = self._settings.get("scale_step", 0.05)
        # Apply clicker settings
        self.clicker.use_bezier = self._settings.get("use_bezier", False)
        # Update failure monitor parameters
        self.failure_monitor.threshold = self._settings.get("failure_rate_threshold", 0.5)
        self.failure_monitor.window = self._settings.get("failure_rate_window", 20)
        self.failure_monitor.reset()
        # Stop conditions
        task.stop_after_consecutive_failures = self._settings.get("stop_after_consecutive_failures", 0)
        task.stop_after_duration_minutes = self._settings.get("stop_after_duration_minutes", 0)
        return task

    def _on_start(self):
        if self.scheduler.state == TaskState.PAUSED:
            self.scheduler.resume()
            return
        task = self._build_task_config()
        if not task.steps:
            QMessageBox.warning(self, "No Steps", "Please add at least one step to the sequence.")
            return
        # Sync webhook registrations
        self._sync_webhooks()
        self._last_summary_round = 0
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
                self._bridge.tray_message_signal.emit(
                    "AutoClick Vision", "Task finished!",
                    QSystemTrayIcon.MessageIcon.Information.value,
                )
                self.webhook_notifier.notify("Task finished")
            elif state == TaskState.ERROR:
                self._bridge.tray_message_signal.emit(
                    "AutoClick Vision", "Task error!",
                    QSystemTrayIcon.MessageIcon.Critical.value,
                )
                self.webhook_notifier.notify("Task error")
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
        # Emit per-round summary when a round completes
        if stats.rounds_completed > self._last_summary_round:
            self._last_summary_round = stats.rounds_completed
            rs = stats.current_round_stats
            self.log_viewer.add_round_summary(
                stats.rounds_completed, rs.success, rs.failure, rs.skipped
            )

    def _on_failure_screenshot(self, image: np.ndarray, tag: str):
        """Save a failure screenshot and optionally archive it."""
        if not self._settings.get("archive_screenshots", True):
            return
        import cv2
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{ts}_{tag}.png"
        fpath = _SCREENSHOTS_DIR / fname
        cv2.imwrite(str(fpath), image)
        self.log_viewer.add_screenshot(str(fpath), tag)

    def _on_tray_message(self, title: str, message: str, icon_type: int):
        """Thread-safe tray notification (always runs on the Qt main thread)."""
        self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon(icon_type))

    # ═════════════════════════════════════════════════════════════
    # Settings / chain / failure-rate callbacks
    # ═════════════════════════════════════════════════════════════

    def _on_settings(self):
        """Open the settings dialog and apply changes."""
        dlg = SettingsDialog(self._settings, parent=self)
        if dlg.exec():
            self._settings.update(dlg.get_settings())
            self.log_viewer.append_log("Settings updated")

    def _on_chain_task(self, path: str):
        """Load a chained task config from *path* and start it."""
        try:
            task = self.config_mgr.load(path)
            self.button_editor.load_from_task(task)
            self.sequence_editor.load_from_task(task)
            self.log_viewer.append_log(f"Chain task loaded: {path}")
            self.scheduler.start(task)
            self.watchdog.start()
        except Exception as e:
            logger.error("Chain task failed: %s", e)
            self._bridge.log_signal.emit(f"Chain task error: {e}")

    def _on_recognition_result(self, success: bool):
        """Feed the failure-rate monitor with each recognition outcome."""
        self.failure_monitor.record(success)

    def _on_failure_rate_alert(self, rate: float, failures: int, total: int):
        """Called when the failure rate exceeds the configured threshold."""
        msg = f"High failure rate: {rate:.0%} ({failures}/{total})"
        logger.warning(msg)
        self._bridge.log_signal.emit(f"[ALERT] {msg}")
        self._bridge.tray_message_signal.emit(
            "AutoClick Vision", msg,
            QSystemTrayIcon.MessageIcon.Warning.value,
        )
        # Notify via webhooks
        self.webhook_notifier.notify(f"Failure-rate alert: {msg}")
        # Stop if consecutive-failure limit exceeded
        stop_limit = self._settings.get("stop_after_consecutive_failures", 0)
        if stop_limit > 0 and failures >= stop_limit:
            self._bridge.log_signal.emit("[ALERT] Consecutive failure limit reached — stopping")
            self.scheduler.stop()

    def _sync_webhooks(self):
        """Synchronise webhook URLs from settings into the notifier."""
        # Clear existing hooks and re-register from settings
        self.webhook_notifier._hooks.clear()
        for i, w in enumerate(self._settings.get("webhooks", [])):
            url = w.get("url", "").strip()
            name = w.get("name", f"hook_{i}")
            if url:
                self.webhook_notifier.register(name, url)

    # ═════════════════════════════════════════════════════════════
    # Watchdog callbacks (may come from background thread)
    # ═════════════════════════════════════════════════════════════

    def _on_watchdog_freeze(self):
        self._bridge.log_signal.emit("[WATCHDOG] \u26a0 Freeze detected \u2014 attempting auto-restart")
        self._bridge.tray_message_signal.emit(
            "AutoClick Vision", "Watchdog: freeze detected \u2014 restarting!",
            QSystemTrayIcon.MessageIcon.Warning.value,
        )
        # Auto-restart: stop + re-start the scheduler with the same task
        if self.scheduler._task is not None:
            task = self.scheduler._task
            self.scheduler.stop()
            self.watchdog.stop()
            import time; time.sleep(0.3)
            self.scheduler.start(task)
            self.watchdog.start()
            self._bridge.log_signal.emit("[WATCHDOG] \u21bb Task auto-restarted")

    def _on_watchdog_inactivity(self):
        self._bridge.log_signal.emit("[WATCHDOG] \u26a0 Prolonged screen inactivity")
        self._bridge.tray_message_signal.emit(
            "AutoClick Vision", "Watchdog: prolonged screen inactivity",
            QSystemTrayIcon.MessageIcon.Warning.value,
        )

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
