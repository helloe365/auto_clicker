# AutoClick Vision — Full Development TODO

> An image-recognition-based tool for automatically detecting and clicking on-screen buttons
> Stack: Python + OpenCV + PyAutoGUI + PyQt6

---

## 📁 Project Structure

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
├── logs/                   # Runtime logs and screenshot archives
├── assets/                 # UI icon resources
├── tests/                  # Unit tests
├── requirements.txt
├── README.md
└── main.py
```

---

## 🔧 PHASE 1 — Core Recognition Engine

### 1.1 Screen Capture Module `capture.py`
- [ ] Implement full-screen capture (using `mss` library, faster than PyAutoGUI)
- [ ] Support **region capture** with a configurable rectangular ROI (Region of Interest)
- [ ] Convert captured frames to OpenCV `numpy` format
- [ ] Support multi-monitor selection

### 1.2 Image Matching Module `matcher.py`
- [ ] Implement basic template matching (`cv2.matchTemplate` + `TM_CCOEFF_NORMED`)
- [ ] Support **per-button custom confidence threshold**
- [ ] Support **multi-scale matching** (scale range 0.7x ~ 1.3x, step 0.05)
- [ ] Support **grayscale matching mode** (handles color changes / highlighted button states)
- [ ] Support SIFT/ORB feature-point matching (optional, for rotated or deformed buttons)
- [ ] Return best-match coordinates, confidence score, and bounding rectangle
- [ ] Implement **region-restricted recognition** — search only within a specified screen area
- [ ] Configurable failure strategy per button: `retry` / `skip` / `abort` / `alert`

### 1.3 Mouse Click Module `clicker.py`
- [ ] Wrap single click, double click, right click, and long press
- [ ] Support **random coordinate offset** on click (±N pixels to simulate human behavior)
- [ ] Support **Bézier curve mouse movement** (avoids straight-line detection)
- [ ] Randomize movement speed (randomized duration per move)
- [ ] Support `PyDirectInput` mode (for fullscreen games requiring direct input injection)

---

## 🔧 PHASE 2 — Task Scheduling System

### 2.1 Button Config Data Structure
- [ ] Define `ButtonConfig` dataclass:
  ```
  id, name, image_path, confidence,
  click_type, click_offset_range,
  retry_count, retry_interval,
  region (ROI), fallback_action
  ```

### 2.2 Sequence Scheduler `scheduler.py`
- [ ] Support defining click sequences, e.g. `A*3 -> B -> C*2`
- [ ] Support **intra-button delay** (interval between repeated clicks of the same button)
- [ ] Support **inter-button delay** (interval between different buttons in a sequence)
- [ ] All delays support: fixed value / random range (min~max) / default random
- [ ] Support **conditional steps**: wait for a button to appear before proceeding, with timeout fallback
- [ ] Support **mutual-exclusion recognition** at the step level (click whichever candidate button is found first)
- [ ] Support "wait for button to disappear" as a step trigger condition

### 2.3 Loop Control
- [ ] Configurable **loop count** (default 50, 0 = infinite loop)
- [ ] Configurable **interval between rounds** (default 10s)
- [ ] Support **scheduled start**: begin execution at a specific date/time
- [ ] Support chained multi-task execution: automatically switch to task B after task A completes

### 2.4 Watchdog Module `watchdog.py`
- [ ] Monitor the main thread for freezes; auto-restart the task on timeout
- [ ] Detect prolonged screen inactivity (possible freeze or disconnection)
- [ ] Trigger notifications on exception (system tray popup / Webhook)

---

## 🔧 PHASE 3 — Configuration Management

### 3.1 Config Schema Design
- [ ] Store full task configuration in JSON / YAML format
- [ ] Config includes: button list, sequence definition, delay parameters, loop settings, global options
- [ ] Support config file **import / export**
- [ ] Support **preset templates**: save and load from `config/presets/`
- [ ] Config versioning: backward-compatible migration for older config files

### 3.2 Config Manager `config_manager.py`
- [ ] Implement config read, validate, and write
- [ ] Auto-save on config change (prevent accidental data loss)
- [ ] Support optional config encryption (protect sensitive path information)

---

## 🔧 PHASE 4 — User Interface

### 4.1 Main Window `main_window.py`
- [ ] Top toolbar: Start / Pause / Stop / Settings
- [ ] Global hotkey bindings: `F9` Start, `F10` Pause, `F11` Stop
- [ ] System tray icon with minimize-to-tray background running support
- [ ] Real-time status display: current step, current round, elapsed time
- [ ] Overall progress bar: completed rounds / total rounds

### 4.2 Button Configuration Panel `button_editor.py`
- [ ] Drag-and-drop image upload with batch import support
- [ ] Per-button configuration: name, confidence, click type, ROI region
- [ ] **Test Recognition button**: take an instant screenshot and highlight all matching positions on screen
- [ ] Button image preview with thumbnails
- [ ] Built-in screen region capture tool to crop button images directly from the screen

### 4.3 Sequence Editor Panel `sequence_editor.py`
- [ ] Visual drag-and-drop step ordering (card-based UI)
- [ ] Per-step configuration: button selection, repeat count, pre-click delay, post-click delay
- [ ] Toggle between **text mode** (`A*3 -> B -> C*2` syntax) and **visual mode**
- [ ] Loop configuration: round count, interval between rounds
- [ ] Schedule configuration: timed start, stop conditions

### 4.4 Log Viewer Panel `log_viewer.py`
- [ ] Real-time scrolling log output (timestamp + step description + result)
- [ ] On recognition failure, attach a **screenshot thumbnail** — click to enlarge
- [ ] Per-round execution summary: success count, failure count, skipped count
- [ ] Export logs as TXT / CSV
- [ ] Browse historical run records

---

## 🔧 PHASE 5 — Error Handling & Notifications

- [ ] Global exception handler: log errors and show user-facing alert dialogs
- [ ] Trigger alert when recognition failure rate exceeds a configurable threshold
- [ ] Optional Webhook notifications: send to Telegram Bot / DingTalk / Slack
- [ ] System tray popup notifications (task complete / task error)
- [ ] Screenshot archiving: auto-save each recognition screenshot to `logs/screenshots/` (toggleable)

---

## 🔧 PHASE 6 — Testing & Optimization

### 6.1 Unit Tests
- [ ] Test template matching accuracy across different screen resolutions
- [ ] Benchmark multi-scale matching performance (latency profiling)
- [ ] Test config read/write edge cases
- [ ] Test sequence scheduler delay precision

### 6.2 Performance Optimization
- [ ] Run screen capture and matching in a separate thread to avoid blocking the UI
- [ ] Parallel multi-button recognition using a thread pool
- [ ] Cache the last recognition result; skip re-capturing the same region within a short window

### 6.3 Build & Distribution
- [ ] Package as a single executable with `PyInstaller` (Windows `.exe`)
- [ ] Bundle OpenCV / Qt dependencies — no Python installation required for end users
- [ ] Provide `requirements.txt` for developers running from source

---

## 📦 Dependencies `requirements.txt`

```
opencv-python>=4.8
mss>=9.0
pyautogui>=0.9.54
pydirectinput>=1.0.4
PyQt6>=6.6
numpy>=1.24
pyyaml>=6.0
keyboard>=0.13
Pillow>=10.0
requests>=2.31       # Webhook notifications
schedule>=1.2        # Scheduled task triggering
pyinstaller>=6.0     # Build & packaging
```

---

## 🚀 Development Priority

| Priority | Scope |
|----------|-------|
| P0 — Must Have | Core recognition engine, basic sequence scheduling, minimal UI |
| P1 — Important | Confidence config, delay config, loop control, logging |
| P2 — Enhanced | Multi-scale matching, conditional steps, hotkeys, system tray |
| P3 — Optional | SIFT matching, Webhook alerts, scheduled triggers, encrypted config |

---

*Last updated: 2026-02-27*
