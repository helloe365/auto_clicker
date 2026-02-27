"""
Image Matching Module
Provides template matching (single-scale & multi-scale), grayscale mode,
optional SIFT/ORB feature-point matching, per-button confidence thresholds,
region-restricted recognition, and configurable failure strategies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# Data classes & enums
# ──────────────────────────────────────────────────────────────────


class FailureAction(str, Enum):
    """What to do when recognition fails for a button."""
    RETRY = "retry"
    SKIP = "skip"
    ABORT = "abort"
    ALERT = "alert"


@dataclass
class MatchResult:
    """Container for a single recognition result."""
    found: bool
    center: Optional[Tuple[int, int]] = None  # (x, y) centre of the match
    confidence: float = 0.0
    bounding_rect: Optional[Tuple[int, int, int, int]] = None  # (x, y, w, h)
    scale: float = 1.0  # scale at which the match was found


# ──────────────────────────────────────────────────────────────────
# Matcher
# ──────────────────────────────────────────────────────────────────


class ImageMatcher:
    """Template-based (and optionally feature-based) image matcher."""

    # Multi-scale default parameters
    DEFAULT_SCALE_RANGE: Tuple[float, float] = (0.7, 1.3)
    DEFAULT_SCALE_STEP: float = 0.05

    def __init__(
        self,
        default_confidence: float = 0.8,
        grayscale: bool = False,
        multi_scale: bool = False,
        scale_range: Optional[Tuple[float, float]] = None,
        scale_step: Optional[float] = None,
    ):
        """
        Args:
            default_confidence: Global confidence threshold if not overridden per-button.
            grayscale: Convert images to grayscale before matching.
            multi_scale: Enable multi-scale template matching.
            scale_range: (min_scale, max_scale) for multi-scale matching.
            scale_step: Scaling increment step.
        """
        self.default_confidence = default_confidence
        self.grayscale = grayscale
        self.multi_scale = multi_scale
        self.scale_range = scale_range or self.DEFAULT_SCALE_RANGE
        self.scale_step = scale_step or self.DEFAULT_SCALE_STEP

    # ─── Template loading ───────────────────────────────────────

    @staticmethod
    def load_template(image_path: str | Path) -> np.ndarray:
        """Load a template image from disk (BGR)."""
        path = str(image_path)
        tpl = cv2.imread(path, cv2.IMREAD_COLOR)
        if tpl is None:
            raise FileNotFoundError(f"Cannot load template image: {path}")
        return tpl

    # ─── Preprocessing ──────────────────────────────────────────

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        """Optionally convert an image to grayscale."""
        if self.grayscale and len(image.shape) == 3:
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return image

    # ─── Single-scale template match ────────────────────────────

    def _match_single_scale(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        confidence: float,
    ) -> MatchResult:
        """Run cv2.matchTemplate at the original scale."""
        ss = self._preprocess(screenshot)
        tpl = self._preprocess(template)

        if ss.shape[0] < tpl.shape[0] or ss.shape[1] < tpl.shape[1]:
            return MatchResult(found=False)

        result = cv2.matchTemplate(ss, tpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= confidence:
            th, tw = template.shape[:2]
            cx = max_loc[0] + tw // 2
            cy = max_loc[1] + th // 2
            return MatchResult(
                found=True,
                center=(cx, cy),
                confidence=max_val,
                bounding_rect=(max_loc[0], max_loc[1], tw, th),
                scale=1.0,
            )
        return MatchResult(found=False, confidence=max_val)

    # ─── Multi-scale template match ─────────────────────────────

    def _match_multi_scale(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        confidence: float,
    ) -> MatchResult:
        """Resize the template across a range of scales and keep the best match."""
        ss = self._preprocess(screenshot)
        tpl_orig = self._preprocess(template)
        th_orig, tw_orig = tpl_orig.shape[:2]

        best = MatchResult(found=False)
        scale = self.scale_range[0]
        while scale <= self.scale_range[1] + 1e-6:
            tw = max(1, int(tw_orig * scale))
            th = max(1, int(th_orig * scale))
            # Skip if the resized template is larger than the screenshot
            if tw > ss.shape[1] or th > ss.shape[0]:
                scale += self.scale_step
                continue
            tpl = cv2.resize(tpl_orig, (tw, th), interpolation=cv2.INTER_LINEAR)
            result = cv2.matchTemplate(ss, tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val > best.confidence:
                best = MatchResult(
                    found=max_val >= confidence,
                    center=(max_loc[0] + tw // 2, max_loc[1] + th // 2),
                    confidence=max_val,
                    bounding_rect=(max_loc[0], max_loc[1], tw, th),
                    scale=scale,
                )
            scale += self.scale_step

        if not best.found:
            best.found = False
        return best

    # ─── SIFT / ORB feature matching (optional) ────────────────

    def match_features(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        confidence: float = 0.7,
        method: str = "ORB",
        min_good_matches: int = 10,
    ) -> MatchResult:
        """
        Feature-point matching for rotated / deformed buttons.

        Args:
            method: ``"ORB"`` or ``"SIFT"``.
            min_good_matches: Minimum number of good matches to declare success.
        """
        ss_gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY) if len(screenshot.shape) == 3 else screenshot
        tpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY) if len(template.shape) == 3 else template

        if method.upper() == "SIFT":
            detector = cv2.SIFT_create()
            matcher = cv2.BFMatcher(cv2.NORM_L2)
        else:
            detector = cv2.ORB_create(nfeatures=1000)
            matcher = cv2.BFMatcher(cv2.NORM_HAMMING)

        kp1, des1 = detector.detectAndCompute(tpl_gray, None)
        kp2, des2 = detector.detectAndCompute(ss_gray, None)

        if des1 is None or des2 is None or len(kp1) < 2 or len(kp2) < 2:
            return MatchResult(found=False)

        matches = matcher.knnMatch(des1, des2, k=2)

        # Lowe's ratio test
        good = []
        for m_pair in matches:
            if len(m_pair) == 2:
                m, n = m_pair
                if m.distance < 0.75 * n.distance:
                    good.append(m)

        if len(good) >= min_good_matches:
            src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
            M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            if M is not None:
                h, w = tpl_gray.shape[:2]
                corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
                dst_corners = cv2.perspectiveTransform(corners, M)
                cx = int(np.mean(dst_corners[:, 0, 0]))
                cy = int(np.mean(dst_corners[:, 0, 1]))
                xs = dst_corners[:, 0, 0]
                ys = dst_corners[:, 0, 1]
                bx, by = int(min(xs)), int(min(ys))
                bw, bh = int(max(xs)) - bx, int(max(ys)) - by
                conf = len(good) / max(len(kp1), 1)
                return MatchResult(
                    found=conf >= confidence,
                    center=(cx, cy),
                    confidence=conf,
                    bounding_rect=(bx, by, bw, bh),
                )
        return MatchResult(found=False, confidence=len(good) / max(len(kp1), 1))

    # ─── Public API ─────────────────────────────────────────────

    def match(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        confidence: Optional[float] = None,
        region: Optional[Tuple[int, int, int, int]] = None,
        use_features: bool = False,
        feature_method: str = "ORB",
    ) -> MatchResult:
        """
        Find *template* inside *screenshot*.

        Args:
            screenshot: BGR numpy array of the screen / region.
            template: BGR numpy array of the button image.
            confidence: Matching threshold (overrides instance default).
            region: (x, y, w, h) — restrict search to this sub-region.
            use_features: Use SIFT/ORB instead of template matching.
            feature_method: ``"ORB"`` or ``"SIFT"`` (only when *use_features*).

        Returns:
            A `MatchResult` with coordinates relative to the **full screenshot**
            (region offset is added back automatically).
        """
        conf = confidence if confidence is not None else self.default_confidence

        # Crop to ROI if supplied
        offset_x, offset_y = 0, 0
        search_area = screenshot
        if region is not None:
            rx, ry, rw, rh = region
            offset_x, offset_y = rx, ry
            search_area = screenshot[ry: ry + rh, rx: rx + rw]

        if use_features:
            result = self.match_features(search_area, template, conf, feature_method)
        elif self.multi_scale:
            result = self._match_multi_scale(search_area, template, conf)
        else:
            result = self._match_single_scale(search_area, template, conf)

        # Translate coordinates back to full-screenshot space
        if result.found and result.center is not None:
            cx, cy = result.center
            result.center = (cx + offset_x, cy + offset_y)
        if result.bounding_rect is not None:
            bx, by, bw, bh = result.bounding_rect
            result.bounding_rect = (bx + offset_x, by + offset_y, bw, bh)

        return result

    def match_from_file(
        self,
        screenshot: np.ndarray,
        template_path: str | Path,
        **kwargs,
    ) -> MatchResult:
        """Convenience: load a template from disk and match."""
        template = self.load_template(template_path)
        return self.match(screenshot, template, **kwargs)
