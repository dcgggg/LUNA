# LUNA 开发日志

## 2026-09-12 — 本地首次核实基线

### 范围

按本地首次核实清单检查根目录说明、工作区、Python 环境、CLI/GUI 入口、六个计算模块和指定真实 FIF。该次只做核实和文档记录，不批量实施尚未完成的功能，不修改分析算法，不执行 Git commit 或 push。

### 代码确认

- 根目录及子目录没有发现 `AGENTS.md` 或大小写变体。
- 项目版本为 `0.2.0`；版本来源为 `src/lfp_analysis/__init__.py`。
- GUI 使用 PySide6 + Matplotlib，入口为 `scripts/run_gui.py`。
- PyCharm 单文件入口为 `scripts/run_single_file.py`；其默认样例路径不在当前仓库，因此未配置路径时会在分析前失败。
- CLI 入口和 `lfp-analysis.exe` 可调用；当前 `.venv` 没有生成 `luna.exe` console 别名。
- 当前工作区在本轮开始前已有未提交修改；所有既有修改均保留。

### 环境核验

Python 3.11.9；MNE 1.12.1；MNE-Connectivity 0.9.0；specparam 2.0.0rc7；FOOOF 1.1.1；PyBispectra 1.3.2；PySide6 6.11.2；NumPy 2.4.6；SciPy 1.17.1；pandas 2.3.3；Matplotlib 3.11.1。

### 运行验证

- `python -m pytest -q`：52 项通过；保留 FOOOF 第三方弃用警告。
- `python -m ruff check src tests scripts`：通过。
- `python -m compileall -q src scripts`：通过。
- `python -m pip check`：无损坏依赖。
- `git diff --check`：退出码 0，仅有换行转换提示。
- `python -m lfp_analysis.cli validate-synthetic`：状态 `ok`，10 Hz 合成主峰识别正确。
- 指定真实 FIF 只读读取：21×16×5000、1000 Hz、有效时长 105 s、25 个候选 epoch、4 个非空 drop log 条目、数据有限值检查通过。
- 真实单文件全流程：状态 `completed`；连接和时间延迟状态均为 `ok`；动物层统计未运行；结果写入唯一临时目录 `C:/Users/PC/AppData/Local/Temp/luna_baseline_3wrxynea`。
- 真实样例映射：`TETFP01–04=M1`、`TETFP05–08=STR`、`TETFP17–20=PF`、`TETFP21–24=SNr`。
- 真实 QC：0 个 fail epoch×channel 行；`TETFP21` 的 epoch 14 有 `abnormal_amplitude` 警告。
- Qt offscreen GUI 构造成功并生成 `C:/Users/PC/AppData/Local/Temp/luna_gui_baseline_20260912.png`；当前环境不能把该结果等同于真实桌面人工验收，且该次进程在 Qt 清理阶段返回非零码。

### 当前限制

- 当前真实样例没有可确认的 animal_id、session_id、给药天数或 AIMs，因此只保留文件级描述性结果。
- 没有将真实数据复制到仓库，也没有覆盖已有 `results/`。
- 125%/150% 系统缩放、真实鼠标交互、多文件真实登记批量统计和视频时间同步本轮未核实。

## 2026-09-13 10:00:58 +08:00 — PSD 动态参数与结果区独立滚动

### 范围与原因

- PSD 参数页改为“方法 → 通用参数 → 当前方法专属参数”；Welch 与 Multitaper 的非当前分组连同标题完全隐藏，隐藏后不占布局空间。
- 结果页移除包住全部内容的外层滚动，改为固定结果选择/绘图控制区与各页面独立图像滚动区。
- 结果数据表默认完全隐藏并延迟创建单元格；首次展示新结果时恢复折叠，同一结果的普通绘图刷新保留用户状态。
- 同步更新 AGENTS.md 的 PSD 参数例外规则。未修改分析算法、默认计算值或导出数值语义。

### 涉及文件

- AGENTS.md
- src/lfp_analysis/gui.py
- src/lfp_analysis/gui_layout.py
- src/lfp_analysis/connectivity_gui.py
- src/lfp_analysis/gui_specs.py
- src/lfp_analysis/gui_engine.py
- tests/test_gui.py

### 关键实现

- 新增可复用 PlotScrollArea，Band Power、FOOOF、Connectivity/TDE 与普通 PSD/波形页均将绘图内容放入独立滚动区；显示参数改变后恢复并约束原滚动位置。
- 新增未聚焦数值框/下拉框滚轮保护。
- PSD 控件只创建并绑定一次；切换方法仅切换持久面板可见性，两个方法最近输入值均保留。运行快照、校验与后端配置只包含当前方法参数；预设保存仍保留两页参数。
- 结果表折叠时不可见、0 行、0 列且不保留高度；展开时最多加载前 1000 行，表格自身滚动。

### 验证

- python -m pytest -q：67 项通过；仅保留 FOOOF 兼容包的既有弃用警告。
- python -m ruff check src tests scripts：通过。
- python -m compileall -q src scripts：通过。
- git diff --check：通过，仅显示仓库既有 Windows 行尾转换提示。
- 指定只读 FIF：21×16×5000、1000 Hz、有效时长 105 s。
- 真实 Welch 运行：PSD、Band Power、FOOOF、wPLI 均完成；运行时 PSD 配置不含 Multitaper 字段。
- 真实 Multitaper PSD 运行完成，334656 行 epoch×channel×frequency 结果；运行时配置不含 Welch 窗、重叠、FFT 或去趋势字段。
- 保存结果可在没有重新读取原始 FIF 的情况下重载；表格保持折叠时成功导出 Band Power SVG 与 CSV。
- 1366×768 Qt offscreen 检查：Band Power 图像滚动最大值 661，滚动前后固定控制区纵坐标均为 215；Connectivity 图像滚动最大值 832；6 个频段矩阵生成 12 个 axes（每矩阵及其独立 colorbar）。
- 截图与验证报告保存在本地忽略目录 results/gui_validation_20260913/，未加入 Git。

### 未完成的人工显示验收

- 当前计算环境的桌面自动化接口未枚举到原生应用窗口；已确认启动的 Python GUI 进程处于响应状态，但不能据此声称完成真实鼠标/触控板人工操作。
- 125%/150% Windows 系统缩放和真实 1920×1080 显示器观感未做桌面级人工核验；自动 Qt 尺寸回归覆盖 980×620、1366×768、1920×1080。
- 真实运行导出阶段出现 Times New Roman 缺少中文字符的既有字体警告；本轮未修改科研图字体或导出语义。

## 2026-09-13 10:47:53 +08:00 — PSD 方法面板与结果区复核修复

### 任务与原因

继续优化当前 Python 版 LUNA GUI：让 PSD 专属参数只显示当前方法；确认结果控制区位于图像滚动区之外；让结果数据预览在新结果时完全折叠且不占用隐藏表格高度。按根目录 `AGENTS.md` 执行；不修改科学算法、默认值或第三方库，不提交、不推送。

### 代码修改

- `src/lfp_analysis/gui_layout.py`：新增 `AdaptiveStackedWidget`，自适应当前 PSD 方法页的 size hint；保留两套控件实例和值，但隐藏页不再影响当前参数区高度。
- `src/lfp_analysis/gui.py`：PSD Welch/Multitaper 面板改用自适应堆叠容器；未知临时方法值安全回到 Welch 页面；保存分析配置滚动区引用；结果表初始及折叠时清除最小/最大高度，展开时才恢复预览高度。
- `tests/test_gui.py`：增加当前堆叠页、当前方法控件可见性及折叠高度的回归断言。

### 实际验证

- 固定只读 FIF `C:/Users/PC/Documents/ChatGPT/testdata/LID-T80_all_channels-epo.fif` 重新读取成功：21 个 epoch、16 通道、5000 点、1000 Hz、有效时长105 s、候选记录数25、4 个非空 `drop_log` 条目、0 个 fail 行和1个 warn行。
- 单文件 CLI 流程实际完成；输出写入 `C:/Users/PC/AppData/Local/Temp/luna_gui_fixed_fif_20260913`，没有写入仓库真实数据目录。
- `./.venv/Scripts/python.exe -m pytest -q`：67 项通过；保留既有 FOOOF 第三方弃用警告。
- `./.venv/Scripts/python.exe -m ruff check src tests scripts`：通过。
- `./.venv/Scripts/python.exe -m compileall -q src scripts`：通过。
- `./.venv/Scripts/python.exe -m pip check`：通过。
- `git diff --check`：退出码0；仅有工作区既有的 LF/CRLF 转换提示。
- Qt offscreen 载入真实 FIF 并保存截图：Welch/Multitaper 参数页、图像滚动时顶部控件、结果表折叠与展开均已生成。截图目录：`C:/Users/PC/AppData/Local/Temp/luna_gui_validation_20260913`。
- 自动尺寸检查覆盖 980×620、1366×768、1920×1080；当前环境没有原生桌面自动化窗口，故真实鼠标、实体显示器及125%/150%系统DPI仍未验证。

### 结果影响

本轮只改 GUI 容器和表格的显示/尺寸生命周期；当前方法参数的读取路径本来已有过滤，本轮用回归测试确认隐藏分支不进入运行快照。未改变 PSD 或其他分析数值，因此已有数值结果不因本轮而必须重算；若用户切换 PSD 方法或其计算参数，仍按既有规则需要重新运行。

## 2026-09-13 11:56:46 +08:00 — 连接频谱工频显示中断诊断与修复

### 任务与范围

- 针对 MIM 连接频谱在工频位置出现视觉断点且图例显示“工频标记”的问题，按根目录 `AGENTS.md` 追踪实际 GUI 绘图调用链；本轮不修改连接估计算法、频段汇总、工频分析遮罩、陷波或重参考。
- 实际解释器为仓库 `.venv`，GUI 入口为 `scripts/run_gui.py`；实际载入的 `connectivity.py`、`connectivity_plots.py` 和 `connectivity_gui.py` 均来自当前工作区 `src/lfp_analysis/`。当前无残留 Python GUI 进程。

### 根因与修改

- 固定只读 FIF 对应的磁盘结果为 21 个有效 epoch、MIM 频率范围 2–100 Hz、步长 0.2 Hz；保存的估计器输出和脑区汇总在 50 Hz/100 Hz 附近均为有限值。缺口首次出现在 `src/lfp_analysis/connectivity_plots.py::plot_spectrum` 的绘图阶段：旧逻辑把 `frequency_is_masked_for_plot`（旧表回退到 `frequency_is_excluded_line_noise`）对应的 y 值改为 NaN，随后又用相同区间绘制 `axvspan` 并添加“工频标记”。
- `plot_spectrum` 现在默认保留有限原始频点；`show_line_noise_markers` 只控制灰色注释，`exclude_line_noise` 只在用户明确选择时对当前绘图插入 NaN。两者互不控制，也不修改保存的 raw 频谱或配置的 band summary。平滑显示在排除关闭时从未修改的汇总值副本构建连续的 display-only 表。
- `src/lfp_analysis/connectivity_gui.py` 新增“显示工频标记”和“绘图排除工频频点”两个独立选项，默认关闭，并在状态栏/设置导出中记录当前选择。导出图沿用当前 GUI 选择；其他连接指标复用同一绘图函数时也遵循同样的显式开关。
- `docs/connectivity_frequency_diagnostics.md`、`docs/gui_guide.md` 更新了两种显示选项的定义；`tests/test_connectivity_plots.py` 和 `tests/test_gui.py` 增加独立开关回归测试。

### 实际验证

- 固定 FIF 只读核验：21×16×5000、1000 Hz、0–4.999 s；文件 SHA-256 与保存结果一致。当前配置实际为 50 Hz、1 Hz 全宽、谐波开启，分析遮罩和旧版绘图遮罩字段均为启用；本轮没有改写该分析设置。
- 同一磁盘重载结果生成 A/B 对照图：A 为旧行为（标记开启且绘图排除开启），B 为标记关闭且绘图排除关闭；两图未重新计算。B 中 50/100 Hz 附近最终 `Line2D` 均为有限值，和保存 raw 值逐点最大差异为 0。标记开启、排除关闭的中间状态也验证为数值不变，仅增加标记图元；显式排除状态产生预期显示断点。
- 平滑显示、设置保存及 MIM GUI offscreen 载入均已验证；保存设置记录了两个开关状态。完整数值诊断表和真实衍生截图仅保存在本地临时目录 `C:/Users/PC/AppData/Local/Temp/luna_mim_line_noise_diagnostic_20260913`，未写入仓库。
- `.venv/Scripts/python.exe -m pytest -q`：全量通过；`ruff check src tests`、`compileall -q src tests` 通过。仅保留既有 FOOOF 第三方弃用警告。

### 限制

- 用户截图中的 12 个有效 epoch、150/200 Hz 频率范围无法由当前指定 FIF/当前保存结果复现；指定数据实际为 21 个有效 epoch且最高100 Hz，因此 150/200 Hz 在诊断表中标记为未覆盖，不能据此推断截图对应结果的估计器阶段。
- 当前计算环境没有可用的原生桌面窗口供 CUA 操作；已完成 PySide6 `offscreen` GUI 实际载入和绘图/导出验证，但真实鼠标、实体显示器和系统 DPI 观感仍需用户本机人工确认。

## 2026-09-13 12:21:45 +08:00 — v0.2.1 发布准备

### 范围与版本

- 将当前工作区的 LUNA 版本更新为 `0.2.1`，按兼容性 GUI、绘图、连接诊断、资源打包和质量修复组成的补丁版本准备预发布。
- 更新 `CHANGELOG.md`，发布说明只记录当前工作区实际存在的功能、修复、验证和限制。

### 暂存与验证

- 精确暂存当前代码、测试、文档和可打包资源；未暂存本地真实衍生截图目录，未包含原始 FIF、结果、缓存或虚拟环境。
- 69 项测试、Ruff、compileall、pip check、版本导入和 PEP 517 wheel 构建均通过；wheel 版本为 `0.2.1`。
- GitHub 推送和 Release 创建需在本地网络恢复后继续核实；本条记录不把未完成的远端动作标为成功。
