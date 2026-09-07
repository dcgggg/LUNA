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

1. 点击“添加 FIF”，可以选择一个或多个文件。读取后会显示真实通道名、物理通道号、脑区映射、采样率、epoch 数和 SHA-256。
2. 在“分析范围”中勾选脑区，点击“应用脑区选择”，再核对实际通道列表。epoch 支持 `all`、`0-20` 和 `0,2,4`。
3. 设置 epoch 内时间窗。Welch 窗长超过该时间窗会在运行前拦截，不会静默缩短。
4. 勾选指标。每个指标独立执行；FOOOF 自动依赖匹配配置的 PSD，Band Power 自动依赖 PSD；MIM 不会自动运行 FOOOF、MIC 或 wPLI。
5. 在参数页修改会传入后端的参数。频段边界和相对功率分母在“频段功率”页编辑；rank 的 fixed 模式可为四个脑区指定固定秩。
6. 点击“运行勾选指标”。运行时控件仍可修改，但当前后台任务使用点击时冻结的快照；修改只影响下一次运行。
7. 结果完成后在右侧结果下拉框切换文件和指标，查看图、数值表和日志。图可用 Matplotlib 工具栏缩放/平移/重置，也可以导出当前图。
8. 用“保存预设”保存参数；用“载入历史”选择含有 `run_manifest.json` 的 run 目录，可在原始 FIF 不可用时恢复表和图。

## 指标与保存内容

每个 GUI run 保存：

- `parameters.json`：指标、通道、epoch、时间窗、脑区对、参数定义和参数快照。
- `run_manifest.json`：输入路径、SHA-256、Python/依赖版本、开始结束时间、每个文件的状态和错误。
- `selected_data.npz`：选定的数据数组、采样率、时间、epoch 和通道索引。
- 各指标目录中的 CSV：PSD、频段功率逐 epoch/通道及跨 epoch 汇总、FOOOF 模型/峰/曲线、连接频谱/脑区汇总/秩诊断、时间延迟谱和失败表。
- `psd/psd_arrays.npz`：PSD 频率坐标、epoch/通道坐标和完整 PSD 数组。
- `figures/*.png` 和 `figures/*.svg`：预览图和可编辑矢量图。

未知动物身份、session、给药天数和 AIMs 继续留空；GUI 只运行文件级描述性计算，不自动生成动物层推断。

## 参数规则

- PSD 使用 `scipy.signal.welch`；窗长以秒输入后按实际采样率换算为 `nperseg`，重叠百分比换算为 `noverlap`。`nfft=0` 表示自动；手动 `nfft` 不得小于 `nperseg`。
- Welch 子窗平均和跨 epoch 汇总是两个独立选项。完整逐 epoch/通道 PSD 总是保存。
- FOOOF 默认使用当前项目的 specparam fixed 后端；输入是有限、正值、线性功率谱，拟合范围、峰宽、最大峰数、峰高和峰检测阈值都会写入快照。失败和无峰结果保留。
- MIC/MIM/wPLI 调用现有 MNE-Connectivity 代码。`MIC`/`MIM` 会映射为后端的 `mic`/`mim`，不使用无效的 `n_components` 控件；wPLI 保留通道对结果和脑区汇总。
- 连接估计不会把不同文件堆叠成一组，也不会拼接不连续 epoch。实际 epoch 数和有效时长写入表格。
- Time Delay 使用现有 PyBispectra 模块；降采样只发生在 TDE 内部，原始 FIF 不变。

## 已执行验收

在 Windows、Python 3.11.9、PySide6 6.11.2 环境中已执行：

- 离屏 Qt 窗口构造：8 个指标控件、28 个以上参数控件。
- 真实 T80 文件读取：16 个通道、21 个 epoch，物理通道和脑区映射均来自 `metadata/channel_map.csv`。
- GUI 选择 PSD + FOOOF，修改 Hamming、0.5 s 窗长和 25% 重叠；保存的参数为 `nperseg=500`、`noverlap=125`，只生成选择的指标。
- GUI 只选择 MIM：保存清单只有 Connectivity，后端方法只有 `mim`，没有生成 PSD/FOOOF 目录。
- GUI 后端三种连接指标：参数快照包含 `mic`、`mim`、`wpli2_debiased`，三种结果均写入 CSV 和图。
- GUI 后端 Time Delay：真实样例完成并写入时间延迟表和图。
- 历史运行载入：不重新读取原始 FIF，能从 run 目录重建结果表和绘图数据。
- 原有测试仍通过；Ruff、`pip check` 和 Python 编译检查通过。

由于当前计算环境没有可供 Computer Use 捕获的原生 Windows app 窗口，尚未完成真实桌面上的人工鼠标截图验收；已完成 PySide6 offscreen 窗口、事件处理、后台线程、实际文件和保存/载入的程序化验收。实际 Windows/PyCharm 启动入口已经提供。
