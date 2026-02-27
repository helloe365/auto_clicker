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

def main():
    from PyQt6.QtWidgets import QApplication
    from autoclickVision.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("AutoClick Vision")
    app.setOrganizationName("AutoClickVision")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
