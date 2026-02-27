"""
PyInstaller build script for AutoClick Vision.

Usage:
    python build.py

Produces:  dist/AutoClickVision.exe  (one-file Windows executable)
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENTRY = ROOT / "autoclickVision" / "main.py"
ASSETS = ROOT / "autoclickVision" / "assets"
ICON = ASSETS / "icon.ico"
NAME = "AutoClickVision"


def build():
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        f"--name={NAME}",
        # Bundle the assets folder
        f"--add-data={ASSETS};autoclickVision/assets",
    ]
    # Optional icon
    if ICON.exists():
        cmd.append(f"--icon={ICON}")

    # Hidden imports that PyInstaller may miss
    cmd.extend([
        "--hidden-import=cv2",
        "--hidden-import=mss",
        "--hidden-import=pyautogui",
        "--hidden-import=pydirectinput",
        "--hidden-import=keyboard",
        "--hidden-import=requests",
        "--hidden-import=yaml",
        "--hidden-import=numpy",
    ])

    cmd.append(str(ENTRY))

    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(ROOT))
    print(f"\nBuild complete → dist/{NAME}.exe")


if __name__ == "__main__":
    build()
