<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/branding/luna-logo-on-white.svg">
    <img src="assets/branding/luna-logo.svg" alt="LUNA — Local field potential Unified Network Analysis platform" width="420">
  </picture>
</p>

# LUNA

LUNA is a modular GUI-based platform for multichannel local field potential analysis.

LUNA supports:

- Multichannel LFP
- EEG/ECoG/SEEG-like field potential recordings
- Spectral analysis
- FOOOF/specparam
- Band power
- Time-frequency analysis (planned; not part of the current validated pipeline)
- Functional connectivity
- Network dynamics (planned; not part of the current validated pipeline)

LUNA focuses on local field potential and neural field signal analysis. Spike sorting and single-unit analysis are not included.

本仓库当前包含小鼠多脑区同步 tetrode LFP 的可追溯分析工作流。输入为经过预处理的 FIF epoch 文件；每个输入文件可以代表一只小鼠在一次记录节点的结果。项目先保存文件级结果，等动物、记录日期、给药时点和行为信息补齐后，再进行动物层统计。

当前版本已经在用户提供的 T80 FIF 样例上完成单文件验证。样例原始数据不存放在 GitHub 仓库中，也不会被程序覆盖。

GUI 启动后，导入文件即可查看原始波形、质量提示和实际有效时长。Channel Mapping 表允许按实际通道名或物理编号编辑脑区，并保存为 `experiment_mapping.json`；M1、STR、PF、SNr 仅是当前样例的可编辑默认模板，不是软件固定的实验定义。

## 当前已经实现

- FIF 读取、通道名称和物理通道映射核查。
- `events`、`selection`、`drop_log` 和 epoch 追溯信息保存。
- NaN/Inf、平直信号、异常幅度、饱和、重复片段和残余工频质量检查。
- 实际有效时长计算；不把不连续 epoch 拼接成连续记录。
- 逐 epoch、逐通道 Welch 或 MNE DPSS Multitaper PSD；结果记录方法、实际频率步长和方法参数。
- 绝对功率、相对功率和可配置频段汇总。
- specparam 参数化；保留非周期背景、周期峰、拟合曲线、残差和失败原因。
- 基于多个有效 epoch 的多变量 MIC、MIM，以及可独立运行的 wPLI、dPLI 和去偏平方 wPLI。
- 连接频率轴诊断：保存完整频率行、工频标记来源、有限值统计、频率分辨率、DPSS taper 元数据和原始频谱粗糙度指标；支持不跨标记区间的可选分箱与仅显示平滑。
- wPLI/dPLI 保留全部跨脑区通道对；dPLI 保存两个有序方向，脑区汇总可选 mean 或 median。
- MIC 保留带符号原始值、绝对强度、多成分轴和后端 patterns；MIM 保留未归一化总相互作用，不被 MIC 成分数截断。
- 基于 PyBispectra 的双谱时间延迟分析，包含标准和 antisymmetrized 结果。
- 四脑区通道冗余、奇异值、有效秩、维度敏感性和片段稳定性检查。
- 单文件入口、批量入口、元数据模板、Notebook、CSV 结果表、PNG/SVG 图和运行日志。
- 动物、记录、文件、epoch 和行为表之间的追溯接口。

当前不会自动完成：

- 根据文件名前缀推断动物编号、记录日期或给药天数。
- 在身份缺失时运行动物层推断统计。
- 将 AIMs 评分复制到每个 epoch 并当作独立行为样本。
- 自动进行 LID/LDN 组间比较或治疗效果推断。
- 默认运行 Granger/时间反转校正；该扩展仍关闭。
- 分析 spike 数据。

连接频率轴与工频处理的详细说明见 [`docs/connectivity_frequency_diagnostics.md`](docs/connectivity_frequency_diagnostics.md)。

## 项目结构

```text
configs/                可编辑分析配置（GUI 默认 configs/luna.yaml）
assets/branding/        LUNA 官方 Logo 及深色背景展示版本
data/real/              本地真实 FIF；默认不提交
data/synthetic/         合成验证数据位置
metadata/               动物、记录、文件、epoch、行为和通道登记模板
notebooks/              可逐步执行的单文件 Notebook
scripts/                PyCharm 可直接运行的 .py 入口
src/lfp_analysis/       读取、质量、频谱、参数化、连接、延迟和绘图模块
tests/                  单元测试和合成信号验证
docs/                   分阶段实施记录和分析限制
results/                运行输出；默认不提交
pyproject.toml          Python 项目和依赖声明
requirements-lock.txt   当前 Windows 环境的依赖版本快照
CHANGELOG.md            版本变化和发布验证记录
```

## Python 环境

推荐环境：

- 操作系统：Windows 10/11（当前版本在 Windows 上验证）。
- Python：3.11，项目约束为 `>=3.11,<3.13`。
- 虚拟环境：项目根目录下的 `.venv`。
- 包管理：`pip`。
- 编辑器：PyCharm、VS Code 或 JupyterLab 均可；计算模块不依赖图形界面。

Python 官方下载：[python.org/downloads](https://www.python.org/downloads/)

Python 虚拟环境文档：[venv documentation](https://docs.python.org/3.11/library/venv.html)

Python Packaging Guide：[pip and virtual environments](https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/)

### Windows 安装环境

在项目根目录创建并激活虚拟环境：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[all]"
```

如果 PowerShell 阻止激活脚本，可以不激活，直接使用虚拟环境解释器：

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[all]"
```

也可以按当前锁定版本安装依赖，再安装本项目：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

`requirements-lock.txt` 是当前 Windows/Python 3.11 环境的可审计快照，其中不再包含本机绝对路径。跨平台安装时，优先使用 `pyproject.toml` 的依赖范围；锁定文件中的个别包可能带有 Windows 或本机环境特征。

默认配置入口是 [`configs/luna.yaml`](configs/luna.yaml)，它继承 [`configs/default.yaml`](configs/default.yaml) 中已有的分析参数并只补充 LUNA 身份信息；保留旧文件是为了兼容已有脚本和历史运行。

### PyCharm 设置

在 PyCharm 中选择：

1. `File` → `Settings` → `Project` → `Python Interpreter`。
2. 选择项目解释器：`<项目根目录>\.venv\Scripts\python.exe`。
3. 打开 `scripts/run_single_file.py`。
4. 修改文件顶部的 `INPUT_FILE` 和 `OUTPUT_DIR`。
5. 右键文件，选择 `Run 'run_single_file'`。

推荐把 FIF 放入 `data/real/`，这样可以使用项目相对路径：

```python
INPUT_FILE = PROJECT_ROOT / "data" / "real" / "your-file-epo.fif"
```

也可以使用自己电脑上的绝对路径。FIF 文件不需要复制进 GitHub 仓库。

### PySide6 桌面 GUI

启动入口为 [`scripts/run_gui.py`](scripts/run_gui.py)。在 PyCharm 中右键该文件并运行，或使用可选的预载入参数：

```powershell
.\.venv\Scripts\python.exe scripts\run_gui.py
.\.venv\Scripts\python.exe scripts\run_gui.py `
  --input "C:\path\to\your-epochs.fif" `
  --output results\gui
```

GUI 的日常操作流程是：

1. 添加一个或多个 FIF 文件，核对采样率、形状、有效 epoch 数、有效时长和 SHA-256。
2. 在 `Channel Mapping` 表中核对或编辑每个实际通道的 `Region` 和 `Label`。物理编号和数组索引只用于追溯，不会被数组位置自动推断。
3. 点击 `Apply Mapping` 应用当前文件的映射；点击 `Save Mapping` 可保存为 `experiment_mapping.json`，以后用 `Load Mapping` 复用到匹配的通道名或物理编号。
4. 在“分析范围”中选择映射后的脑区、实际通道、epoch 子集和 epoch 内时间窗。脑区对会根据当前映射动态生成；没有映射的通道不会参与脑区级连接。
5. 在“功能连接 Connectivity”下先选择脑区对，再独立勾选 MIC、MIM、`wpli`、`dpli` 或 `wpli2_debiased`；wPLI/dPLI 的通道对汇总方式在 Connectivity 参数页单独设置。
6. 在参数页调整真正会传入后端的 Welch、specparam、multitaper、秩、频段和时间延迟参数。
7. 点击顶部 `Run Analysis`；计算在后台线程执行，运行状态、取消按钮和进度都位于窗口顶部，不需要滚动到参数区底部。
8. 使用顶部 `Save Result` 或 `Export Figure` 保存当前结果。使用“保存预设”保存参数，使用“载入历史”从 `run_manifest.json` 恢复结果，即使原始 FIF 暂时不可用也可以查看已保存图表和表格。

默认模板与自定义映射示例：

- LUNA 不把 M1、STR、PF、SNr 作为固定实验定义；它们只是当前样例的可编辑模板。
- 例如可将前 8 个实际通道的 `Region` 改为 `CTX`，后 8 个改为 `STR_CUSTOM`，应用后连接脑区对和结果矩阵会自动使用这两个新脑区。
- 保存的 JSON 同时记录脑区到物理通道的关系和逐通道信息，便于复核；空白脑区表示该通道暂不参加脑区级分析。

每次 GUI 运行在输出目录中创建独立 `run_id/`，保存 `parameters.json`、`run_manifest.json`、每个文件的 CSV、完整 PSD/选择数据 NPZ、质量信息及 PNG/SVG 图。输入文件内容变化会产生新的 SHA-256，不能误用旧运行结果。修改显示设置只影响当前图；修改计算参数或数据选择会提示需要重新计算。

顶部“颜色模板”只控制分类显示颜色，不会重新计算数据；同一脑区使用同一色系、同一通道使用稳定的色阶变体。连续数据图（PSD、功率和质量热图）仍使用各自的连续色图。

GUI 使用 PySide6 和 Matplotlib Qt canvas；计算层位于 `src/lfp_analysis/gui_engine.py`，不依赖 Notebook，也不复制命令行算法。Qt 官方线程文档：[QThread](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html)；Matplotlib 嵌入 Qt 示例：[Embedding in Qt](https://matplotlib.org/stable/gallery/user_interfaces/embedding_in_qt_sgskip.html)。

## 依赖和官方文档

### 必需依赖

| 包 | 用途 | 官方网站 |
|---|---|---|
| NumPy | 数组和数值计算 | [numpy.org](https://numpy.org/) |
| SciPy | Welch PSD、滤波和信号处理 | [scipy.org](https://scipy.org/) |
| pandas | 元数据和结果表 | [pandas.pydata.org](https://pandas.pydata.org/) |
| Matplotlib | PNG/SVG 图形 | [matplotlib.org](https://matplotlib.org/) |
| PyYAML | YAML 配置文件 | [PyYAML documentation](https://pyyaml.org/wiki/PyYAMLDocumentation) |
| MNE-Python | FIF 读取和神经信号数据结构 | [mne.tools](https://mne.tools/stable/index.html) |

### 分析和开发依赖

| 包 | 用途 | 官方网站 |
|---|---|---|
| MNE-Connectivity | MIC、MIM、wPLI、dPLI 等连接估计 | [MNE-Connectivity](https://mne.tools/mne-connectivity/stable/) |
| PyBispectra | 双谱时间延迟分析 | [PyBispectra documentation](https://pybispectra.readthedocs.io/) |
| specparam | 功率谱非周期/周期参数化 | [specparam on PyPI](https://pypi.org/project/specparam/) |
| FOOOF | specparam 的兼容后端 | [FOOOF documentation](https://fooof-tools.github.io/fooof/) |
| PySide6 | 桌面 GUI、后台任务和控件 | [Qt for Python](https://doc.qt.io/qtforpython-6/) |
| JupyterLab | Notebook 运行环境 | [jupyter.org](https://jupyter.org/) |
| pytest | 自动化测试 | [pytest.org](https://pytest.org/) |
| Ruff | Python 代码检查 | [docs.astral.sh/ruff](https://docs.astral.sh/ruff/) |

项目依赖分组定义在 `pyproject.toml`：

```text
.[connectivity]       MNE-Connectivity
.[tde]                PyBispectra
.[parameterization]   specparam 和 FOOOF
.[notebook]           JupyterLab、Notebook 和 ipykernel
.[dev]                pytest 和 Ruff
.[all]                上述全部依赖
```

## 输入数据和元数据

原始 FIF 文件建议放在本地 `data/real/`，但不会提交到仓库。至少需要确认：

- 采样率和 epoch 形状。
- 实际通道名称与物理通道编号。
- 脑区映射。
- 给药前/后状态和名义给药后时间。
- 动物编号、记录节点和记录日期。
- AIMs 评分及其观察窗。

当前样例使用的脑区映射为：物理通道 1–4 为 M1，5–8 为 STR，17–20 为 PF，21–24 为 SNr。映射必须在 `metadata/channel_map.csv` 中按实际通道名称确认，代码不会把数组第 9 个位置自动当作物理通道 9。

元数据表的粒度如下：

| 表 | 一行代表什么 | 主要关联 |
|---|---|---|
| `animals.csv` | 一只小鼠 | `animal_id` |
| `records.csv` | 一只小鼠的一次记录/session | `session_id`、`animal_id` |
| `files.csv` | 一个 FIF 文件及给药节点 | `file_id`、`session_id` |
| `epochs.csv` | 一个文件中的候选/保留 epoch | `file_id + saved_index` |
| `behavior.csv` | 动物×记录×给药时点的行为记录 | `animal_id + session_id + nominal_dose_time_min` |
| `channel_map.csv` | 实际通道名到物理编号/脑区的映射 | `channel_name` |

空值代表未知，不用 `0` 代替未知天数、评分或时间。给药前基线使用 `pre_dose_baseline`，不自动写成给药后 0 分钟。`T80` 只表示名义给药后 80 分钟，不表示每个 epoch 的精确起止时间。

## 运行方式

### 1. 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ruff check src tests scripts
```

### 2. 合成信号验证

```powershell
.\.venv\Scripts\python.exe -m lfp_analysis.cli validate-synthetic `
  --output results/synthetic_validation
```

命令行合成验证目前覆盖频率识别、功率积分和 epoch 边界等 PSD/频带功率基本标定；连接、FOOOF/specparam、TDE 和边界情形由 `tests/` 中明确的合成测试覆盖。所有合成数据均不代表真实实验结果。

### 3. 单文件命令行运行

```powershell
.\.venv\Scripts\python.exe -m lfp_analysis.cli single-file `
  --input "C:\path\to\your-epochs.fif" `
  --config configs\luna.yaml `
  --output results\your-file
```

如果不想使用终端，使用上面的 [PyCharm 运行脚本](scripts/run_single_file.py)。它只是调用同一套 `src/lfp_analysis` 计算模块，不复制算法逻辑。

### 4. 批量运行

先在 `metadata/files.csv` 登记文件，再运行：

```powershell
.\.venv\Scripts\python.exe -m lfp_analysis.cli batch `
  --files metadata\files.csv `
  --config configs\luna.yaml `
  --output results\batch
```

不存在、身份冲突或无法解析的文件会写入批量清单和运行日志，不会静默纳入统计。

### 5. Notebook

打开 `notebooks/01_single_file_workflow.ipynb`，选择项目 `.venv` 内核并按顺序执行。Notebook 默认运行唯一目录中的合成验证；要运行真实 FIF，可在启动 Jupyter 前设置 `LUNA_NOTEBOOK_INPUT`，可选用 `LUNA_NOTEBOOK_OUTPUT_DIR` 指定一个空的输出目录。Notebook 拒绝覆盖非空目录。核心计算仍在 `src/lfp_analysis`，因此也可以从 PyCharm 或批量入口运行。

## 主要输出

单文件结果目录通常包含：

- `run_manifest.json`：输入文件哈希、软件/参数摘要、输出状态和限制。
- `epochs_trace.csv`、`traceability/`：epoch、events、selection 和 drop log 追溯。
- `quality_epoch_channel.csv`、质量汇总和原始波形图。
- `psd_channel.csv`、`band_power_channel.csv`、PSD/频段功率图。
- `parameterization_model.csv`、`parameterization_peaks.csv`、`parameterization_curves.csv` 和拟合图。
- `connectivity_spectrum.csv`、`connectivity_region_summary.csv`、`connectivity_band_summary.csv`。
- GUI Connectivity 运行还保存 `channel_pair_band_summary.csv`，以及按方法独立命名的 `connectivity_wpli_*`、`connectivity_dpli_*` 频谱/矩阵/组合图；dPLI 图保留 A→B 与 B→A，不将矩阵镜像当成第二次估计。
- `connectivity_arrays.npz`：完整连接频谱的频率、方法、脑区对、MIC 成分、原始值/展示强度及 rank 坐标。
- `connectivity_rank_summary.csv`、`connectivity_stability.csv` 和连接质量图。
- `time_delay_spectrum.csv`、`time_delay_band_summary.csv`、`time_delay_metadata.json` 和延迟图。
- `figures/`：预览用 PNG 和可编辑 SVG。

真实 T80 样例当前只支持文件级描述性结果：重新核验得到 21 个有效 epoch、105 秒有效时长。由于动物身份、session、给药天数和 AIMs 关联尚未登记，程序不会运行 LID/LDN 组间推断或行为相关统计。

## 分析约定和重要限制

- 连接估计在同一动物×记录节点×给药时点内使用多个有效 epoch；不跨动物、记录天数或时点混合，也不拼接不连续 epoch。
- 通道、epoch 和通道对是动物内部重复测量，不能当作独立小鼠样本。
- MIC 保留有符号原值；图中强度可使用明确标注的绝对值，但不解释为因果方向。
- MIM 保留原始未归一化值，不强行裁剪到 0–1。
- wPLI、dPLI 和去偏平方 wPLI 不把通道对当作独立动物；保留全部通道对及有效数量。dPLI 矩阵不镜像，0.5 是中性参考。
- 时间延迟的正负号只表示 seed→target 的时间符号约定，不等于解剖方向或因果证明。
- 默认不再次强滤波、陷波、重参考或强清洗；质量标记不会静默删除数据。
- 配置中的频段、阈值、降维和延迟范围是可编辑的起步设置，不是已经验证的小鼠生理边界。
- LDN 名称、剂量和给药安排未知时留空，不根据文件名推定。

更完整的分阶段记录见 [`docs/analysis_plan.md`](docs/analysis_plan.md)，字段定义见 [`metadata/README.md`](metadata/README.md)。

## 版本和复现

每次运行都会记录输入文件标识、SHA-256、参数配置、有效 epoch 数、有效时长、质量状态和排除/失败原因。建议：

1. 不修改原始 FIF。
2. 每个输入文件使用独立的输出目录。
3. 修改分析参数后保留配置文件副本。
4. 在提交结果前运行 pytest、`pip check` 和 Ruff。
5. 将动物身份和行为信息登记到 `metadata/`，再进行动物层统计。

当前仓库只包含代码、配置、模板、Notebook 和测试；真实 FIF、`.venv/`、`.idea/`、结果和日志默认被 `.gitignore` 排除。

## 研究方法参考

- [MNE-Connectivity spectral connectivity API](https://mne.tools/mne-connectivity/stable/generated/mne_connectivity.spectral_connectivity_epochs.html)
- [MNE-Connectivity MIC/MIM example](https://mne.tools/mne-connectivity/stable/auto_examples/mic_mim.html)
- [SciPy Welch documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.welch.html)
- [FOOOF model fitting tutorial](https://fooof-tools.github.io/fooof/auto_tutorials/plot_02-FOOOF.html)
- [PyBispectra time-delay examples](https://pybispectra.readthedocs.io/latest/examples.html)
- [PyBispectra JOSS article](https://doi.org/10.21105/joss.08504)
- [PyBispectra time-delay paper](https://arxiv.org/abs/2502.17474)

## License

当前仓库尚未声明开源许可证。如需公开复用，建议在 GitHub 仓库中根据作者和数据权限补充许可证；原始实验数据不应随代码仓库公开上传。
