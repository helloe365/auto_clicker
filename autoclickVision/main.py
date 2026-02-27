"""
AutoClick Vision — main entry point
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# ── Logging setup ────────────────────────────────────────────────
_LOG_DIR = Path(__file__).resolve().parent / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(_LOG_DIR / "autoclickvision.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("autoclickvision")

# ── Global error handler ────────────────────────────────────────

from autoclickVision.notifications import install_global_exception_handler  # noqa: E402


def _show_alert(msg: str):
    """Show a Qt error dialog (only when the app is running)."""
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance()
        if app:
            QMessageBox.critical(None, "AutoClick Vision — Error", msg)
    except Exception:
        pass


install_global_exception_handler(alert_callback=_show_alert)

# ── Application launch ──────────────────────────────────────────

def _choose_language_dialog():
    """Show a first-run language chooser and return 'en' or 'zh'."""
    from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QDialogButtonBox

    dlg = QDialog()
    dlg.setWindowTitle("AutoClick Vision")
    dlg.setMinimumWidth(320)
    layout = QVBoxLayout(dlg)

    lbl = QLabel("Please select your language / 请选择您的语言:")
    lbl.setStyleSheet("font-size: 14px; margin-bottom: 8px;")
    layout.addWidget(lbl)

    combo = QComboBox()
    combo.addItem("English", "en")
    combo.addItem("中文 (Chinese)", "zh")
    combo.setStyleSheet("font-size: 13px; padding: 4px;")
    layout.addWidget(combo)

    bbox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
    bbox.accepted.connect(dlg.accept)
    layout.addWidget(bbox)

    dlg.exec()
    return combo.currentData() or "en"


def main():
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QIcon, QPixmap
    from autoclickVision.i18n import init_language, save_preference, set_language, _load_preference

    app = QApplication(sys.argv)
    app.setApplicationName("AutoClick Vision")
    app.setOrganizationName("AutoClickVision")

    # Set application-level icon (loaded via QPixmap for reliability)
    icon_path = Path(__file__).resolve().parent / "assets" / "icon.ico"
    if icon_path.exists():
        pm = QPixmap(str(icon_path))
        if not pm.isNull():
            app.setWindowIcon(QIcon(pm))

    # ── Language initialization ──────────────────────────────
    saved = _load_preference()
    if saved in ("en", "zh"):
        set_language(saved)
    else:
        # First run: show language chooser
        lang = _choose_language_dialog()
        set_language(lang)
        save_preference(lang)

    from autoclickVision.ui.main_window import MainWindow

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
