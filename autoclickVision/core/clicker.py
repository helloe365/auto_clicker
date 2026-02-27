"""
Mouse Click Module
Wraps single click, double click, right click, long press.
Supports random coordinate offset, Bézier-curve mouse movement,
randomised movement speed, and PyDirectInput mode for fullscreen games.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Optional, Tuple

import pyautogui

logger = logging.getLogger(__name__)

# Safety: allow PyAutoGUI to move to screen edges
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.02  # Small global pause to reduce CPU load

# Try to import pydirectinput for games that need low-level input
try:
    import pydirectinput

    _HAS_DIRECTINPUT = True
except ImportError:
    _HAS_DIRECTINPUT = False


# ──────────────────────────────────────────────────────────────────
# Bézier curve helpers
# ──────────────────────────────────────────────────────────────────

def _bezier_point(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
    """Compute a point on a cubic Bézier curve at parameter *t*."""
    return (
        (1 - t) ** 3 * p0
        + 3 * (1 - t) ** 2 * t * p1
        + 3 * (1 - t) * t ** 2 * p2
        + t ** 3 * p3
    )


def _generate_bezier_path(
    start: Tuple[int, int],
    end: Tuple[int, int],
    num_points: int = 30,
) -> list[Tuple[int, int]]:
    """
    Return a list of (x, y) waypoints along a cubic Bézier curve from *start*
    to *end* with two random control points to simulate natural hand motion.
    """
    sx, sy = start
    ex, ey = end

    # Random control points somewhere between start and end, with some jitter
    dx = ex - sx
    dy = ey - sy
    cp1 = (
        sx + dx * random.uniform(0.2, 0.4) + random.randint(-50, 50),
        sy + dy * random.uniform(0.0, 0.3) + random.randint(-50, 50),
    )
    cp2 = (
        sx + dx * random.uniform(0.6, 0.8) + random.randint(-50, 50),
        sy + dy * random.uniform(0.7, 1.0) + random.randint(-50, 50),
    )

    path: list[Tuple[int, int]] = []
    for i in range(num_points + 1):
        t = i / num_points
        x = int(_bezier_point(t, sx, cp1[0], cp2[0], ex))
        y = int(_bezier_point(t, sy, cp1[1], cp2[1], ey))
        path.append((x, y))
    return path


# ──────────────────────────────────────────────────────────────────
# Clicker class
# ──────────────────────────────────────────────────────────────────


class Clicker:
    """High-level mouse-click controller."""

    def __init__(
        self,
        offset_range: int = 0,
        use_bezier: bool = False,
        duration_range: Tuple[float, float] = (0.15, 0.45),
        use_directinput: bool = False,
    ):
        """
        Args:
            offset_range: Max random pixel offset applied to the target (±N).
            use_bezier: Move along a Bézier curve instead of a straight line.
            duration_range: (min, max) seconds for mouse movement duration.
            use_directinput: Use ``pydirectinput`` low-level backend.
        """
        self.offset_range = offset_range
        self.use_bezier = use_bezier
        self.duration_range = duration_range
        self.use_directinput = use_directinput and _HAS_DIRECTINPUT

        if use_directinput and not _HAS_DIRECTINPUT:
            logger.warning(
                "pydirectinput is not installed — falling back to pyautogui."
            )

    # ─── Internal helpers ───────────────────────────────────────

    def _jitter(self, x: int, y: int) -> Tuple[int, int]:
        """Apply random offset to simulate human imprecision."""
        if self.offset_range > 0:
            x += random.randint(-self.offset_range, self.offset_range)
            y += random.randint(-self.offset_range, self.offset_range)
        return x, y

    def _random_duration(self) -> float:
        lo, hi = self.duration_range
        return random.uniform(lo, hi)

    def _move_to(self, x: int, y: int) -> None:
        """Move the cursor to (x, y) using the configured strategy."""
        if self.use_directinput:
            # pydirectinput.moveTo doesn't support duration; jump directly
            pydirectinput.moveTo(x, y)
            return

        if self.use_bezier:
            cur_x, cur_y = pyautogui.position()
            path = _generate_bezier_path((cur_x, cur_y), (x, y))
            total_dur = self._random_duration()
            segment = total_dur / max(len(path), 1)
            for px, py in path:
                pyautogui.moveTo(px, py, _pause=False)
                time.sleep(segment)
        else:
            pyautogui.moveTo(x, y, duration=self._random_duration())

    def _backend_click(self, button: str = "left", clicks: int = 1) -> None:
        """Perform the click through the active backend."""
        if self.use_directinput:
            for _ in range(clicks):
                pydirectinput.click(button=button)
        else:
            pyautogui.click(button=button, clicks=clicks)

    # ─── Public API ─────────────────────────────────────────────

    def click(
        self,
        x: int,
        y: int,
        button: str = "left",
        clicks: int = 1,
        offset: Optional[int] = None,
    ) -> Tuple[int, int]:
        """
        Move to (x, y) with optional jitter and perform *clicks*.

        Args:
            x, y: Target screen coordinates.
            button: ``"left"`` | ``"right"`` | ``"middle"``.
            clicks: Number of consecutive clicks (2 = double-click).
            offset: Override instance ``offset_range`` for this call.

        Returns:
            The actual (x, y) where the click landed after jitter.
        """
        old_offset = self.offset_range
        if offset is not None:
            self.offset_range = offset
        tx, ty = self._jitter(x, y)
        self.offset_range = old_offset

        logger.debug("click (%d, %d) → jittered (%d, %d), button=%s, clicks=%d",
                      x, y, tx, ty, button, clicks)
        self._move_to(tx, ty)
        self._backend_click(button, clicks)
        return tx, ty

    def single_click(self, x: int, y: int, **kw) -> Tuple[int, int]:
        return self.click(x, y, button="left", clicks=1, **kw)

    def double_click(self, x: int, y: int, **kw) -> Tuple[int, int]:
        return self.click(x, y, button="left", clicks=2, **kw)

    def right_click(self, x: int, y: int, **kw) -> Tuple[int, int]:
        return self.click(x, y, button="right", clicks=1, **kw)

    def long_press(
        self,
        x: int,
        y: int,
        duration: float = 1.0,
        button: str = "left",
        offset: Optional[int] = None,
    ) -> Tuple[int, int]:
        """
        Press and hold at (x, y) for *duration* seconds.

        Args:
            x, y: Target screen coordinates.
            duration: How long to hold the button down.
            button: ``"left"`` | ``"right"`` | ``"middle"``.
            offset: Override instance ``offset_range`` for this call.

        Returns:
            The actual (x, y) where the press landed after jitter.
        """
        old_offset = self.offset_range
        if offset is not None:
            self.offset_range = offset
        tx, ty = self._jitter(x, y)
        self.offset_range = old_offset
        logger.debug("long_press (%d, %d) → jittered (%d, %d), %.2fs",
                      x, y, tx, ty, duration)
        self._move_to(tx, ty)

        if self.use_directinput:
            pydirectinput.mouseDown(button=button)
            time.sleep(duration)
            pydirectinput.mouseUp(button=button)
        else:
            pyautogui.mouseDown(tx, ty, button=button)
            time.sleep(duration)
            pyautogui.mouseUp(tx, ty, button=button)
        return tx, ty
