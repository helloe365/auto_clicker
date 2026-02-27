# AutoClick Vision

> Image-recognition-based tool for automatically detecting and clicking on-screen buttons.

## Features

- **Screen Capture** — high-performance full-screen and region-based capture via `mss`, multi-monitor support
- **Template Matching** — single-scale and multi-scale matching with configurable confidence thresholds, grayscale mode, optional SIFT/ORB feature matching
- **Smart Clicking** — single / double / right-click / long-press with random offset and Bézier-curve mouse movement for human-like behavior; `pydirectinput` mode for fullscreen games
- **Sequence Scheduling** — define click sequences (`A*3 -> B -> C*2`), conditional steps (wait for appear / disappear), mutual-exclusion recognition, intra/inter-button delays
- **Loop Control** — configurable round count, interval, scheduled start, and chained multi-task execution
- **Watchdog** — heartbeat monitoring, screen-inactivity detection, auto-restart on freeze
- **Configuration** — JSON / YAML configs, import / export, preset templates, optional encryption, auto-save, config versioning with migration
- **PyQt6 UI** — button editor with drag-and-drop, visual & text sequence editor, real-time log viewer with screenshot thumbnails, system tray, global hotkeys (F9/F10/F11)
- **Error Handling** — global exception handler, failure-rate alerting, Webhook notifications (Telegram / DingTalk / Slack), screenshot archiving

## Project Structure

```
autoclickVision/
├── core/
│   ├── capture.py          # Screen capture module
│   ├── matcher.py          # Image recognition module
│   ├── clicker.py          # Mouse click module
│   ├── scheduler.py        # Task scheduling module
│   └── watchdog.py         # Watchdog module
├── config/
│   ├── config_manager.py   # Config read/write
│   └── presets/            # Saved preset templates
├── ui/
│   ├── main_window.py      # Main window
│   ├── button_editor.py    # Button configuration panel
│   ├── sequence_editor.py  # Sequence editor panel
│   └── log_viewer.py       # Log viewer panel
├── notifications.py        # Error handling & webhook notifications
├── logs/                   # Runtime logs and screenshot archives
├── assets/                 # UI icon resources
├── tests/                  # Unit tests
├── requirements.txt
├── main.py                 # Entry point
└── README.md
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r autoclickVision/requirements.txt
```

### 2. Run the Application

```bash
python -m autoclickVision.main
```

### 3. Global Hotkeys

| Key  | Action |
|------|--------|
| F9   | Start  |
| F10  | Pause / Resume |
| F11  | Stop   |

## Usage Guide

### Adding Buttons

1. Open the **Buttons** tab in the left panel.
2. Click **+ Add** or drag-and-drop image files (PNG, JPG, BMP) onto the panel.
3. Use **✂ Capture from Screen** to crop a button directly from the current screen.
4. Configure each button: name, confidence threshold, click type, ROI region, retry strategy.
5. Click **🔍 Test Recognition** to verify matching on the current screen.

### Creating a Sequence

1. Switch to the **Sequence** tab.
2. Use **Visual Mode** to add steps with the **+ Add Step** button, or switch to **Text Mode** and enter a sequence like `Login*1 -> Confirm*3 -> Close`.
3. Configure per-step delays, conditions (wait-appear / wait-disappear), and timeouts.
4. Set loop count, round interval, and optional scheduled start.

### Saving / Loading Configs

- Use the toolbar buttons **📂 Open**, **💾 Save**, and **📄 Save As…** to manage task configurations.
- Configs are stored as JSON or YAML files and can be shared across machines.
- Preset templates can be saved via the config manager for quick re-use.

## Building a Standalone Executable

```bash
pip install pyinstaller
pyinstaller --onefile --windowed autoclickVision/main.py --name AutoClickVision
```

The resulting `.exe` in `dist/` can be distributed without requiring Python.

## Running Tests

```bash
python -m pytest autoclickVision/tests/ -v
```

## Dependencies

| Package | Purpose |
|---------|---------|
| opencv-python | Image matching & processing |
| mss | Fast screen capture |
| pyautogui | Mouse / keyboard automation |
| pydirectinput | Low-level input for games |
| PyQt6 | GUI framework |
| numpy | Array operations |
| pyyaml | YAML config support |
| keyboard | Global hotkeys |
| Pillow | Image utilities |
| requests | Webhook HTTP calls |
| schedule | Scheduled task triggers |

## License

MIT
