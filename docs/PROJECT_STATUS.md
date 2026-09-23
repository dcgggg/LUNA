# LUNA 当前项目状态

最后核查：2026-09-22。以下状态只依据当前工作区代码、当前虚拟环境和本次实际运行结果；未把旧需求、历史截图或未执行的人工操作记为通过。

## 总体状态

| 项目 | 当前状态 | 证据/限制 |
|---|---|---|
| 软件版本 | `0.3.0.dev0` | 未发布开发版本；版本来源为 `src/lfp_analysis/__init__.py`，`pyproject.toml` 使用动态版本 |
| GUI 框架 | PySide6 + Matplotlib | `scripts/run_gui.py` → `lfp_analysis.gui.launch()` → `MainWindow` |
| CLI | 可用 | `lfp-analysis.exe` 和 `python -m lfp_analysis.cli --help` 已核实；当前环境没有 `luna.exe` 别名 |
| 测试 | 82 项通过 | 仅有第三方 FOOOF 弃用警告；全仓 Ruff 另有既有 Notebook 导入顺序提示 |
| 真实样例 | 文件级全流程完成 | 身份未解析，不能做动物层推断 |
| Git 状态 | 有既有未提交修改 | 本轮未提交、未推送、未清理或重置 |

## 项目管理阶段（2026-09-19）

- 已建立 SQLite 项目索引：项目 → 被试 → session → 状态记录 → 数据单元；关联使用稳定 ID，重命名不改外键。
- 已实现可编辑文件导入预览、SHA-256 内容重复检测、通道映射确认、外部源重定位核验和 Unicode 显示名称。
- 项目管理窗口现在只保留结构、模板、导入、归属、概况和“打开分析/加入批处理”；后台批量、结果复核和 A/B 比较由主分析窗口顶部入口打开，不再在管理窗口并列维护第二套流程。
- 已实现版本化 `luna-result-bundle/1.0`、原子 manifest 写入、SQLite 索引、无 GUI 读取/长表导出及 legacy run 显式接入接口。
- 已实现从主单份分析参数控件复制批处理计算方案、保存/载入方案、数据单元检查决定独立叠加、冻结快照、逐数据单元错误隔离、取消/恢复和严格指纹复用。
- 已实现按组别、session_key、条件、数值时间点和模块的比较预览；缺失与重复记录显式报告，参数不兼容结果不静默合并。
- 已实现按稳定 `subject_id` 的双时间点配对显示、通道/脑区/脑区对结果筛选，以及保存比较快照后的精确 `analysis_id` 重载。
- 已实现项目树元数据编辑、源文件指纹重定位、前后数据导航和中断批量任务恢复；恢复只重排未完成项目。
- 已实现同一源文件按明确 epoch/时间选择拆分为多个数据单元；完全相同的来源与选择仍按指纹阻止重复。项目模板、任务设置和单数据覆盖均可编辑并冻结为有效参数快照。
- `scripts/create_project_demo.py` 已生成 5 个明确标记的虚拟被试：3 个无歧义 T100、1 个重复 T100、1 个缺失 T100，并包含参数/映射差异和失败任务。

### 本轮验证

- 自动测试 76 项全部通过；Ruff、compileall 和 pip check 通过。
- 固定只读 FIF 通过项目批量路径运行 Quality、PSD、Band Power，并成功由无 GUI API 重载 3 个 schema 1.0 结果包；第二个相同任务命中缓存且没有新增结果。
- 同一只读 FIF 使用明确标记、无生物学含义的 `TEST_R1…TEST_R4` 映射完成 Quality、PSD、Band Power、FOOOF、Connectivity 和 Time Delay；6 个结果包均为 `completed/saved`。
- 同一只读 FIF、同一项目身份与参数下，单份和批量路径的 PSD（67,200 行）及 Band Power（2,016 行）结果表逐列一致；数值比较使用 `rtol=1e-12, atol=0`。
- Qt offscreen 在 1366×768 与 1920×1080 下实际显示项目数据、批量、T100 比较和 T80→T100 配对页面；截图位于 `C:/Users/PC/AppData/Local/Temp/luna_project_gui_validation_20260919_v8/`，不纳入 Git。
- 当前 Computer Use 通道未返回可操作的 Windows 原生应用窗口；原生鼠标交互、125%/150% 系统缩放和多显示器仍未验证。
- 离屏批量导出连接图时观察到既有 Times New Roman 中文缺字警告；图文件成功生成，未隐藏该警告，本轮未改变绘图语义。

## 简化项目工作流（2026-09-22）

- 新建项目改为“项目名称＋父目录”，界面预览真实目标文件夹；同名文件夹不覆盖。项目 schema 升级到 2，旧 schema 1 项目在原数据库内非破坏迁移。
- 新导入默认复制到 `data/raw/<SHA-256 前缀>/`，复制后重新核验大小与 SHA-256，数据库保存项目相对路径和原始来源路径；项目整体移动后可以重开。旧外部引用由显式“整理到项目”操作迁移。
- 增加三步结构模板：被试、session、状态/数值时间点；模板可命名保存和再次套用，同名稳定结构复用，不更改已有数据归属。
- 已修复标准 Apply 按钮信号未进入处理函数的问题；模板应用现在同时持久化 SQLite 层级和 `subjects/<被试>/<session>/<状态>/` 目录，空状态显示“未导入数据”，重复应用不重复，增量模板只补缺失节点。
- 多文件/文件夹导入在同一预览表中编辑；选择树节点时继承明确上下文，文件名中的 `T<number>` 只作为可见时间点建议，动物和 session 不静默推断。
- 项目树隐藏 UUID，只显示名称、数量和检查/导入状态；单份工作区增加保存检查、上一份、下一份和下一份待检查导航。
- 固定只读 FIF 实测为 21×16×5000、1000 Hz、105 s。验证项目保存 15 个通道和 epoch `[0,1,2]` 的检查决定，PSD 与 Band Power 批量结果 manifest 均保留该快照；项目移动后无 GUI API 可重载 2 个结果。
- 离屏运行截图位于 `C:/Users/PC/AppData/Local/Temp/luna_simplified_gui_validation_20260922/`，包含创建项目、结构模板、导入预览、项目管理、单份检查、批处理和 A/B 比较；真实数据截图和合成比较截图不纳入 Git。
- 单独主窗口加载真实 FIF、等待读取线程完成并关闭时正常退出。组合离屏截图工具在统一销毁多个 Qt/Matplotlib 窗口时曾出现一次 Windows 访问冲突；该工具不属于产品运行入口，原生 Computer Use 仍未暴露 Windows 应用窗口，因此真实鼠标、系统 125%/150% DPI 和多显示器验收未完成。

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

## 稳定状态导入与版本化检查（2026-09-22）

- 在 schema 4 阶段，导入已改为只绑定现有 `state_record_id`，不再按显示名称回查或静默新建结构；项目树显示持久化数据子节点，新数据初始为“待检查”。当前 schema 已在后续条目升级为 5。
- 检查记录具有 revision、fingerprint、保存状态和审计历史；保存当前通道/坏道、映射、epoch 原始标识、时间选择、状态与备注。源结构不兼容时不套用旧掩码。
- 计算、保存、当前有效性和人工复核状态独立。检查变化不篡改历史计算状态，只把相关结果标记为 `needs_recompute`；旧成功结果仍可读取。
- 单份与批量结果均保存 `dataset_id`、`analysis_run_id`、冻结检查快照和条件元数据；默认缓存/比较只使用当前兼容结果。
- 固定真实 FIF 验证为 21×16×5000、1000 Hz、105 s；模板状态数导入前后不变，同一状态可保存不同选择的多条记录，相同来源与相同选择会被阻止。

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

## 2026-09-23 项目保存与结果恢复状态

- 当前项目数据库 schema 为 5；在 schema 4 基础上增加行为附件、行为评分和同步记录。行为评分区分缺失与真实零，视频文件只登记来源，不做视频处理。
- Project Manager 已提供显式 `Save project`/Ctrl+S、脏状态和关闭时 Save/Discard/Cancel。检查自动保存与分析结果自动保存仍是独立流程。
- 主分析 GUI 从项目数据单元打开时，会直接加载已保存的结果 bundle，不自动重新计算；默认选择最新可读取的成功版本，可从“历史版本”选择其他版本，并查看只读参数/检查快照或复制为待运行参数。
- 真实 FIF 项目验证：固定只读 `C:/Users/PC/Documents/ChatGPT/testdata/LID-T80_all_channels-epo.fif` 已用于导入、PSD/Band Power 索引、结果 bundle 恢复和源文件不可用时的结果浏览；未修改源文件。
- 已完成的离屏验证：项目草稿 Save/Discard、行为零/缺失、SQLite backup 恢复、保存结果恢复均通过。自动测试、Ruff、compileall、pip check 和 git diff --check 在本轮末复核。
- 限制：草稿通过项目本地 backup/marker 提供恢复边界，编辑时 SQLite 元数据仍即时写入，尚不是跨进程事务工作区；原生 Windows 鼠标、125%/150% DPI、多显示器和视频逐帧同步未验证。
