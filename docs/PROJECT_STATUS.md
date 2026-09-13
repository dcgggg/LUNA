# LUNA 当前项目状态

最后核查：2026-09-13。以下状态只依据当前工作区代码、当前虚拟环境和本次实际运行结果；未把旧需求、历史截图或未执行的人工操作记为通过。

## 总体状态

| 项目 | 当前状态 | 证据/限制 |
|---|---|---|
| 软件版本 | `0.2.2` | 版本来源为 `src/lfp_analysis/__init__.py`，`pyproject.toml` 使用动态版本；本次按补丁版本准备预发布 |
| GUI 框架 | PySide6 + Matplotlib | `scripts/run_gui.py` → `lfp_analysis.gui.launch()` → `MainWindow` |
| CLI | 可用 | `lfp-analysis.exe` 和 `python -m lfp_analysis.cli --help` 已核实；当前环境没有 `luna.exe` 别名 |
| 测试 | 52 项通过 | 仅有第三方 FOOOF 弃用警告 |
| 真实样例 | 文件级全流程完成 | 身份未解析，不能做动物层推断 |
| Git 状态 | 有既有未提交修改 | 本轮未提交、未推送、未清理或重置 |

## 本轮 GUI 复核（2026-09-13）

- 根目录 `AGENTS.md` 已读取；其 PSD 规则明确要求隐藏非当前方法的专属参数。本轮按该规则执行，没有把不适用的 PSD 参数保留为灰色可见控件。
- PSD 页面使用自适应方法面板：Welch 与 Multitaper 控件只创建并绑定一次，切换时不重建控件；隐藏分支不参与当前运行快照和校验。
- 结果页面的结果选择/各页面绘图控制位于图像滚动容器外；普通 PSD/波形、频带功率、FOOOF 和连接结果的图像内容使用独立滚动区。
- 结果数据预览默认完全折叠，折叠时不创建表格单元格并释放高度；展开后最多展示前1000行，完整结果仍由保存/导出流程保留。
- 固定真实测试文件 `C:/Users/PC/Documents/ChatGPT/testdata/LID-T80_all_channels-epo.fif` 已重新读取：21×16×5000、1000 Hz、有效时长105 s，候选记录数25，4个非空 `drop_log` 条目。
- Qt offscreen 实际截图已验证 Welch/Multitaper 面板、图像滚动时顶部控件、结果表折叠/展开。自动尺寸回归覆盖 980×620、1366×768、1920×1080。

### 本轮限制

- 当前环境没有可供 Computer Use 操作的原生桌面窗口；因此未把 offscreen 构造替代为真实鼠标人工验收。
- 125%/150% Windows 系统缩放、实体显示器上的拖动/点击和多显示器布局未验证。
- 本轮没有改变已有 PSD/连接/FOOOF 算法、默认计算参数或结果数值；真实单文件运行输出位于 `C:/Users/PC/AppData/Local/Temp/luna_gui_fixed_fif_20260913`。

## 当前虚拟环境

解释器：`.venv/Scripts/python.exe`，Python 3.11.9。

实际关键版本：NumPy 2.4.6、SciPy 1.17.1、pandas 2.3.3、Matplotlib 3.11.1、MNE 1.12.1、MNE-Connectivity 0.9.0、specparam 2.0.0rc7、FOOOF 1.1.1、PyBispectra 1.3.2、PySide6 6.11.2。`pip check` 无损坏依赖。

## 六个实际计算模块

本项目当前状态表将“六个模块”定义为：FIF 输入/QC、PSD、频带功率、FOOOF/specparam、功能连接、时间延迟。行为/统计是后续节点级接口，spike 未纳入本次分析。

| 模块 | 代码入口 | 当前实现状态 | 本次实测状态 | 仍未核实或限制 |
|---|---|---|---|---|
| FIF 输入与质量检查 | `io.read_fif()`、`quality.assess_quality()` | 已实现；保留 events、selection、drop_log；支持通道映射和分析输入 QC | 真实 FIF 读取成功；21 epoch、16 通道、105 s；0 个 fail 行、1 个 warn 行 | 身份和实际采集时间仍未知；质量标记是提示，不自动清洗 |
| PSD | `spectral.compute_psd()` | 已实现 Welch 与 MNE DPSS Multitaper；逐 epoch×通道保存；批量 Multitaper 路径已测试 | 真实单文件全流程成功；合成 10 Hz 频率识别成功 | Welch/Multitaper 参数仍是起始配置，不是实验确认参数 |
| 频带功率 | `spectral.compute_band_power()` | 已实现绝对/相对功率、频率边界和缺口分段积分 | 真实单文件输出 `band_power_epoch_channel.csv` 和图；合成时长/积分测试通过 | 频带边界和相对功率分母需由研究方案最终确认 |
| FOOOF/specparam | `parameterization.fit_channel_psd_table()`、`fit_single_psd()` | 已实现 specparam 主后端、FOOOF 兼容后端、非周期参数、峰参数、模型曲线和失败状态 | 真实样例 16/16 通道拟合成功、95 个峰；兼容后端有合成/测试覆盖 | 不是生理机制判定；旧版本受峰宽修复影响的结果需重算 |
| 功能连接 | `connectivity.compute_connectivity()` | 已实现显式脑区对、多变量 MIC/MIM、通道对 wPLI/dPLI/wPLI²、rank 诊断和稳定性诊断 | 默认真实配置的 `mic`、`mim`、`wpli2_debiased` 成功；连接结果 78 次估计调用 | 当前默认配置未选择 dPLI；单文件不能支持组间/动物层统计；共同参考和混合影响仍存在 |
| 时间延迟 | `time_delay.compute_time_delay()` | 已实现 PyBispectra Method I、标准/反对称结果、跨区通道对和质量汇总 | 真实样例状态 `ok`，输出 538,944 行 | 仅为方法性/文件级结果；不能直接解释为生物学因果方向 |

## 真实 FIF 当前核验结果

输入：`C:/Users/PC/Desktop/94/LID-94/T80/LID-T80_all_channels-epo.fif`。

- 实际形状：`21 × 16 × 5000`。
- 采样率：1000 Hz；epoch 时间为 0–4.999 s。
- 候选记录数：25；`drop_log` 非空条目：4；保留 epoch：21。
- 有效时长：`21 × 5 s = 105 s`，这不是一段连续 105 秒记录。
- 通道：`TETFP01–08`、`TETFP17–24`，MNE 类型为 `seeg`。
- 当前元数据映射：1–4=M1、5–8=STR、17–20=PF、21–24=SNr；映射依据实际通道名/物理编号。
- QC：0 个 fail epoch×channel 行；`TETFP21` 的 epoch 14 有 `abnormal_amplitude` 警告。
- 文件身份：`file_only_identity_unresolved`；metadata 通过唯一 basename fallback 找到样例行，没有填入 animal/session。
- 全流程状态：`completed`；`connectivity_status=ok`；`time_delay_status=ok`；动物层统计未运行。
- 本次临时结果目录：`C:/Users/PC/AppData/Local/Temp/luna_baseline_3wrxynea`。

## GUI 状态

- 入口：`scripts/run_gui.py`。
- 顶部品牌、文件载入、通道/脑区映射、质量提示、参数面板、后台任务、结果图表和结果表代码均存在。
- GUI 通过 `gui_engine.py` 调用公共分析核心，不单独复制连接、PSD 或参数化算法。
- 真实 FIF 的 offscreen 窗口构造和 1366×768 截图已完成；截图路径为 `C:/Users/PC/AppData/Local/Temp/luna_gui_baseline_20260912.png`。
- 该次 offscreen 进程在 Qt 清理阶段非零退出，所以“窗口能构造和显示”是已核实项，“真实桌面干净退出”不是已核实项。
- 尚未在真实 Windows 桌面上人工核查鼠标点击、拖动分隔线、125%/150% DPI 和多显示器布局。

## 不纳入当前已验证结论的内容

- 没有真实 animal/session/记录天数/LDN/AIMs 信息，不运行 LID 进展、LDN 配对、行为关联或组间推断。
- spike 仅保留未来接口，本轮不分析。
- Granger/时间反转校正当前关闭。
- time-frequency analysis、network dynamics 在 README 中应理解为规划/未验证范围，而不是本次已完成指标。
- 真实多文件批量统计、配对缺失模式和视频逐 epoch 同步未用真实登记数据核实。
