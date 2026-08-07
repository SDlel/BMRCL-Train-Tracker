#!/usr/bin/env python3
"""Package the dashboard into a standalone desktop executable with PyInstaller.

Usage::

    python -m pip install -e ".[package]"
    python package.py

Named ``package.py`` rather than ``build.py`` because a module named ``build``
in the project root shadows the PyPA ``build`` package for anything run from
here, which breaks ``python -m build``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "bmrcl" / "data"
SEP = ";" if sys.platform.startswith("win") else ":"
APP_NAME = "BMRCL-Train-Tracker"


def ensure_pyinstaller() -> None:
    """Fail early with a useful message rather than a bare exit code."""
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        sys.exit(
            "PyInstaller is not installed.\n"
            '  python -m pip install -e ".[package]"\n'
            "or\n"
            "  python -m pip install pyinstaller"
        )


def main() -> int:
    ensure_pyinstaller()
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        "--add-data",
        f"{DATA / 'timetable.json'}{SEP}bmrcl/data",
        "--add-data",
        f"{DATA / 'lines'}{SEP}bmrcl/data/lines",
        str(ROOT / "run.py"),
    ]
    print(" ".join(args))
    result = subprocess.call(args, cwd=ROOT)
    if result == 0:
        print(f"\nBuilt: {ROOT / 'dist' / APP_NAME}")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
