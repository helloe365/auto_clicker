[English](README.md) | **中文**

# AutoClick Vision

> 基于图像识别的自动点击工具 —— 通过 OpenCV 模板匹配自动检测并点击屏幕上的按钮。
>
> **技术栈：** Python 3 · OpenCV · mss · PyAutoGUI · PyQt6

![主窗口总览](image/README/4.png)

---

## 功能特性

| 分类 | 说明 |
|------|------|
| **屏幕截图** | 基于 `mss` 的高性能全屏 / 区域截图；支持多显示器；线程安全（每线程独立 `mss` 实例） |
| **模板匹配** | 单尺度 & 多尺度匹配（`TM_CCOEFF_NORMED`）；每按钮独立置信度阈值；灰度模式；区域限定搜索（ROI） |
| **智能点击** | 单击 / 双击 / 右键 / 长按；随机坐标偏移（±N 像素）；贝塞尔曲线鼠标移动；`pydirectinput` 全屏游戏模式 |
| **序列调度** | 文本语法（`A*3 -> B -> C*2`）与可视化卡片编辑器；条件步骤（等待出现 / 等待消失）；互斥识别；可配置按钮内 / 按钮间延迟 |
| **循环控制** | 可配置循环次数与间隔；定时启动；链式多任务执行；基于时长 & 连续失败的停止条件 |
| **看门狗** | 心跳监测；屏幕无活动检测；卡死时自动重启任务 |
| **配置管理** | JSON / YAML 配置文件；导入 / 导出；预设模板；自动保存；配置版本迁移 |
| **用户界面** | PyQt6 主窗口，滑动切换可视化 ↔ 文本模式；拖拽式按钮编辑器；可滚动彩色步骤卡片；实时日志查看器（含截图缩略图）；系统托盘图标；全局热键（F9 / F10 / F11）；设置对话框 |
| **错误处理** | 全局异常处理器；识别失败率告警；Webhook 通知（Telegram / 钉钉 / Slack）；截图自动归档 |

---

## 项目结构

```
autoclickVision/
├── core/
│   ├── capture.py          # 屏幕截图（线程安全 mss）
│   ├── matcher.py          # 模板匹配引擎
│   ├── clicker.py          # 鼠标点击自动化
│   ├── scheduler.py        # 序列调度器 & 循环控制
│   └── watchdog.py         # 卡死 / 无活动 看门狗
├── config/
│   ├── config_manager.py   # 配置读写 / 校验
│   └── presets/            # 已保存的预设模板
├── ui/
│   ├── main_window.py      # 主窗口 & 工具栏
│   ├── button_editor.py    # 按钮配置面板 & 屏幕截取覆盖层
│   ├── sequence_editor.py  # 滑动式可视化 / 文本序列编辑器
│   ├── log_viewer.py       # 实时日志查看器 & 轮次摘要
│   └── settings_dialog.py  # 应用设置对话框
├── notifications.py        # 异常处理 & Webhook 通知器
├── logs/                   # 运行时日志 & 截图归档
│   └── screenshots/        # 自动保存的失败截图
├── assets/                 # 图标 & 截取的按钮图片
│   └── captures/           # 从屏幕截取的按钮裁剪图
├── tests/                  # 单元测试
├── requirements.txt
├── main.py                 # 入口文件
└── README.md
```

---

## 快速开始

### 1. 创建虚拟环境（推荐）

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r autoclickVision/requirements.txt
```

### 3. 运行程序

```bash
python -m autoclickVision.main
```

主窗口将会打开并在系统托盘显示图标。可以最小化到托盘，双击托盘图标恢复窗口。

---

## 全局热键

| 按键 | 功能 |
|------|------|
| F9   | 开始 |
| F10  | 暂停 / 恢复 |
| F11  | 停止 |

---

## 使用指南

### 添加按钮

1. 打开左侧面板的 **Buttons（按钮）** 选项卡。
2. 点击 **+ Add** 或将图片文件（PNG、JPG、BMP）拖拽到面板中。
3. 使用 **✂ Capture from Screen（从屏幕截取）** 在屏幕上框选区域 —— 截取的图像会自动保存并添加为新按钮。
4. 使用 **Select ROI…（选择感兴趣区域）** 限定匹配的搜索范围。
5. 为每个按钮配置：名称、置信度阈值、点击类型、重试策略。
6. 点击 **🔍 Test Recognition（测试识别）** 在当前屏幕上验证匹配效果。

![按钮编辑器](image/README/1.png)

![测试识别](image/README/5.png)

### 创建序列

1. 切换到 **Sequence（序列）** 选项卡。
2. **Visual Mode（可视化模式）** —— 点击 **+ Add Step** 添加彩色步骤卡片；使用 **↑ Up / ↓ Down** 调整顺序；步骤较多时可滚动查看。

![序列编辑器 - 可视化模式](image/README/2.png)

3. **Text Mode（文本模式）** —— 输入序列语法如 `Login*1 -> Confirm*3 -> Close`，点击 **Apply** 应用（会显示成功或错误提示）。

![序列编辑器 - 文本模式](image/README/3.png)

4. 两种模式之间使用滑动动画切换。
5. 为每个步骤配置：按钮选择、重复次数、按钮内 / 按钮间延迟、条件（无 / 等待出现 / 等待消失）、超时时间。
6. 在"循环与调度"面板中设置 **Loop Count（循环次数）**、**Round Interval（轮次间隔）** 和可选的 **Scheduled Start（定时启动）**。

### 设置

从工具栏打开 **Settings（设置）** 可以配置：

- 灰度匹配模式
- 多尺度匹配（缩放范围和步长）
- 贝塞尔曲线鼠标移动
- DirectInput 模式
- 截图归档
- 失败率阈值和窗口大小
- Webhook 通知地址
- 停止条件（连续失败次数 / 运行时长限制）

### 保存 / 加载配置

- 工具栏上的 **📂 Open** / **💾 Save** / **📄 Save As…** 用于管理任务配置。
- 配置文件为 JSON 或 YAML 格式，可在不同设备间共享。

---

## 打包为独立可执行文件

使用内置的打包脚本：

```bash
python build.py
```

或手动执行：

```bash
pip install pyinstaller
pyinstaller --onefile --windowed autoclickVision/main.py --name AutoClickVision
```

生成的 `dist/AutoClickVision.exe` 无需安装 Python 即可分发运行。

---

## 运行测试

```bash
python -m pytest autoclickVision/tests/ -v
```

---

## 依赖列表

| 包名 | 用途 |
|------|------|
| `opencv-python` >= 4.8 | 图像匹配与处理 |
| `mss` >= 9.0 | 高速屏幕截图 |
| `pyautogui` >= 0.9.54 | 鼠标 / 键盘自动化 |
| `pydirectinput` >= 1.0.4 | 全屏游戏底层输入 |
| `PyQt6` >= 6.6 | GUI 框架 |
| `numpy` >= 1.24 | 数组运算 |
| `pyyaml` >= 6.0 | YAML 配置支持 |
| `keyboard` >= 0.13 | 全局热键 |
| `Pillow` >= 10.0 | 图像工具库 |
| `requests` >= 2.31 | Webhook HTTP 请求 |

---

## 开源协议

MIT
