"""
Unit Tests — Image Matching
Tests template matching accuracy, multi-scale matching, and performance benchmarking.
"""

from __future__ import annotations

import time
import unittest

import cv2
import numpy as np

from autoclickVision.core.matcher import ImageMatcher, MatchResult, FailureAction


class TestSingleScaleMatch(unittest.TestCase):
    """Test basic single-scale template matching."""

    def _make_scene_and_template(self, scale=1.0):
        """Create a synthetic 800×600 scene with a textured 60×40 button.

        The button has internal detail (lines + circle) so that
        TM_CCOEFF_NORMED sees non-zero variance in the template.
        """
        scene = np.full((600, 800, 3), 200, dtype=np.uint8)  # grey background
        # Draw a "button" at (300, 250)
        bx, by, bw, bh = 300, 250, 60, 40
        cv2.rectangle(scene, (bx, by), (bx + bw, by + bh), (0, 0, 255), -1)
        # Add internal texture so the template is NOT uniform
        cv2.line(scene, (bx + 5, by + 5), (bx + bw - 5, by + bh - 5), (255, 255, 255), 2)
        cv2.circle(scene, (bx + bw // 2, by + bh // 2), 8, (0, 255, 0), -1)
        # Template is the exact button region
        template = scene[by: by + bh, bx: bx + bw].copy()
        if scale != 1.0:
            tw = max(1, int(bw * scale))
            th = max(1, int(bh * scale))
            template = cv2.resize(template, (tw, th))
        return scene, template, (bx + bw // 2, by + bh // 2)

    def test_exact_match(self):
        scene, tpl, expected_center = self._make_scene_and_template()
        matcher = ImageMatcher(default_confidence=0.9)
        result = matcher.match(scene, tpl)
        self.assertTrue(result.found)
        self.assertIsNotNone(result.center)
        self.assertAlmostEqual(result.center[0], expected_center[0], delta=2)
        self.assertAlmostEqual(result.center[1], expected_center[1], delta=2)
        self.assertGreaterEqual(result.confidence, 0.99)

    def test_no_match_low_confidence(self):
        scene, tpl, _ = self._make_scene_and_template()
        # Create a textured template that does NOT appear in the scene
        tpl = np.full_like(tpl, 50)
        cv2.line(tpl, (0, 0), (tpl.shape[1], tpl.shape[0]), (255, 255, 0), 3)
        cv2.circle(tpl, (tpl.shape[1] // 2, tpl.shape[0] // 2), 5, (0, 100, 200), -1)
        matcher = ImageMatcher(default_confidence=0.9)
        result = matcher.match(scene, tpl)
        self.assertFalse(result.found)

    def test_grayscale_mode(self):
        scene, tpl, expected_center = self._make_scene_and_template()
        matcher = ImageMatcher(default_confidence=0.8, grayscale=True)
        result = matcher.match(scene, tpl)
        self.assertTrue(result.found)

    def test_region_restricted(self):
        scene, tpl, _ = self._make_scene_and_template()
        matcher = ImageMatcher(default_confidence=0.9)
        # Search only in a region that contains the button
        result = matcher.match(scene, tpl, region=(250, 200, 200, 150))
        self.assertTrue(result.found)
        # Centre should be in absolute coordinates
        self.assertGreater(result.center[0], 250)
        self.assertGreater(result.center[1], 200)

    def test_region_miss(self):
        scene, tpl, _ = self._make_scene_and_template()
        matcher = ImageMatcher(default_confidence=0.9)
        # Search far from the button
        result = matcher.match(scene, tpl, region=(0, 0, 100, 100))
        self.assertFalse(result.found)


class TestMultiScaleMatch(unittest.TestCase):
    """Test multi-scale template matching."""

    def test_scaled_template(self):
        scene = np.full((600, 800, 3), 200, dtype=np.uint8)
        bx, by, bw, bh = 300, 250, 80, 50
        cv2.rectangle(scene, (bx, by), (bx + bw, by + bh), (0, 0, 255), -1)
        # Add texture so the template has non-zero variance
        cv2.line(scene, (bx + 5, by + 5), (bx + bw - 5, by + bh - 5), (255, 255, 255), 2)
        cv2.circle(scene, (bx + bw // 2, by + bh // 2), 10, (0, 255, 0), -1)
        # Template at 0.8× scale
        tpl_region = scene[by: by + bh, bx: bx + bw].copy()
        tpl_small = cv2.resize(tpl_region, (int(bw * 0.8), int(bh * 0.8)))

        matcher = ImageMatcher(default_confidence=0.7, multi_scale=True, scale_range=(0.7, 1.3), scale_step=0.05)
        result = matcher.match(scene, tpl_small)
        self.assertTrue(result.found)
        # Scale should be somewhere near 1.25 (inverse of 0.8)
        self.assertGreater(result.scale, 1.0)


class TestMatchPerformance(unittest.TestCase):
    """Benchmark matching latency (informational, not strict pass/fail)."""

    def test_single_scale_benchmark(self):
        scene = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
        tpl = scene[500:540, 900:960].copy()
        matcher = ImageMatcher()
        t0 = time.perf_counter()
        for _ in range(10):
            matcher.match(scene, tpl)
        avg = (time.perf_counter() - t0) / 10
        print(f"Single-scale match avg: {avg * 1000:.1f} ms")
        self.assertLess(avg, 2.0, "Single-scale match too slow (>2s)")

    def test_multi_scale_benchmark(self):
        scene = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
        tpl = scene[500:540, 900:960].copy()
        matcher = ImageMatcher(multi_scale=True)
        t0 = time.perf_counter()
        for _ in range(5):
            matcher.match(scene, tpl)
        avg = (time.perf_counter() - t0) / 5
        print(f"Multi-scale match avg: {avg * 1000:.1f} ms")
        self.assertLess(avg, 10.0, "Multi-scale match too slow (>10s)")


if __name__ == "__main__":
    unittest.main()
