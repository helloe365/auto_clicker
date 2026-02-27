"""
Sequence Editor Panel
Visual drag-and-drop step ordering (card-based), per-step config, text/visual
mode toggle, loop configuration, and schedule configuration.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..config.config_manager import ConfigManager
from ..core.scheduler import (
    ButtonConfig,
    DelayConfig,
    StepCondition,
    StepConfig,
    TaskConfig,
    parse_sequence_text,
)

logger = logging.getLogger(__name__)


class StepCard(QWidget):
    """A compact card representing one sequence step."""

    removed = pyqtSignal(object)
    changed = pyqtSignal()

    def __init__(self, step: StepConfig, available_buttons: List[ButtonConfig], parent=None):
        super().__init__(parent)
        self.step = step
        self._buttons = available_buttons
        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.setStyleSheet("StepCard { border: 1px solid #aaa; border-radius: 4px; background: #f9f9f9; }")

        # Button selection (multi-select via comma-separated IDs shown as names)
        self._combo_button = QComboBox()
        for b in self._buttons:
            self._combo_button.addItem(b.name or b.id, b.id)
        # Pre-select first matching button
        if self.step.button_ids:
            idx = next(
                (i for i, b in enumerate(self._buttons) if b.id in self.step.button_ids),
                0,
            )
            self._combo_button.setCurrentIndex(idx)
        self._combo_button.currentIndexChanged.connect(self._on_changed)
        layout.addRow("Button:", self._combo_button)

        # Repeat
        self._spin_repeat = QSpinBox()
        self._spin_repeat.setRange(1, 9999)
        self._spin_repeat.setValue(self.step.repeat)
        self._spin_repeat.valueChanged.connect(self._on_changed)
        layout.addRow("Repeat:", self._spin_repeat)

        # Intra-delay
        self._spin_intra = QDoubleSpinBox()
        self._spin_intra.setRange(0, 300)
        self._spin_intra.setValue(self.step.intra_delay.fixed_value)
        self._spin_intra.setSuffix(" s")
        self._spin_intra.valueChanged.connect(self._on_changed)
        layout.addRow("Intra Delay:", self._spin_intra)

        # Inter-delay
        self._spin_inter = QDoubleSpinBox()
        self._spin_inter.setRange(0, 300)
        self._spin_inter.setValue(self.step.inter_delay.fixed_value)
        self._spin_inter.setSuffix(" s")
        self._spin_inter.valueChanged.connect(self._on_changed)
        layout.addRow("Inter Delay:", self._spin_inter)

        # Condition
        self._combo_cond = QComboBox()
        for c in StepCondition:
            self._combo_cond.addItem(c.value, c)
        idx = self._combo_cond.findData(self.step.condition)
        self._combo_cond.setCurrentIndex(max(idx, 0))
        self._combo_cond.currentIndexChanged.connect(self._on_changed)
        layout.addRow("Condition:", self._combo_cond)

        # Condition timeout
        self._spin_timeout = QDoubleSpinBox()
        self._spin_timeout.setRange(0, 600)
        self._spin_timeout.setValue(self.step.condition_timeout)
        self._spin_timeout.setSuffix(" s")
        self._spin_timeout.valueChanged.connect(self._on_changed)
        layout.addRow("Timeout:", self._spin_timeout)

        # Remove button
        btn_remove = QPushButton("✕ Remove")
        btn_remove.clicked.connect(lambda: self.removed.emit(self))
        layout.addRow(btn_remove)

    def _on_changed(self):
        bid = self._combo_button.currentData()
        self.step.button_ids = [bid] if bid else []
        self.step.repeat = self._spin_repeat.value()
        self.step.intra_delay = DelayConfig(mode="fixed", fixed_value=self._spin_intra.value())
        self.step.inter_delay = DelayConfig(mode="fixed", fixed_value=self._spin_inter.value())
        self.step.condition = self._combo_cond.currentData() or StepCondition.NONE
        self.step.condition_timeout = self._spin_timeout.value()
        self.changed.emit()

    def sync_from_step(self):
        """Re-populate widgets from self.step."""
        self._spin_repeat.setValue(self.step.repeat)


# ──────────────────────────────────────────────────────────────────
# Sequence Editor
# ──────────────────────────────────────────────────────────────────

class SequenceEditor(QWidget):
    """Panel for editing the click sequence, with text & visual modes."""

    def __init__(self, config_mgr: ConfigManager, parent=None):
        super().__init__(parent)
        self._config = config_mgr
        self._steps: List[StepConfig] = []
        self._cards: List[StepCard] = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        # Mode toggle
        mode_row = QHBoxLayout()
        self._btn_visual = QPushButton("Visual Mode")
        self._btn_visual.setCheckable(True)
        self._btn_visual.setChecked(True)
        self._btn_visual.clicked.connect(lambda: self._switch_mode(0))
        self._btn_text = QPushButton("Text Mode")
        self._btn_text.setCheckable(True)
        self._btn_text.clicked.connect(lambda: self._switch_mode(1))
        mode_row.addWidget(self._btn_visual)
        mode_row.addWidget(self._btn_text)
        root.addLayout(mode_row)

        # Stacked pages
        self._stack = QStackedWidget()

        # -- Page 0: Visual mode ------
        visual_page = QWidget()
        vl = QVBoxLayout(visual_page)
        self._card_container = QVBoxLayout()
        vl.addLayout(self._card_container)
        btn_add_step = QPushButton("+ Add Step")
        btn_add_step.clicked.connect(self._on_add_step)
        vl.addWidget(btn_add_step)

        # Move up/down
        move_row = QHBoxLayout()
        btn_up = QPushButton("↑ Up")
        btn_up.clicked.connect(self._on_move_up)
        btn_down = QPushButton("↓ Down")
        btn_down.clicked.connect(self._on_move_down)
        move_row.addWidget(btn_up)
        move_row.addWidget(btn_down)
        vl.addLayout(move_row)
        vl.addStretch()
        self._stack.addWidget(visual_page)

        # -- Page 1: Text mode ------
        text_page = QWidget()
        tl = QVBoxLayout(text_page)
        tl.addWidget(QLabel("Enter sequence (e.g. A*3 -> B -> C*2):"))
        self._text_edit = QPlainTextEdit()
        self._text_edit.setPlaceholderText("A*3 -> B -> C*2")
        tl.addWidget(self._text_edit)
        btn_apply_text = QPushButton("Apply")
        btn_apply_text.clicked.connect(self._on_apply_text)
        tl.addWidget(btn_apply_text)
        tl.addStretch()
        self._stack.addWidget(text_page)

        root.addWidget(self._stack)

        # ── Loop / schedule settings ────────────────
        grp = QGroupBox("Loop & Schedule")
        gl = QFormLayout()

        self._spin_loop = QSpinBox()
        self._spin_loop.setRange(0, 999999)
        self._spin_loop.setValue(50)
        self._spin_loop.setSpecialValueText("∞ (infinite)")
        gl.addRow("Loop Count:", self._spin_loop)

        self._spin_interval = QDoubleSpinBox()
        self._spin_interval.setRange(0, 86400)
        self._spin_interval.setValue(10.0)
        self._spin_interval.setSuffix(" s")
        gl.addRow("Round Interval:", self._spin_interval)

        self._chk_scheduled = QCheckBox("Scheduled Start")
        self._dt_scheduled = QDateTimeEdit()
        self._dt_scheduled.setEnabled(False)
        self._chk_scheduled.toggled.connect(self._dt_scheduled.setEnabled)
        gl.addRow(self._chk_scheduled, self._dt_scheduled)

        grp.setLayout(gl)
        root.addWidget(grp)

    # ═════════════════════════════════════════════════════════════
    # Mode switching
    # ═════════════════════════════════════════════════════════════

    def _switch_mode(self, idx: int):
        self._stack.setCurrentIndex(idx)
        self._btn_visual.setChecked(idx == 0)
        self._btn_text.setChecked(idx == 1)
        if idx == 1:
            # Populate text from current steps
            self._text_edit.setPlainText(self._steps_to_text())

    def _steps_to_text(self) -> str:
        """Convert current steps back to text representation."""
        parts = []
        task = self._config.task
        for s in self._steps:
            names = []
            for bid in s.button_ids:
                b = task.button_by_id(bid) if task else None
                names.append(b.name if b else bid)
            label = "|".join(names)
            if s.repeat > 1:
                label += f"*{s.repeat}"
            parts.append(label)
        return " -> ".join(parts)

    # ═════════════════════════════════════════════════════════════
    # Visual mode actions
    # ═════════════════════════════════════════════════════════════

    def _available_buttons(self) -> List[ButtonConfig]:
        task = self._config.task
        return list(task.buttons) if task else []

    def _on_add_step(self):
        step = StepConfig()
        buttons = self._available_buttons()
        if buttons:
            step.button_ids = [buttons[0].id]
        self._steps.append(step)
        self._rebuild_cards()

    def _on_remove_step(self, card: StepCard):
        idx = self._cards.index(card)
        self._steps.pop(idx)
        self._rebuild_cards()

    def _on_move_up(self):
        """Move the last-edited card up (for simplicity, we move the last step)."""
        if len(self._steps) < 2:
            return
        # Move the last step up by one
        self._steps[-1], self._steps[-2] = self._steps[-2], self._steps[-1]
        self._rebuild_cards()

    def _on_move_down(self):
        if len(self._steps) < 2:
            return
        self._steps[0], self._steps[1] = self._steps[1], self._steps[0]
        self._rebuild_cards()

    def _rebuild_cards(self):
        # Clear existing cards
        for c in self._cards:
            self._card_container.removeWidget(c)
            c.deleteLater()
        self._cards.clear()

        buttons = self._available_buttons()
        for step in self._steps:
            card = StepCard(step, buttons)
            card.removed.connect(self._on_remove_step)
            self._card_container.addWidget(card)
            self._cards.append(card)

    # ═════════════════════════════════════════════════════════════
    # Text mode
    # ═════════════════════════════════════════════════════════════

    def _on_apply_text(self):
        text = self._text_edit.toPlainText().strip()
        if not text:
            self._steps.clear()
            self._rebuild_cards()
            return
        task = self._config.task
        button_map = {}
        if task:
            for b in task.buttons:
                button_map[b.name] = b.id
                button_map[b.id] = b.id
        self._steps = parse_sequence_text(text, button_map)
        self._rebuild_cards()

    # ═════════════════════════════════════════════════════════════
    # Public API
    # ═════════════════════════════════════════════════════════════

    def get_step_configs(self) -> List[StepConfig]:
        return list(self._steps)

    def get_loop_settings(self) -> Dict[str, Any]:
        settings: Dict[str, Any] = {
            "loop_count": self._spin_loop.value(),
            "round_interval": self._spin_interval.value(),
            "scheduled_start": None,
        }
        if self._chk_scheduled.isChecked():
            settings["scheduled_start"] = self._dt_scheduled.dateTime().toString(Qt.DateFormat.ISODate)
        return settings

    def load_from_task(self, task: TaskConfig):
        self._steps = list(task.steps)
        self._spin_loop.setValue(task.loop_count)
        self._spin_interval.setValue(task.round_interval)
        if task.scheduled_start:
            self._chk_scheduled.setChecked(True)
            from PyQt6.QtCore import QDateTime
            self._dt_scheduled.setDateTime(QDateTime.fromString(task.scheduled_start, Qt.DateFormat.ISODate))
        self._rebuild_cards()
