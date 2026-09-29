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

## 2026-09-24 09:00:00 +08:00 — v0.3.0-dev1 发布准备

- 范围：发布上次 `v0.3.0-dev0` 之后的项目管理范围收敛、筛选/导出、session 顺序、schema 6 迁移、草稿恢复回归和交接文档；未修改科学算法、默认估计参数或原始 FIF。
- 版本：源码和动态打包版本更新为 `0.3.0.dev1`，拟使用不可覆盖的新标签 `v0.3.0-dev1` 并创建 GitHub prerelease。
- 验证：全量 `pytest -q` 通过（103 项）；`ruff check src tests scripts`、`compileall -q src tests scripts`、`pip check` 和 `git diff --check` 通过，仅保留 FOOOF 第三方弃用警告。
- 固定只读 FIF：已核实 `21×16×5000`、1000 Hz、4.999 s/epoch、有效时长 105 s；文件指纹与既有记录一致，未修改源文件。GUI/结果读取入口帮助检查仍可用。
- 产品边界：当前 GUI 不再提供跨数据 A/B、跨被试配对、组间/组内统计或科研比较绘图；旧比较存储和读取接口仅作兼容，外部脚本或 notebook 读取保存结果完成下游统计。
- 限制：原生 Windows 鼠标、实体 DPI、多显示器和视频逐帧同步未在本环境验证；真实身份和行为信息仍未解析。`docs/screenshots/` 本地截图不纳入提交。

## 2026-09-23 10:38:49 +08:00 — 移除软件内跨数据比较并完善项目记录筛选

- 任务：按产品方向将 LUNA 的当前 GUI 范围收敛到项目管理、数据检查、分析计算、结果保存/恢复和单数据可视化；跨被试、组间、组内统计与科研绘图改由独立代码读取保存结果完成。本轮未修改科学算法、默认估计参数、原始 FIF，未 commit、未 push。
- GUI：主分析窗口删除跨项目 Compare 按钮和工作区引用；Project Manager 不再提供 Compare 模式，新增 `Filter / export list`。筛选只产生数据记录清单，不配对、不平均、不跨记录计算；单条数据内的通道/频带/脑区视图仍保留。
- 项目管理：数据表支持多选后编辑 group 和 condition，按稳定 `subject_id`/`state_record_id` 写回；混合值显示“多个值”，空值可清除，编辑进入项目 dirty/save 流程。筛选窗口支持同字段 OR、跨字段 AND、结构化时间、检查状态和当前结果可用性，并导出 CSV/JSON。
- 兼容：保留 `comparison.py`、SQLite `comparison_snapshots` 表和旧比较文件读取能力，避免旧项目打不开；这些接口不再由当前 GUI 调用。移除刷新流程中残留的比较控件刷新调用。
- 数据模型：项目 schema 从 5 升级到 6，为 session 增加显式 `sort_order`；新建/模板应用按用户输入顺序显示，旧项目按历史创建顺序非破坏迁移。初始化版本标记、迁移、查询排序和结果查询均已同步。
- 验证：`ruff check src tests scripts`、`compileall -q src tests scripts`、`pytest -q`（88 项）、`pip check` 和 `git diff --check` 通过。指定只读 FIF 实测读取为 21×16×5000、1000 Hz、有效时长 105 s、25 个候选 epoch、4 个非空 drop_log 条目。
- 合成项目/离屏 Qt：在含空格和中文路径的临时项目中应用 2 被试×2 session×2 state 模板，目录和 SQLite 记录在重开后保留；同一被试 session 显式顺序保持；导入指定 FIF 的项目数据记录可被筛选窗口读取。主 GUI 离屏启动后仅显示 Project、Batch、Review，全局 Compare 按钮不存在。
- 限制：未在当前环境进行实体 Windows 原生窗口、鼠标、多显示器和 125%/150% DPI 人工验收；真实动物身份、行为同步和动物层统计仍未解析。临时项目与截图未写入仓库。

## 2026-09-23 11:00:03 +08:00 — 产品范围调整后的代码恢复与最终回归

- 复核：移除跨数据比较实现后，逐段恢复并检查项目管理、导入、模板、批处理、结果复核和关闭保存流程；当前 `ProjectWorkspace` 不再创建或刷新比较控件，历史比较存储与读取接口仍保留兼容。
- 会话字段：项目管理编辑入口现在可修改 session 日期和显式显示顺序；schema 6 的迁移、模板顺序、查询排序和结果索引保持一致。
- 验证：`pytest -q` 88 项通过；`ruff check src tests scripts`、`compileall -q src tests scripts`、`pip check` 和 `git diff --check` 通过。固定只读 FIF 实测读取为 21×16×5000、1000 Hz、有效时长105 s；临时项目导入和筛选窗口各返回1条对应记录。
- GUI：Qt offscreen 主窗口实际构造，顶部项目入口为 Project、Batch、Review，`project_compare_button` 不存在；项目管理、Batch、Filter / export list 和 Review 工作区均可构造。未执行原生 Windows 鼠标、系统 DPI 或多显示器人工验收。
- 边界：未改变 PSD、FOOOF、频带功率、连接、时间延迟及其他分析算法、默认计算参数、原始 FIF 或导出数值语义；本轮未 commit、未 push。临时测试项目和真实数据衍生物未写入仓库。

## 2026-09-23 14:58:11 +08:00 — 项目整体审查与开发交接整理

### 范围

- 依据当前工作区代码、`AGENTS.md`、README、依赖配置、入口、项目管理/结果保存调用链和现有测试，整理 LUNA 的架构、产品范围、证据状态和下一步交接材料。本轮不修改分析算法、默认参数、真实数据或源代码，不执行 commit/push。
- 创建 `docs/ARCHITECTURE.md` 和 `docs/HANDOFF.md`；将 `docs/DEVELOPMENT.md` 压缩为当前入口/环境/验证指南；在 `docs/PROJECT_STATUS.md` 增加当前审查覆盖；更新 `AGENTS.md` 的首次接手清单语义。

### 代码确认

- 单条和批处理最终复用 `gui_engine.run_gui_analysis()`；`ProjectStore` 负责 schema 6、稳定身份、导入指纹、检查、结果索引和旧比较数据兼容；`ProjectResults` 提供无 Qt 表/数组/长表读取。
- 当前 GUI 不再调用跨数据比较入口；`comparison.py`、`comparison_snapshots` 和历史比较文件仅保留兼容。行为模块当前是附件/评分/同步字段的结构化存储，不处理视频逐帧或逐 epoch 对齐。
- 主要维护风险是 `MainWindow`、`ProjectWorkspace` 和 `ProjectStore` 职责集中，以及 Project Manager “编辑即时写 SQLite、Save 确认 backup/marker”的可恢复草稿语义。后者已有 Save/Discard/backup 测试，但不是跨进程事务工作区，交接材料中已列为 P1 语义风险。

### 验证

- `.venv\Scripts\python.exe -m pytest -q`：88 项通过；FOOOF 兼容后端出现第三方弃用警告。
- `ruff check src tests scripts`、`compileall -q src tests scripts`、`pip check`、`git diff --check`：通过。
- 固定只读 FIF `C:/Users/PC/Documents/ChatGPT/testdata/LID-T80_all_channels-epo.fif` 读取为 21×16×5000、1000 Hz、4 个非空 `drop_log` 条目；身份未解析。`scripts/run_gui.py --help` 和 `scripts/read_project_results.py --help` 通过。
- 本轮再次尝试 offscreen 主 GUI 载入时进程以退出码 1 且无输出结束，因此未将该次列为新的 GUI 通过证据；此前离屏构造记录仍保留，但不替代实体 Windows 鼠标、DPI 和多显示器验收。

### 未解决

- 未改变代码，因此未新增源代码回归；下一步应先补 Save/Discard 的崩溃、重开、第二读取者和目录保护测试，再评估 ProjectStore 拆分。真实动物身份、行为同步、动物层统计和原生 GUI/DPI 仍未验证。

## 2026-09-23 15:16:48 +08:00 — Project Manager 草稿恢复与 Save/Discard 回归

### 范围与代码确认

- 沿 `ProjectWorkspace._begin_project_edit()`、`save_project()`、`discard_project_changes()`、`_offer_draft_recovery()` 和 `ProjectStore.backup_database()` / `restore_database_backup()` 检查保存调用链；没有修改分析算法、默认计算参数或真实 FIF。
- 确认项目编辑在 Save 前已写入活动 SQLite；独立 `ProjectStore` 可立即读到草稿字段。Save 校验层级/数据引用后移除 marker 和备份；Discard 从 SQLite 备份恢复并清理可安全移除的草稿内容，因此该机制是可恢复草稿，不提供第二读取者隔离。
- 草稿 marker 改为临时文件写入、flush/fsync 后 `os.replace`。崩溃恢复对照初始目录清单补认 marker 尚未记录的新目录；Discard 仍只对项目根内路径调用 `rmdir()`，非空目录不删除。

### 运行验证

- 新增 `tests/test_project_draft.py` 4 项：Save/Discard 与第二 `ProjectStore` 可见性；子进程异常终止、重开后 Discard 和目录保护；异常重开后恢复草稿、Save 并再次重开；schema 5→6 迁移保留层级/数据身份并建立 session 顺序索引。
- 子进程测试在独立临时项目调用 `os._exit(73)` 模拟进程突然终止；仅使用临时合成项目及合成来源字节，不读取或更改真实 FIF。
- `.venv\Scripts\python.exe -m pytest -q`：92 项通过（含第三方 FOOOF 弃用警告）；`ruff check src tests scripts`、`compileall -q src tests scripts`、`pip check`、`git diff --check` 均通过。
- `docs/ARCHITECTURE.md`、`docs/PROJECT_STATUS.md` 和本交接文件已同步当前保存语义、测试覆盖和待产品决策。

### 未验证与限制

- ProjectWorkspace 在 Qt offscreen 下由测试实际构造并触发恢复回调；未进行原生 Windows 鼠标人工操作、实体显示器尺寸、100%/125%/150% DPI 或多显示器验证，也没有生成 GUI 截图。
- 草稿期间其他读取者可见写入是经测试确认的既有行为，不是故障修复；若产品要求 Save 前隔离，需另行设计 draft DB。测试未覆盖电源/磁盘损坏级故障，也不证明底层文件系统对断电的持久化保证。
- 本轮未提交或推送；保留原有工作区改动。

## 2026-09-23 16:35:04 +08:00 — Project Manager 目录范围联动与按钮说明

### 根因与修改

- 代码确认的旧根因：`ProjectWorkspace._build_data_tab()` 只把树选择事件接到状态资源刷新；`_refresh_data_table()` 又无条件调用全项目 `ProjectStore.data_units()`，所以选择 project/subject/session/state/data 节点都仍展示整项目数据。
- `ProjectStore.data_units()` 增加 project、subject、session、state、data unit 稳定 ID 过滤，并将明确传入的空 ID 集合定义为空结果。表格、状态资源、筛选导出按所选层级的父子 ID 查询，名称和路径只用于显示。
- 左树单击更新范围提示、范围总数和过滤后数量；搜索及 Group/Condition/Inspection 筛选只作用于当前范围。空节点和筛选后无结果分别提示。刷新保留稳定 ID/展开状态；删除选中节点时回退最近仍存在的父节点。行选中与批处理复选框分离，切换范围不自动批量勾选。
- 直接测试发现关闭 Project Manager 后，非模态 Filter/export 窗口仍可能留在屏幕显示旧项目数据；现改为关闭管理器时同步关闭其全部筛选窗口，并添加回归测试。
- `docs/PROJECT_WORKFLOW.md` 整理了当前真实按钮、菜单、右键、对话框、保存/文件影响与使用前提。确认主 GUI 的 `Save Result`/`Export Figure` 同接 `_export_figure`，补充双语 tooltip 明确其重复导出路径和自动分析 bundle 的区别；不合并/删除按钮。当前 Project Manager 没有动态语言切换，已在说明中如实列出。
- 不改分析算法、默认参数或项目 schema；不修改真实 FIF；未 commit/push。

### 运行验证

- 新增/扩展 `tests/test_project_manager_scope.py` 共 7 项：项目/被试/session/state/data 五级范围、同名节点隔离、空 subject/session/state、范围内搜索与筛选、批处理勾选分离、导入后刷新/保存重开、改名后按 ID 保持选择、删除后父级回退、过滤窗口关闭；全量结果为 99 passed。
- 固定只读 FIF `C:/Users/PC/Documents/ChatGPT/testdata/LID-T80_all_channels-epo.fif` 重新读取：21×16×5000、1000 Hz、`0–4.999 s`、16 个实际通道名称；读取前后 SHA-256 相同。将其仅以 external 引用登记在临时项目的 state 后，右侧范围显示一条；打开信号发出相同源路径和 data-unit ID，源文件未复制、移动或改写。
- 临时合成项目实际构造 ProjectWorkspace 并渲染 project、subject、session、state、data leaf、空 subject/session/state 及真实 FIF 行共九种界面截图；路径：`C:/Users/PC/AppData/Local/Temp/luna_pm_scope_final_20260923_8dg7mmlu/`。另外用明确标记的合成 Quality bundle（`C:/Users/PC/AppData/Local/Temp/luna_pm_result_restore_20260923_azqm_gt0/`）通过 `MainWindow` 恢复结果和当次参数，确认 `analysis_thread is None` 且未启动计算。测试输出、截图和项目均留在 `%TEMP%`。
- `.venv\Scripts\python.exe -m pytest -q`：99 项通过；`ruff check src tests scripts`、`compileall -q src tests scripts`、`pip check`、`git diff --check` 均通过。测试只保留 FOOOF 兼容包的既有弃用警告；`git diff --check` 有现存 LF/CRLF 提示，无 whitespace error。
- 原先全项目展示的根因是代码确认且有回归测试支持；异步过期查询不适用，因为当前查询同步在 GUI 线程完成，没有并行刷新结果可覆盖。

### 未验证与限制

- 本轮 Qt 控件交互与截图在 `QT_QPA_PLATFORM=offscreen` 下完成。Computer Use 返回 `apps=[]`，只暴露 Codex IAB；启动的试验 GUI 进程无原生窗口句柄，因此未完成实体 Windows 鼠标验收、真实屏幕分辨率/DPI 或高 DPI 人工检查。
- 使用的真实 FIF 没有已有项目结果 bundle；结果直接恢复路径以隔离的合成 bundle 验证，不能称为恢复该真实文件的既有科学结果。
- Project Manager 无动态中英文切换。按钮/操作清单与明确发现的问题已记于 `docs/PROJECT_WORKFLOW.md`；项目状态和交接材料已同步。

## 2026-09-23 17:09:29 +08:00 — Project Manager 辅助窗口生命周期复核

### 检查结论与修改

- 本轮是对附件所述旧项目窗口串上下文问题做当前代码核验。原先“关闭 Project Manager 后 Filter/export 仍可见”的表现，在本轮开始前已被 `ProjectWorkspace.closeEvent()` 的 accepted-close 分支挡住；关闭确认选择 Cancel 也会 `event.ignore()`，已有筛选窗不应被提前关闭。
- 但 offscreen 运行检查确认仍有生命周期缺口：accepted close 只 `close()` 隐藏子窗口；`ProjectFilterExportDialog` 的 Qt 对象仍有效、仍持有旧 ProjectStore，旧 ProjectWorkspace 也仍作为 MainWindow QObject 子对象存活。故该场景不是完全无问题，本轮只修复对象销毁/上下文释放。
- `ProjectFilterExportDialog` 现在使用 `WA_DeleteOnClose`，单独关窗时清理 Workspace 引用；Workspace 关闭只有在 Save/Discard 被接受后才关闭并 `deleteLater()` 全部 Filter/export 子窗，Cancel 路径不变。`MainWindow._attach_project()` 在项目替换后对关闭成功的旧 manager/batch/review workspace 调用 `deleteLater()` 并清空属性；批处理线程运行期间则拒绝切换并提示先停止/等待，避免旧任务窗口被静默隐藏。
- 其他窗口按代码分为：Import Preview、结构模板、映射、JSON/参数编辑、元数据和重复 state 操作均为有 parent 的模态 `exec()` 对话框；Import Preview 行目标通过 `state_record_id` 保存，背景树选择不会重定向。Batch/Review 是 MainWindow 持有的 project workspace；项目切换时统一关闭/销毁。未发现其他 project-scoped 非模态辅助窗。
- 未修改分析算法、默认参数、项目 schema 或真实 FIF；没有提交/推送。

### 运行验证

- Qt offscreen 直接复现并记录了基线：A 的筛选窗在 A manager 接受关闭后已不可见，但 `shiboken6.isValid(dialog)` 仍为真且仍是旧 Workspace 的子对象；B 新建窗口自身使用 B 的 store。该证据将“可见残留已修复”和“隐藏对象仍存活”区分开。
- `tests/test_project_manager_scope.py` 当前 11 项通过，覆盖所有 Filter 窗接受关闭后的销毁、Cancel 保持 Workspace/筛选窗可见、独立关窗清理引用并可重开、A→B 销毁旧对象并绑定 B、运行中批处理阻止切换、Import Preview 目标 ID 在树选择改变后保持不变；原 scope 测试继续覆盖同名层级与空节点。
- 全量 `.venv\Scripts\python.exe -m pytest -q` 收集/运行 103 项并以 exit code 0 完成；FOOOF 兼容依赖发出既有弃用警告。Ruff、compileall、pip check 和 `git diff --check` 均通过；git 仅报告既有 LF/CRLF 工作区提示。
- 未加载真实 FIF，因为改动只涉及 Qt 对象生命周期；没有执行 GUI 原生鼠标操作。

### 未验证与限制

- Qt 测试使用 offscreen 平台；原生 Windows 鼠标、125%/150% DPI、多显示器仍未验证。
- 当前 close/delete 行为通过 Qt 延迟删除队列运行验证；断电级故障与正在退出应用时的操作系统级窗口清理不属于本轮覆盖。

## 2026-09-27 23:28:38 +08:00 — 分析流程读图指南与结果字段词典

### 检查与修改

- 按当前 `pipeline.py`、`gui_engine.py`、各 `*_plots.py`、GUI view、bundle 和 `ProjectResults` 读取调用链，建立图表→函数→结果字段和 CSV/NPZ/manifest/SQLite 文件清单。帮助正文统一存于 `src/lfp_analysis/analysis_help_content.py`；GUI 新增离线“如何读图”按钮及帮助菜单，详细说明可展开；`scripts/build_analysis_docs.py` 生成 `docs/ANALYSIS_GUIDE.md`、`docs/RESULT_DATA_DICTIONARY.md`、`docs/FIGURE_RESULT_INDEX.md`。README、DEVELOPMENT、PROJECT_STATUS 和 HANDOFF 已增补入口/当前状态。
- 运行固定只读 FIF：`C:/Users/PC/Documents/ChatGPT/testdata/LID-T80_all_channels-epo.fif`，输出在 `%TEMP%/luna_explainer_final_83455015be5846f39980f924b2f2a252`。样例有21个有效 epoch、16通道、1000 Hz、5000点/epoch、有效累计时长105秒；SHA-256 与 manifest 一致。自动质量摘要有1条 warn epoch×channel 记录、0 fail；参数化16通道拟合成功且0失败；连接汇总表8838行、22列，shape 与 metadata 一致；TDE结果表已生成。manifest 仍为 `file_only_identity_unresolved`，动物层统计未运行。该次运行启用 PSD、频带功率、specparam、MIC/MIM/wpli2_debiased 和TDE方法1（standard/antisym）；dPLI、普通wPLI等没有用此样例运行。
- 检查该样例实际生成的41个CSV文件名及列名，全部进入字段目录；17类图各有PNG与SVG。真实文件级 Band Power 多面板图存在标题/旋转标签拥挤的布局限制，本轮记录但未重构。
- 修正 PSD y 轴单位文案和频带功率绝对单位标签；修复 connectivity metadata 的 `region_summary_shape` 使用实际汇总 DataFrame 形状。连接数值计算未改，针对 shape 加了回归断言。文档明确：CLI `config_used.yaml` 若使用 `extends` 只是入口配置副本，CLI manifest 目前不是完整解析参数快照；项目 bundle 才有独立有效参数快照。配置审计标为 unused 的兼容项不能误称为已传入后端。
- 依据当前安装版本核对 SciPy Welch、MNE-Connectivity、specparam 和 PyBispectra 官方说明；可选方法未由本次真实样例验证的部分在指南/交付中分开标记。

### 验证

- `.venv\Scripts\python.exe scripts\build_analysis_docs.py` 生成三份文档；`pytest -q -ra`：108项通过；`ruff check src tests scripts`、`compileall -q src tests scripts`、`pip check` 均通过。FOOOF 兼容包有上游弃用警告。`git diff --check` 无空白错误，仅有既有/仓库 LF→CRLF 提示。
- Qt offscreen 检查帮助弹窗、当前结果→主题路由和展开说明；全量 MainWindow Qt 布局测试通过。未声称完成原生 Windows 桌面人工操作或 DPI 验收。
- 只改说明/显示标签和结果 shape 元数据，不改 LFP/连接/TDE科学数值，不需为本次修改重算。未 commit/push；保留任务开始前已存在的未提交改动和 `docs/screenshots/`。

## 2026-09-28 17:52:27 +08:00 — 主 GUI 紧凑布局与绘图区扩展

### 修改

- `src/lfp_analysis/gui.py`：压缩并自适应顶部两行工具栏；Logo 等比例固定为 160×54 逻辑像素；数据摘要改为文件名及 epoch/时长/通道摘要；长名称省略但保留完整 tooltip。运行控制按钮高度统一为 32。主分隔器记忆并约束左侧参数区宽度，绘图区获得额外伸缩空间；增加专注绘图模式，检查操作控件改为紧凑网格。
- `src/lfp_analysis/connectivity_gui.py`：频带、脑区对选择改为固定控制栏中的菜单；坐标、矩阵、字体、A/B 顺序、频谱显示、平滑和工频显示设置默认折叠；把两类选择各并为一行、更多设置入口并入指标行，减少控制栏占高。绘图区仍在独立滚动区，计算选择和方向含义未改。
- `src/lfp_analysis/connectivity_plots.py`：长频谱标题按中英文显示宽度换行，保留完整文件标识与所有频段名称。
- `src/lfp_analysis/band_power_plots.py`：绘图准备时，仅当功率结果表缺少脑区/物理通道标签时，按明确的 `channel_name` 从同次运行的 `channel_table` 补齐显示元数据。此修复解决真实结果被当前脑区筛选成空图的问题，不改功率值、聚合、保存字段或导出数值。
- 回归测试更新 `tests/test_gui.py`、`tests/test_band_power_plots.py`，新增标题换行测试 `tests/test_connectivity_plots.py`。GUI 测试临时固定 splitter 测试值并在结束后还原原 QSettings，避免测试污染用户的面板宽度。

### 验证

- 用只读 FIF `C:/Users/PC/Documents/ChatGPT/testdata/LID-T80_all_channels-epo.fif` 经 GUI 检查入口读取；SHA-256=`2751bce6cdad2a17d7ba72978b0b59221f8265dd27d9c77a8e77600ed75a0582`，21×16×5000、1000 Hz、有效时长 105 s、映射 4 个脑区。只重绘同 SHA 的既有运行 CSV，没有重新计算分析；输出继续位于 `%TEMP%/luna_explainer_final_83455015be5846f39980f924b2f2a252`。
- Band Power 真实显示复核：输入功率长表 2016 行原本没有 `region`/`physical_channel_number` 列；通过同一运行 `channel_table` 按真实通道名称关联后，完整选择下得到 2016 个 epoch×channel×band 行及 96 行通道汇总，M1/STR/PF/SNr 分组热图正常绘制；原始功率 CSV 未变。
- 同一 offscreen Qt 测量：1366×768 顶栏高 101 px、Logo 160×54、左/右面板 424/924 px、通用绘图视口 908×449 px；既有基线记录为顶栏 122 px、Logo 218×72、左/右 430/910 px、绘图视口 892×406 px。对比约增加绘图区宽 16 px、高 43 px。Connectivity 页压缩控件前视口约 260 px，当前 317 px；图像区滚动时频带/脑区对按钮保持原位。1920×1080 时通用绘图视口 1476×761 px；860×600 最小窗口可用，右侧结果区保留 480 px 宽。
- 通过 Qt `QT_SCALE_FACTOR=1/1.25/1.5` 模拟显示缩放：顶栏逻辑高度均为 101 px、Logo 为 160×54、主操作按钮均高 32 px。此项为 Qt 缩放模拟，不是原生 Windows 显示器 DPI 人工检查。
- 最终页面截图保存在本地 `%TEMP%`，未加入仓库：`luna_pre_layout_raw_1366x768.png`、`luna_final_raw_1366x768.png`、`luna_final_raw_860x600.png`、`luna_final_raw_1920x1080.png`、`luna_final_psd_1366x768.png`、`luna_final_band_power_1366x768.png`、`luna_final_fooof_1366x768.png`、`luna_final_connectivity_1366x768.png`、`luna_final_connectivity_1920x1080.png`、`luna_final_time_delay_1366x768.png`。
- `.venv` 全量 `pytest -q`：110 项通过；`ruff check src tests scripts`、`compileall -q src tests scripts`、`pip check`、`git diff --check` 通过。测试唯一警告为上游 `fooof` 1.1 弃用提示；Git 仅报告工作区既有 LF/CRLF 提示。
- 未修改分析算法、计算参数、结果或导出语义；未执行 commit/push。原生 Windows 桌面窗口、真实物理屏幕 1366/1920 分辨率与系统 DPI 尚未人工操作验收；本轮 Qt 控件/页面通过 offscreen 实例化、真实 FIF 读取、结果重绘、canvas 截图和自动测试核查。

## 2026-09-28 19:13 +08:00 — 功能连接跨机诊断与 Windows/macOS 安装兼容

### 检查与修改

- 沿 `MainWindow` → `AnalysisWorker` → `gui_engine.run_gui_analysis()` → `connectivity.compute_connectivity()` 检查连接估计、图表/CSV/NPZ/metadata 保存和 `load_saved_run()` 重载。单条 GUI 任务在 QThread 中执行，结果通过 Qt signal 回 GUI 主线程；本项目这些分析路径未使用 Python 子进程。MIC/MIM 使用 MNE-Connectivity 多变量路径，wPLI/dPLI/wPLI²-debiased 使用对应双变量方法，TDE 单独使用 PyBispectra；单条与批处理复用同一计算核心。
- 确认并记录兼容风险：`pyproject.toml` 原 `mne-connectivity>=0.7,<1` 允许 API/导入不兼容组合。在隔离 Python 3.11/MNE 1.13.2 环境对 0.8.0/0.8.1 做 `--no-deps` 导入探查，报 `ImportError: cannot import name 'jit' from mne.fixes`，但 `pip check` 未能识别该 API 兼容性。将 `connectivity`、`desktop`、`all` extra 的下限收窄到 `>=0.9,<1`；当前 MNE-Connectivity 官方 API 文档注明 `fdecim`/`n_components` 自 0.8 加入，而 LUNA 的已测试 API 为0.9.0。此项是项目依赖边界修复，不足以确认用户其他电脑的具体故障根因。
- 新增 `src/lfp_analysis/optional_dependencies.py`：启动时导入可选后端并核对必需 API；只禁用导入/接口故障所影响的连接或 TDE 方法，其他分析方法保持可用，不替换估计器。相应方法提示安装哪个 LUNA extra 并提供诊断方向。
- 新增 `src/lfp_analysis/diagnostics.py` 和 `luna-diagnose` 入口：无 Qt 环境报告系统/架构/Python/解释器、版本/模块位置/包 namespace owner、可选后端 API、数值线程池、允许列出的线程环境变量、配置/日志/结果/临时目录写权限；可选读取 FIF 头但不加载样本或导出通道名。GUI worker 与连接估计失败保存脱敏 JSON traceback、输入维度/参数/rank 和失败阶段，并回传简短状态及报告位置；日志报告写失败不会覆盖原始计算异常。
- 新增 `app_paths.py`、`ui_fonts.py`：安装环境使用 Windows/macOS/Linux 对应的每用户可写目录，项目 checkout 仍沿用现有 `metadata/`、`configs/`、`results/` 约定；Logo/YAML 由 package resource 路径加载，字体不依赖 Windows 字体路径。跨平台逻辑由临时目录测试覆盖。
- `docs/DEPENDENCIES.md` 与 README 明确区分 `mne` 与独立发行包 `mne-connectivity`，列出 core/gui/connectivity/TDE/parameterization/desktop/dev/all 安装组和传递依赖；`docs/DEVELOPMENT.md`、`PROJECT_STATUS.md`、`HANDOFF.md` 更新环境、根因证据和验证边界。`.github/workflows/platform-smoke.yml` 对 Windows x64 与 macOS 15 arm64 配置 Python 3.11/3.12 wheel 安装、连接 API 符号、测试和静态检查；工作流尚未推送/远端执行。

### 验证

- 项目 `.venv`：`python -m pytest -o addopts= -q` 为 119 passed/1 FOOOF 上游弃用警告；Ruff、compileall、pip check、`git diff --check` 通过。
- 干净环境：本地源码构建 wheel，独立 Python 3.11.9 Windows x64 venv 使用 `.[desktop,dev]` 安装，不手动补装传递依赖；pip check 和全量 119 项测试通过，Ruff/compileall 通过。MNE 1.13.2、MNE-Connectivity 0.9.0、PySide6 6.11.2、NumPy2.4.6、SciPy1.17.1、PyBispectra1.3.2 等在该环境解析。该环境测试另出现 Matplotlib 检查 Qt 旧高 DPI 枚举的弃用警告；测试通过，未隐藏警告。
- 从仓库外目录用安装 wheel 运行 CLI 帮助、诊断命令和 Qt offscreen MainWindow；核实 Logo SVG 与默认 YAML 从 site-packages resources 正确载入，FIF 检查元数据返回 21 epochs、16 channels、1000Hz。诊断报告未包含信号样本/通道名，家目录路径已遮蔽。用 GUI `_load_history()` 实际打开上述真实 FIF 生成的保存连接运行，结果选择器出现 Connectivity，Logo 正常显示，无需重新计算或原始 FIF。
- 固定只读样例 `C:/Users/PC/Documents/ChatGPT/testdata/LID-T80_all_channels-epo.fif`，SHA-256 `2751bce6cdad2a17d7ba72978b0b59221f8265dd27d9c77a8e77600ed75a0582`；全程后复核一致。以 21 epochs、1000Hz、显式分组 `QC_Test_A/B`（仅质量验证，不声称生物区域映射）、同一记录的8通道计算 MIC、MIM、wPLI、dPLI、wPLI²-debiased；五种均完成，连接汇总 32,406 行，2–100Hz。记录12次主估计/秩敏感性/分段稳定性调用；重复 multitaper 日志对应这些有记录的诊断调用，不是只因改图例重复计算。结果包的 run manifest 为 `completed`，五方法列表和连接文件路径齐全；独立调用 `load_saved_run()` 成功读回参数/索引。未做组间或行为推断。
- 开发 `.venv` 的诊断报告识别出 `lfp_analysis` namespace 被 `luna-analysis` 与历史 `mouse-lfp-analysis` editable distribution 同时登记；当前实际导入文件仍指向本 checkout，隔离 wheel 安装仅一个 owner。本轮保留用户虚拟环境，不擅自卸载旧 distribution。

### 未验证与限制

- 没有其他电脑的真实报错/诊断 JSON，故远端功能连接故障根因尚未确认；本轮只能报告项目自身确认的版本兼容风险和本机已验证结果。
- 没有 macOS 设备；Apple Silicon 仅配置了尚未运行的 GitHub Actions smoke，macOS 原生安装、GUI、导入、计算、保存、重载均待验证。Intel Mac 未验证。Python 3.12 元数据允许但本地未测；当前真实运行是 Windows x64/Python3.11。
- Qt 仅 offscreen 验证，无真实鼠标、系统 DPI、多显示器检查。GitHub CI 由于本轮禁止推送，未触发。
- 真实样例无动物身份；QC 测试通道组不能替代正式脑区映射或任何生物学统计。
- 无分析公式/默认计算参数变化；未改 FIF，未 commit/push。干净环境、诊断 JSON 和分析结果均留在 `%TEMP%`。

## 2026-09-28 22:30 +08:00 — 合成连接端到端回归与 Intel macOS CI

### 修改

- 用户确认没有其他电脑或 Mac 的诊断报告；远端故障仍未归因，不把依赖风险或本机成功写成远端问题已解决。
- 新增 `tests/test_platform_workflow.py`：在临时目录生成有已知滞后结构、明确标记为合成数据的 FIF，调用 GUI 与批处理共用的 `run_gui_analysis()`，用明确的 `QC_A/QC_B` 通道映射测试 MIC、MIM、wPLI、dPLI、wPLI²-debiased，再从 run bundle 读取 manifest、参数、连接 CSV 和 NPZ。断言验证方法字段、频率坐标、epoch 数、输出数组长度与 CSV 一致；不进行动物推断，不使用真实动物/脑区标签。
- `.github/workflows/platform-smoke.yml` 新增独立 `macos-15-intel` runner；现有 `macos-15` 作为 Apple Silicon runner 保留。CI 安装声明的 `.[desktop,dev]` 后执行此端到端测试及完整测试集。
- 更新 `docs/DEPENDENCIES.md`、`docs/PROJECT_STATUS.md`、`docs/DEVELOPMENT.md` 和 `docs/HANDOFF.md`，区分已配置与已运行的平台证据，并记下当前无远程诊断报告的事实。

### 验证

- `.venv`：新端到端测试通过；全量 `pytest -o addopts= -q`：120 passed、1 个 FOOOF 上游弃用警告。Ruff、compileall、pip check 通过。
- 独立非 editable wheel 环境（Windows x64 / Python 3.11.9）：新端到端测试通过；全量 120 passed。另有 64 个 Matplotlib 检查 Qt 旧高 DPI 枚举的上游弃用提示和1个 FOOOF 弃用提示；没有屏蔽警告。Ruff、compileall 通过。
- 固定只读样例 `C:/Users/PC/Documents/ChatGPT/testdata/LID-T80_all_channels-epo.fif`：21×16×5000、1000 Hz，选8个实际通道名称并显式映射至 `QC_Test_A/B`（仅测试分组）。MIC、MIM、wPLI、dPLI、wPLI²-debiased 均返回；频谱 CSV 32,406 行，manifest `completed`，NPZ/CSV 和 `load_saved_run()` 可重载。源文件哈希前后均为 `2751bce6cdad2a17d7ba72978b0b59221f8265dd27d9c77a8e77600ed75a0582`。输出留在 `%TEMP%/luna-cross-platform-real-9i2ncjx9`。读取此较大 CSV 时 pandas 对 `estimated_rank_metadata` 报 `DtypeWarning`，文件仍成功读回；本轮未改结果表字段/类型契约。
- 新增端到端测试首次失败是因为测试错误假设 NPZ key 命名为 `frequencies_hz/spectrum`；检查 `_save_connectivity_npz()` 确认真实契约为逐行 `frequency_hz/value_raw/value_strength/method` 等，修正测试断言后合成与真实运行均通过。生产计算/保存算法未因此修改。
- 已查 GitHub 官方 runner 文档：`macos-15` 为 Apple Silicon arm64，`macos-15-intel` 为 x86_64。两者 workflow 尚未远端执行；本任务不 push。Windows 原生 GUI 已有先前 offscreen 和隔离环境证据，本轮未进行实体显示器/DPI人工操作。

### 限制

- 目前仍无目标电脑的诊断 JSON 或原始错误阶段，无法确认其特定故障根因。
- 没有本机 macOS；Intel 与 Apple Silicon 仅配置 CI runner，不能写成已通过 macOS。Python 3.12 也未在本机验证。
- 本轮只增补合成集成测试、CI 平台目标和文档；不改连接指标、参数或结果数值；不提交、不推送。真实输入、临时运行包不在仓库内。

## 2026-09-28 22:35 +08:00 — 仓库外诊断入口与脱敏复核

- 继续任务时用户确认没有其他电脑或 Mac 的诊断报告；因此目标电脑的具体故障原因依然未确认。本机诊断只能验证报告工具和已知安装环境，不能替代故障设备证据。
- 从独立 wheel 环境、当前仓库之外的临时工作目录运行 `python -m lfp_analysis.diagnostics --output <临时目录>/diagnostic.json --input <固定只读 FIF> --output-dir <临时目录>/results`。
- 命令成功；报告识别 Python 3.11.9/Windows AMD64，MNE-Connectivity 与 PyBispectra 导入状态为 `ok`；FIF 仅返回头信息（21 epochs、16 channels、1000 Hz），明确 `signal_samples_loaded=false`。自动检查报告 JSON 不包含本机 Documents/AppData 绝对路径，`privacy.signal_data_included=false`。
- 报告仅留在 `%TEMP%/luna-diag-audit-*`。未改分析代码/参数或真实文件；无其他机器与 macOS，原生安装/GUI/保存重开仍待在相应系统验证。没有提交或推送。

## 2026-09-28 22:42 +08:00 — 隔离 Qt 测试设置并复跑跨环境套件

- 新增的合成 FIF 端到端测试同时调用 `inspect_input_metadata()`，断言 FIF 头信息正确且不包含通道名、文件路径或信号样本载入状态；开发环境和独立 wheel 环境的该测试均通过。
- 并发运行两套 Windows 测试环境时，观察到开发环境 Qt 主窗口测试的 splitter 宽度断言失败一次；单独重跑通过。排查确认两个环境的 `QSettings("LUNA", "LUNA")` 都指向同一个 `HKEY_CURRENT_USER\Software\LUNA\LUNA` 注册表键，测试此前临时覆盖同一设置，足以解释并行时的竞争，但不证明产品 GUI 有运行时缺陷。
- 修正 `tests/test_gui.py`：只在该测试进程中把 GUI 模块的 QSettings 构造重定向到 `tmp_path/LUNA.ini`，不读写用户注册表；其他测试和软件运行时设置方式不变。开发与独立 wheel 环境同时重跑主窗口测试均通过，随后并行运行两套全量测试各 120 passed，竞争未再复现。
- 再次从仓库外临时目录运行独立 wheel 的诊断命令并传入固定 FIF；脱敏、只读取头信息及可写目录检查通过。输入样例未修改。
- 本轮没有连接算法或生产数据路径改动。CI 远端仍未触发；macOS 与 Python 3.12 仍没有本机执行证据。操作未提交/推送。

## 2026-09-28 22:50 +08:00 — 跨平台代码路径复核与安装包外部启动检查

- 用户再次确认没有其他电脑或 Mac 的故障诊断报告；远端故障归因仍保持“未确认”。
- 静态检查生产源码中的平台专属调用、盘符/反斜杠路径、用户目录写入、快捷键和资源定位：未发现 `os.startfile`、Windows 注册表/PowerShell/Explorer 调用或开发机绝对路径；GUI 使用 Qt `StandardKey`、`pathlib` 和包内资源定位。此项是代码检查证据，不等于 macOS 运行验证。
- 当前 Windows x64 / Python 3.11.9 再运行全量测试：120 passed、1 个 FOOOF 上游弃用警告；Ruff 与 `pip check` 通过。独立 wheel venv 从仓库外目录通过连接计算—保存—重载端到端测试及 `pip check`，且导入路径确认为安装目录中的 `site-packages/lfp_analysis`；Logo、默认 YAML 和 `luna-gui --help` 可从仓库外访问。
- 从当前环境生成固定只读 FIF 的脱敏诊断：MNE-Connectivity/PyBispectra 导入成功，头信息为 21 epochs、16 通道、1000 Hz，未加载信号样本。
- 当前桌面自动化未返回可访问的原生应用窗口，故本轮未进行鼠标级 GUI 操作；已有离屏测试不能替代原生 Windows 手动交互。macOS Apple Silicon/Intel、Python 3.12 和未推送的 GitHub Actions 仍未运行。
- 未改计算代码、参数、算法或真实文件；未提交/推送。诊断文件留在 `%TEMP%`。

## 2026-09-28 23:10 +08:00 — Python 3.12 干净安装与真实 FIF 连接回归

- 为验证 `pyproject.toml` 声明允许的 Python 3.12，使用临时隔离目录安装 Python 3.12.14 与独立工具，不改系统 Python、项目 `.venv` 或生产源码；从项目声明的 `.[desktop,dev]` 解析并安装 54 个包，无手工补装。
- `uv pip check` 通过。Python 3.12 环境从仓库根目录执行全量 pytest：120 passed；Ruff 0.16.9、compileall 均通过。测试出现 64 条 Matplotlib `AA_UseHighDpiPixmaps` 上游弃用提示和 1 条 FOOOF 弃用提示，未屏蔽。
- 首次从仓库外目录收集完整测试时，`test_analysis_help.py` 因测试导入仓库根下的 `scripts` 而无法收集；改从仓库根执行后全量通过。此为测试工作目录要求，不是安装包无法从外部启动（包导入位置确认在临时环境的 `site-packages`）。
- 固定只读 FIF 在 Python 3.12 环境中读取为 21 epochs、1000 Hz；基于实际通道名 `TETFP01–08` 明确建立仅用于验证的 `QC_A/QC_B` 分组，不推定生物脑区或动物身份。MIC、MIM、wPLI、dPLI、wPLI²-debiased 全部计算成功，Connectivity 状态 `ok`；保存的频谱 CSV 含五种方法，`load_saved_run()` 与 `load_saved_table()` 重载成功。输入 SHA-256 前后均为 `2751bce6cdad2a17d7ba72978b0b59221f8265dd27d9c77a8e77600ed75a0582`，输出留在 `%TEMP%`。
- 一次临时测试脚本最初把 GUI 的展示分组名 `Connectivity` 当作计算指标传入，结果只做文件检查而无 metric；核实 `gui_engine.run_gui_analysis()` 后改为传入真实指标 ID，再次运行通过。这不是 GUI 算法缺陷。保存谱 CSV 重载时 pandas 对混合类型元数据列给出 `DtypeWarning`，读取完整且方法/状态均正确，本轮未改变表字段契约。
- 更新依赖指南、项目状态、开发环境和交接文档，明确 Windows x64/Python 3.12.14 已验证。当前没有 macOS 主机、原生桌面窗口或外部诊断报告；macOS Apple Silicon/Intel、原生 GUI/DPI 和远端工作流仍未验证，不能归因用户电脑故障。未改算法、默认值或测试源数据；不提交/推送。

## 2026-09-28 23:16 +08:00 — macOS 目标依赖 wheel 解析检查

- 用户确认没有其他电脑或 Mac 的诊断报告；因此目标电脑上的连接模块故障阶段与根因仍不可确认。本轮继续本机可做的验证，不把本机通过等同于远端修复。
- 使用临时目录和隔离安装的 uv 解析器，对项目 `pyproject.toml` 中 `.[desktop,dev]` 依赖执行 `uv pip compile --only-binary :all:`，分别指定 `aarch64-apple-darwin`、`x86_64-apple-darwin` 与 Python 3.11、3.12。四种平台/版本组合均解析成功，每种目标52个发行包；示例后端版本包括 MNE-Connectivity 0.9.0、PyBispectra 1.3.2、PySide6 6.11.2、NumPy/SciPy、specparam/FOOOF。输出仅写入 `%TEMP%`，未修改锁文件或项目环境。
- 这只证明当前包索引状态下依赖元数据可解析且存在目标 wheel，不验证 macOS 二进制导入、Qt 图形插件、连接数值、保存重载、文件系统权限或 GUI。没有 Mac 主机，两个 macOS CI job 尚未触发。
- 复核 `pyproject.toml` 直接依赖与实际导入：核心 NumPy/SciPy/pandas/Matplotlib/PyYAML/MNE；功能连接独立 extra `mne-connectivity`（下限0.9）；TDE 为 `pybispectra`；参数化为 `specparam` 与兼容 FOOOF；桌面为 PySide6；开发为 pytest/Ruff；Notebook 为 JupyterLab/nbformat/ipykernel。netCDF4/xarray/scikit-learn、Numba/llvmlite/joblib、PySide6 子包由各后端元数据传递安装。`threadpoolctl` 仅用于可选线程池诊断，不是 LFP 核心分析依赖。安装说明已有这些依赖层级；未发现需要用户手动补装的必需传递包。
- 更新 `docs/DEPENDENCIES.md`、`docs/PROJECT_STATUS.md`、`docs/DEVELOPMENT.md`、`docs/HANDOFF.md`，区分 wheel 解析和实机运行证据。
- 本轮仅改文档，未改算法、参数、结果或真实数据；尚待运行 `git diff --check` 和文档状态核对。无 commit/push。

## 2026-09-28 23:35 +08:00 — 仅 GUI 安装的可选方法禁用回归

- 用户无其他电脑/Mac诊断报告；目标机器的具体连接故障仍未确认。本轮从最小安装场景继续验证依赖缺失的隔离行为。
- 先在独立 Windows x64/Python 3.12.14 环境按 `.[gui]` 安装、未安装 MNE-Connectivity、PyBispectra、specparam、FOOOF。实际创建 offscreen `MainWindow`，确认连接 MIC、TDE 被禁用但 PSD可用；复核发现 FOOOF 复选框仍启用，尽管两个后端都不存在。这是本机代码确认和真实 GUI 控件复现的缺陷，不是远端故障根因。
- 修复 `optional_dependencies.py`：FOOOF可用性按配置后端检查；明确 `fooof` 时不以 specparam 替代，默认 `specparam` 仅在其不可用时接受已有兼容 FOOOF 后端；两个后端都缺失或 API 导入异常时提供 `.[parameterization]` 提示。`gui.py` 在 FOOOF 控件创建及载入预设时调用同一检查，禁用不可用选项。
- 新增依赖解析测试，覆盖两个后端均缺失、单独 specparam、兼容 FOOOF 后端、及显式 fooof 不被 specparam 取代；新增 GUI 按参数配置传递后端的回归测试。更新 README 与依赖/状态/交接文档，解释后端关系、控件禁用与结果警告字段。
- 在修订代码重新安装到隔离 `.[gui]` 环境后，`uv pip check`通过；从安装目录启动 offscreen GUI、打开固定只读 FIF 成功，识别21 epochs、16通道、1000 Hz；FOOOF、MIC、TDE均 disabled且PSD enabled。输入源 SHA-256 前后相同：`2751bce6cdad2a17d7ba72978b0b59221f8265dd27d9c77a8e77600ed75a0582`。首次检查脚本误用未随 uv venv 提供的 `python -m pip`；改为 `uv pip check --python` 后通过，此为验证命令修正。
- 当前开发 `.venv` 中 `tests/test_app_paths.py`、`tests/test_optional_methods.py`、`tests/test_gui.py` targeted suite 通过；FOOOF上游弃用警告保留。Ruff及compileall通过；全量测试和最终差异检查待本次源码/文档更新后复跑。
- 未修改连接/参数化科学计算、默认值、FIF或算法结果；无 commit/push。Mac原生安装/运行与目标故障设备仍未验证，需后续 CI 或设备报告。

## 2026-09-28 23:43 +08:00 — 可选依赖隔离下的 GUI PSD 保存重载与关窗回归

- 以修订源码重装 Windows x64/Python 3.12.14 临时 `.[gui]` 环境；未安装 mne-connectivity、pybispectra、specparam、fooof。`uv pip check` 通过。offscreen GUI 使用固定只读 FIF，成功识别21 epochs、16通道、1000 Hz；设置仅 PSD 后，经 MainWindow 后台线程完成分析，Quality/PSD 相关 manifest 状态 completed，逐epoch/通道 PSD CSV 67,200行且含 `frequency_hz`、`psd_value`；`load_saved_table()` 和 `load_saved_run()` 重载通过。FOOOF/MIC/TDE在界面禁用，PSD保持可用。
- 首次生命周期回归在已成功计算和重载后关闭窗口，复现 `RuntimeError: Internal C++ object (QThread) already deleted`。`load_paths()` 的 `finished` 信号触发 `deleteLater()`，但 MainWindow 仍保有 `inspect_thread` Python wrapper；`closeEvent()` 未先用 Shiboken 验证 C++ 对象有效就调用 `isRunning()`。该结论由真实 offscreen GUI 运行复现，并在 `gui.py` 加入 `shiboken6.isValid()` 防护；分析线程、检查线程和 worker 均先校验对象有效性。新增已删除 QThread wrapper 的回归测试，针对性3项通过；同一真实 GUI 计算/保存/重载/关窗流程随后全通过。
- 两次分析验证脚本首次的列名假设使用 `power`，而真实契约字段为 `psd_value`；据结果文件字段修正断言后验证通过。此为测试脚本错误，不是计算或保存失败。固定 FIF 哈希前后均为 `2751bce6cdad2a17d7ba72978b0b59221f8265dd27d9c77a8e77600ed75a0582`；输出留在 `%TEMP%`。
- 本轮最终 `.venv` 全量 pytest 123 passed、1个 FOOOF 上游弃用警告；Ruff、compileall、pip check、git diff --check 均通过（Git有工作区 LF/CRLF 提示）。算法、参数、结果定义未变；未 commit/push。
- macOS 实际安装、Qt原生GUI、连接计算及项目迁移仍没有运行证据；其他电脑也没有诊断报告，远端具体故障根因仍未确认。本轮不宣称跨平台验收完成。

## 2026-09-28 23:55 +08:00 — 跨平台 CI 显式启用 Qt 回归与 GUI 安装流程 smoke test

- 继续在无其他电脑/Mac诊断报告的前提下进行本机验证；远端连接故障的具体设备环境和根因仍未知。
- 代码检查发现 `.github/workflows/platform-smoke.yml` 设置了 `QT_QPA_PLATFORM=offscreen`，但 `tests/test_gui.py` 的4项窗口测试在 `CI=true` 时无条件跳过。调整为仅在 CI 且没有 `LUNA_RUN_QT_TESTS=1` 时跳过，并在跨平台工作流显式启用该开关。
- 新增合成 FIF GUI 集成回归：隔离临时应用目录和 QSettings → MainWindow 异步导入 → GUI 运行 PSD → 验证 manifest/表格文件保存 → 新 MainWindow 通过“载入历史”恢复结果。输入与输出均为临时合成测试文件，不涉及真实实验数据。测试首次断言沿用了不适用的 `save_status` 字段；依据当前 manifest 契约改为验证 `status=completed`、表格文件存在及历史结果成功载入，产品保存格式未修改。
- 本机执行新集成测试：1 passed。随后设置 `CI=true`、`QT_QPA_PLATFORM=offscreen`、`LUNA_RUN_QT_TESTS=1` 执行完整测试：124 passed，1个 FOOOF 上游弃用警告。此次覆盖的是 Windows x64/Python 3.11 本机 offscreen，不等于 macOS runner 结果或原生 GUI 交互。
- 更新 `docs/DEPENDENCIES.md`、`docs/DEVELOPMENT.md`、`docs/HANDOFF.md`、`docs/PROJECT_STATUS.md`，说明 CI Qt 测试实际覆盖以及 Mac/远端 CI 尚未执行的限制。
- 本轮没有改变连接算法、科学参数或结果格式；未提交/推送。后续仍需远端 GitHub matrix（含 macOS arm64/Intel）和真实 Mac 安装/运行证据；目标用户故障若要定因，仍需失败机器的脱敏诊断报告或完整错误信息。

## 2026-09-29 00:00 +08:00 — 跨平台调用面扫描与 macOS runner 生命周期核对

- 对 `src/lfp_analysis`、`scripts`、测试及 CI 配置执行平台专属调用扫描。生产路径中未发现 `os.startfile`、Windows 注册表/PowerShell/Explorer 启动、硬编码开发机绝对路径、fork 依赖或 Windows 专属进程标志；发现的盘符路径只存在于启动脚本示例/测试样本，平台目录常量集中在 `app_paths.py`。这是静态检查结论，不替代 Mac 运行。
- 浏览 GitHub 官方 runner-images 文档，确认现有 CI 标签：`macos-15` 为 arm64，`macos-15-intel` 为 x86_64；官方公告计划 Intel 标签提供至2027年8月。将架构和生命周期提示加入 `docs/DEPENDENCIES.md` 与 `docs/PROJECT_STATUS.md`，并添加官方来源链接。
- 文档修改通过 `git diff --check`；没有代码或分析行为变化，未重跑数值测试。尚无 macOS 主机、远端工作流运行结果或其他故障电脑诊断报告；因此仍无法确认目标电脑的具体连接失败原因，亦不能宣称 Mac 安装/运行已通过。未提交/推送。

## 2026-09-29 00:09 +08:00 — 诊断入口与 PySide6 API 误报修复

- 用户确认没有其他电脑或 Mac 的诊断报告；没有新增外部根因证据，本轮继续验证本机诊断能力和依赖说明，不把本机结果推广为远端已修复。
- `.venv` 元数据列有 `luna-diagnose` 入口但启动脚本原先缺失。仅对当前 `.venv` 执行 `python -m pip install --no-deps -e .` 后，console launcher 出现并可从 `%TEMP%` 成功运行；没有安装/升级依赖。`python -m lfp_analysis.diagnostics` 仍是无需console launcher的替代入口。该现象属于本地editable安装不一致，不是已确认的源代码跨机故障。
- 实际报告把能正常 `from PySide6 import QtCore, QtWidgets` 的 PySide6 6.11.2 误报为 `api_missing`：诊断器错误地检查 `PySide6.QtCore`、`PySide6.QtWidgets` 是否为包顶层属性。本轮将 API 检查改为子模块中的 `QtCore.QObject` 与 `QtWidgets.QApplication`，添加正常API及缺失符号两项回归，并以真实诊断报告确认状态 `ok`。
- 固定只读 FIF 通过console入口仅读头信息：21 epochs、16 channels、5000 samples/epoch、1000 Hz；报告不含通道名或信号样本。SHA-256 前后未变。依赖 AST 审计覆盖生产 `src/` 与 `scripts/` 顶层 imports，没有发现未声明的直接第三方依赖；`shiboken6` 由 PySide6 传递安装，`threadpoolctl` 是可选诊断工具，其余连接/TDE/参数化包在独立 extra 中。更新 `docs/DEPENDENCIES.md` 的安装入口恢复和重复 namespace 处理说明。
- `.venv` 全量测试：126 passed，1项 FOOOF 上游弃用警告；针对性诊断/可选方法测试17 passed；Ruff、compileall、pip check、`git diff --check` 均通过。真实连接值未重算，算法及默认参数未改变。
- 诊断报告仍显示 `lfp_analysis` 有 `luna-analysis` 与 `mouse-lfp-analysis` 两个元数据 owner；进一步只读核实二者的 editable `direct_url` 都指向当前工作区，`lfp_analysis` 也从当前仓库 `src/` 加载。这是旧发行名遗留的本机元数据/入口冲突风险，不证明运行了错误代码；因两个发行包共用脚本入口，本轮未擅自卸载。依赖指南建议来源不明时用干净虚拟环境重装。
- 无 Mac 主机、GitHub CI结果或故障设备报告，macOS运行和远端连接故障根因仍待证。未提交/推送。

## 2026-09-29 00:30 +08:00 — 连接性合成自检与安装说明收尾

- 用户确认没有其他电脑或 Mac 的诊断报告；目标设备的连接故障仍无法定因。本轮增加不依赖 GUI、也不读取研究信号的 `--self-test-connectivity` 选项：以固定随机种子的合成 epochs 调用 LUNA 连接计算核心，逐方法记录状态、失败阶段、频率范围、实际秩、估计调用数和耗时；依赖缺失与数值调用失败分别报告，失败时命令非零退出。诊断 JSON 不包含合成信号样本。补充测试覆盖全方法执行、缺依赖状态及失败退出码。
- 在本机 Windows x64/Python 3.11.9 通过已安装的 `luna-diagnose` 入口从仓库外运行；MIC、MIM、wPLI、dPLI、wPLI²-debiased、imcoh、coh 均成功。验证样本为 6×4×3000 合成数据，500 Hz，multitaper、5–80 Hz；451个频率点、3次估计调用，约3秒。随同指定真实 FIF 参数运行时仅读头信息，21×16×5000、1000 Hz；原文件 SHA-256 前后相同。
- 依赖说明继续明确 MNE-Python 与 MNE-Connectivity 是不同发行包、应安装 `.[connectivity]`（或 `.[desktop]`/`.[all]`）；README 增加可复制的合成自检用途提示。对照本机安装包的 distribution metadata 和官方安装文档复核依赖：MNE-Connectivity 的 `netCDF4`、`xarray`、scikit-learn、`tqdm`，PyBispectra 的 Numba/llvmlite、joblib、scikit-learn 等均由声明的可选 extra 传递解析；直接依赖审计未发现其他遗漏。用户无需手工猜装这些子依赖。
- 验证：`tests/test_diagnostics.py` 6项通过；全量 `CI=true QT_QPA_PLATFORM=offscreen LUNA_RUN_QT_TESTS=1 python -m pytest` 129项通过，保留1项 FOOOF 上游弃用警告；Ruff、compileall、pip check、git diff --check 通过。未改变连接算法、频谱参数或结果契约；未提交/推送。
- 限制：合成自检证明本机当前 Python 环境中的依赖/API/调用链可运行，不证明方法科学准确，也不能代替目标电脑上的真实输入诊断。没有 macOS 主机；Apple Silicon、Intel macOS 安装/GUI/数据流、GitHub macOS runner 仍未实际运行。若将来要定因目标设备故障，需在故障环境运行脱敏诊断并提供 JSON 或完整错误栈。

## 2026-09-29 00:40 +08:00 — 当前源码 wheel 的仓库外安装检查

- 用项目 `pyproject.toml` 构建当前 `0.3.0.dev1` wheel，临时安装后从仓库外确认 `lfp_analysis` 由临时安装位置加载，包内 LUNA Logo SVG 和默认 YAML 存在可读，`luna-diagnose` 命令帮助与七方法合成连接自检均成功。该临时安装复用了本机 Windows 虚拟环境中已有的科学计算依赖；不是全新依赖环境，也不代表 macOS wheel/runtime 已验证。
- 首次验证使用 `pip --target` 时发现此安装模式未在目标目录生成 console wrappers；改用临时 `--prefix` 后入口运行成功。该 prefix 调用曾令 pip 移除当前 `.venv` 的 LUNA console launchers；立即通过当前解释器 `python -m pip install --no-deps -e .` 重新生成。复核 `luna-diagnose.exe` 存在且 `pip check` 无依赖问题。此为本次验证的临时副作用，已恢复；无数据、源码或 Git 历史被删除。
- 当前源码 wheel SHA-256=`ac3866c3ca79a337cef58666e7ea46b6ebe71b454ce2859a3b5ac0ecdc9586df`；wheel、临时安装和无信号样本的诊断报告留在 `%TEMP%/luna-wheel-check-b86172d02eb54778b3317b4fbca3b1d0`，未写入仓库。
- 恢复后的 `.venv\Scripts\luna-diagnose.exe` 从 `%TEMP%` 再次运行，并附上 AGENTS 指定的只读 FIF。报告显示七种合成连接方法状态均为 `ok`；FIF 元数据为21×16×5000、1000 Hz，`signal_samples_loaded=false`、未包含通道名。源文件 SHA-256=`2751bce6cdad2a17d7ba72978b0b59221f8265dd27d9c77a8e77600ed75a0582`，与既有基线一致。

## 2026-09-29 00:46 +08:00 — wheel 的全新 Windows 桌面依赖安装验证

- 使用上一项构建的当前源码 wheel，在新建于 `%TEMP%` 的 Windows x64/Python 3.11 venv 中只安装 wheel 的 `.[desktop]` extra；没有安装开发机其他包或手动补依赖。解析版本包括 MNE 1.13.2、MNE-Connectivity 0.9.0、PyBispectra 1.3.2、PySide6 6.11.2、NumPy 2.4.6、SciPy 1.17.1。`pip check` 无冲突。
- 在仓库外执行安装版 `luna-gui --help`、`luna-diagnose --self-test-connectivity`，七种连接方法状态全为 `ok`；在 `QT_QPA_PLATFORM=offscreen` 下实例化已安装 wheel 的 `MainWindow`，确认窗口可显示并可正常关闭，QSettings/输出路径放在临时测试目录。该检查不覆盖实际显示器鼠标/DPI，也没有在该环境对真实样例运行 GUI 分析。
- 临时 venv 和结果均留在 `%TEMP%`，未写入仓库。此项加强了 Windows wheel/声明依赖可复现性证据；macOS arm64/Intel 的安装、GUI、真实 FIF 计算/保存/重开仍未实机验证，目标外部电脑故障根因也仍未知。未提交/推送。

## 2026-09-29 00:47 +08:00 — 将独立连接诊断加入平台 CI matrix

- `.github/workflows/platform-smoke.yml` 现显式执行 `python -m lfp_analysis.diagnostics --self-test-connectivity`，在每个配置的 Windows x64、macOS arm64、macOS Intel 与 Python 3.11/3.12 runner 中，以合成数据逐一探测七种 MNE-Connectivity 调用；失败会以非零退出使相应 job 失败。原有全量 pytest、合成计算保存重载、GUI offscreen 与资源入口检查仍保留。
- 此为后续远端运行的自动化覆盖，不代表当前 CI 已运行；本轮没有 push，macOS runner 仍无结果。本机现有 wheel 的完整桌面 extra 验证已记录于上一节。

## 2026-09-29 00:53 +08:00 — 干净 wheel 环境的真实 FIF 连接保存/重载

- 在 Windows x64/Python 3.11 全新 `%TEMP%` venv（从本项目 wheel 安装 `.[desktop]`、无手工依赖补装）中，用 AGENTS 固定只读 FIF 运行 `gui_engine.run_gui_analysis()`。分析输入21 epochs、16通道、5000点/段、1000 Hz；本次仅选8通道，按实际通道名将前4个与后4个临时映射至 `QC_A/QC_B`，选全部21段与一个无向计算脑区对。该映射仅为数值后端冒烟测试，不代表M1/STR等生物脑区；样例动物/session身份仍未解析。
- 使用单worker multitaper配置（2–100 Hz、4 Hz带宽）计算MIC、MIM、wPLI、dPLI、wPLI²-debiased。run manifest=`completed`，Connectivity=`ok`；表内五个方法均存在、频率/数值列有效，连接频谱CSV 32,406行、有效epoch=21。`load_saved_table()` 与 `load_saved_run()` 重载通过。输出仅写入 `%TEMP%/luna-clean-real-connectivity-*`。真实FIF SHA-256仍为 `2751bce6cdad2a17d7ba72978b0b59221f8265dd27d9c77a8e77600ed75a0582`。
- 首轮后置断言先后把GUI指标标签大写别名当成保存表规范值、又假设manifest存在 `n_epochs_selected`；检查实际契约后将方法名称规范化为小写并使用 `n_epochs`/`n_channels` 字段，已保存结果上的全部核验通过。计算及保存本身两次都成功，未因断言失配重跑。CSV重载时pandas对 `estimated_rank_metadata` 发出混合类型 `DtypeWarning`；抽样检查确认该列在可用估计行保存JSON文本，其余行为空值，读入类型为object、其余为NaN，连接结果读取及数值核验成功。该警告未屏蔽、未修改保存字段。
- 本轮提高了 Windows clean-install + 真实数据计算/重载的证据强度，但不能证明目标用户电脑已修复，也不能替代 macOS 运行。没有 Mac 或外部诊断报告；未改科学算法、未提交/推送。

## 2026-09-29 01:00 +08:00 — 安装版 wheel 全量回归

- 在同一全新 Windows x64/Python 3.11 venv 安装 `.[desktop,dev]` 后运行完整测试套件，并核对 `lfp_analysis` 从该 venv 的 `site-packages` 加载，而不是从仓库 `src/` 导入。结果：129 passed，81 warnings，28.82 s；警告为 Matplotlib Qt 高 DPI 枚举弃用和 FOOOF 上游弃用，未屏蔽。
- 同环境此前已通过 `pip check`、仓库外 CLI/诊断入口、七种连接方法合成自检、offscreen 主窗口生命周期，以及固定只读 FIF 的五种 GUI 连接方法计算/保存/重载。此新增全量测试仅验证 Windows wheel 安装环境，不是 macOS 或外部故障机运行证据。
- 仅更新验证文档；未修改分析实现、算法或结果。无 Mac/其他电脑诊断报告，远端根因未确认；未提交/推送。

## 2026-09-29 01:04 +08:00 — 平台 CI 保留脱敏诊断附件

- 复核 `.github/workflows/platform-smoke.yml` 后确认：矩阵任务已执行常规环境诊断和合成连接自检，但任务结束后没有保留两个 JSON 报告，未来失败时不便下载对照。增加 `always()` 运行的 `actions/upload-artifact@v4` 步骤，按 OS/Python 命名并保留7天；找不到报告时仅警告，不覆盖测试失败状态。
- 报告由诊断器脱敏，不含信号样本；第二份只包含合成连接自检的状态、形状和参数。PyYAML 成功解析 workflow，并断言 artifact 名称、`always()`、七天保留期及两个报告路径正确。此改动不会触发远端任务，也不代表 Mac 已验证。
- 未改变科学代码、参数、结果契约或依赖。没有其他电脑/Mac 报告；未提交/推送。

## 2026-09-29 01:08 +08:00 — 核心安装缺少可选后端时的诊断回归

- 在 `%TEMP%` 新建 Windows x64/Python 3.11 隔离 venv，仅安装当前 wheel（核心依赖，没有 GUI 或可选分析 extras），用户目录重定向到同一临时根目录；未修改开发环境。
- 安装版 `python -m lfp_analysis.diagnostics` 在没有 PySide6/MNE-Connectivity 时正常写出报告，断言两者为 `not_installed` 且不含信号样本。安装版 `--self-test-connectivity` 明确返回 `dependency_unavailable`、`install_extra=connectivity`，并以退出码2告知测试未运行成功；`pip check` 无依赖冲突。
- 这确认最小安装的诊断入口不依赖 GUI，且缺依赖不会伪报成功；不等于连接方法运行成功，也不是 macOS/外部故障电脑验证。输出报告和隔离环境仅在 `%TEMP%`，未读取实验数据。
- 当前源码回归：`tests/test_diagnostics.py` 与 `tests/test_platform_workflow.py` 共8项通过；Ruff、compileall、`pip check` 和 `git diff --check` 通过。另用 PyYAML 解析平台工作流并断言诊断 artifact 步骤条件/路径/保留期正确。Git 的 LF→CRLF 消息是工作区行尾提示，不是 diff 校验失败。

## 2026-09-29 01:30 +08:00 — Windows 项目路径在 POSIX 系统的兼容修复

- 代码确认此前多个持久化路径直接使用 Windows `str(Path)`：项目内 FIF 的 `data_units.source_path`（旧项目）、层级 `relative_path`、SQLite `analysis_runs.result_path`、结果 manifest 的表/数组相对路径、GUI run manifest 的 `file_dir` 与图表/表格路径。Windows 项目复制到 macOS 后，原始数据、树节点目录或保存结果会按带反斜杠的单个名称查找。此为已确认的跨平台缺陷，不足以认定它就是用户所述远端连接失败根因。
- 新增 `src/lfp_analysis/portable_paths.py`，统一解析旧 Windows/POSIX 相对路径并在解析后校验目标仍位于指定根目录；拒绝盘符绝对路径、UNC、`..` 与逃逸 symlink。新写入路径统一使用 POSIX `/`。扩展项目存储、批次索引、结果 manifest/API、GUI 历史加载和项目树显示；比较模块仅作为历史兼容代码，同样经安全解析。
- 回归测试：旧 Windows SQLite result path + 旧 Windows manifest table/array path 在复制到含空格的新项目目录后可由 `ProjectResults` 读表/读数组；旧反斜杠项目层级可加载且模板增量创建到正确节点；run manifest 旧 `file_dir` 正确解析并阻止绝对路径/目录穿越。
- 固定只读 FIF 验证：创建临时项目并将样例复制入 `data/raw/`，把 SQLite `source_path` 和层级 `relative_path` 模拟为旧 Windows 分隔符，复制整个项目到另一条含空格路径后重载 FIF；读取21×16×5000，采样率1000 Hz，源 SHA-256 未改变。首次临时 smoke 脚本在旧路径模拟语句中报错，调整为参数化更新后重跑成功；没有触及产品输入或代码数据。输出目录已清理。
- 最终验证：`CI=true QT_QPA_PLATFORM=offscreen LUNA_RUN_QT_TESTS=1 .venv/Scripts/python.exe -m pytest` 为132 passed、1项上游 FOOOF deprecation warning；`ruff check src tests scripts`、`compileall -q src tests scripts`、`pip check`、`git diff --check`通过。未修改连接算法、频谱参数、指标或结果数值。
- 另运行 `python -m lfp_analysis.diagnostics --self-test-connectivity`；本机七种方法 MIC/MIM/wPLI/dPLI/wPLI²-debiased/imcoh/coh 状态均为 `ok`，6×4×3000、500 Hz 合成数据，5–80 Hz、multitaper、单 worker；无原始信号写入报告。诊断仍提示当前开发环境有两个发行元数据 owner（`luna-analysis` 与旧 `mouse-lfp-analysis`），模块实际位置仍在当前工作区；此前隔离 wheel 环境仅有一个 owner，未擅自卸载本机旧元数据。
- 额外执行 `ruff check .` 时唯一报告是既有 `notebooks/01_single_file_workflow.ipynb` cell 的导入排序；该 notebook 与本任务无关且未修改。项目文档约定的生产/测试/脚本范围 `ruff check src tests scripts` 通过。
- 无原生 macOS 环境、尚无已运行的 GitHub macOS CI、无外部电脑诊断报告。已解决“项目内部 Windows 路径移动到 POSIX 后失效”的代码问题；用户所述连接故障仍需故障设备的脱敏报告或完整堆栈才能定位。未 commit/push。

## 2026-09-29 01:44 +08:00 — 最新工作区 wheel 安装回归

- 使用当前工作区（含未提交修改）重新构建 `luna_analysis-0.3.0.dev1` wheel，并在 `%TEMP%` 新建 Windows x64/Python 3.11 venv，仅安装 wheel 的 `.[desktop,dev]`；不手工补依赖。隔离环境 `pip check` 通过，导入位置确认是该 venv 的 `site-packages`。
- 从仓库外运行安装版 `luna-diagnose --self-test-connectivity`，MIC、MIM、wPLI、dPLI、wPLI²-debiased、imcoh、coh 七项均完成；随后以仓库为 pytest 工作目录（使测试可导入仓库脚本辅助包，但被测 `lfp_analysis` 仍来自隔离 wheel）执行全量套件，132项全部通过。初次尝试从 `%TEMP%` 直接启动 pytest 时仅因测试文件导入仓库 `scripts` 辅助包而在收集阶段失败；按项目测试工作目录重跑后通过，不是 wheel 运行故障。
- 同一隔离 wheel 环境对固定只读 FIF 运行 GUI 分析核心的实际连接计算、保存和重载：21 epochs、16个输入通道、1000 Hz，本次显式选取8通道并临时标为 `QC_A/QC_B`（仅用于软件验证，不是生物学分区），运行五种主要方法，连接状态 `ok`，长表32,340行，重新载入同一 run 成功。输出和诊断报告只写入 `%TEMP%`；保留并记录 CSV 混合类型 `DtypeWarning`，未屏蔽。
- 全过程未修改分析源码、算法、参数或默认值，固定 FIF 未修改。Windows wheel 当前工作区安装及连接链路的验证证据增强；macOS Apple Silicon/Intel、远端 CI、实际故障电脑仍未验证。没有其他电脑诊断报告，因此原始跨电脑连接故障的特定根因仍未知。未提交/推送。

## 2026-09-29 01:55 +08:00 — 诊断报告路径脱敏回归与 Python 3.12 wheel 验证

- 对当前安装版诊断 JSON 做隐私检查时确认：原逻辑先把 Windows 用户目录替换成波浪号，使后续绝对路径清理无法匹配，故可能泄露其下的项目/数据文件夹名称；诊断字段 invoked_as 也曾保留 launcher 的完整安装路径。修复为先清除完整 Windows/UNC/POSIX 绝对路径，并仅报告启动器 basename；路径边界规则避免把 https:// 误认成盘符路径。
- 新增脱敏回归，覆盖 Windows 路径、含空格 POSIX 路径、根级临时目录路径、URL 保持和 launcher basename。首次测试发现 URL 被过宽匹配，增加独立盘符边界后 tests/test_diagnostics.py 10项通过。
- 修复后 .venv 全量测试：136 passed、1项 FOOOF 上游弃用警告（28.90秒）；Ruff、compileall、pip check 与 git diff --check 通过。指定只读 FIF 的诊断仅读取文件头，21×16×5000、1000 Hz，报告不含输入路径/文件名、通道名或样本；源 SHA-256 仍为 2751bce6cdad2a17d7ba72978b0b59221f8265dd27d9c77a8e77600ed75a0582。同一报告中的七种合成连接方法均为 ok。
- 重新构建包含此次脱敏修复的 wheel（SHA-256 2e26ab04ab4727cf198a986fd9febc44bfabde4b1aafe3b61cc1121d41593f12）。Windows x64/Python 3.11.9 隔离 wheel 环境的诊断专项10项通过；安装入口对固定 FIF 头信息检查和七方法合成自检通过，报告仅写入 %TEMP%。另在短路径 Windows x64/Python 3.12.14 隔离 venv 安装同一 wheel 的 .[desktop,dev]，pip check 和完整136项测试通过（81条 Qt/FOOOF 上游弃用警告，30.87秒），模块从该 venv 的 site-packages 加载；再用 Python 3.12 安装版 console launcher 对同一只读 FIF 运行文件头诊断及七方法合成自检，输入隐私断言全部通过。
- Python 3.12 首次安装测试放在过深的临时目录时，Qt 包解压遇到 Windows 路径长度导致的文件不存在错误；将隔离环境移到短临时路径后完整安装成功。这是验证目录长度问题，不是 LUNA 运行/算法失败。
- 仅修改诊断脱敏与测试/文档，没有改变连接算法、依赖范围、科学参数或结果格式。无原生 macOS、无已运行的远端 CI，也没有故障电脑诊断报告；因此目标电脑连接故障根因仍未知，未提交/推送。

## 2026-09-29 02:02 +08:00 — Python 3.12 最新 wheel 的固定 FIF 连接重载

- 在 Windows x64/Python 3.12.14 最新 wheel 的隔离环境中，使用固定只读 FIF 通过安装包的 gui_engine.run_gui_analysis() 运行实际连接计算，再从已保存 bundle 重载连接长表与 run。依赖解析版本包括 NumPy 2.5.3、SciPy 1.18.1、MNE 1.13.2、MNE-Connectivity 0.9.0、PySide6 6.11.2；pip check 此前通过。
- 输入21 epochs、16通道、5000 samples/epoch、1000 Hz；此兼容性测试选取前8个实际通道、全部21 epochs，并以四通道 QC_A / 四通道 QC_B 作软件测试分组，不能解释为解剖脑区。MIC、MIM、wPLI、dPLI、wPLI²-debiased 均在频谱输出中存在，连接状态 ok、manifest completed；32,340行频谱表及run重载通过。输出位于 %TEMP%。
- pandas 在重载含稀疏JSON元数据的表列时仍报告 DtypeWarning；该列读取与数值核查成功，原警告保留。本轮未修改算法、参数、输入或保存契约；这仅补强 Windows Python 3.12 实际数据证据，不替代 macOS 原生运行或目标故障机器诊断。未提交/推送。

## 2026-09-29 02:07 +08:00 — 本机跨平台检查收尾（无外部诊断报告）

- 用户确认目前没有其他电脑或 Mac 的诊断报告；这不妨碍本机验证，故继续完成本地检查。`wsl.exe --list --quiet` 显示本机未配置可用 WSL Linux 发行版，本轮不安装/更改系统组件。
- 使用项目 `.venv` 运行 `tests/test_platform_workflow.py`、`tests/test_diagnostics.py`、`tests/test_optional_methods.py`：26 passed，1 项 FOOOF 上游弃用警告。`ruff check src tests scripts`、`compileall -q src tests scripts`、`pip check` 与 `git diff --check` 均通过；Git 的 LF/CRLF 提示仅为行尾转换提醒。
- 对平台用户目录和项目/结果路径再运行 `tests/test_app_paths.py`、`tests/test_project_store.py`、`tests/test_gui_engine.py`：32 passed。依赖文档中平台验证表的旧“120测试”计数已更新为当前工作区 Windows Python 3.11/3.12 各136项全量通过，并明确 Qt offscreen 不能代表 macOS 或实体桌面验收。
- 跨平台审计再次搜索 production 源码中的平台专属启动/注册表调用、硬编码盘符和文件分隔符；除启动脚本中的路径格式示例、平台目录分支与兼容路径解析逻辑外，未找到 `os.startfile`、PowerShell、Explorer 或其他 Windows 专属运行调用。依赖指南的验证表仍写旧的120项测试数，已按当前工作区最新证据更正为 Python 3.11/3.12 各136项，并保留“Windows Qt offscreen，不代表 macOS”的限定。
- 再运行无 GUI 的合成连接诊断，MIC、MIM、wPLI、dPLI、wPLI²-debiased、imcoh、coh 全部为 `ok`；6×4×3000 合成输入、500 Hz、5–80 Hz、multitaper、单 worker；451 个频率点、3 次估计调用。诊断报告位于 `%TEMP%\luna-connectivity-selftest-20260929.json`，声明未包含信号样本。未把合成软件烟测当作科学准确性或外部电脑验证。
- 复核官方平台依据：GitHub runner 清单当前区分 `macos-15`（arm64）和 `macos-15-intel`（x64）；Qt for Python 支持的 macOS 架构包含 arm64 与 x86_64；MNE 官方文档说明连接功能位于独立的 `mne-connectivity` 包。参考：[runner labels](https://github.com/actions/runner-images/blob/main/README.md)、[Qt supported platforms](https://doc.qt.io/qtforpython-6/overviews/qtdoc-supported-platforms.html)、[MNE Connectivity installation](https://mne.tools/mne-connectivity/dev/install.html)。
- 未改算法、依赖、默认参数或结果格式；没有原生 macOS/Intel Mac/Apple Silicon、远端 GitHub Actions 执行，也没有故障设备堆栈，因此 macOS 实际运行与用户报告的连接错误根因仍未确认。未提交/推送。

## 2026-09-29 09:01:01 +08:00 — v0.3.0-dev2 发布准备

- 范围：整理 `v0.3.0-dev1` 之后的可选依赖诊断、安装入口、跨平台路径、GUI/连接健壮性、CI smoke workflow、帮助文档和回归测试；未修改科学算法、默认谱估计参数、原始 FIF 或实验结果。
- README：补充当前版本、安装/启动/诊断边界、活动 Python 导入路径检查、项目流程和文档索引，明确 Windows 已验证范围与 macOS/原生桌面未验证边界。
- 版本：源码版本更新为 `0.3.0.dev2`，拟创建新的 Git 标签 `v0.3.0-dev2` 和 GitHub prerelease，不移动已有标签。
- 验证：`CI=true QT_QPA_PLATFORM=offscreen LUNA_RUN_QT_TESTS=1 .venv/Scripts/python.exe -m pytest -q` 为 136 passed；Ruff、compileall、pip check、git diff check 通过。固定只读 FIF 诊断成功读取 21×16×5000、1000 Hz 头信息，七种合成连接方法均返回 ok，报告不含信号样本或用户路径。
- 约束：本机实际验证为 Windows x64；macOS 原生安装/运行、远程 GitHub Actions、实体桌面鼠标/DPI、多显示器和故障电脑连接根因仍未确认。`docs/screenshots/`、真实数据、结果和临时诊断报告不纳入提交。
