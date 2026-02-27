"""
Button Configuration Panel
Drag-and-drop image upload, per-button config (name, confidence, click type, ROI),
test recognition, image preview with thumbnails, and a built-in screen-region
capture tool.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QMimeData, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QImage, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRubberBand,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..config.config_manager import ConfigManager
from ..core.capture import ScreenCapture
from ..core.matcher import FailureAction, ImageMatcher, MatchResult
from ..core.scheduler import ButtonConfig, ClickType, TaskConfig

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# Region capture overlay
# ──────────────────────────────────────────────────────────────────

class RegionCaptureOverlay(QWidget):
    """Full-screen translucent overlay that lets the user draw a rectangle."""

    region_selected = pyqtSignal(int, int, int, int)  # x, y, w, h

    def __init__(self, screenshot: np.ndarray, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # Convert BGR screenshot to QPixmap for background
        h, w, ch = screenshot.shape
        bytes_per_line = ch * w
        rgb = cv2.cvtColor(screenshot, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        self._bg_pixmap = QPixmap.fromImage(qimg)

        self._origin = None
        self._rubber = QRubberBand(QRubberBand.Shape.Rectangle, self)

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._bg_pixmap)

    def mousePressEvent(self, event):
        self._origin = event.pos()
        self._rubber.setGeometry(self._origin.x(), self._origin.y(), 0, 0)
        self._rubber.show()

    def mouseMoveEvent(self, event):
        if self._origin:
            rect = self._make_rect(self._origin, event.pos())
            self._rubber.setGeometry(rect)

    def mouseReleaseEvent(self, event):
        if self._origin:
            rect = self._make_rect(self._origin, event.pos())
            self._rubber.hide()
            self._origin = None
            if rect.width() > 5 and rect.height() > 5:
                self.region_selected.emit(rect.x(), rect.y(), rect.width(), rect.height())
            self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    @staticmethod
    def _make_rect(p1, p2):
        from PyQt6.QtCore import QRect, QPoint
        return QRect(
            min(p1.x(), p2.x()), min(p1.y(), p2.y()),
            abs(p2.x() - p1.x()), abs(p2.y() - p1.y()),
        )


# ──────────────────────────────────────────────────────────────────
# Button Editor Panel
# ──────────────────────────────────────────────────────────────────

class ButtonEditor(QWidget):
    """Panel for managing button configurations."""

    buttons_changed = pyqtSignal()

    def __init__(
        self,
        config_mgr: ConfigManager,
        capture: ScreenCapture,
        matcher: ImageMatcher,
        parent=None,
    ):
        super().__init__(parent)
        self._config = config_mgr
        self._capture = capture
        self._matcher = matcher
        self._buttons: List[ButtonConfig] = []
        self._current_idx: int = -1
        self._build_ui()
        self.setAcceptDrops(True)

    # ═════════════════════════════════════════════════════════════
    # UI
    # ═════════════════════════════════════════════════════════════

    def _build_ui(self):
        layout = QHBoxLayout(self)

        # Left: button list
        left = QVBoxLayout()
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_select)
        left.addWidget(self._list)

        btn_row = QHBoxLayout()
        self._btn_add = QPushButton("+ Add")
        self._btn_add.clicked.connect(self._on_add)
        self._btn_remove = QPushButton("– Remove")
        self._btn_remove.clicked.connect(self._on_remove)
        self._btn_import = QPushButton("📂 Import")
        self._btn_import.clicked.connect(self._on_import_images)
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_remove)
        btn_row.addWidget(self._btn_import)
        left.addLayout(btn_row)

        # Right: config form
        right = QVBoxLayout()

        # Thumbnail preview
        self._lbl_thumb = QLabel()
        self._lbl_thumb.setFixedSize(200, 120)
        self._lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_thumb.setStyleSheet("border: 1px solid #888;")
        right.addWidget(self._lbl_thumb)

        form = QFormLayout()

        self._edit_name = QLineEdit()
        self._edit_name.textChanged.connect(self._on_field_changed)
        form.addRow("Name:", self._edit_name)

        self._edit_image = QLineEdit()
        self._edit_image.setReadOnly(True)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._on_browse_image)
        img_row = QHBoxLayout()
        img_row.addWidget(self._edit_image)
        img_row.addWidget(browse_btn)
        form.addRow("Image:", img_row)

        self._spin_confidence = QDoubleSpinBox()
        self._spin_confidence.setRange(0.0, 1.0)
        self._spin_confidence.setSingleStep(0.05)
        self._spin_confidence.setValue(0.8)
        self._spin_confidence.valueChanged.connect(self._on_field_changed)
        form.addRow("Confidence:", self._spin_confidence)

        self._combo_click = QComboBox()
        for ct in ClickType:
            self._combo_click.addItem(ct.value, ct)
        self._combo_click.currentIndexChanged.connect(self._on_field_changed)
        form.addRow("Click Type:", self._combo_click)

        self._spin_offset = QSpinBox()
        self._spin_offset.setRange(0, 100)
        self._spin_offset.setSuffix(" px")
        self._spin_offset.valueChanged.connect(self._on_field_changed)
        form.addRow("Offset Range:", self._spin_offset)

        self._spin_retry = QSpinBox()
        self._spin_retry.setRange(0, 50)
        self._spin_retry.setValue(3)
        self._spin_retry.valueChanged.connect(self._on_field_changed)
        form.addRow("Retry Count:", self._spin_retry)

        self._spin_retry_interval = QDoubleSpinBox()
        self._spin_retry_interval.setRange(0.0, 60.0)
        self._spin_retry_interval.setValue(0.5)
        self._spin_retry_interval.setSuffix(" s")
        self._spin_retry_interval.valueChanged.connect(self._on_field_changed)
        form.addRow("Retry Interval:", self._spin_retry_interval)

        self._combo_fallback = QComboBox()
        for fa in FailureAction:
            self._combo_fallback.addItem(fa.value, fa)
        self._combo_fallback.currentIndexChanged.connect(self._on_field_changed)
        form.addRow("Fallback:", self._combo_fallback)

        # ROI
        self._edit_roi = QLineEdit()
        self._edit_roi.setPlaceholderText("x, y, w, h (blank = full screen)")
        self._edit_roi.textChanged.connect(self._on_field_changed)
        roi_btn = QPushButton("Select ROI…")
        roi_btn.clicked.connect(self._on_select_roi)
        roi_row = QHBoxLayout()
        roi_row.addWidget(self._edit_roi)
        roi_row.addWidget(roi_btn)
        form.addRow("ROI:", roi_row)

        right.addLayout(form)

        # Action buttons
        action_row = QHBoxLayout()
        self._btn_test = QPushButton("🔍 Test Recognition")
        self._btn_test.clicked.connect(self._on_test_recognition)
        self._btn_capture = QPushButton("✂ Capture from Screen")
        self._btn_capture.clicked.connect(self._on_capture_from_screen)
        action_row.addWidget(self._btn_test)
        action_row.addWidget(self._btn_capture)
        right.addLayout(action_row)

        right.addStretch()

        layout.addLayout(left, 2)
        layout.addLayout(right, 3)

    # ═════════════════════════════════════════════════════════════
    # Drag-and-drop support
    # ═════════════════════════════════════════════════════════════

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                self._add_button_from_image(path)

    # ═════════════════════════════════════════════════════════════
    # List management
    # ═════════════════════════════════════════════════════════════

    def _refresh_list(self):
        self._list.clear()
        for b in self._buttons:
            label = b.name or Path(b.image_path).stem if b.image_path else b.id
            self._list.addItem(label)
        self.buttons_changed.emit()

    def _on_select(self, idx: int):
        self._current_idx = idx
        if 0 <= idx < len(self._buttons):
            self._load_fields(self._buttons[idx])

    def _on_add(self):
        bc = ButtonConfig(name=f"Button_{len(self._buttons) + 1}")
        self._buttons.append(bc)
        self._refresh_list()
        self._list.setCurrentRow(len(self._buttons) - 1)

    def _on_remove(self):
        idx = self._current_idx
        if 0 <= idx < len(self._buttons):
            self._buttons.pop(idx)
            self._refresh_list()

    def _on_import_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import Button Images", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        for p in paths:
            self._add_button_from_image(p)

    def _add_button_from_image(self, path: str):
        name = Path(path).stem
        bc = ButtonConfig(name=name, image_path=path)
        self._buttons.append(bc)
        self._refresh_list()
        self._list.setCurrentRow(len(self._buttons) - 1)

    # ═════════════════════════════════════════════════════════════
    # Field ↔ model sync
    # ═════════════════════════════════════════════════════════════

    def _load_fields(self, b: ButtonConfig):
        self._edit_name.blockSignals(True)
        self._edit_name.setText(b.name)
        self._edit_name.blockSignals(False)

        self._edit_image.setText(b.image_path)
        self._update_thumbnail(b.image_path)

        self._spin_confidence.blockSignals(True)
        self._spin_confidence.setValue(b.confidence)
        self._spin_confidence.blockSignals(False)

        idx = self._combo_click.findData(b.click_type)
        self._combo_click.blockSignals(True)
        self._combo_click.setCurrentIndex(idx if idx >= 0 else 0)
        self._combo_click.blockSignals(False)

        self._spin_offset.blockSignals(True)
        self._spin_offset.setValue(b.click_offset_range)
        self._spin_offset.blockSignals(False)

        self._spin_retry.blockSignals(True)
        self._spin_retry.setValue(b.retry_count)
        self._spin_retry.blockSignals(False)

        self._spin_retry_interval.blockSignals(True)
        self._spin_retry_interval.setValue(b.retry_interval)
        self._spin_retry_interval.blockSignals(False)

        fi = self._combo_fallback.findData(b.fallback_action)
        self._combo_fallback.blockSignals(True)
        self._combo_fallback.setCurrentIndex(fi if fi >= 0 else 0)
        self._combo_fallback.blockSignals(False)

        self._edit_roi.blockSignals(True)
        if b.region:
            self._edit_roi.setText(", ".join(str(v) for v in b.region))
        else:
            self._edit_roi.setText("")
        self._edit_roi.blockSignals(False)

    def _on_field_changed(self):
        idx = self._current_idx
        if idx < 0 or idx >= len(self._buttons):
            return
        b = self._buttons[idx]
        b.name = self._edit_name.text()
        b.confidence = self._spin_confidence.value()
        b.click_type = self._combo_click.currentData() or ClickType.SINGLE
        b.click_offset_range = self._spin_offset.value()
        b.retry_count = self._spin_retry.value()
        b.retry_interval = self._spin_retry_interval.value()
        b.fallback_action = self._combo_fallback.currentData() or FailureAction.RETRY

        roi_text = self._edit_roi.text().strip()
        if roi_text:
            try:
                parts = [int(v.strip()) for v in roi_text.split(",")]
                if len(parts) == 4:
                    b.region = tuple(parts)
            except ValueError:
                pass
        else:
            b.region = None

        # Refresh the list label
        item = self._list.currentItem()
        if item is not None:
            item.setText(b.name or b.id)
        self.buttons_changed.emit()

    def _on_browse_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Button Image", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if path:
            self._edit_image.setText(path)
            if 0 <= self._current_idx < len(self._buttons):
                self._buttons[self._current_idx].image_path = path
            self._update_thumbnail(path)

    def _update_thumbnail(self, path: str):
        if path and os.path.isfile(path):
            pm = QPixmap(path).scaled(
                self._lbl_thumb.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._lbl_thumb.setPixmap(pm)
        else:
            self._lbl_thumb.clear()

    # ═════════════════════════════════════════════════════════════
    # Region capture from screen
    # ═════════════════════════════════════════════════════════════

    def _on_select_roi(self):
        ss = self._capture.capture_full()
        overlay = RegionCaptureOverlay(ss)
        overlay.region_selected.connect(self._on_roi_selected)
        overlay.show()

    def _on_roi_selected(self, x, y, w, h):
        self._edit_roi.setText(f"{x}, {y}, {w}, {h}")

    def _on_capture_from_screen(self):
        """Let the user draw a rectangle on the screen and save as button image."""
        ss = self._capture.capture_full()
        overlay = RegionCaptureOverlay(ss)

        def _handle_region(x, y, w, h):
            crop = ss[y: y + h, x: x + w]
            save_dir = Path(__file__).resolve().parent.parent / "assets" / "captures"
            save_dir.mkdir(parents=True, exist_ok=True)
            fname = f"capture_{uuid.uuid4().hex[:6]}.png"
            fpath = save_dir / fname
            cv2.imwrite(str(fpath), crop)
            self._add_button_from_image(str(fpath))

        overlay.region_selected.connect(_handle_region)
        overlay.show()

    # ═════════════════════════════════════════════════════════════
    # Test recognition
    # ═════════════════════════════════════════════════════════════

    def _on_test_recognition(self):
        idx = self._current_idx
        if idx < 0 or idx >= len(self._buttons):
            QMessageBox.warning(self, "No Button", "Select a button first.")
            return
        b = self._buttons[idx]
        if not b.image_path or not os.path.isfile(b.image_path):
            QMessageBox.warning(self, "No Image", "Button has no valid image path.")
            return

        ss = self._capture.capture_full()
        tpl = self._matcher.load_template(b.image_path)
        result = self._matcher.match(ss, tpl, confidence=b.confidence, region=b.region)

        if result.found and result.bounding_rect:
            bx, by, bw, bh = result.bounding_rect
            annotated = ss.copy()
            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (0, 255, 0), 3)
            cv2.putText(
                annotated,
                f"{result.confidence:.2f}",
                (bx, by - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )
            self._show_image_dialog(annotated, "Match Found")
        else:
            QMessageBox.information(
                self,
                "Not Found",
                f"Button not found (best confidence: {result.confidence:.2f})",
            )

    def _show_image_dialog(self, image: np.ndarray, title: str):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(800, 600)
        lbl = QLabel()
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pm = QPixmap.fromImage(qimg).scaled(780, 580, Qt.AspectRatioMode.KeepAspectRatio)
        lbl.setPixmap(pm)
        layout = QVBoxLayout(dlg)
        layout.addWidget(lbl)
        dlg.exec()

    # ═════════════════════════════════════════════════════════════
    # Public API (used by MainWindow)
    # ═════════════════════════════════════════════════════════════

    def get_button_configs(self) -> List[ButtonConfig]:
        return list(self._buttons)

    def load_from_task(self, task: TaskConfig):
        self._buttons = list(task.buttons)
        self._refresh_list()
        if self._buttons:
            self._list.setCurrentRow(0)
