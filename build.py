#!/usr/bin/env python3
"""Package the dashboard into a single desktop executable with PyInstaller.

Usage::

    python -m pip install pyinstaller
    python build.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "bmrcl" / "data"
SEP = ";" if sys.platform.startswith("win") else ":"


def main() -> int:
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "BMRCL-Train-Tracker",
        "--add-data",
        f"{DATA / 'timetable.json'}{SEP}bmrcl/data",
        "--add-data",
        f"{DATA / 'lines'}{SEP}bmrcl/data/lines",
        str(ROOT / "run.py"),
    ]
    print(" ".join(args))
    return subprocess.call(args, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
