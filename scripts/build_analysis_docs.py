from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from lfp_analysis.analysis_help_content import (
    FIGURES,
    HELP_TOPICS,
    TABLE_SCHEMAS,
    field_description,
    render_topic,
)

SOURCES = """## 方法与软件来源

- Welch 参数与 PSD 量纲： [SciPy `signal.welch`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.welch.html)
- Epoch 间频谱连接、输入假设及 MIC/MIM： [MNE-Connectivity 0.9.0 `spectral_connectivity_epochs`](https://mne.tools/mne-connectivity/stable/generated/mne_connectivity.spectral_connectivity_epochs.html)；[MIC/MIM 示例](https://mne.tools/mne-connectivity/stable/auto_examples/mic_mim.html)
- PLI、dPLI 与 wPLI 家族： [MNE-Connectivity 相位滞后连接示例](https://mne.tools/mne-connectivity/stable/auto_examples/dpli_wpli_pli.html)
- 当前 specparam 固定/拐点模型与峰拟合： [specparam 2.0.0rc7 `SpectralModel`](https://specparam-tools.github.io/generated/specparam.SpectralModel.html)；[峰参数示例](https://specparam-tools.github.io/auto_examples/models/plot_peak_params.html)
- FOOOF 兼容后端模型解释： [FOOOF 模型教程](https://fooof-tools.github.io/fooof/auto_tutorials/plot_02-FOOOF.html)
- TDE 方法 I 与反对称处理： [PyBispectra 1.3.2 TDE 官方示例](https://pybispectra.readthedocs.io/1.3/auto_examples/plot_compute_tde.html)；[PyBispectra JOSS 论文](https://joss.theoj.org/papers/10.21105/joss.08504)；相关混合噪声方法预印本 [arXiv:2502.17474](https://arxiv.org/abs/2502.17474)。正负号以 LUNA 本地输入顺序、合成方向测试和 `time_delay_metadata.json` 为准。

当前工作区核验的依赖版本：Python 3.11.9、NumPy 2.4.6、SciPy 1.17.1、pandas 2.3.3、Matplotlib 3.11.1、MNE 1.12.1、MNE-Connectivity 0.9.0、specparam 2.0.0rc7、FOOOF 1.1.1、PyBispectra 1.3.2、PySide6 6.11.2。版本会变化，单次分析 manifest 才是该结果的实际版本依据。
"""


def build_guide() -> str:
    parts = ["# LUNA 分析流程与读图指南", "", "本指南解释当前代码实际生成的图和计算路径。通用读图说明不对疾病、药效或动物组差异作判断。频带边界及方法参数以当次运行配置为准，不是已验证的小鼠生理边界。", ""]
    for key in HELP_TOPICS:
        parts.append(render_topic(key))
    parts.extend(["", "## 单文件样例验证范围", "", "本次使用固定只读 FIF 在临时输出目录跑通代表性单文件流程：21 个有效 epoch、16 通道、1000 Hz、每段 5000 点，有效累计时长 105 秒（片段不连续）。输入哈希与输出 manifest 一致；身份仍为 `file_only_identity_unresolved`，不运行动物层推断。", "", "该次参数来自 `configs/luna.yaml` 继承的起步配置：PSD 为 Welch、1–200 Hz、nperseg 1000、重叠 500；频带为 delta 1–4、theta 4–8、alpha 8–12、beta 12–30、low gamma 30–55、high gamma 65–100 Hz，相对功率分母 1–100 Hz；参数化为 fixed、2–150 Hz；连接运行 MIC、MIM、wpli2_debiased、2–100 Hz multitaper、4 Hz 带宽；TDE 运行 PyBispectra 方法1、200 Hz 分析采样率及标准/反对称输出。这些值只用于说明这一次运行，不是经过本研究验证的生理边界或推荐方案。dPLI、普通 wPLI 等未在这次样例运行。", "", "文件级 CLI 的 `config_used.yaml` 是传入配置文件副本；若该文件使用 `extends`，它不是展开后的完整有效配置。CLI manifest 仅保存配置审计、部分关键范围和状态，参数也分布在各科学表及模块 metadata。项目 result bundle 则有独立的有效参数快照。使用 CLI 结果时，应联合核对这些来源；当前 CLI 完整解析参数快照不足是已知追溯限制。", "", "样例未运行的可选方法仅由代码、当前依赖/API 与官方资料交叉核对；本指南不把单次运行宣称为所有分支均已验证。", "", SOURCES])
    return "\n\n".join(parts).rstrip() + "\n"


def build_dictionary() -> str:
    parts = ["# LUNA 保存结果与指标数据字典", "", "## 如何定位一条结果", "", "项目结果使用 `luna-result-bundle/1.0`。SQLite 项目索引提供查询，bundle `manifest.json` 保存该次运行的稳定 ID、输入指纹、实际参数、映射、选择、依赖、表/数组坐标与状态。外部 Python 读取优先使用 `lfp_analysis.results_api.ProjectResults`，不要仅按显示名称或文件名配对。", "", "项目层级：`project_id → subject_id → session_id → state_record_id → data_unit_id → analysis_id`。CLI 文件级输出没有自动补齐缺失动物/session 身份。`calculation_status`（是否完成）、`save_status`（是否落盘成功）和 `result_validity`（是否仍与当前检查/参数一致）是不同概念。", "", "## 文件角色", "", "| 文件/对象 | 角色与说明 |", "|---|---|"]
    file_rows = [
        ("输入 FIF", "原始/预处理 epoch 信号来源；读取只读，不由输出目录替换。项目导入策略可复制到项目 data/raw，外部引用不移动。"),
        ("run_manifest.json / file_manifest.json", "文件级或 GUI 运行身份、输入哈希、结构、实际选区、状态、警告与结果路径索引。"),
        ("config_used.yaml / effective_parameters", "CLI 保存传入配置文件副本；若含 extends，不代表已展开的完整配置。CLI manifest 当前只含配置审计、部分范围和状态；项目 result bundle 的 effective_parameters 才是完整运行参数快照。关键实际参数也分别保存在结果表和模块 metadata。"),
        ("channel_table.csv", "数组索引、真实通道名、物理通道编号、映射脑区和 MNE 单位码；不可用数组位置猜物理编号。"),
        ("epochs_trace.csv + traceability/{events_raw,selection,drop_log}.json", "保存 epoch/候选段追溯；原始 events 未被擅自解释为记录时间。"),
        ("quality_*.csv / inspection_snapshot", "自动检查摘要和用户检查配置；标记与纳入/排除决定要区分。原始文件不因标记而删除。"),
        ("科学结果 CSV", "长表保存逐 epoch、通道、频率、脑区对、成分、峰或延迟点的数值与状态。下表列出实际文件级输出及行粒度。"),
        ("psd_arrays.npz / connectivity_arrays.npz", "PSD 数组含 selected_data(epoch,channel,time)、psd(epoch,channel,frequency) 及对应频率/epoch/通道坐标；连接 NPZ 是与 connectivity_spectrum.csv 逐行对齐的一维字段数组，不是 4×4 矩阵。manifest 记录 shape、axes、单位与数值空间。"),
        ("PNG / SVG 图", "预览与可编辑矢量图；是数值结果的可视摘要，不替代表格/数组。显示平滑表仅供显示。"),
        ("project SQLite", "项目层级、导入关联、检查快照、运行索引与筛选；科学结果具体数值以 bundle 表/数组为准。"),
        ("缓存/计算调用记录", "调用记录可说明估计任务和耗时；缓存或临时预览不是独立科学结果。CLI 本次连接估计未使用计算缓存。"),
    ]
    parts.extend([f"| {name} | {meaning} |" for name, meaning in file_rows])
    parts.extend(["", "## 运行清单与身份/状态字段", "", "| 字段 | 含义 |", "|---|---|"])
    manifest_fields = [
        ("analysis_id / analysis_run_id", "一次分析运行的稳定标识；重算会创建新运行，不覆盖历史结果。"),
        ("project_id / subject_id / session_id / state_record_id / data_unit_id", "项目层级稳定身份；缺失身份不得由文件名或树节点位置猜补。"),
        ("source / file_uid / input_sha256 / data_fingerprint", "输入路径/文件标识与数据指纹；用于说明结果来源及检查是否为同一输入。"),
        ("selection / inspection_snapshot / channel_mapping", "实际纳入的 epoch、通道/时间选择、检查快照和通道—脑区映射。"),
        ("effective_parameters / parameter_fingerprint", "项目 result bundle 中的生效参数及指纹；单文件 CLI run_manifest 当前可能没有完整快照，需同时核对 config_used、configuration_audit、结果表及模块 metadata。"),
        ("dependencies / software_version / schema_version", "计算环境依赖版本、LUNA 版本和结果契约版本。"),
        ("calculation_status / save_status / bundle_complete", "计算与落盘状态彼此独立；bundle_complete 只有计算完成且保存成功才为真。"),
        ("result_validity（项目 SQLite）", "当前结果是否仍与检查/计算输入一致；needs_recompute 表示需重算，旧 bundle 仍保留。该字段由项目索引管理，不等于历史数据文件损坏。"),
        ("tables / arrays / quality_summary / warnings", "表格、数组、维度/单位、质量摘要与警告路径；manifest 是结果目录索引，不代替具体数值表。"),
    ]
    parts.extend([f"| `{field}` | {meaning} |" for field, meaning in manifest_fields])
    parts.extend(["", "## NPZ 数组维度与坐标", "", "| 文件/数组 | 形状与坐标 |", "|---|---|", "| `selected_data.npz:data` | `(epoch, channel, time)`；同文件保存 `sfreq`、`times`、`epoch_indices` 和 `channel_indices`。|", "| `psd_arrays.npz:selected_data` | `(epoch, channel, time)`；数组来自本次选择，另保存 `sfreq`、`epoch_indices` 和 `channel_array_indices`；采样点可按 `sfreq` 换算为 epoch 内相对时间，非零起点需查运行元数据。|", "| `psd_arrays.npz:psd` | `(epoch, channel, frequency)`；`frequencies`、`epoch_indices`、`channel_array_indices` 分别标注各轴；值为线性 PSD。|", "| `connectivity_arrays.npz` | 多个一维数组按 `connectivity_spectrum.csv` 行顺序逐行对应；同时保存 method、脑区、通道、方向、频率、raw/strength、rank、epoch 数及遮罩标记。需按 CSV 中的身份字段筛选，不能当作三维规则矩阵。|", "| TDE | 当前结果以 CSV 长表为主，不生成 TDE NPZ 数组。|"])
    parts.extend(["", "## 文件级 CSV：行粒度与列定义", "", "列名采用代码/实际输出的英文原名。数值科学字段有精确定义；索引、参数、单位、质量及运行字段属于追溯元数据。字段定义可在下列每个表的列清单中查找。", ""])
    for filename, info in TABLE_SCHEMAS.items():
        parts.extend([f"### `{filename}`", "", f"模块：{info['module']}。每行：{info['grain']}。", "", "| 字段 | 含义 |", "|---|---|"])
        fields = [field.strip() for field in info["fields"].split(",")]
        for field in fields:
            description = field_description(field)
            if field.startswith("gaussian_"):
                description = "一个拟合高斯峰在该频点的 log10 加性贡献；N 为峰序号，缺少的峰列为空。"
            parts.append(f"| `{field}` | {description} |")
        parts.append("")
    parts.extend([
        "## 常见读值提醒", "",
        "- PSD 单位取决于输入信号单位和 `scaling`；只有 density 才是输入单位²/Hz。",
        "- 相对功率文件值是比例，显示为百分比时乘100；分母范围必须一起报告。",
        "- FOOOF/specparam 的 `peak_power_log10` 是峰高于非周期背景的 log10 差；BW 是2σ，不是 FWHM。",
        "- MIC 的 `value_raw` 与 `value_strength=abs(value_raw)` 同时保留；MIM 不截到0–1；wPLI²_debiased 的负估计保留；dPLI 0.5 中性且保留方向。",
        "- TDE 的 `estimate_strength` 是特定 PyBispectra 方法输出；正延迟按项目约定为 seed 领先 target。",
        "- NaN、空峰表、失败状态和实际零值语义不同，不要静默补0。",
        "- 文件级演示记录不自动构成动物样本；group、配对、跨被试统计应在外部按稳定 subject ID 设计。",
        "", SOURCES,
    ])
    return "\n".join(parts).rstrip() + "\n"


def build_figure_index() -> str:
    parts = ["# 图表—结果字段—计算函数索引", "", "文件名为文件级 pipeline 的当前命名模式；GUI 项目分析另将同类图放入该 data unit/analysis run 的 figures 目录，并由结果记录索引。PNG 为预览、SVG 为矢量导出。只有本次配置启用且存在相应数据时才生成可选图。", ""]
    parts.extend(["| 图表/文件模式 | 出现条件 | 绘图函数 | 数值来源字段 |", "|---|---|---|---|"])
    for figure in FIGURES:
        parts.append(f"| **{figure['title']}**<br>`{figure['files']}` | {figure['condition']} | `{figure['function']}` | `{figure['fields']}` |")
    parts.extend(["", "## 每类图的简明解释", ""])
    for figure in FIGURES:
        parts.extend([f"### {figure['title']}", "", figure["short"], "", f"详细边界：{figure['detail']}", ""])
    parts.extend(["## GUI 可切换结果", "", "GUI 复用保存表格进行显示筛选，不因改变色标、通道、脑区、频带或布局重新计算科学结果；需要重新计算的参数变化会触发相应计算流程。GUI 支持：Band Power 通道×频带热图和单一比较图；FOOOF 总览、非周期参数、周期曲线/热图、峰参数、峰分布和单通道详情；Connectivity 指标频谱、频带脑区矩阵与适用指标的通道对矩阵；Time Delay 延迟曲线及峰延迟矩阵。", "", "本索引覆盖生成器、静态绘图函数和 GUI view 当前实际存在的视图；项目内跨数据组间/组内比较已取消，不在本索引中。", "", SOURCES])
    return "\n".join(parts).rstrip() + "\n"


def build_all() -> dict[str, str]:
    return {
        "ANALYSIS_GUIDE.md": build_guide(),
        "RESULT_DATA_DICTIONARY.md": build_dictionary(),
        "FIGURE_RESULT_INDEX.md": build_figure_index(),
    }


def main() -> int:
    docs_dir = PROJECT_ROOT / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in build_all().items():
        (docs_dir / filename).write_text(content, encoding="utf-8")
        print(f"generated {docs_dir / filename}")
    return 0


if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    raise SystemExit(main())
