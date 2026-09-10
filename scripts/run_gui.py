"""Start the PySide6 desktop GUI.

Examples:
    python scripts/run_gui.py
    python scripts/run_gui.py --input "C:\\path\\file-epo.fif" --output results/luna_gui
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lfp_analysis.app_info import APP_FULL_NAME, APP_NAME, DEFAULT_OUTPUT_DIRNAME
from lfp_analysis.gui import launch


def main() -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} — {APP_FULL_NAME}")
    parser.add_argument("--input", action="append", default=[], help="预先载入的 FIF 路径；可重复指定")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "results" / DEFAULT_OUTPUT_DIRNAME), help="GUI 默认输出根目录")
    args = parser.parse_args()
    return launch(input_files=args.input or None, output_dir=args.output)


if __name__ == "__main__":
    raise SystemExit(main())
