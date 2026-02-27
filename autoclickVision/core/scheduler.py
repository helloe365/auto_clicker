"""
Task Scheduling Module
Defines ButtonConfig, StepConfig, TaskConfig data structures and the
SequenceScheduler that drives the recognition → click → wait pipeline.

Supports:
- Click sequences with repeat counts  (A*3 -> B -> C*2)
- Intra-button / inter-button delays (fixed, random range, default random)
- Conditional steps: wait for appear / disappear with timeout
- Mutual-exclusion recognition per step
- Loop control: round count, inter-round interval, scheduled start
- Chained multi-task execution
"""

from __future__ import annotations

import logging
import random
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .capture import ScreenCapture
from .clicker import Clicker
from .matcher import FailureAction, ImageMatcher, MatchResult

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# Enums & small helpers
# ──────────────────────────────────────────────────────────────────

class ClickType(str, Enum):
    SINGLE = "single"
    DOUBLE = "double"
    RIGHT = "right"
    LONG_PRESS = "long_press"


class StepCondition(str, Enum):
    """Condition evaluated before executing a step."""
    NONE = "none"
    WAIT_APPEAR = "wait_appear"        # wait until the button appears on screen
    WAIT_DISAPPEAR = "wait_disappear"  # wait until the button disappears


class TaskState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    FINISHED = "finished"
    ERROR = "error"


# ──────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────

@dataclass
class DelayConfig:
    """Configurable delay: fixed value, random range, or default random."""
    mode: str = "default"        # "fixed" | "range" | "default"
    fixed_value: float = 0.5     # used when mode == "fixed"
    range_min: float = 0.3       # used when mode == "range"
    range_max: float = 1.0
    default_min: float = 0.2     # used when mode == "default"
    default_max: float = 0.8

    def get(self) -> float:
        if self.mode == "fixed":
            return self.fixed_value
        elif self.mode == "range":
            return random.uniform(self.range_min, self.range_max)
        else:
            return random.uniform(self.default_min, self.default_max)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "fixed_value": self.fixed_value,
            "range_min": self.range_min,
            "range_max": self.range_max,
            "default_min": self.default_min,
            "default_max": self.default_max,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DelayConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ButtonConfig:
    """Configuration for a single recognisable button."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    image_path: str = ""
    confidence: float = 0.8
    click_type: ClickType = ClickType.SINGLE
    click_offset_range: int = 0
    retry_count: int = 3
    retry_interval: float = 0.5
    region: Optional[Tuple[int, int, int, int]] = None  # (x, y, w, h) ROI
    fallback_action: FailureAction = FailureAction.RETRY
    long_press_duration: float = 1.0

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "image_path": self.image_path,
            "confidence": self.confidence,
            "click_type": self.click_type.value,
            "click_offset_range": self.click_offset_range,
            "retry_count": self.retry_count,
            "retry_interval": self.retry_interval,
            "region": list(self.region) if self.region else None,
            "fallback_action": self.fallback_action.value,
            "long_press_duration": self.long_press_duration,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ButtonConfig":
        kw = dict(d)
        if "click_type" in kw:
            kw["click_type"] = ClickType(kw["click_type"])
        if "fallback_action" in kw:
            kw["fallback_action"] = FailureAction(kw["fallback_action"])
        if kw.get("region") is not None:
            kw["region"] = tuple(kw["region"])
        return cls(**{k: v for k, v in kw.items() if k in cls.__dataclass_fields__})


@dataclass
class StepConfig:
    """A single step in the click sequence."""
    button_ids: List[str] = field(default_factory=list)  # supports mutual-exclusion (first found wins)
    repeat: int = 1
    intra_delay: DelayConfig = field(default_factory=DelayConfig)   # within repeats of same button
    inter_delay: DelayConfig = field(default_factory=DelayConfig)   # after this step before next
    condition: StepCondition = StepCondition.NONE
    condition_timeout: float = 30.0  # seconds to wait for the condition before fallback

    def to_dict(self) -> dict:
        return {
            "button_ids": self.button_ids,
            "repeat": self.repeat,
            "intra_delay": self.intra_delay.to_dict(),
            "inter_delay": self.inter_delay.to_dict(),
            "condition": self.condition.value,
            "condition_timeout": self.condition_timeout,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StepConfig":
        kw = dict(d)
        if "intra_delay" in kw:
            kw["intra_delay"] = DelayConfig.from_dict(kw["intra_delay"])
        if "inter_delay" in kw:
            kw["inter_delay"] = DelayConfig.from_dict(kw["inter_delay"])
        if "condition" in kw:
            kw["condition"] = StepCondition(kw["condition"])
        return cls(**{k: v for k, v in kw.items() if k in cls.__dataclass_fields__})


@dataclass
class TaskConfig:
    """Full task configuration: buttons + sequence + scheduling."""
    name: str = "Untitled Task"
    buttons: List[ButtonConfig] = field(default_factory=list)
    steps: List[StepConfig] = field(default_factory=list)
    loop_count: int = 50        # 0 = infinite
    round_interval: float = 10.0
    round_interval_delay: DelayConfig = field(default_factory=lambda: DelayConfig(mode="fixed", fixed_value=10.0))
    scheduled_start: Optional[str] = None  # ISO datetime string
    chain_task_path: Optional[str] = None  # next task config to run after this one
    stop_after_consecutive_failures: int = 0  # 0 = disabled
    stop_after_duration_minutes: int = 0  # 0 = disabled

    def button_by_id(self, bid: str) -> Optional[ButtonConfig]:
        for b in self.buttons:
            if b.id == bid:
                return b
        return None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "buttons": [b.to_dict() for b in self.buttons],
            "steps": [s.to_dict() for s in self.steps],
            "loop_count": self.loop_count,
            "round_interval": self.round_interval,
            "round_interval_delay": self.round_interval_delay.to_dict(),
            "scheduled_start": self.scheduled_start,
            "chain_task_path": self.chain_task_path,
            "stop_after_consecutive_failures": self.stop_after_consecutive_failures,
            "stop_after_duration_minutes": self.stop_after_duration_minutes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TaskConfig":
        kw = dict(d)
        if "buttons" in kw:
            kw["buttons"] = [ButtonConfig.from_dict(b) for b in kw["buttons"]]
        if "steps" in kw:
            kw["steps"] = [StepConfig.from_dict(s) for s in kw["steps"]]
        if "round_interval_delay" in kw:
            kw["round_interval_delay"] = DelayConfig.from_dict(kw["round_interval_delay"])
        return cls(**{k: v for k, v in kw.items() if k in cls.__dataclass_fields__})


# ──────────────────────────────────────────────────────────────────
# Text-based sequence parser  (e.g. "A*3 -> B -> C*2")
# ──────────────────────────────────────────────────────────────────

_STEP_RE = re.compile(r"([A-Za-z0-9_]+)(?:\*(\d+))?")


def parse_sequence_text(text: str, button_map: Dict[str, str]) -> List[StepConfig]:
    """
    Parse a text sequence like ``A*3 -> B -> C*2`` into StepConfigs.

    Args:
        text: The sequence string.
        button_map: Mapping from short name → button id.

    Returns:
        List of ``StepConfig``.
    """
    steps: List[StepConfig] = []
    parts = [p.strip() for p in text.split("->")]
    for part in parts:
        # Support mutual-exclusion: "A|B" means whichever is found first
        alternatives = [alt.strip() for alt in part.split("|")]
        button_ids: List[str] = []
        repeat = 1
        for alt in alternatives:
            m = _STEP_RE.fullmatch(alt)
            if m:
                name = m.group(1)
                r = int(m.group(2)) if m.group(2) else 1
                repeat = max(repeat, r)
                bid = button_map.get(name)
                if bid:
                    button_ids.append(bid)
        if button_ids:
            steps.append(StepConfig(button_ids=button_ids, repeat=repeat))
    return steps


# ──────────────────────────────────────────────────────────────────
# Execution statistics
# ──────────────────────────────────────────────────────────────────

@dataclass
class RoundStats:
    success: int = 0
    failure: int = 0
    skipped: int = 0


@dataclass
class RunStats:
    rounds_completed: int = 0
    total_rounds: int = 0
    current_step: int = 0
    total_steps: int = 0
    current_round_stats: RoundStats = field(default_factory=RoundStats)
    elapsed: float = 0.0


# ──────────────────────────────────────────────────────────────────
# Sequence Scheduler
# ──────────────────────────────────────────────────────────────────

class SequenceScheduler:
    """Execute a TaskConfig in a background thread."""

    def __init__(
        self,
        capture: ScreenCapture,
        matcher: ImageMatcher,
        clicker: Clicker,
        on_log: Optional[Callable[[str], None]] = None,
        on_state_change: Optional[Callable[[TaskState], None]] = None,
        on_stats_update: Optional[Callable[[RunStats], None]] = None,
        on_failure_screenshot: Optional[Callable[[np.ndarray, str], None]] = None,
        on_chain_task: Optional[Callable[[str], None]] = None,
        on_recognition_result: Optional[Callable[[bool], None]] = None,
    ):
        self.capture = capture
        self.matcher = matcher
        self.clicker = clicker
        self._on_log = on_log or (lambda msg: None)
        self._on_state_change = on_state_change or (lambda s: None)
        self._on_stats_update = on_stats_update or (lambda s: None)
        self._on_failure_screenshot = on_failure_screenshot or (lambda img, msg: None)
        self._on_chain_task = on_chain_task or (lambda path: None)
        self._on_recognition_result = on_recognition_result or (lambda success: None)

        self._state = TaskState.IDLE
        self._thread: Optional[threading.Thread] = None
        self._pause_event = threading.Event()
        self._pause_event.set()  # not paused
        self._stop_event = threading.Event()

        self._task: Optional[TaskConfig] = None
        self._stats = RunStats()
        self._template_cache: Dict[str, np.ndarray] = {}

        # Screenshot cache: avoid re-capturing within a short window
        self._screenshot_cache: Optional[np.ndarray] = None
        self._screenshot_cache_time: float = 0.0
        self._screenshot_cache_ttl: float = 0.15  # 150ms

        # Consecutive failure tracking (for stop conditions)
        self._consecutive_failures: int = 0

    # ─── State management ───────────────────────────────────────

    @property
    def state(self) -> TaskState:
        return self._state

    @property
    def stats(self) -> RunStats:
        return self._stats

    def _set_state(self, state: TaskState) -> None:
        self._state = state
        self._on_state_change(state)

    def _log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        full = f"[{ts}] {msg}"
        logger.info(full)
        self._on_log(full)

    # ─── Control ────────────────────────────────────────────────

    def start(self, task: TaskConfig) -> None:
        if self._state == TaskState.RUNNING:
            logger.warning("Scheduler already running")
            return
        self._task = task
        self._stop_event.clear()
        self._pause_event.set()
        self._template_cache.clear()
        self._stats = RunStats(total_rounds=task.loop_count, total_steps=len(task.steps))
        self._screenshot_cache = None
        self._screenshot_cache_time = 0.0
        self._consecutive_failures = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self) -> None:
        if self._state == TaskState.RUNNING:
            self._pause_event.clear()
            self._set_state(TaskState.PAUSED)
            self._log("⏸ Task paused")

    def resume(self) -> None:
        if self._state == TaskState.PAUSED:
            self._pause_event.set()
            self._set_state(TaskState.RUNNING)
            self._log("▶ Task resumed")

    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.set()  # unblock if paused
        self._set_state(TaskState.STOPPED)
        self._log("⏹ Task stopped")

    def is_running(self) -> bool:
        return self._state in (TaskState.RUNNING, TaskState.PAUSED)

    # ─── Cached screenshot capture ───────────────────────────────

    def _capture_screenshot(self) -> np.ndarray:
        """Capture a screenshot, using the cache if still fresh."""
        now = time.time()
        if (
            self._screenshot_cache is not None
            and (now - self._screenshot_cache_time) < self._screenshot_cache_ttl
        ):
            return self._screenshot_cache
        frame = self.capture.capture_full()
        self._screenshot_cache = frame
        self._screenshot_cache_time = now
        return frame

    def _invalidate_screenshot_cache(self) -> None:
        self._screenshot_cache = None
        self._screenshot_cache_time = 0.0

    # ─── Template loading (cached) ──────────────────────────────

    def _get_template(self, button: ButtonConfig) -> Optional[np.ndarray]:
        path = button.image_path
        if path in self._template_cache:
            return self._template_cache[path]
        try:
            tpl = self.matcher.load_template(path)
            self._template_cache[path] = tpl
            return tpl
        except FileNotFoundError:
            self._log(f"✖ Template not found: {path}")
            return None

    # ─── Recognition ────────────────────────────────────────────

    def _recognise(
        self, button: ButtonConfig, screenshot: np.ndarray
    ) -> MatchResult:
        tpl = self._get_template(button)
        if tpl is None:
            return MatchResult(found=False)
        return self.matcher.match(
            screenshot,
            tpl,
            confidence=button.confidence,
            region=button.region,
        )

    # ─── Single step execution ──────────────────────────────────

    def _wait_condition(
        self, step: StepConfig, buttons: List[ButtonConfig]
    ) -> bool:
        """Wait until condition met or timeout. Returns True if met."""
        deadline = time.time() + step.condition_timeout
        while time.time() < deadline:
            if self._stop_event.is_set():
                return False
            self._pause_event.wait()
            self._invalidate_screenshot_cache()
            screenshot = self._capture_screenshot()
            found_any = any(self._recognise(b, screenshot).found for b in buttons)
            if step.condition == StepCondition.WAIT_APPEAR and found_any:
                return True
            if step.condition == StepCondition.WAIT_DISAPPEAR and not found_any:
                return True
            time.sleep(0.3)
        self._log(f"⏰ Condition timeout ({step.condition.value}) after {step.condition_timeout}s")
        return False

    def _execute_step(self, step: StepConfig, step_idx: int) -> None:
        """Execute a single step: recognise → (optional condition) → click × repeat."""
        buttons = [self._task.button_by_id(bid) for bid in step.button_ids]
        buttons = [b for b in buttons if b is not None]
        if not buttons:
            self._log(f"Step {step_idx + 1}: no valid buttons configured — skipping")
            self._stats.current_round_stats.skipped += 1
            return

        names = "/".join(b.name or b.id for b in buttons)
        self._log(f"Step {step_idx + 1}: [{names}] ×{step.repeat}")

        # Condition check
        if step.condition != StepCondition.NONE:
            if not self._wait_condition(step, buttons):
                self._stats.current_round_stats.skipped += 1
                return

        for rep in range(step.repeat):
            if self._stop_event.is_set():
                return
            self._pause_event.wait()

            self._invalidate_screenshot_cache()
            screenshot = self._capture_screenshot()

            # Mutual-exclusion: try each button, click the first found
            # Use parallel recognition when there are multiple buttons
            matched_button: Optional[ButtonConfig] = None
            result: Optional[MatchResult] = None

            if len(buttons) > 1:
                # Parallel multi-button recognition via thread pool
                with ThreadPoolExecutor(max_workers=min(len(buttons), 4)) as pool:
                    futures = {
                        pool.submit(self._recognise, btn, screenshot): btn
                        for btn in buttons
                    }
                    for future in as_completed(futures):
                        res = future.result()
                        if res.found:
                            matched_button = futures[future]
                            result = res
                            # Cancel remaining futures
                            for f in futures:
                                f.cancel()
                            break
            else:
                for btn in buttons:
                    res = self._recognise(btn, screenshot)
                    if res.found:
                        matched_button = btn
                        result = res
                        break

            if matched_button is not None and result is not None and result.center is not None:
                cx, cy = result.center
                self._perform_click(matched_button, cx, cy)
                self._log(
                    f"  ✔ {matched_button.name or matched_button.id} found "
                    f"({result.confidence:.2f}) at ({cx},{cy}) — clicked"
                )
                self._stats.current_round_stats.success += 1
                self._consecutive_failures = 0
                self._on_recognition_result(True)
            else:
                self._consecutive_failures += 1
                self._on_recognition_result(False)
                # Handle failure for the first button (primary)
                primary = buttons[0]
                handled = self._handle_failure(primary, step_idx, rep, screenshot)
                if not handled:
                    return  # abort

            # Intra-button delay between repeats
            if rep < step.repeat - 1:
                d = step.intra_delay.get()
                time.sleep(d)

        # Inter-button delay after this step
        d = step.inter_delay.get()
        time.sleep(d)

    def _perform_click(self, button: ButtonConfig, x: int, y: int) -> None:
        ct = button.click_type
        if ct == ClickType.SINGLE:
            self.clicker.single_click(x, y, offset=button.click_offset_range)
        elif ct == ClickType.DOUBLE:
            self.clicker.double_click(x, y, offset=button.click_offset_range)
        elif ct == ClickType.RIGHT:
            self.clicker.right_click(x, y, offset=button.click_offset_range)
        elif ct == ClickType.LONG_PRESS:
            self.clicker.long_press(x, y, duration=button.long_press_duration, offset=button.click_offset_range)

    def _handle_failure(
        self,
        button: ButtonConfig,
        step_idx: int,
        rep: int,
        screenshot: np.ndarray,
    ) -> bool:
        """
        Apply the button's fallback strategy.
        Returns True if the step can continue, False to abort.
        """
        name = button.name or button.id
        action = button.fallback_action

        # Retry logic
        if action == FailureAction.RETRY:
            for attempt in range(button.retry_count):
                if self._stop_event.is_set():
                    return False
                self._log(f"  ↻ Retry {attempt + 1}/{button.retry_count} for {name}")
                time.sleep(button.retry_interval)
                screenshot = self.capture.capture_full()
                res = self._recognise(button, screenshot)
                if res.found and res.center:
                    self._perform_click(button, *res.center)
                    self._stats.current_round_stats.success += 1
                    self._log(f"  ✔ {name} found on retry ({res.confidence:.2f})")
                    return True
            self._log(f"  ✖ {name} not found after retries — skipping")
            self._stats.current_round_stats.failure += 1
            self._on_failure_screenshot(screenshot, f"step{step_idx}_rep{rep}_{name}")
            return True  # continue with next step

        if action == FailureAction.SKIP:
            self._log(f"  ⏭ {name} not found — skipping")
            self._stats.current_round_stats.skipped += 1
            return True

        if action == FailureAction.ABORT:
            self._log(f"  ✖ {name} not found — aborting task")
            self._stats.current_round_stats.failure += 1
            self._on_failure_screenshot(screenshot, f"step{step_idx}_rep{rep}_{name}")
            return False

        if action == FailureAction.ALERT:
            self._log(f"  ⚠ {name} not found — alert triggered")
            self._stats.current_round_stats.failure += 1
            self._on_failure_screenshot(screenshot, f"step{step_idx}_rep{rep}_{name}")
            return True

        return True

    # ─── Main loop ──────────────────────────────────────────────

    def _run(self) -> None:
        task = self._task
        if task is None:
            return

        # Scheduled start
        if task.scheduled_start:
            try:
                target = datetime.fromisoformat(task.scheduled_start)
                now = datetime.now()
                if target > now:
                    wait = (target - now).total_seconds()
                    self._log(f"⏰ Waiting until {task.scheduled_start} ({wait:.0f}s)")
                    # Interruptible wait
                    if self._stop_event.wait(timeout=wait):
                        return
            except ValueError:
                self._log(f"⚠ Invalid scheduled_start: {task.scheduled_start}")

        self._set_state(TaskState.RUNNING)
        self._log(f"▶ Starting task: {task.name}")
        start_time = time.time()

        loop_count = task.loop_count if task.loop_count > 0 else float("inf")
        rnd = 0
        try:
            while rnd < loop_count:
                if self._stop_event.is_set():
                    break
                self._pause_event.wait()

                # Duration-limit stop condition
                if task.stop_after_duration_minutes > 0:
                    elapsed_min = (time.time() - start_time) / 60.0
                    if elapsed_min >= task.stop_after_duration_minutes:
                        self._log(f"⏹ Duration limit reached ({task.stop_after_duration_minutes}min)")
                        break

                rnd += 1
                self._stats.rounds_completed = rnd - 1
                self._stats.current_round_stats = RoundStats()
                self._log(f"── Round {rnd}/{task.loop_count if task.loop_count > 0 else '∞'} ──")

                for si, step in enumerate(task.steps):
                    if self._stop_event.is_set():
                        break
                    self._stats.current_step = si + 1
                    self._stats.elapsed = time.time() - start_time
                    self._on_stats_update(self._stats)
                    self._execute_step(step, si)

                    # Consecutive-failure stop condition
                    if (
                        task.stop_after_consecutive_failures > 0
                        and self._consecutive_failures >= task.stop_after_consecutive_failures
                    ):
                        self._log(
                            f"⏹ Consecutive failure limit reached "
                            f"({self._consecutive_failures} failures)"
                        )
                        self._stop_event.set()
                        break

                self._stats.rounds_completed = rnd
                self._stats.elapsed = time.time() - start_time
                self._on_stats_update(self._stats)

                rs = self._stats.current_round_stats
                self._log(
                    f"── Round {rnd} done: ✔{rs.success} ✖{rs.failure} ⏭{rs.skipped} ──"
                )

                # Interval between rounds
                if rnd < loop_count and not self._stop_event.is_set():
                    d = task.round_interval_delay.get()
                    self._log(f"Waiting {d:.1f}s before next round…")
                    if self._stop_event.wait(timeout=d):
                        break

            if not self._stop_event.is_set():
                self._set_state(TaskState.FINISHED)
                self._log("✔ Task finished")
            else:
                self._log("Task was stopped")

        except Exception as exc:
            self._set_state(TaskState.ERROR)
            self._log(f"✖ Error: {exc}")
            logger.exception("Scheduler error")

        # Chain to next task if configured
        if (
            not self._stop_event.is_set()
            and task.chain_task_path
            and self._state == TaskState.FINISHED
        ):
            self._log(f"Chaining to next task: {task.chain_task_path}")
            self._on_chain_task(task.chain_task_path)
