"""
Unit Tests — Scheduler
Tests sequence parsing, delay precision, and data-class round-trips.
"""

from __future__ import annotations

import time
import unittest

from autoclickVision.core.scheduler import (
    ButtonConfig,
    ClickType,
    DelayConfig,
    StepCondition,
    StepConfig,
    TaskConfig,
    parse_sequence_text,
)
from autoclickVision.core.matcher import FailureAction


class TestParseSequenceText(unittest.TestCase):
    """Test the A*3 -> B -> C*2 parser."""

    def _make_map(self):
        return {"A": "id_a", "B": "id_b", "C": "id_c", "D": "id_d"}

    def test_simple(self):
        steps = parse_sequence_text("A -> B -> C", self._make_map())
        self.assertEqual(len(steps), 3)
        self.assertEqual(steps[0].button_ids, ["id_a"])
        self.assertEqual(steps[0].repeat, 1)

    def test_repeat(self):
        steps = parse_sequence_text("A*3 -> B -> C*2", self._make_map())
        self.assertEqual(steps[0].repeat, 3)
        self.assertEqual(steps[1].repeat, 1)
        self.assertEqual(steps[2].repeat, 2)

    def test_mutual_exclusion(self):
        steps = parse_sequence_text("A|B -> C", self._make_map())
        self.assertEqual(len(steps), 2)
        self.assertIn("id_a", steps[0].button_ids)
        self.assertIn("id_b", steps[0].button_ids)

    def test_unknown_button(self):
        steps = parse_sequence_text("X -> Y", self._make_map())
        self.assertEqual(len(steps), 0)  # no valid buttons


class TestDataClassRoundTrip(unittest.TestCase):
    """Ensure to_dict / from_dict identity."""

    def test_button_config(self):
        b = ButtonConfig(
            name="ok",
            image_path="ok.png",
            confidence=0.9,
            click_type=ClickType.DOUBLE,
            region=(10, 20, 100, 50),
            fallback_action=FailureAction.SKIP,
        )
        b2 = ButtonConfig.from_dict(b.to_dict())
        self.assertEqual(b2.name, "ok")
        self.assertEqual(b2.click_type, ClickType.DOUBLE)
        self.assertEqual(b2.region, (10, 20, 100, 50))
        self.assertEqual(b2.fallback_action, FailureAction.SKIP)

    def test_step_config(self):
        s = StepConfig(
            button_ids=["a", "b"],
            repeat=5,
            condition=StepCondition.WAIT_APPEAR,
            condition_timeout=15.0,
        )
        s2 = StepConfig.from_dict(s.to_dict())
        self.assertEqual(s2.button_ids, ["a", "b"])
        self.assertEqual(s2.repeat, 5)
        self.assertEqual(s2.condition, StepCondition.WAIT_APPEAR)

    def test_task_config(self):
        t = TaskConfig(
            name="Test",
            buttons=[ButtonConfig(name="A")],
            steps=[StepConfig(button_ids=["x"])],
            loop_count=100,
            scheduled_start="2026-03-01T10:00:00",
        )
        t2 = TaskConfig.from_dict(t.to_dict())
        self.assertEqual(t2.name, "Test")
        self.assertEqual(len(t2.buttons), 1)
        self.assertEqual(t2.scheduled_start, "2026-03-01T10:00:00")


class TestDelayPrecision(unittest.TestCase):
    """Verify that delay values are within expected range."""

    def test_fixed_delay(self):
        d = DelayConfig(mode="fixed", fixed_value=0.25)
        t0 = time.perf_counter()
        time.sleep(d.get())
        elapsed = time.perf_counter() - t0
        self.assertAlmostEqual(elapsed, 0.25, delta=0.1)

    def test_range_delay_bounds(self):
        d = DelayConfig(mode="range", range_min=0.1, range_max=0.3)
        for _ in range(100):
            v = d.get()
            self.assertGreaterEqual(v, 0.1)
            self.assertLessEqual(v, 0.3)


if __name__ == "__main__":
    unittest.main()
