# LUNA 本地开发与首次核实清单

本文件记录在本地工作区执行过的可复现命令，以及对应的实际结果。它是运行核实记录，不把历史需求、旧截图或其他文档中的声明自动视为当前版本已验证功能。

## 1. 核查范围与安全边界

- 初次核查日期：2026-09-12；本次 GUI 复核更新：2026-09-13。
- 项目根目录：`C:/Users/PC/Documents/ChatGPT/LID_Tetrode_Analysis`。
- 2026-09-12 初次核查时未发现 `AGENTS.md`；本次复核已读取根目录 `AGENTS.md`，并按其当前规则执行。该文件说明规则本身不代表功能已验证。
- 当前分支：`master`。
- 当前 HEAD：`5780f02 release: prepare LUNA 0.2.0 prerelease`。
- 工作区在核查前已经存在大量未提交修改；本轮没有 reset、checkout、清理、提交或推送。
- 真实 FIF 只读打开；本轮没有复制、改写或覆盖真实 FIF，也没有覆盖仓库 `results/`。
- 本次固定测试文件为 `C:/Users/PC/Documents/ChatGPT/testdata/LID-T80_all_channels-epo.fif`；本轮 GUI/单文件验证输出均写入系统临时目录。

## 2. 工作区检查

### 2.1 发现的主要入口和目录

- GUI 启动脚本：`scripts/run_gui.py`。
- PyCharm 可编辑单文件入口：`scripts/run_single_file.py`。
- CLI 入口：`lfp_analysis.cli:main`；`pyproject.toml` 声明了 `lfp-analysis` 和 `luna` 两个 console entry point。
- 代码目录：`src/lfp_analysis/`。
- 配置：`configs/luna.yaml`（用户入口，继承 `default.yaml`）和 `configs/default.yaml`（科学计算默认值）。
- 元数据模板：`metadata/`。
- 测试：`tests/`。

### 2.2 未提交改动

核查前 `git status --short` 显示工作区已修改 README、配置、Notebook、GUI、编排、频谱、连接、时间延迟、参数化、绘图、元数据、行为/统计和测试文件，并有新增的连接诊断、颜色、身份、资源及测试文件。上述改动的归属没有在本轮重新拆分；它们均被保留。新增本文件及同一核查批次的状态文档也保持未提交。

## 3. Python 环境核查

使用的解释器是：

```powershell
Set-Location C:/Users/PC/Documents/ChatGPT/LID_Tetrode_Analysis
./.venv/Scripts/python.exe
```

实际版本输出：

| 组件 | 实际版本 |
|---|---:|
| Python | 3.11.9 |
| NumPy | 2.4.6 |
| SciPy | 1.17.1 |
| pandas | 2.3.3 |
| Matplotlib | 3.11.1 |
| MNE | 1.12.1 |
| MNE-Connectivity | 0.9.0 |
| specparam | 2.0.0rc7 |
| FOOOF | 1.1.1 |
| PyBispectra | 1.3.2 |
| PySide6 | 6.11.2 |
| pytest | 8.4.2 |
| Ruff | 0.16.6 |

版本核查命令：

```powershell
./.venv/Scripts/python.exe -c "import sys, importlib.metadata as md; names=['numpy','scipy','pandas','matplotlib','mne','mne-connectivity','specparam','fooof','pybispectra','PySide6','pytest','ruff']; print(sys.version); print(sys.executable); [print(n + '=' + md.version(n)) for n in names]"
```

已确认当前后端 API：

```powershell
./.venv/Scripts/python.exe -c "import inspect; from mne_connectivity import spectral_connectivity_epochs; import specparam, fooof, pybispectra; print(inspect.signature(spectral_connectivity_epochs)); print(specparam.__version__, hasattr(specparam, 'SpectralModel')); print(fooof.__version__, hasattr(fooof, 'FOOOF')); print(pybispectra.__version__)"
```

MNE-Connectivity 0.9.0 的 `spectral_connectivity_epochs` 支持当前代码使用的 `indices`、`mode`、`fmin/fmax`、`faverage`、`rank`、`n_components` 等参数。导入 FOOOF 1.1.1 时会产生第三方弃用提示；本轮未升级或修改第三方库。

## 4. 可复现验证命令

### 4.1 单元测试和静态检查

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m ruff check src tests scripts
./.venv/Scripts/python.exe -m compileall -q src scripts
./.venv/Scripts/python.exe -m pip check
git diff --check
```

本次实际结果：

- `pytest`：52 项通过；仅有 FOOOF 第三方弃用警告。
- Ruff：`All checks passed!`。
- `compileall`：通过。
- `pip check`：`No broken requirements found.`。
- `git diff --check`：退出码为 0；Git 仅提示部分工作区文件的 LF/CRLF 转换，不是内容错误。

### 4.2 CLI 和 PyCharm 入口

```powershell
./.venv/Scripts/python.exe -m lfp_analysis.cli --help
./.venv/Scripts/python.exe -m lfp_analysis.cli single-file --help
./.venv/Scripts/python.exe -m lfp_analysis.cli validate-synthetic --help
./.venv/Scripts/lfp-analysis.exe --help
./.venv/Scripts/python.exe scripts/run_gui.py --help
```

CLI help、`lfp-analysis.exe` help 和 GUI help 均能启动并返回帮助文本。当前 `.venv/Scripts` 中没有 `luna.exe`，虽然 `pyproject.toml` 声明了该 entry point；这表示当前虚拟环境没有在最近一次项目安装后生成该别名，不影响 `scripts/run_gui.py` 或 `lfp-analysis.exe` 的使用。

PyCharm 单文件入口默认将 `INPUT_FILE` 指向 `data/real/LID-T80_all_channels-epo.fif`。该样例不在仓库中，因此直接运行未修改过的脚本会在进入分析前报告找不到默认 FIF；这是输入路径未配置，不是算法运行失败。使用自己的文件前需要编辑脚本顶部的 `INPUT_FILE`，或使用 CLI 的 `--input` 指定实际路径。

### 4.3 合成数据核查

```powershell
$syntheticOutput = Join-Path $env:TEMP ('luna_synthetic_baseline_' + [guid]::NewGuid().ToString('N'))
./.venv/Scripts/python.exe -m lfp_analysis.cli validate-synthetic --output $syntheticOutput
```

实际结果：状态 `ok`；合成主峰识别为 10 Hz；有效时长 30 s；PSD 行数 2,400。该命令只表示当前合成校准覆盖的频率识别、PSD/时长基本检查，不代表真实实验结论。

### 4.4 真实 FIF 只读读取

真实样例路径：

```text
C:/Users/PC/Desktop/94/LID-94/T80/LID-T80_all_channels-epo.fif
```

读取核查命令：

```powershell
./.venv/Scripts/python.exe -c "from pathlib import Path; import mne, numpy as np; p=Path('C:/Users/PC/Desktop/94/LID-94/T80/LID-T80_all_channels-epo.fif'); e=mne.read_epochs(p, preload=True, verbose='ERROR'); x=e.get_data(); print(x.shape); print(float(e.info['sfreq']), float(e.tmin), float(e.tmax)); print(e.ch_names); print(e.get_channel_types()); print(e.events.shape, len(e.selection), len(e.drop_log), sum(bool(row) for row in e.drop_log)); print(np.isfinite(x).all(), x.shape[0]*x.shape[2]/float(e.info['sfreq']))"
```

实际结果：`(21, 16, 5000)`、1000 Hz、0–4.999 s、21 个保留 epoch、25 个候选记录、4 个非空 `drop_log` 条目、数据全为有限值、有效时长 105 s。通道为 `TETFP01–08` 和 `TETFP17–24`，MNE 类型均为 `seeg`。

### 4.5 真实样例全流程（唯一临时输出）

本次用 `pipeline.run_single_file()` 从 Python 入口执行了与 CLI 相同的单文件编排，输出目录由 `tempfile.mkdtemp()` 生成，避免覆盖仓库结果：

```powershell
./.venv/Scripts/python.exe -c "import json,sys,tempfile; from pathlib import Path; root=Path.cwd(); sys.path.insert(0,str(root/'src')); from lfp_analysis.pipeline import run_single_file; inp=Path('C:/Users/PC/Desktop/94/LID-94/T80/LID-T80_all_channels-epo.fif'); out=Path(tempfile.mkdtemp(prefix='luna_baseline_')); m=run_single_file(inp, root/'configs'/'luna.yaml', out, root/'metadata'); print(json.dumps({'output_dir':str(out),'status':m.get('status'),'file_id':m.get('file_id'),'identity_status':m.get('identity_status'),'registry_match_status':m.get('registry_match_status'),'n_epochs':m.get('n_epochs'),'n_channels':m.get('n_channels'),'n_times':m.get('n_times'),'sampling_rate_hz':m.get('sampling_rate_hz'),'effective_valid_duration_s':m.get('effective_valid_duration_s'),'connectivity_status':m.get('connectivity_status'),'time_delay_status':m.get('time_delay_status'),'animal_level_statistics_run':m.get('animal_level_statistics_run'),'configuration_audit_count':len(m.get('configuration_audit',[]))},ensure_ascii=False))"
```

实际输出目录为：`C:/Users/PC/AppData/Local/Temp/luna_baseline_3wrxynea`。状态为 `completed`；连接和时间延迟状态均为 `ok`；动物层统计为 `false`。

### 4.6 GUI 离屏启动

当前环境没有可供人工 Computer Use 操作的原生桌面窗口，因此使用 Qt offscreen 构造 `MainWindow`、载入真实文件、处理事件并保存截图。截图已生成：`C:/Users/PC/AppData/Local/Temp/luna_gui_baseline_20260912.png`。

offscreen 窗口构造、真实文件载入和截图成功；该次进程在 Qt 清理阶段返回非零退出码，因此不能把它记为“桌面 GUI 正常退出已通过”。

### 4.7 2026-09-13 GUI 复核命令与结果

本次修改仅涉及 GUI 布局、PSD 方法面板显示和结果表折叠尺寸；没有修改分析算法、科学默认值或导出数值定义。使用固定只读 FIF：

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
./.venv/Scripts/python.exe -m pytest -q tests/test_gui.py
./.venv/Scripts/python.exe -c "from pathlib import Path; import mne; p=Path('C:/Users/PC/Documents/ChatGPT/testdata/LID-T80_all_channels-epo.fif'); e=mne.read_epochs(p, preload=False, verbose='ERROR'); print(len(e), len(e.ch_names), len(e.times), e.info['sfreq'], e.ch_names)"
./.venv/Scripts/python.exe -m lfp_analysis.cli single-file --input C:/Users/PC/Documents/ChatGPT/testdata/LID-T80_all_channels-epo.fif --config configs/default.yaml --output C:/Users/PC/AppData/Local/Temp/luna_gui_fixed_fif_20260913
```

实际固定文件核验：21 个保留 epoch、16 通道、5000 点、1000 Hz、0–4.999 s；4 个非空 `drop_log` 条目，对应候选记录数为25；有效时长105 s；文件身份仍为 `file_only_identity_unresolved`。单文件输出完成，未进行动物层统计。

GUI 离屏截图脚本实际完成以下场景：载入固定 FIF、切换 Welch/Multitaper、滚动图像区、折叠/展开结果表，并保存到：

```text
C:/Users/PC/AppData/Local/Temp/luna_gui_validation_20260913/
```

截图文件：`welch_parameters_visible.png`、`multitaper_parameters_visible.png`、`plot_scrolled_controls_visible.png`、`result_table_collapsed.png`、`result_table_expanded.png`。自动 Qt 尺寸回归覆盖 980×620、1366×768、1920×1080；没有可用的原生桌面自动化窗口，因此真实鼠标操作、实体显示器及 Windows 125%/150% DPI 未验证。

本次 GUI 回归还确认：隐藏 PSD 分支不进入 `_read_parameter_values()`；两种方法输入值切换后保留；结果表折叠时行列为0且最小/最大高度为0，展开才恢复固定预览高度。

## 5. 当前禁止的验证结论

- 尚无真实动物编号、session、L-DOPA 天数、LDN 记录或 AIMs 行为同步，因此不运行动物层统计、LID/LDN 比较或行为相关。
- 尚未用真实登记数据核实多动物批量键、配对设计和行为匹配。
- Qt offscreen 不等价于真实 Windows 鼠标操作；1366×768 的构造和截图已完成，125%/150% 系统缩放、实体显示器下的拖拽/点击和人工 GUI 操作仍未核实。
- 历史 `docs/analysis_plan.md` 和 README 中的“已完成”描述不替代本文件的本次运行证据。
