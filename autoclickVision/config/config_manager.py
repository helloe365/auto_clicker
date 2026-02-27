"""
Configuration Manager
Handles reading, validating, writing, importing/exporting task configs
in JSON/YAML format.  Supports preset templates, auto-save, optional
encryption, and config versioning with backward-compatible migration.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ..core.scheduler import TaskConfig

logger = logging.getLogger(__name__)

# Current schema version — bump when the config format changes
CONFIG_VERSION = 1

# Directories relative to the package root
_PKG_ROOT = Path(__file__).resolve().parent.parent
PRESETS_DIR = _PKG_ROOT / "config" / "presets"
PRESETS_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────
# Simple XOR-based obfuscation (not cryptographically secure, but
# deters casual reading of sensitive paths / tokens).
# ──────────────────────────────────────────────────────────────────

def _xor_bytes(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _encrypt(text: str, password: str) -> str:
    key = hashlib.sha256(password.encode()).digest()
    enc = _xor_bytes(text.encode("utf-8"), key)
    return base64.b64encode(enc).decode("ascii")


def _decrypt(token: str, password: str) -> str:
    key = hashlib.sha256(password.encode()).digest()
    dec = _xor_bytes(base64.b64decode(token), key)
    return dec.decode("utf-8")


# ──────────────────────────────────────────────────────────────────
# Migration helpers  (version N → version N+1)
# ──────────────────────────────────────────────────────────────────

def _migrate(data: dict) -> dict:
    """Apply successive migrations until we reach CONFIG_VERSION."""
    version = data.get("_version", 0)
    if version < 1:
        # v0 → v1: nothing to do — v1 is the first formal version
        data.setdefault("name", "Untitled Task")
        data.setdefault("buttons", [])
        data.setdefault("steps", [])
        data.setdefault("loop_count", 50)
        data.setdefault("round_interval", 10.0)
        version = 1
    data["_version"] = version
    return data


# ──────────────────────────────────────────────────────────────────
# Config Manager
# ──────────────────────────────────────────────────────────────────

class ConfigManager:
    """Read, validate, save, and manage task configuration files."""

    def __init__(self, auto_save: bool = True, encryption_password: Optional[str] = None):
        """
        Args:
            auto_save: If True, automatically save on every ``set_task``.
            encryption_password: If provided, configs are XOR-obfuscated with this.
        """
        self.auto_save = auto_save
        self._password = encryption_password
        self._current_path: Optional[Path] = None
        self._task: Optional[TaskConfig] = None

    # ─── Properties ─────────────────────────────────────────────

    @property
    def task(self) -> Optional[TaskConfig]:
        return self._task

    @property
    def current_path(self) -> Optional[Path]:
        return self._current_path

    # ─── Core I/O ───────────────────────────────────────────────

    def load(self, path: str | Path) -> TaskConfig:
        """Load a task config from a JSON or YAML file."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {p}")

        raw = p.read_text(encoding="utf-8")

        # Decrypt if necessary
        if self._password:
            try:
                raw = _decrypt(raw, self._password)
            except Exception:
                pass  # assume plaintext

        # Parse
        if p.suffix in (".yaml", ".yml"):
            data = yaml.safe_load(raw)
        else:
            data = json.loads(raw)

        if not isinstance(data, dict):
            raise ValueError("Config file root must be a JSON object / YAML mapping")

        data = _migrate(data)
        self._validate(data)

        self._task = TaskConfig.from_dict(data)
        self._current_path = p
        logger.info("Config loaded: %s", p)
        return self._task

    def save(self, path: Optional[str | Path] = None) -> Path:
        """
        Save the current task config.  Uses the last loaded path if *path*
        is `None`.
        """
        if self._task is None:
            raise RuntimeError("No task to save")

        p = Path(path) if path else self._current_path
        if p is None:
            raise RuntimeError("No save path specified and no file was previously loaded")

        data = self._task.to_dict()
        data["_version"] = CONFIG_VERSION

        if p.suffix in (".yaml", ".yml"):
            text = yaml.dump(data, default_flow_style=False, allow_unicode=True)
        else:
            text = json.dumps(data, indent=2, ensure_ascii=False)

        if self._password:
            text = _encrypt(text, self._password)

        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        self._current_path = p
        logger.info("Config saved: %s", p)
        return p

    def set_task(self, task: TaskConfig, path: Optional[str | Path] = None) -> None:
        """Set the active task (and optionally auto-save)."""
        self._task = task
        if path:
            self._current_path = Path(path)
        if self.auto_save and self._current_path:
            self.save()

    # ─── Import / Export ────────────────────────────────────────

    def export_config(self, dest_path: str | Path) -> Path:
        """Export the current config to a new file."""
        return self.save(dest_path)

    def import_config(self, src_path: str | Path) -> TaskConfig:
        """Import a config from an external file."""
        return self.load(src_path)

    # ─── Preset Management ──────────────────────────────────────

    def save_preset(self, preset_name: str) -> Path:
        """Save current config as a preset template."""
        p = PRESETS_DIR / f"{preset_name}.json"
        return self.save(p)

    def load_preset(self, preset_name: str) -> TaskConfig:
        """Load a named preset."""
        p = PRESETS_DIR / f"{preset_name}.json"
        return self.load(p)

    @staticmethod
    def list_presets() -> List[str]:
        """Return names of all available presets."""
        return sorted(
            p.stem
            for p in PRESETS_DIR.glob("*.json")
        )

    def delete_preset(self, preset_name: str) -> None:
        p = PRESETS_DIR / f"{preset_name}.json"
        if p.exists():
            p.unlink()
            logger.info("Preset deleted: %s", preset_name)

    # ─── Validation ─────────────────────────────────────────────

    @staticmethod
    def _validate(data: dict) -> None:
        """Basic structural validation of a config dict."""
        if "buttons" in data:
            if not isinstance(data["buttons"], list):
                raise ValueError("'buttons' must be a list")
            for i, b in enumerate(data["buttons"]):
                if not isinstance(b, dict):
                    raise ValueError(f"buttons[{i}] must be a dict")
                if "image_path" not in b and "id" not in b:
                    raise ValueError(f"buttons[{i}] must have 'image_path' or 'id'")
        if "steps" in data:
            if not isinstance(data["steps"], list):
                raise ValueError("'steps' must be a list")

    # ─── New / blank task ───────────────────────────────────────

    def new_task(self, name: str = "Untitled Task") -> TaskConfig:
        """Create and set a new blank task."""
        task = TaskConfig(name=name)
        self._task = task
        self._current_path = None
        return task
