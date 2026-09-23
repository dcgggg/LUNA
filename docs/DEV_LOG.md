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

## 2026-09-13 12:30:00 +08:00 — v0.2.2 合并与发布准备

### 远程同步

- 远程仓库已迁移到 `https://github.com/dcgggg/LUNA.git`；保留远程 `main` 上的 README 和最新 Logo/TIFF 更新，不执行强制推送。
- 本地版本与远程提交合并后递增为 `0.2.2`，已为新版本准备独立标签；已存在的 `v0.2.1` 不移动、不覆盖。

### 范围与验证

- 发布内容包含当前代码、测试、文档、配置和可打包资源；真实数据、缓存、结果和本地截图不纳入提交。
- 本地 69 项测试、Ruff、compileall、pip check、版本导入和 wheel 构建已通过；远程主分支推送与 Release 创建待完成后再补充状态。
## 2026-09-19 19:14:05 +08:00 — 项目管理、多记录批量与结果比较

- 任务：进入项目管理阶段，在保留现有单份分析核心的前提下增加项目、被试、session、状态记录、数据单元、批量任务、复核和结果比较。
- 规则：更新 `AGENTS.md` 的单-session 阶段限制；保留算法来源、真实数据只读验证、双语/数据保护及 Git 授权规则。本轮未 commit、push 或发布。
- 新增：`project_store.py`（SQLite 稳定身份和事务）、`result_contract.py`（schema 1.0）、`project_batch.py`（公共核心批量编排）、`results_api.py`（无 GUI 读取/长表）、`comparison.py`、`project_gui.py`。
- GUI：主窗口新增 Project 入口和 `--project` 启动参数；项目工作区包括数据层级/导入预览、批量任务、人工复核和比较页面。通道映射建议必须确认后才能运行区域级连接/延迟。
- 保存：每个模块保留独立历史结果，写入具名 CSV/NPZ 和 manifest；SQLite 仅在 manifest 校验成功后登记。计算、保存、复核状态分离。
- 批量：参数快照按项目模板 → 任务 → 单数据覆盖合并；串行加载数据单元，避免嵌套并行；失败隔离；相同数据/选择/映射/参数指纹才复用。
- 修复：真实运行发现稳定 ID 组成的目录过长会在 Windows 创建临时 CSV 失败，改为短随机运行目录；身份仍完整保存在 SQLite/manifest。批量层不再把“无成功文件的 completed_with_errors”标为完成。
- 合成验收：5 个虚拟被试、Day7、T80/T100；SYN04 重复 T100，SYN05 缺失 T100，SYN03 参数不兼容；比较预览实际返回 3 个无歧义结果、1 个重复、1 个缺失。
- 真实文件验收：固定只读 FIF 完成基础项目批量并由无 GUI API 重载；全模块软件回归生成 Quality、PSD、Band Power、FOOOF、Connectivity、Time Delay 六个 `completed/saved` 包。测试脑区名为 `TEST_R1…TEST_R4`，不代表真实解剖身份。
- GUI 验收：Qt offscreen 1366×768 截图成功，路径 `C:/Users/PC/AppData/Local/Temp/luna_project_gui_validation_20260919_v2/`。桌面控制未暴露原生 Windows 窗口，因此未声称真实鼠标、125%/150% DPI 或多显示器通过。
- 后续补齐：项目树支持编辑被试/session/状态，数据源指纹重定位，前后数据导航；批量页支持恢复最近中断任务，已完成项目不会重跑。
- 比较增强：支持通道/脑区/脑区对筛选、按稳定 `subject_id` 的双时间点配对连线、双侧缺失/重复状态显示、比较快照列表与固定 `analysis_id` 重载。参数不兼容结果继续分开或明确标记，不按行序配对。
- 项目数据增强：同一源可在导入预览中复制为多个明确状态，但必须填写不同的 epoch 集合或时间区间；源内容和选择都相同的记录继续阻止。选择边界按实际 FIF 核验，不从 epoch 序号推断实验时间。
- 配置与筛选：项目模板、本次批量任务和单数据覆盖均可编辑并按既定优先级冻结；项目表显示每个活动模块的计算/保存/复核状态。比较页增加单被试、具体 session 和时间范围筛选；无 GUI 读取脚本同步支持 session ID、时间范围和复核状态。
- 连接结果比较：直接读取已保存 `spectrum` 与 `band_summary`，增加指定脑区对频谱和逐被试脑区矩阵；矩阵采用同任务公共 normalization、各自 colorbar，并保留 dPLI 0.5 中心和去偏平方 wPLI 可能为负的显示语义。真实单文件项目的 MIC 频谱/矩阵离屏截图位于 `C:/Users/PC/AppData/Local/Temp/luna_project_connectivity_compare_20260919/`。
- 最新验证：74 项测试通过，Ruff、compileall、pip check 通过；Qt offscreen 1366×768 与 1920×1080 截图位于 `C:/Users/PC/AppData/Local/Temp/luna_project_gui_validation_20260919_v8/`。Computer Use 未暴露原生 Windows 窗口，真实鼠标及125%/150% DPI仍未验证。
- 单份/批量一致性：固定只读 FIF 在相同项目身份、通道/epoch/时间选择和默认参数下分别调用公共 `run_gui_analysis` 与 `ProjectBatchRunner`；PSD 67,200 行、Band Power 2,016 行的列结构一致，所有数值列以 `rtol=1e-12, atol=0` 逐列一致，分类/身份列逐值一致。临时结果位于 `C:/Users/PC/AppData/Local/Temp/luna_single_batch_equivalence_wp30xipb/`。
- 未解决：真实多动物数据、真实配对设计和行为同步仍未提供；离屏连接图导出有 Times New Roman 中文缺字警告，未静默忽略；项目工作区尚未独立实现完整中英文切换（沿用主程序现状）。

## 2026-09-22 14:17:36 +08:00 — 简化项目创建、导入、检查、批处理与比较流程

- 任务：在既有 SQLite 项目模型、公共计算核心和 `luna-result-bundle/1.0` 上调整职责与交互，不修改科学算法、默认参数或历史结果。
- 项目目录：schema 升级为 2；新建项目使用“名称＋父目录”，名称生成可见的 Windows 安全目录；建立 `data/raw`、`data/derived`、`results`、`exports`、`logs`、`templates`。新导入复制后核验 SHA-256/大小并保存相对路径，旧外部引用提供显式整理迁移。
- 结构与导入：新增无需 JSON 的被试/session/状态三步模板及保存复用；多文件、文件夹选择或拖入均使用一张可编辑预览表，支持继承当前树节点、表格复制粘贴、向下填充和复制状态行。`T<number>` 仅为可见时间建议，不推断动物或 session。
- GUI 职责：项目管理仅保留层级、模板、导入、归属、打开分析和加入批处理；批处理、复核和 A/B 比较从主分析窗口进入。树中隐藏内部 ID，ID 继续作为 SQLite/manifest 外键。
- 人工检查：单份界面保存每个数据单元的映射、通道、epoch、时间窗、状态和备注；增加上一份、下一份、下一份待检查。批处理解析每份数据自己的检查快照并冻结到 manifest，修改科学选择会将活动结果标为需重算。
- 批处理：支持筛选/多选数据、模块、复制当前单份计算参数、保存/载入方案、查看有效参数和任务预检；主参数面板是唯一可编辑参数来源，检查选择不会从当前文件复制给其他数据。
- 比较：A/B 分别选择组、被试、session、条件和时间点，支持复制 A 到 B；纳入表展示两侧 session、条件/时间、文件、有效 epoch/时长、结果版本、状态、兼容性和排除原因，并随 CSV 导出。没有结果的数据只能明确加入批处理，不在比较时自动计算；按稳定 `subject_id` 配对。
- 真实验证：固定只读 FIF 为 21×16×5000、1000 Hz、105 s；复制后的项目内源和外部源 SHA-256 均为 `2751bce6cdad2a17d7ba72978b0b59221f8265dd27d9c77a8e77600ed75a0582`。保存 15 通道、epoch `[0,1,2]` 检查决定后运行 PSD 与 Band Power；两个 manifest 均保留项目相对源、检查状态和实际选择。移动项目目录后源文件仍可解析，无 GUI API 可重载结果。
- 合成验证：明确标记的五被试项目用于模板、缺失/重复/参数不兼容和 A/B 配对界面；不冒充真实动物数据。
- 自动验证：76 项 pytest 全部通过；Ruff、compileall、pip check 通过。单独主窗口加载真实 FIF 并关闭的离屏探针退出码 0。
- GUI 证据：`C:/Users/PC/AppData/Local/Temp/luna_simplified_gui_validation_20260922/` 保存本地截图，不纳入 Git。组合截图工具在全部图生成后统一销毁多个 Qt/Matplotlib 窗口时出现一次 Windows 离屏后端访问冲突；独立主窗口关闭未复现。Computer Use 未暴露原生应用窗口，真实鼠标、125%/150% DPI 与多显示器仍未验证。
- Git：保留进入任务前的未提交修改；本轮未 commit、未 push，未加入真实数据、衍生结果或截图。

## 2026-09-22 18:52:06 +08:00 — 修复项目结构模板未应用

- 范围：仅修复模板按钮调用、模板实例化、层级目录持久化和项目树同步；未修改任何科学算法、分析参数、数据内容或结果格式；未 commit、未 push。
- 已确认根因：`StructureTemplateDialog` 使用标准 Apply 按钮，却把应用函数连接到 `QDialogButtonBox.accepted`；ApplyRole 不发出该信号，因此真实按钮点击没有进入 `_apply()`。直接调用后，旧 `ProjectStore.apply_structure_template()` 又只写 SQLite、不创建层级目录；树虽读取空记录，但刷新后仅展开项目根节点，成功写入也不易被看见。
- 修复：Apply 按钮直接连接 `_apply()`；应用当前编辑内容前显示新增/复用计划。项目 schema 升级为 3，为被试、session、状态保存 `relative_path`，模板应用在一个事务语义下写入记录并创建 `subjects/<被试>/<session>/<状态>/`，失败回滚记录并仅清理本次新建空目录。重复应用复用同一父节点下的逻辑记录，增量应用只补缺失状态。打开旧项目时自动补齐路径和目录。
- GUI：项目树从持久化记录构建，空状态明确显示“未导入数据”；刷新保留原展开/选择状态，模板完成后展开并定位对应分支。保存模板与应用模板的含义分开说明；应用期间禁用按钮并记录项目本地 `logs/project_operations.jsonl`，成功反馈使用实际持久化计数。
- 自动验证：新增按钮绑定、2 被试×2 session×3 状态、目录存在、关闭重开、重复应用、增量 T80、中文/空格路径、项目隔离、空目录重试、非空目录保护、schema 2 迁移、写目录失败回滚和空树节点显示测试。全量 `82 passed`；改动文件 Ruff 通过；compileall 和 pip check 通过。仓库全量 Ruff 仍报告既有 `notebooks/01_single_file_workflow.ipynb` 导入顺序问题，本轮未改该无关文件。
- 真实 FIF：只读文件 `C:/Users/PC/Documents/ChatGPT/testdata/LID-T80_all_channels-epo.fif` 核验为 21 epoch、16 通道、1000 Hz。导入临时项目 T80 后复制件指纹与源一致，源指纹前后不变；项目树和数据表可打开该数据单元，关闭重开后 2/4/16 层级及数据单元仍存在。
- 证据：离屏项目树与项目管理截图、目录清单和验证摘要位于 `C:/Users/PC/AppData/Local/Temp/luna_template_fix_artifacts_20260922/`，未加入 Git。当前桌面控制没有暴露 Windows 原生应用窗口，因此真实鼠标和系统 DPI 未声称通过。

## 2026-09-22 23:29:18 +08:00 — 修复导入状态关联、版本化检查和结果有效性

- 根因：导入预览只传递被试/session/state 显示字段，丢失已选模板状态的 `state_record_id`；提交时再按显示文字和可选元数据匹配，任一字段差异都会调用 `add_state_record()`，因此同一父级出现第二个 T0/T80。树刷新只是如实显示 SQLite 中的两个状态，不是重复追加控件。
- 导入：预览表改为逐文件选择已有状态，固定内部 ID；项目级批量导入支持向下填充目标，未分配行不能提交，导入路径不再创建结构。状态右键和工具栏增加“导入到选中状态”；项目树显示持久化数据子节点，初始状态为“待检查”。相同内容与相同 epoch/time 选择阻止重复，不同选择可作为同一状态下的独立数据单元。
- 迁移：增加同父级重复状态预览。仅语义字段完全一致的组可自动合并；执行前用 SQLite backup API 写入 `logs/backups/`，数据记录按稳定 ID 改绑，歧义组保留人工处理。
- 检查：项目 schema 升级到 4；增加 inspection revision/fingerprint/save status、源结构快照/指纹和 `inspection_history`。主 GUI 对通道、坏道、映射、原始 epoch 对应、时间选择、检查状态及备注进行防抖自动保存，切换数据、关闭或启动计算前刷新待保存内容；结构不兼容时不自动套用旧掩码。
- 状态：计算、保存、结果有效性和人工复核分离。检查或映射变化只将结果设为 `result_validity=needs_recompute`，不改写历史 `completed/saved`；最新失败运行不会取代旧的成功兼容结果。
- 结果：单份与批处理均冻结任务启动时的检查 revision/fingerprint 和条件元数据。manifest 增加兼容别名 `dataset_id/state_id/analysis_run_id`、检查快照和完整标记；缓存与默认比较只使用 `result_validity=current`。
- 自动验证：86 项 pytest 全部通过；`ruff check src tests scripts`、`compileall -q src tests scripts`、`pip check` 和 `git diff --check` 通过。新增稳定状态关联、不同父级同名状态、重复导入、检查审计、结果失效分离、精确重复状态备份归并、半成品 manifest 拒绝和树中数据子节点测试。
- 真实 FIF：只读文件核验为 21×16×5000、1000 Hz。临时模板项目导入前后均为 8 个状态；同一目标状态保存两条不同 epoch 选择，完全相同来源/选择被阻止。3 个 epoch 的 PSD 与 Band Power 批处理完成并生成可重载 bundle；修改检查后旧结果仍为 `completed/saved` 且可读取，同时标记 `needs_recompute`。
- 单份/批量一致性：恢复后的 15 通道、epoch `[0,1]` 检查配置分别进入 `run_gui_analysis` 和 `ProjectBatchRunner`；PSD 6000 行、Band Power 180 行，数值列 `rtol=1e-12, atol=0` 一致，标签列逐值一致。
- GUI：Qt offscreen 实际加载真实 FIF，自动保存后重开恢复首通道坏道/排除和 epoch `0,1`。本地证据位于 `results/local_validation/`，受 `.gitignore` 保护，不纳入 Git。Computer Use 仍未返回原生 Windows 应用窗口，因此真实鼠标、125%/150% DPI 未声称通过。
- Git：保留进入任务前的修改；本轮未 commit、未 push，未改写原始 FIF。

## 2026-09-23 09:24:22 +08:00 — 项目保存、历史结果恢复与行为元数据

- 任务：继续完善 Project Manager、项目显式保存/恢复和已保存结果浏览；不修改科学算法、默认参数、原始数据或执行 Git commit/push。
- 项目存储：schema 升级到 5，新增行为附件、AIMs/行为评分和同步记录表。评分 `NULL` 保持缺失，`0` 保持真实零；附件和同步记录可关联稳定状态/数据单元，但本轮不处理视频内容。
- 项目保存：Project Manager 增加 `Save project`/Ctrl+S、脏状态、关闭时 Save/Discard/Cancel 和本地草稿标记。首次结构/导入/元数据编辑前建立 SQLite backup，保存后清理草稿；Discard/恢复只处理本次新增且可安全删除的空目录/文件，不覆盖既有数据。检查自动保存和结果自动保存仍与项目结构保存分开。
- 结果恢复：从项目数据单元打开分析时先读取持久化结果索引和 `luna-result-bundle` manifest，直接恢复 PSD、Band Power 及其他已登记模块，不重新计算；原始 FIF 缺失时仍可浏览可读结果。当前成功结果优先，失败/损坏候选不会遮蔽较早成功版本。新增历史版本选择、只读参数查看和“应用为待运行参数”入口；历史结果使用唯一 `data_unit_id:analysis_id` 载荷键，避免版本互相覆盖。
- GUI：Project Manager 明确设为非模态普通窗口；主分析窗口保留项目上下文和结果版本入口。保存、恢复和失败候选均写入项目/运行日志，未把旧结果误标为新计算完成。
- 验证：固定只读 FIF `C:/Users/PC/Documents/ChatGPT/testdata/LID-T80_all_channels-epo.fif` 已用于项目导入、PSD/Band Power 结果索引、原始源缺失时恢复和离屏主 GUI 恢复；项目草稿 Save/Discard、行为零/缺失、SQLite backup 恢复验证通过。全量 pytest、Ruff、compileall、pip check、git diff --check 通过；历史版本双运行包的唯一载荷键和结果选择控件也通过离屏验证。
- 限制：当前草稿机制通过 SQLite backup/journal 提供可恢复 Save/Discard 边界，编辑写入 SQLite 后仍可被同一项目的其他进程读取；尚未改造成跨进程事务工作区。原生 Windows 鼠标、系统 DPI 和视频逐帧同步未在本环境验证。

## 2026-09-23 09:47:37 +08:00 — v0.3.0-dev0 发布准备

- 范围：整理当前项目管理阶段的 LUNA 代码、测试、文档和结果契约改动；未修改科学算法、默认估计参数、原始 FIF 或本地衍生结果。
- 版本：源码和动态打包版本均为 `0.3.0.dev0`；按开发版本规则拟使用 Git 标签 `v0.3.0-dev0` 并创建 GitHub prerelease，不移动既有 `v0.2.0`、`v0.2.1` 或 `v0.2.2` 标签。
- 验证：全量 pytest、`ruff check src tests scripts`、`compileall -q src tests scripts`、`pip check` 和版本导入均通过；固定只读 FIF 实际读取为 21×16×5000、1000 Hz、`0–4.999 s`，SHA-256 与已记录指纹一致。
- 入口：`scripts/run_gui.py --help`、项目演示脚本和无 GUI 结果读取脚本的帮助检查通过；wheel 将在提交前从当前工作区重新构建。
- 提交边界：不纳入真实数据、`results/` 衍生结果、缓存、虚拟环境、日志输出目录和 `docs/screenshots/` 本地截图；发布前检查暂存区和远程提交一致性。
- 限制：当前验证仍不替代实体 Windows 窗口下的鼠标、系统 DPI 和多显示器人工检查；真实动物身份、行为同步和动物层级推断继续保持未解析状态。
