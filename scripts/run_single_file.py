"""Run the complete analysis for one FIF file from PyCharm.

Edit the four paths in the configuration block, then right-click this file in
PyCharm and choose ``Run 'run_single_file'``. The analysis algorithms remain in
``src/lfp_analysis``; this file is only a transparent, editable entry point.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# ========================= Editable configuration =========================
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Change only this path for another FIF file.
INPUT_FILE = Path(r"C:\Users\PC\Desktop\94\LID-94\T80\LID-T80_all_channels-epo.fif")

# These paths normally stay unchanged.
CONFIG_FILE = PROJECT_ROOT / "configs" / "default.yaml"
METADATA_DIR = PROJECT_ROOT / "metadata"
OUTPUT_DIR = PROJECT_ROOT / "results" / "pycharm_LID-T80"
# ============================================================================


def main() -> None:
    src_dir = PROJECT_ROOT / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from lfp_analysis.pipeline import run_single_file

    if not INPUT_FILE.is_file():
        raise FileNotFoundError(
            f"找不到输入 FIF 文件：{INPUT_FILE}\n"
            "请修改本文件顶部的 INPUT_FILE，然后重新运行。"
        )
    if not CONFIG_FILE.is_file():
        raise FileNotFoundError(f"找不到配置文件：{CONFIG_FILE}")

    print("开始分析")
    print(f"输入文件：{INPUT_FILE}")
    print(f"输出目录：{OUTPUT_DIR.resolve()}")
    print("原始 FIF 只读，不会被覆盖。")

    manifest = run_single_file(
        input_path=INPUT_FILE,
        config_path=CONFIG_FILE,
        output_dir=OUTPUT_DIR,
        metadata_dir=METADATA_DIR,
    )

    print("\n分析完成")
    print(f"文件 ID：{manifest['file_id']}")
    print(f"epoch 数：{manifest['n_epochs']}")
    print(f"有效时长：{manifest['effective_valid_duration_s']} s")
    print(f"连接状态：{manifest['connectivity_status']}")
    print(f"时间延迟状态：{manifest['time_delay_status']}")
    print(f"动物层统计：{manifest['animal_level_statistics_run']}")
    print(f"结果目录：{OUTPUT_DIR.resolve()}")
    print(f"运行记录：{(OUTPUT_DIR / 'run_manifest.json').resolve()}")

    # Also save a compact, human-readable summary beside the detailed outputs.
    summary_path = OUTPUT_DIR / "pycharm_run_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "input_file": str(INPUT_FILE.resolve()),
                "output_dir": str(OUTPUT_DIR.resolve()),
                "file_id": manifest["file_id"],
                "n_epochs": manifest["n_epochs"],
                "effective_valid_duration_s": manifest["effective_valid_duration_s"],
                "connectivity_status": manifest["connectivity_status"],
                "time_delay_status": manifest["time_delay_status"],
                "animal_level_statistics_run": manifest["animal_level_statistics_run"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"简要总结：{summary_path.resolve()}")


if __name__ == "__main__":
    main()
