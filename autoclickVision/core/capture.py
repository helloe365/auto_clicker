"""
Screen Capture Module
Provides full-screen and region-based screen capture using the `mss` library.
Supports multi-monitor selection and returns frames in OpenCV numpy format.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import threading

import mss
import mss.tools
import numpy as np

logger = logging.getLogger(__name__)


class ScreenCapture:
    """High-performance screen capture using mss.

    Thread-safe: each thread automatically gets its own ``mss`` instance
    via ``threading.local()``, avoiding the *_thread._local* attribute
    errors that occur when a single ``mss`` handle is shared across
    threads.
    """

    def __init__(self, monitor_index: int = 0):
        """
        Args:
            monitor_index: 0 = all monitors combined, 1 = primary, 2 = second, etc.
        """
        self._local = threading.local()
        self.monitor_index = monitor_index

    @property
    def _sct(self) -> mss.mss:
        """Return a per-thread ``mss`` instance, creating one if needed."""
        sct = getattr(self._local, "sct", None)
        if sct is None:
            sct = mss.mss()
            self._local.sct = sct
        return sct

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def monitors(self) -> list[dict]:
        """Return the list of available monitors (index 0 is the virtual full desktop)."""
        return self._sct.monitors

    def set_monitor(self, index: int) -> None:
        """Select which monitor to capture from."""
        if index < 0 or index >= len(self._sct.monitors):
            raise ValueError(
                f"Monitor index {index} out of range. "
                f"Available: 0..{len(self._sct.monitors) - 1}"
            )
        self.monitor_index = index
        logger.info("Monitor switched to index %d", index)

    # ------------------------------------------------------------------
    # Capture methods
    # ------------------------------------------------------------------

    def capture_full(self) -> np.ndarray:
        """Capture the entire selected monitor and return a BGR numpy array."""
        monitor = self._sct.monitors[self.monitor_index]
        return self._grab(monitor)

    def capture_region(
        self,
        left: int,
        top: int,
        width: int,
        height: int,
    ) -> np.ndarray:
        """
        Capture a rectangular region of the screen.

        Args:
            left: X coordinate of the top-left corner.
            top: Y coordinate of the top-left corner.
            width: Width of the capture rectangle.
            height: Height of the capture rectangle.

        Returns:
            BGR numpy array of the captured region.
        """
        region = {"left": left, "top": top, "width": width, "height": height}
        return self._grab(region)

    def capture_roi(
        self,
        roi: Optional[Tuple[int, int, int, int]],
    ) -> np.ndarray:
        """
        Convenience wrapper — capture a region given as (x, y, w, h) tuple,
        or the full monitor if *roi* is ``None``.
        """
        if roi is None:
            return self.capture_full()
        x, y, w, h = roi
        return self.capture_region(x, y, w, h)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _grab(self, region: dict) -> np.ndarray:
        """Grab a screenshot for *region* and convert BGRA → BGR numpy array."""
        sct_img = self._sct.grab(region)
        # mss returns BGRA; drop the alpha channel to get standard BGR for OpenCV.
        frame = np.array(sct_img, dtype=np.uint8)
        return frame[:, :, :3].copy()  # Ensure contiguous memory

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def close(self) -> None:
        sct = getattr(self._local, "sct", None)
        if sct is not None:
            sct.close()
            self._local.sct = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
