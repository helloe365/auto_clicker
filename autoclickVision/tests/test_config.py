"""
Unit Tests — Config Manager
Tests config read/write, validation, preset management, and edge cases.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import yaml

from autoclickVision.config.config_manager import ConfigManager, CONFIG_VERSION
from autoclickVision.core.scheduler import (
    ButtonConfig,
    ClickType,
    DelayConfig,
    StepConfig,
    TaskConfig,
)
from autoclickVision.core.matcher import FailureAction


class TestConfigReadWrite(unittest.TestCase):
    """Test saving and loading configs in JSON and YAML."""

    def _make_task(self) -> TaskConfig:
        b1 = ButtonConfig(id="b1", name="OK", image_path="ok.png", confidence=0.85)
        b2 = ButtonConfig(id="b2", name="Cancel", image_path="cancel.png", click_type=ClickType.DOUBLE)
        s1 = StepConfig(button_ids=["b1"], repeat=3)
        s2 = StepConfig(button_ids=["b2"], repeat=1)
        return TaskConfig(name="Test Task", buttons=[b1, b2], steps=[s1, s2], loop_count=10)

    def test_save_load_json(self):
        task = self._make_task()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "task.json"
            mgr = ConfigManager(auto_save=False)
            mgr.set_task(task, path)
            mgr.save()

            mgr2 = ConfigManager(auto_save=False)
            loaded = mgr2.load(path)

            self.assertEqual(loaded.name, "Test Task")
            self.assertEqual(len(loaded.buttons), 2)
            self.assertEqual(loaded.buttons[0].name, "OK")
            self.assertEqual(loaded.buttons[1].click_type, ClickType.DOUBLE)
            self.assertEqual(len(loaded.steps), 2)
            self.assertEqual(loaded.steps[0].repeat, 3)
            self.assertEqual(loaded.loop_count, 10)

    def test_save_load_yaml(self):
        task = self._make_task()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "task.yaml"
            mgr = ConfigManager(auto_save=False)
            mgr.set_task(task, path)
            mgr.save()

            mgr2 = ConfigManager(auto_save=False)
            loaded = mgr2.load(path)
            self.assertEqual(loaded.name, "Test Task")

    def test_encrypted_roundtrip(self):
        task = self._make_task()
        password = "secret123"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "encrypted.json"
            mgr = ConfigManager(auto_save=False, encryption_password=password)
            mgr.set_task(task, path)
            mgr.save()

            # Raw file content should not be readable JSON
            raw = path.read_text(encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                json.loads(raw)

            # But loading with the correct password works
            mgr2 = ConfigManager(auto_save=False, encryption_password=password)
            loaded = mgr2.load(path)
            self.assertEqual(loaded.name, "Test Task")

    def test_version_migration(self):
        """A config with no version field should be migrated to v1."""
        data = {"buttons": [], "steps": [], "loop_count": 5}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "old.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            mgr = ConfigManager(auto_save=False)
            loaded = mgr.load(path)
            self.assertEqual(loaded.loop_count, 5)


class TestConfigValidation(unittest.TestCase):
    """Test validation of config data."""

    def test_invalid_buttons_type(self):
        data = {"buttons": "not a list"}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            mgr = ConfigManager(auto_save=False)
            with self.assertRaises(ValueError):
                mgr.load(path)

    def test_missing_file(self):
        mgr = ConfigManager(auto_save=False)
        with self.assertRaises(FileNotFoundError):
            mgr.load("nonexistent_file_12345.json")


class TestPresets(unittest.TestCase):
    """Test preset save/load/list/delete."""

    def test_preset_roundtrip(self):
        mgr = ConfigManager(auto_save=False)
        task = TaskConfig(name="Preset Test")
        mgr.set_task(task)
        mgr.save_preset("test_preset_unit")

        names = ConfigManager.list_presets()
        self.assertIn("test_preset_unit", names)

        loaded = mgr.load_preset("test_preset_unit")
        self.assertEqual(loaded.name, "Preset Test")

        mgr.delete_preset("test_preset_unit")
        names2 = ConfigManager.list_presets()
        self.assertNotIn("test_preset_unit", names2)


class TestDelayConfig(unittest.TestCase):
    """Test DelayConfig modes."""

    def test_fixed(self):
        d = DelayConfig(mode="fixed", fixed_value=1.5)
        self.assertAlmostEqual(d.get(), 1.5)

    def test_range(self):
        d = DelayConfig(mode="range", range_min=1.0, range_max=2.0)
        for _ in range(50):
            v = d.get()
            self.assertGreaterEqual(v, 1.0)
            self.assertLessEqual(v, 2.0)

    def test_default(self):
        d = DelayConfig(mode="default")
        v = d.get()
        self.assertGreaterEqual(v, d.default_min)
        self.assertLessEqual(v, d.default_max)

    def test_serialization(self):
        d = DelayConfig(mode="range", range_min=0.5, range_max=3.0)
        d2 = DelayConfig.from_dict(d.to_dict())
        self.assertEqual(d2.mode, "range")
        self.assertAlmostEqual(d2.range_min, 0.5)


if __name__ == "__main__":
    unittest.main()
