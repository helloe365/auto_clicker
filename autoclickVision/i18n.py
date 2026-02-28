"""
Internationalization (i18n) module for AutoClick Vision.

Provides a simple dictionary-based translation system.
The current language is loaded from a JSON preference file on startup.
All UI strings are wrapped with ``tr("english text")`` which returns
the translated string for the active language.

Supported languages: English ("en"), Chinese ("zh").
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

# ── Preference persistence ────────────────────────────────────────
_PREF_FILE = Path(__file__).resolve().parent / "config" / "language.json"

_current_lang: str = "en"


def _load_preference() -> str:
    """Return the saved language code, or empty string if none."""
    try:
        if _PREF_FILE.exists():
            data = json.loads(_PREF_FILE.read_text(encoding="utf-8"))
            return data.get("language", "")
    except Exception:
        pass
    return ""


def save_preference(lang: str) -> None:
    """Persist the language choice to disk."""
    _PREF_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PREF_FILE.write_text(json.dumps({"language": lang}), encoding="utf-8")


def set_language(lang: str) -> None:
    """Set the active language (call before building UI)."""
    global _current_lang
    _current_lang = lang


def get_language() -> str:
    """Return the current language code."""
    return _current_lang


def init_language() -> str:
    """Load saved preference and set the active language. Returns the code."""
    lang = _load_preference()
    if lang in ("en", "zh"):
        set_language(lang)
    else:
        set_language("en")
    return get_language()


# ── Translation dictionary ────────────────────────────────────────
# Key = English string, Value = Chinese translation.
# If a key is not found, the original (English) string is returned.

_ZH: Dict[str, str] = {
    # ── General ──────────────────────────────────────────────
    "AutoClick Vision": "AutoClick Vision — 自动点击视觉",
    "Error": "错误",
    "Success": "成功",
    "Warning": "警告",
    "OK": "确定",
    "Cancel": "取消",
    "Close": "关闭",
    "Language": "语言",

    # ── Main Window — toolbar ────────────────────────────────
    "Main Toolbar": "主工具栏",
    "▶ Start": "▶ 开始",
    "⏸ Pause": "⏸ 暂停",
    "⏹ Stop": "⏹ 停止",
    "📂 Open": "📂 打开",
    "💾 Save": "💾 保存",
    "📄 Save As…": "📄 另存为…",
    "Settings": "设置",

    # ── Main Window — tabs ───────────────────────────────────
    "Buttons": "按钮",
    "Sequence": "序列",

    # ── Main Window — status bar ─────────────────────────────
    "Idle": "空闲",
    "Step: –": "步骤: –",
    "Round: –": "轮次: –",
    "Elapsed: 0s": "已用时: 0s",

    # ── Main Window — tray ───────────────────────────────────
    "Show": "显示",
    "Quit": "退出",
    "Running in background. Double-click tray icon to restore.":
        "已最小化至托盘。双击托盘图标恢复窗口。",

    # ── Main Window — dialogs / messages ─────────────────────
    "No Steps": "无步骤",
    "Please add at least one step to the sequence.":
        "请至少添加一个步骤到序列中。",
    "Open Config": "打开配置",
    "Config Files (*.json *.yaml *.yml)": "配置文件 (*.json *.yaml *.yml)",
    "Save Config As": "配置另存为",
    "JSON (*.json);;YAML (*.yaml)": "JSON (*.json);;YAML (*.yaml)",
    "Settings updated": "设置已更新",
    "Task finished!": "任务完成！",
    "Task error!": "任务出错！",

    # ── Button Editor ────────────────────────────────────────
    "+ Add": "+ 添加",
    "– Remove": "– 删除",
    "📂 Import": "📂 导入",
    "Name:": "名称:",
    "Image:": "图像:",
    "Browse…": "浏览…",
    "Confidence:": "置信度:",
    "Click Type:": "点击类型:",
    "Offset Range:": "偏移范围:",
    "Retry Count:": "重试次数:",
    "Retry Interval:": "重试间隔:",
    "Fallback:": "失败策略:",
    "ROI:": "识别区域:",
    "Select ROI…": "选择区域…",
    "🔍 Test Recognition": "🔍 测试识别",
    "✂ Capture from Screen": "✂ 屏幕截取",
    "Import Button Images": "导入按钮图片",
    "Images (*.png *.jpg *.jpeg *.bmp)": "图片 (*.png *.jpg *.jpeg *.bmp)",
    "No Button": "未选择按钮",
    "Select a button first.": "请先选择一个按钮。",
    "No Image": "无图片",
    "Button has no valid image path.": "按钮没有有效的图片路径。",
    "Match Found": "匹配成功",
    "Not Found": "未找到",
    "Select Button Image": "选择按钮图片",

    # ── Sequence Editor ──────────────────────────────────────
    "Visual Mode": "可视模式",
    "Text Mode": "文本模式",
    "Button:": "按钮:",
    "Repeat:": "重复:",
    "Intra Delay:": "步内延迟:",
    "Inter Delay:": "步间延迟:",
    "Condition:": "条件:",
    "Timeout:": "超时:",
    "Remove": "删除",
    "+ Add Step": "+ 添加步骤",
    "↑ Up": "↑ 上移",
    "↓ Down": "↓ 下移",
    "Enter sequence (e.g. A*3 -> B -> C*2):": "输入序列（例如 A*3 -> B -> C*2）:",
    "Apply": "应用",
    "Loop & Schedule": "循环与计划",
    "Loop Count:": "循环次数:",
    "Round Interval:": "轮次间隔:",
    "Scheduled Start": "定时启动",
    "Sequence cleared successfully.": "序列已成功清空。",
    "Sequence applied successfully": "序列应用成功",

    # ── Log Viewer ───────────────────────────────────────────
    "Round Summary": "轮次摘要",
    "Round": "轮次",
    "Failure": "失败",
    "Skipped": "跳过",
    "Clear": "清空",
    "Export TXT": "导出 TXT",
    "Export CSV": "导出 CSV",
    "History": "历史记录",
    "Screenshot": "截图",
    "Export Log": "导出日志",
    "Text Files (*.txt)": "文本文件 (*.txt)",
    "CSV Files (*.csv)": "CSV 文件 (*.csv)",
    "No log files found.": "未找到日志文件。",
    "Historical Runs": "历史运行记录",
    "Load into viewer": "加载到查看器",

    # ── Settings Dialog ──────────────────────────────────────
    "Grayscale matching": "灰度匹配",
    "Multi-scale matching": "多尺度匹配",
    "Scale min:": "最小缩放:",
    "Scale max:": "最大缩放:",
    "Scale step:": "缩放步长:",
    "Bézier curve mouse movement": "贝塞尔曲线鼠标移动",
    "PyDirectInput mode (fullscreen games)": "PyDirectInput 模式（全屏游戏）",
    "Matcher": "匹配器",
    "Click": "点击",
    "Notifications": "通知",
    "Screenshots": "截图",
    "Stop Conditions": "停止条件",
    "Failure-Rate Alert": "失败率告警",
    "Threshold:": "阈值:",
    "Window size:": "窗口大小:",
    "Webhooks (Telegram / DingTalk / Slack)": "Webhooks（Telegram / 钉钉 / Slack）",
    "Name": "名称",
    "URL": "URL",
    "Archive failure screenshots to logs/screenshots/":
        "将失败截图归档至 logs/screenshots/",
    "Stop after N consecutive failures:": "连续失败 N 次后停止:",
    "Stop after duration:": "运行时长后停止:",
    "Disabled": "禁用",

    # ── Capture overlay HUD ──────────────────────────────────
    "Zoom": "缩放",
    "Wheel": "滚轮",
    "zoom": "缩放",
    "Drag": "拖拽",
    "pan": "平移",
    "select": "选择",
    "cancel": "取消",

    # ── Language dialog ──────────────────────────────────────
    "Select Language": "选择语言",
    "English": "English",
    "Chinese (中文)": "Chinese (中文)",
    "Please select your language:": "请选择您的语言:",
    "Language changed. Please restart the application for the change to take effect.":
        "语言已更改。请重启应用程序以使更改生效。",
    "Restart Required": "需要重启",
}


def tr(text: str) -> str:
    """Return the translated string for the current language.

    If the current language is English or the key is missing, return *text* unchanged.
    """
    if _current_lang == "en":
        return text
    return _ZH.get(text, text)
