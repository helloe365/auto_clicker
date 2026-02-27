"""
Error Handling & Notification Module
Global exception handler, failure-rate alerting, Webhook notifications
(Telegram / DingTalk / Slack), system tray popups, and screenshot archiving.
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

_LOGS_DIR = Path(__file__).resolve().parent / "logs"
_LOGS_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────
# Global exception handler
# ──────────────────────────────────────────────────────────────────

_original_excepthook = sys.excepthook
_ui_alert_cb: Optional[Callable[[str], None]] = None


def install_global_exception_handler(
    alert_callback: Optional[Callable[[str], None]] = None,
) -> None:
    """
    Install a global ``sys.excepthook`` that logs unhandled exceptions and
    optionally shows a user-facing alert dialog via *alert_callback*.
    """
    global _ui_alert_cb
    _ui_alert_cb = alert_callback

    def _handler(exc_type, exc_value, exc_tb):
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.critical("Unhandled exception:\n%s", msg)
        # Write to crash log
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        crash_file = _LOGS_DIR / f"crash_{ts}.log"
        try:
            crash_file.write_text(msg, encoding="utf-8")
        except Exception:
            pass
        if _ui_alert_cb:
            try:
                _ui_alert_cb(f"Unhandled error:\n{exc_value}")
            except Exception:
                pass
        # Still call the original hook so the traceback is printed
        _original_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _handler


# ──────────────────────────────────────────────────────────────────
# Failure-rate monitor
# ──────────────────────────────────────────────────────────────────

class FailureRateMonitor:
    """
    Track recognition success/failure counts and trigger an alert when the
    failure rate exceeds a configurable threshold.
    """

    def __init__(
        self,
        threshold: float = 0.5,
        window: int = 20,
        on_alert: Optional[Callable[[float, int, int], None]] = None,
    ):
        """
        Args:
            threshold: Failure ratio (0.0–1.0) above which an alert fires.
            window: Number of recent attempts to track.
            on_alert: ``callback(failure_rate, failures, total)``
        """
        self.threshold = threshold
        self.window = window
        self._on_alert = on_alert or (lambda r, f, t: None)
        self._history: List[bool] = []  # True = success

    def record(self, success: bool) -> None:
        self._history.append(success)
        if len(self._history) > self.window:
            self._history = self._history[-self.window:]
        total = len(self._history)
        if total >= 5:  # minimum sample
            failures = self._history.count(False)
            rate = failures / total
            if rate >= self.threshold:
                self._on_alert(rate, failures, total)

    def reset(self) -> None:
        self._history.clear()


# ──────────────────────────────────────────────────────────────────
# Webhook notifications
# ──────────────────────────────────────────────────────────────────

class WebhookNotifier:
    """Send notifications to Telegram Bot, DingTalk, or Slack webhooks."""

    def __init__(self, timeout: float = 10.0):
        self._hooks: Dict[str, str] = {}  # name → URL
        self._timeout = timeout

    def register(self, name: str, url: str) -> None:
        self._hooks[name] = url

    def unregister(self, name: str) -> None:
        self._hooks.pop(name, None)

    def notify(self, message: str) -> Dict[str, bool]:
        """
        Send *message* to all registered webhooks.

        Returns a dict ``{name: success}`` indicating delivery status.
        """
        results: Dict[str, bool] = {}
        for name, url in self._hooks.items():
            try:
                ok = self._send(url, message)
                results[name] = ok
            except Exception as e:
                logger.error("Webhook '%s' failed: %s", name, e)
                results[name] = False
        return results

    def _send(self, url: str, message: str) -> bool:
        """Attempt to detect the platform and send accordingly."""
        # Slack style
        if "hooks.slack.com" in url:
            payload = {"text": message}
        # DingTalk
        elif "oapi.dingtalk.com" in url:
            payload = {"msgtype": "text", "text": {"content": message}}
        # Telegram Bot
        elif "api.telegram.org" in url:
            # URL should already contain /sendMessage?chat_id=...
            payload = {"text": message}
        else:
            # Generic JSON POST
            payload = {"text": message, "content": message}

        resp = requests.post(url, json=payload, timeout=self._timeout)
        ok = resp.status_code in (200, 201, 204)
        if not ok:
            logger.warning("Webhook POST %s returned %d: %s", url, resp.status_code, resp.text[:200])
        return ok


# ──────────────────────────────────────────────────────────────────
# Screenshot archiving helper
# ──────────────────────────────────────────────────────────────────

_SCREENSHOT_DIR = _LOGS_DIR / "screenshots"
_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def archive_screenshot(image, tag: str = "") -> Optional[Path]:
    """
    Save an OpenCV image (numpy array) to the screenshot archive directory.

    Returns the saved file path, or None on failure.
    """
    try:
        import cv2
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        fname = f"{ts}_{tag}.png" if tag else f"{ts}.png"
        fpath = _SCREENSHOT_DIR / fname
        cv2.imwrite(str(fpath), image)
        logger.info("Screenshot archived: %s", fpath)
        return fpath
    except Exception as e:
        logger.error("Failed to archive screenshot: %s", e)
        return None
