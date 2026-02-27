"""
Watchdog Module
Monitors the main scheduler thread for freezes, detects prolonged
screen inactivity, and triggers notifications on exceptions.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class Watchdog:
    """
    Monitors a SequenceScheduler for:
    - Thread freeze (no heartbeat within *timeout* seconds)
    - Prolonged screen inactivity (idle detection)

    Calls the registered notification callback when an anomaly is detected.
    """

    def __init__(
        self,
        heartbeat_timeout: float = 60.0,
        inactivity_timeout: float = 120.0,
        check_interval: float = 5.0,
        on_freeze: Optional[Callable[[], None]] = None,
        on_inactivity: Optional[Callable[[], None]] = None,
        on_exception: Optional[Callable[[Exception], None]] = None,
    ):
        """
        Args:
            heartbeat_timeout: Seconds without a heartbeat before declaring a freeze.
            inactivity_timeout: Seconds of screen inactivity before alerting.
            check_interval: How often (in seconds) the watchdog checks the heartbeat.
            on_freeze: Callback invoked when a freeze is detected.
            on_inactivity: Callback invoked when inactivity is detected.
            on_exception: Callback invoked when an exception is detected.
        """
        self.heartbeat_timeout = heartbeat_timeout
        self.inactivity_timeout = inactivity_timeout
        self.check_interval = check_interval

        self._on_freeze = on_freeze or (lambda: None)
        self._on_inactivity = on_inactivity or (lambda: None)
        self._on_exception = on_exception or (lambda e: None)

        self._last_heartbeat: float = 0.0
        self._last_activity: float = 0.0
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._freeze_triggered = False
        self._inactivity_triggered = False

    # ─── Heartbeat API (called by the scheduler) ────────────────

    def heartbeat(self) -> None:
        """Signal that the scheduler thread is alive."""
        self._last_heartbeat = time.time()
        self._freeze_triggered = False

    def report_activity(self) -> None:
        """Signal that meaningful screen activity has been observed."""
        self._last_activity = time.time()
        self._inactivity_triggered = False

    def report_exception(self, exc: Exception) -> None:
        """Forward an exception to the watchdog notification handler."""
        logger.error("Watchdog received exception: %s", exc)
        self._on_exception(exc)

    # ─── Lifecycle ──────────────────────────────────────────────

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._last_heartbeat = time.time()
        self._last_activity = time.time()
        self._freeze_triggered = False
        self._inactivity_triggered = False
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Watchdog started (heartbeat timeout=%.0fs, inactivity timeout=%.0fs)",
                     self.heartbeat_timeout, self.inactivity_timeout)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self.check_interval + 2)
        logger.info("Watchdog stopped")

    # ─── Internal monitor loop ──────────────────────────────────

    def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            now = time.time()

            # Check heartbeat
            if (now - self._last_heartbeat) > self.heartbeat_timeout:
                if not self._freeze_triggered:
                    self._freeze_triggered = True
                    elapsed = now - self._last_heartbeat
                    logger.warning("Watchdog: no heartbeat for %.0fs — freeze detected", elapsed)
                    try:
                        self._on_freeze()
                    except Exception as e:
                        logger.exception("Watchdog on_freeze callback error: %s", e)

            # Check inactivity
            if (now - self._last_activity) > self.inactivity_timeout:
                if not self._inactivity_triggered:
                    self._inactivity_triggered = True
                    elapsed = now - self._last_activity
                    logger.warning("Watchdog: screen inactive for %.0fs", elapsed)
                    try:
                        self._on_inactivity()
                    except Exception as e:
                        logger.exception("Watchdog on_inactivity callback error: %s", e)

            self._stop_event.wait(timeout=self.check_interval)
