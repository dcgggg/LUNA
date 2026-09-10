# 桌面 GUI 使用说明与验收记录

## 启动

在项目 `.venv` 解释器中运行：

```powershell
.\.venv\Scripts\python.exe scripts\run_gui.py
```

也可以预先载入文件：

```powershell
.\.venv\Scripts\python.exe scripts\run_gui.py `
  --input "C:\path\to\your-epochs.fif" `
  --output results\gui
```

PyCharm 操作：打开 `scripts/run_gui.py`，确认项目解释器为 `.venv\Scripts\python.exe`，右键选择 `Run 'run_gui'`。

## 操作流程

1. 点击“导入文件”，可以选择一个或多个 FIF 文件。读取在后台线程完成，不会冻结窗口；读取后会显示真实通道名、物理通道号、脑区映射、采样率、epoch 数和 SHA-256。文件下拉框显示文件名，悬停可查看完整路径。
2. 添加完成后，右侧会立即显示“原始波形”。“右侧预览 epoch”可切换保存数组索引；通道列表勾选/取消会实时更新预览。波形按通道做垂直显示偏移，仅用于显示，不会改变输入数据。
3. 添加完成后会自动运行质量检查，并在文件信息中显示名义保留时长、按有限样本计算的实际有效时长、候选 epoch 数和上游删除数。通道列表中的 `⚠` 和颜色表示该通道至少有一个 fail/warn epoch。
4. 右侧“自动质量检查 / 异常提示”会列出上游删除候选分段、可疑通道、可疑 epoch 和质量标记原因，例如 `abnormal_amplitude`、`nonfinite`、`flat`、`possible_saturation`、`line_noise_peak` 或 `duplicate_epoch`。这些是提示，不会自动排除数据；异常判断仍需结合波形、PSD 和实验记录。
5. 在“分析范围”中勾选脑区，点击“应用脑区选择”，再核对实际通道列表。epoch 支持 `all`、`0-20` 和 `0,2,4`。右侧预览 epoch 与正式分析的 epoch 子集是两个独立设置。
6. 修改 PSD、FOOOF、连接、时间延迟、频段或其他分析参数时，只会标记“需要重新计算”，不会刷新或切换原始波形预览。点击“运行分析”后，结果图才会更新。
7. 设置 epoch 内时间窗。Welch 窗长超过该时间窗会在运行前拦截，不会静默缩短；Multitaper 使用整段选定时间窗建立 DPSS 频谱。
8. 勾选指标。每个指标独立执行；FOOOF 自动依赖匹配配置的 PSD，Band Power 自动依赖 PSD；MIM、wPLI 和 dPLI 不会自动运行 FOOOF 或其他连接指标。
9. 在参数页修改会传入后端的参数。频段边界和相对功率分母在“频段功率”页编辑；rank 的 fixed 模式可为四个脑区指定固定秩。
10. 点击“运行分析”。运行时控件仍可修改，但当前后台任务使用点击时冻结的快照；修改只影响下一次运行。左侧参数区可独立纵向滚动，左右分隔线可拖动；结果区会优先获得窗口新增空间。
11. 结果完成后在右侧结果下拉框切换文件和指标，查看图、数值表和简洁状态信息。详细日志默认折叠，点击“展开详细日志”后查看完整过程；图可用 Matplotlib 工具栏缩放/平移/重置，也可以导出当前图。
12. 用“保存预设”保存参数；用“载入历史”选择含有 `run_manifest.json` 的 run 目录，可在原始 FIF 不可用时恢复表和图。

### 频带功率的双图视图

选择“频带功率”结果后，右侧只保留两个主要绘图区：

- 上图是“通道 × 频带总览”热图。横轴按频率升序排列，纵轴使用实际物理通道号和通道名，并按 M1、STR、PF、SNr 分组。点击任意单元格会同步选择该通道和频带。
- 下图是单一比较图。`比较通道`显示所选频带下各通道的点，颜色只表示脑区；`比较频带`显示所选通道下各频带的点，当前频带用高亮色标出。两种模式不会同时生成多组比较子图。

上方控件只改变展示，不重新计算 PSD 或频带功率：

- `绝对功率 / 相对功率`：相对功率显示为百分比，分母范围写在坐标轴和色条标签中。
- `线性 / 对数`：对数显示只对绝对功率开放；零值和负值不会被加小量伪造，而是标记或省略并提示切换线性尺度。
- `均值 / 中位数`：有逐 epoch 结果时按当前筛选重新汇总；底层逐 epoch 表不改变。
- `显示 epoch 分布`：仅在存在逐 epoch 表时叠加低透明度点。它表示 epoch 内分布，不是动物间置信区间。
- `频带筛选`、通道列表和脑区筛选会同步更新两张图；筛选不会触发 PSD 重算。

频带功率定义沿用结果表中的 `absolute_power`/`relative_power`。本项目首版将频带 PSD 在频带上下界内积分，并保留频带上下界；宽频带总功率不直接等同于纯振荡功率，也不与 FOOOF 周期峰混用同一色标。

频带功率视图的三个按钮分别导出当前热图、当前比较图和两图组合。文件对话框支持 PNG、TIFF、SVG、PDF；每次导图还会在同目录自动生成同名 CSV。CSV 包含物理通道、脑区、频带边界、绝对/相对功率、当前单位、汇总方式、epoch 数、显示尺度和相对功率分母，并与屏幕当前筛选保持一致。

### FOOOF/specparam 结果视图

选择 `FOOOF` 结果后，右侧进入独立的 FOOOF/specparam 视图，不再只显示一张拟合 PSD 曲线。默认打开当前筛选通道、M1 周期曲线和第一个配置频带；这只是显示默认值，不会改变已完成的拟合。

页面包含以下标签页：

- `总览`：2×3 面板依次显示 exponent、offset、当前脑区周期曲线、CF、PW、BW。横轴是实际物理通道和通道名，脑区颜色固定；D/E/F 标题带有当前频带边界。
- `非周期参数`：exponent、offset 散点和参数表。拟合失败、低质量拟合和缺失值保留在表中，不填 0。
- `周期曲线`：可切换按 M1/STR/PF/SNr 分成 2×2 面板，或使用左侧实际通道选择叠加少量通道；可分别显示去背景后的观测谱、拟合周期成分或两者叠加。浅线是观测谱，实线是周期模型；纵轴为 log10 加性尺度。
- `峰参数`：CF、PW、BW 三个比较图和峰分布图。峰分布图中的横线是 `CF ± BW/2`，表示 FOOOF 带宽范围，不是置信区间。
- `单通道详情`：输入 PSD、完整模型、非周期背景、去背景观测谱、拟合周期模型、残差、独立高斯峰叠加，以及拟合质量和参数表。

峰选择有两个模式：`全部峰` 保留当前频带内所有检出峰；`频段代表峰（PW最大）` 对每个通道选择该频段内后端 PW 最大的峰。频带筛选使用左闭右开边界 `[low, high)`。没有峰时 CF、PW、BW 保留为空，并显示 `no_peak_in_band`；拟合失败、低质量和拟合范围未覆盖频带分别保留状态。改变显示频带只筛选已有峰，扩大拟合范围必须修改 FOOOF 参数并重新运行。

定义说明：`offset`、`exponent`、`knee` 和 CF/PW/BW 均来自本次运行的 specparam/FOOOF 后端；PW 是高于非周期背景的 log10 功率差，不是原始 PSD 峰高或频带积分功率；经典 FOOOF 的 BW 按后端定义为 `2σ`，不是 FWHM。项目会把后端内部的 Gaussian σ 转成 `bandwidth_hz=2σ`；加载旧版结果时会标记并转换旧的 σ 字段。周期模型曲线是 `完整对数模型 − 非周期对数模型`；去背景观测谱是 `log10(输入 PSD) − 非周期模型`，两者不混称为纯周期信号。

改变脑区、通道、频带、峰模式、曲线模式、质量筛选、坐标统一和字体设置只刷新已有表和曲线，不重新拟合。只有左侧 FOOOF 参数改变并再次点击运行后，旧结果才会被新拟合替换。

`导出当前图`按当前标签页导出；`导出全部图`导出总览、非周期、周期曲线、周期热图、峰参数、峰分布和单通道详情的 PNG/SVG；`导出数值表`及图导出时会生成模型表、全部峰表、当前峰筛选表、曲线表和显示设置表。曲线 CSV 保留去背景观测谱、周期模型、残差和独立高斯峰列。

### 功能连接视图：MIC、MIM、wPLI、dPLI 和 TDE

左侧 `功能连接 Connectivity` 先选择脑区对，再选择分析指标。MIC、MIM、wPLI、dPLI、wPLI²_debiased 和 TDE 的参数按指标动态显示；未选指标的 rank、component、去偏或延迟参数不会混在当前面板中。切换参数页或指标不会修改底层算法结果，只有点击“运行分析”才会重新计算。

选择 `Connectivity` 结果后，右侧保留两个主绘图区：上方是当前指标的连接频谱，下方是所勾选频段的脑区矩阵。频段列表支持同时勾选多个频段，矩阵按两列网格显示；窗口不足时矩阵区域可以滚动。矩阵对角线为 `N/A`，未计算或失败的脑区对留空，不填 0；点击任一已计算单元格会聚焦上方频谱。矩阵的数值汇总与频谱使用同一个指标和 MIC 成分选择。

当前本地环境实际安装的是 `mne-connectivity 0.9.0`；开发版文档仅用于核对概念和参数，代码按本地实际签名运行，没有整体升级依赖。

左侧“功能连接 Connectivity”下先勾选六组脑区对，再独立勾选 `MIC`、`MIM`、`wpli`、`dpli` 和 `wpli2_debiased`。连接参数页只包含当前后端真正使用的选项：`mode`、`fmin/fmax`、Multitaper `mt_bandwidth/mt_adaptive/mt_low_bias`、wPLI/dPLI 的通道对脑区汇总方式、每个脑区的自动/固定 rank、MIC `n_components` 和 `n_jobs`。`n_components` 仅在勾选 MIC 时显示；MIM 不显示该控件，也不会因 MIC 只选择一个成分而被截断。

每次连接估计使用同一文件、同一记录节点和同一给药时点内对齐的多个 epoch，并显式构造所选脑区对。数据不跨 epoch 拼接。真实通道顺序来自 FIF 通道名和 `channel_map.csv`，不是数组位置；结果表同时保存实际通道集合、rank、epoch 数、有效时长、频率网格和参数快照。MIC 的 `value_raw` 保留符号，`value_strength` 是绝对值展示；MIM 保留未归一化原始值，不减均值、不裁剪到 0–1。wPLI/dPLI 逐 4×4 跨区通道对保存；dPLI 同时保存 A→B 和 B→A，矩阵不做镜像。

对 wPLI/dPLI，连接矩阵是脑区层面的描述性汇总；每组完整四通道脑区对包含 16 个跨区通道对。`region_pair_summary` 可选 mean 或 median，先在通道对内汇总频率，再汇总有效通道对。通道对频谱和 `channel_pair_band_summary.csv` 始终保留。wPLI 为 0–1；dPLI 为 0–1，0.5 是中性参考。dPLI 的 `seed→target` 只表示计算顺序，不代表因果方向。

`spectrum.csv`/`region_summary.csv` 的 MIC 维度为脑区对×成分×频率（单成分时成分列为 1），MIM/wPLI/dPLI 的脑区摘要为脑区对×频率；原始 wPLI/dPLI 通道对频谱另带 `aggregation_level=cross_region_channel_pair`。`band_summary.csv` 和 `channel_pair_band_summary.csv` 都从完整频谱按配置频段重新汇总。`connectivity_arrays.npz` 保存同一 run 的完整频谱数值坐标，`patterns.csv` 仅在后端提供 MIC patterns 时写入；patterns 是后端空间模式，不是源定位、通道生物学贡献率或因果方向。

改变指标、脑区对、频段勾选、MIC 成分和坐标尺度只重绘/重新汇总，不重新计算连接。改变输入 epoch/通道、频率范围、Multitaper、rank、wPLI/dPLI 汇总方式或 MIC 成分数后，需要重新运行；旧结果不会被静默当成新参数结果。对数轴只使用正值，MIM 不强行变成非负或 0–1 指标。TDE 视图显示 delay curve 和 band-level brain-region comparison，不使用 MIC/MIM 矩阵。

## 指标与保存内容

每个 GUI run 保存：

- `parameters.json`：指标、通道、epoch、时间窗、脑区对、参数定义和参数快照。
- `run_manifest.json`：输入路径、SHA-256、Python/依赖版本、开始结束时间、每个文件的状态和错误。
- `selected_data.npz`：选定的数据数组、采样率、时间、epoch 和通道索引。
- 各指标目录中的 CSV：PSD、频段功率逐 epoch/通道及跨 epoch 汇总、FOOOF 模型/峰/曲线、连接频谱/脑区汇总/秩诊断、时间延迟谱和失败表。
- `psd/psd_arrays.npz`：PSD 频率坐标、epoch/通道坐标和完整 PSD 数组。
- `connectivity/connectivity_arrays.npz`：连接频谱数组及方法、脑区对、成分和 rank 坐标。
- `figures/*.png` 和 `figures/*.svg`：预览图和可编辑矢量图。

未知动物身份、session、给药天数和 AIMs 继续留空；GUI 只运行文件级描述性计算，不自动生成动物层推断。

## 参数规则

- PSD 默认使用 `scipy.signal.welch`，也可以在“PSD 方法 / 参数”页切换为 MNE DPSS `Multitaper`。Welch 的窗函数、窗长、重叠、`nfft`、去趋势和子窗平均只在 Welch 方法下生效；窗长以秒输入后按实际采样率换算为 `nperseg`，`nfft=0` 表示自动，手动 `nfft` 不得小于 `nperseg`。
- Multitaper 的 `multitaper_bandwidth_hz` 是 DPSS 的频谱平滑带宽，不是频率栅格间隔；`adaptive` 控制自适应 taper 权重，`low_bias` 保留频谱集中度足够高的 taper，`normalization` 可选 `length`/`full`，`remove_dc` 控制去除均值，`n_jobs` 控制并行数。Multitaper 的频率栅格主要由选定时间窗长度决定，结果表会同时记录实际频率步长和这些方法参数。
- 切换方法只改变下一次运行的 PSD 计算，不会自动刷新原始波形；PSD、频带功率、FOOOF 使用同一次运行中选定的方法。结果表、FOOOF 表和 `runtime_config.json` 会记录 `psd_method`、频率分辨率及对应参数，便于后续比较时核对设置。
- Welch 子窗平均和跨 epoch 汇总是两个独立选项。完整逐 epoch/通道 PSD 总是保存。
- FOOOF 默认使用当前项目的 specparam fixed 后端；输入是有限、正值、线性功率谱，拟合范围、峰宽、最大峰数、峰高和峰检测阈值都会写入快照。失败和无峰结果保留。
- MIC/MIM/wPLI/dPLI 调用现有 MNE-Connectivity 代码。MIC/MIM 使用显式多变量 `indices`；`rank` 是每个脑区保留的信号维度，`n_components` 只传给 MIC，MIM 始终计算未归一化总相互作用；wPLI/dPLI 保留全部通道对和脑区汇总。
- 连接估计不会把不同文件堆叠成一组，也不会拼接不连续 epoch。实际 epoch 数和有效时长写入表格。
- Time Delay 使用现有 PyBispectra 模块；降采样只发生在 TDE 内部，原始 FIF 不变。

## 已执行验收

在 Windows、Python 3.11.9、PySide6 6.11.2 环境中已执行：

- 离屏 Qt 窗口构造：10 个指标控件、28 个以上参数控件。
- 真实 T80 文件读取：16 个通道、21 个 epoch，物理通道和脑区映射均来自 `metadata/channel_map.csv`。
- GUI 选择 PSD + FOOOF，修改 Hamming、0.5 s 窗长和 25% 重叠；保存的参数为 `nperseg=500`、`noverlap=125`，只生成选择的指标。
- GUI 只选择 MIM：保存清单只有 Connectivity，后端方法只有 `mim`，没有生成 PSD/FOOOF 目录。
- GUI 后端连接指标：MIC、MIM、wPLI、dPLI 和 `wpli2_debiased` 可独立或共同计算，结果分别写入完整 CSV 和独立 PNG/SVG 图。
- GUI 后端 Time Delay：真实样例完成并写入时间延迟表和图。
- 历史运行载入：不重新读取原始 FIF，能从 run 目录重建结果表和绘图数据。
- 原有测试仍通过；Ruff、`pip check` 和 Python 编译检查通过。
- 新增的真实 T80 读取验证：21 个保留 epoch、25 个候选 epoch、4 个上游删除候选，实际有效时长 105 s；检测到 `TETFP21` 在 epoch 14 有 `abnormal_amplitude` 警告，并在 GUI 质量提示区显示。

由于当前计算环境没有可供 Computer Use 捕获的原生 Windows app 窗口，尚未完成真实桌面上的人工鼠标截图验收；已完成 PySide6 offscreen 窗口、事件处理、后台线程、实际文件和保存/载入的程序化验收。实际 Windows/PyCharm 启动入口已经提供。
