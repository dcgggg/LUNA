# LUNA 当前项目状态

最后核查：2026-09-29。以下状态只依据当前工作区代码、当前虚拟环境和本次实际运行结果；未把旧需求、历史截图或未执行的人工操作记为通过。

## 总体状态

| 项目 | 当前状态 | 证据/限制 |
|---|---|---|
| 软件版本 | `0.3.0.dev2` | 本次待发布开发版本；版本来源为 `src/lfp_analysis/__init__.py`，`pyproject.toml` 使用动态版本 |
| GUI 框架 | PySide6 + Matplotlib | `scripts/run_gui.py` → `lfp_analysis.gui.launch()` → `MainWindow` |
| CLI | 可用 | `lfp-analysis.exe`、`luna-diagnose.exe` 和模块入口均已核实；当前环境没有 `luna.exe` 别名 |
| 测试 | 136 项通过 | 2026-09-29 Windows x64/Python 3.11 源码环境与 Python 3.12.14 最新 wheel 隔离环境，均在 `CI=true`、Qt offscreen 窗口测试显式启用时完成全量测试；Ruff、compileall、依赖检查通过。另以无可选分析后端的 `.[gui]` 安装完成真实 FIF 的 GUI PSD 计算、保存、重载和正常关窗。FOOOF/Qt 上游弃用警告保留 |
| 真实样例 | 文件级全流程及读图文档核对完成 | 固定 FIF 21×16×5000，1000 Hz、有效片段累计105 s；animal/session 身份未解析，不能做动物层推断 |
| 分析说明 | 已加入 GUI 读图帮助和 3 份生成式中文文档 | 文档与 GUI 使用同一说明源；本轮核对 CLI 实际 41 个 CSV 的全部字段均进入目录，GUI 原生桌面/DPI未手动验收 |
| Git 状态 | 有既有未提交修改 | 本轮未提交、未推送、未清理或重置 |

## 功能连接跨机诊断与兼容性（2026-09-28 至 2026-09-29）

- 已确认项目依赖边界：`mne`（MNE-Python，用于 FIF I/O 等）与 `mne-connectivity`（MIC/MIM、wPLI、dPLI 等估计器）是两个独立发行包。`pyproject.toml` 的 `connectivity`、`desktop`、`all` extras 均明确包含 `mne-connectivity>=0.9,<1`；TDE 使用独立的 `pybispectra` extra。依赖分组、安装命令和传递依赖说明见 `docs/DEPENDENCIES.md`。
- 已确认一项兼容风险，但不能将其冒充为其他电脑故障的已知根因：在隔离 Python 3.11/MNE 1.13.2 环境中用 `--no-deps` 探查 MNE-Connectivity 0.8.0/0.8.1 时，包导入因 `mne.fixes.jit` 缺失而失败，`pip check` 仍未发现包元数据冲突。因此项目对连接 extra 的下限调整至 0.9。常规 wheel 安装的 0.9.0 在本机成功导入和计算。
- 诊断入口 `python -m lfp_analysis.diagnostics --output <报告.json> [--input <epochs.fif>]` 无需启动 Qt；报告包含 OS/Python/架构、LUNA 与关键模块位置、依赖版本/API、线程后端、路径可写性及可选 FIF 头信息，不含信号样本、通道名或完整环境变量。GUI 后台检查/分析失败会写入脱敏 JSON 技术报告，并在状态/日志中给出错误与报告位置。当前开发虚拟环境发现 `lfp_analysis` namespace 同时被 `luna-analysis` 与旧 `mouse-lfp-analysis` editable 元数据登记；本轮没有擅自卸载或更改该既有虚拟环境。隔离 wheel 环境仅有 `luna-analysis` 一个 owner。
- 核心版 wheel 的额外边界验证：全新 Windows x64/Python 3.11 venv 只安装核心包时，诊断模块仍能生成报告；缺少 PySide6/MNE-Connectivity 被准确标记为未安装，连接自检明确报告 `dependency_unavailable`、提示 `.[connectivity]` 并以退出码2结束，未错误报为成功。该轮未加载真实信号。
- 新增 `src/lfp_analysis/app_paths.py`、`ui_fonts.py` 与 `optional_dependencies.py`：用户数据/配置/日志/结果采用平台用户目录；安装包资源通过 `importlib.resources` 定位；UI 字体依平台选择；可选后端导入/API 损坏时只禁用相关方法，不隐式替换算法。GUI 启动、FIF 检查和连接计算仍由既有入口/计算核心执行。
- 固定只读 FIF 的 Windows x64 真实连接运行在隔离环境完成：Python 3.11.9、MNE 1.13.2、MNE-Connectivity 0.9.0、NumPy 2.4.6、SciPy 1.17.1、PySide6 6.11.2。21 epochs、1000 Hz；使用 8 个通道组成两个显式 `QC_Test_A/B` 通道集合，仅作质量验证、不代表生物脑区映射。MIC、MIM、wPLI、dPLI、wPLI²-debiased 五种方法均成功；共 12 次主/降秩/片段稳定性估计调用。数值表、完整频谱和图已保存到隔离临时结果包，manifest 状态 `completed`，`load_saved_run()` 可从包重载参数及索引；输入源哈希复核未变。
- Python 3.12.14 的全新 Windows x64 环境再次按 `.[desktop,dev]` 安装，并通过全量 120 项测试、依赖检查、Ruff 0.16.9 与 compileall。用隔离环境实际运行固定 FIF 的 MIC、MIM、wPLI、dPLI、wPLI²-debiased 五种连接方法，manifest 与连接状态均为成功；21 epochs、1000 Hz、显式 `QC_A/QC_B` 测试分组（不是生物脑区映射），保存的频谱 CSV 含五种方法且 `load_saved_run()`/CSV 可重载。输入 SHA-256 前后相同，结果位于 `%TEMP%`。读取连接 CSV 时 pandas 对混合类型元数据列发出 `DtypeWarning`，读取成功；不影响数值或运行状态。
- 干净安装验证：从本次源码构建非 editable wheel，在独立 Python 3.11 环境按 `.[desktop,dev]` 安装，没有手工补装依赖；`pip check`、120 测试、Ruff、compileall 均通过。从仓库外目录运行诊断、命令帮助和 Qt offscreen 主窗口成功，Logo/YAML 使用 wheel 内资源；用户目录经环境隔离重定向到临时目录。GUI 的真实鼠标/屏幕操作没有在本轮执行。
- 后续以该全新 wheel venv 中的安装版 `site-packages` 再运行完整测试套件：129 passed，81 warnings，28.82 s；警告为 Matplotlib Qt 高 DPI 枚举及 FOOOF 上游弃用。该项补充确认测试针对安装包而非仓库源码导入；不代表 macOS 运行验证。
- 平台边界：本机 Windows x64 的 Python 3.11.9 与临时隔离 Python 3.12.14 环境均已验证；没有 macOS 主机。2026-09-28 使用 `uv pip compile --only-binary :all:` 为 macOS arm64/x86_64 × Python 3.11/3.12 各解析 `.[desktop,dev]` 依赖成功（每组52个发行包），这仅证明 wheel 解析可行，不是 macOS 安装或运行证据。GitHub Actions smoke matrix 配置 Windows x64、macOS Apple Silicon (`macos-15`) 和 macOS Intel (`macos-15-intel`)；workflow 已加入 standalone `--self-test-connectivity`、合成连接保存/重载和 GUI offscreen 测试，并在每个 job 结束时上传脱敏诊断 JSON 七天。本机模拟 CI 条件运行的129项全量测试通过，但远端矩阵尚未运行，真实桌面鼠标/DPI 未验收。GitHub 官方 runner 文档当前将 `macos-15` 标为 arm64、`macos-15-intel` 标为 x64，并计划 Intel 标签支持至2027年8月。macOS CI 仍待远端触发。
- 在隔离 Python 3.12.14 Windows 环境仅安装 `.[gui]`、不安装连接/TDE/谱参数化 extra 时，实际启动 offscreen MainWindow 并加载固定 FIF 成功（21 epochs、16通道、1000 Hz）；MIC、TDE、FOOOF 被禁用且带安装提示，PSD 保持可用。进一步完成 GUI PSD-only 计算，写出67,200行逐epoch/通道频谱表，manifest=`completed`，表和运行索引重载成功。该流程暴露并修复已删除 QThread 包装器仍被 closeEvent 查询导致关窗 RuntimeError 的问题；正常关窗回归通过。FIF SHA-256 前后相同。验证不是原生桌面交互，也不代表 Mac 运行证据。
- 2026-09-29 补充：当前 Windows 开发环境的 `luna-diagnose.exe` 首次未生成，虽安装元数据已有入口。以 `.venv` 当前解释器执行 `python -m pip install --no-deps -e .` 后生成并可从仓库外运行；未改动依赖。实际报告发现诊断器错误地把 PySide6 标为 API 缺失，因为 QtCore/QtWidgets 是子模块，不是包顶层属性；现已检查真实的 `QtCore.QObject` 与 `QtWidgets.QApplication`，并有存在/缺失两种测试。完整126项测试通过。当前 `lfp_analysis` 分发元数据仍登记 `luna-analysis` 与旧 `mouse-lfp-analysis` 两个 owner，但模块实际加载自当前仓库 `src/lfp_analysis`；保留警告、未擅自卸载旧环境记录。

- 2026-09-29 最新诊断隐私复核：曾确认用户目录替换为波浪号后绕过自定义路径清理，可能露出其下的项目/数据文件夹名称；已修复 Windows/UNC/POSIX 完整路径脱敏，并将 invoked_as 限为启动器名称，添加 URL 与含空格路径回归。当前源码 Python 3.11 全量136项通过；最新 wheel 在隔离 Windows Python 3.11 与3.12环境通过诊断专项及 Python 3.12 全量136项。安装版诊断只读固定 FIF 文件头并运行七种合成连接方法，报告不含输入路径、文件名、通道名或信号样本；源哈希不变。没有 macOS 或故障电脑报告，远端连接故障根因仍未确认。
- 最新 Python 3.12.14 wheel 另以固定只读 FIF（21 epochs、16通道、1000 Hz）完成五种 GUI 连接方法的计算、结果保存和重载，状态 completed/ok、谱表32,340行；仅选8通道并临时映射到QC_A/QC_B供软件测试，非生物学脑区映射。原文件未修改。

## Windows 项目迁移到 POSIX 的相对路径回归（2026-09-29）

- 确认一项真实跨系统兼容缺陷：旧 Windows 项目把项目内 FIF、层级目录、分析 bundle、结果表/数组及批次运行目录写成反斜杠相对路径。POSIX 系统把反斜杠当普通字符，复制项目后相关原始数据、目录或结果无法通过这些旧索引定位。该问题由代码路径和新增复现测试确认，但没有证据表明它就是用户另一台电脑上连接模块故障的根因。
- 新增 `portable_paths.py` 作为统一解析层：读入旧 Windows 或 POSIX 分隔符，拒绝盘符/绝对路径、`..` 和解析后逃出项目/运行目录的 symlink；新写入的 result manifest、SQLite result path、batch run `file_dir` 与表/图相对路径统一为 `/`。Project Manager 层级路径、项目内 FIF 与已保存结果可在搬迁后解析，旧清单保持可读；诊断/科学数值未改。
- 固定只读 FIF 项目搬迁烟测：导入后将数据库路径模拟为旧反斜杠，复制整个含空格项目目录，再从新位置打开 FIF；读到21×16×5000、1000 Hz，源文件 SHA-256 前后相同。合成 bundle 回归覆盖旧 Windows SQLite `result_path` 与 manifest 的 table/array 路径，搬迁后 `ProjectResults` 可读取表格和数组；模板可在旧反斜杠层级节点下增量创建 session。
- 全量测试在 `CI=true`、Qt offscreen 与 `LUNA_RUN_QT_TESTS=1` 下为132 passed、1项 FOOOF 上游弃用警告；`ruff check src tests scripts`、`compileall`、`pip check`、`git diff --check` 均通过。项目内路径不变量、绝对路径和目录逃逸有对应回归覆盖。
- 限制：本机为 Windows x64，不能据此宣称 macOS 原生运行已验证；GitHub macOS matrix 尚未运行，另一台故障电脑没有诊断报告。连接故障具体根因仍未知；诊断命令和诊断附件流程已准备好，需在实际故障环境执行才能定位环境/API/后端差异。

## 功能连接诊断合成自检（2026-09-29）

- 无 GUI 命令 `luna-diagnose --self-test-connectivity --output <报告>` 现会通过 LUNA 实际连接计算核心运行所有 MNE-Connectivity 方法，使用仅作软件执行检查的合成数据（6 epochs × 4 通道 × 3000 样本，500 Hz、5–80 Hz、multitaper 6 Hz、单 worker），并按方法写入状态。
- 本机 Windows x64/Python 3.11.9 从 `%TEMP%` 调用安装入口实测全部 7 种方法 MIC、MIM、wPLI、dPLI、wPLI²-debiased、imcoh、coh 成功；频率网格 451 点，5–80 Hz；3 次估计调用，约 3 s。与命令同时提供的固定真实 FIF 只读加载文件头，21×16×5000、1000 Hz，未读样本且哈希不变。
- 当前工作区另构建了 `0.3.0.dev1` wheel 并在两个临时安装位置检查：prefix 安装确认模块/资源/console script；随后新建 Windows x64/Python 3.11 venv，仅从 wheel 安装 `.[desktop]`，未手工补装包。`pip check` 通过；安装版 `luna-diagnose` 七方法合成自检全为 `ok`，`luna-gui --help` 正常，PySide6 offscreen 下主窗口可显示并正常关闭。wheel 来自本机 Windows 构建，不是 macOS wheel/runtime 证据。验证中 prefix 测试曾使开发 venv 的 LUNA console launchers 被移除，随后通过 `python -m pip install --no-deps -e .` 恢复；最终入口存在且 `pip check` 通过。
- 在上述全新 wheel venv 中另使用 AGENTS 指定只读 FIF 实际运行项目 GUI 分析核心并保存/重载连接结果：21 epochs、16通道、1000 Hz、有效累计105 s；明确选8个文件通道并临时标成两组 `QC_A/QC_B`（各4通道，仅软件兼容性检查，不是生物脑区映射），选择全部21个epoch。五个 GUI 连接方法 MIC/MIM/wPLI/dPLI/wPLI²-debiased 均写入结果，Connectivity 状态 `ok`、run manifest `completed`；重载连接CSV和run bundle成功，谱表32,406行，报告中的有效epoch数21。输入SHA-256与基线相同。加载CSV时 pandas 对稀疏文本元数据列 `estimated_rank_metadata` 发出 `DtypeWarning`；进一步核对为 JSON 文本与空值混合，结果表成功读取且数值核验通过，不是连接估计失败或静默吞错。
- 该命令验证软件/后端执行和 API 连通，不验证科学准确性、目标故障电脑真实数据或 macOS；缺少后端和方法失败会记录在报告中，并以非零退出码提示。完整测试129项通过；无 Mac 或远端故障报告，相关结论仍待原生/外部证据。

## 分析流程解释文档（2026-09-27）

- `docs/ANALYSIS_GUIDE.md`、`docs/RESULT_DATA_DICTIONARY.md`、`docs/FIGURE_RESULT_INDEX.md` 由 `src/lfp_analysis/analysis_help_content.py` 单一内容源生成；README 和 GUI“如何读图”入口链接/使用该内容。
- 对固定只读 FIF 在 `%TEMP%/luna_explainer_final_83455015be5846f39980f924b2f2a252` 完成一次单文件代表流程。核对该次生成的 41 个 CSV 文件名和所有实际列；额外确认 16/16 谱参数化拟合成功、连接区域汇总表 8838×22 与连接 metadata 中 shape 一致、TDE 区域延迟表存在。该次启用模块为 PSD、Band Power、specparam、MIC/MIM/wpli2_debiased、TDE 方法1（标准及反对称）；未运行 dPLI、普通 wPLI 或其他可选连接方法。
- 文件哈希与输入源一致；manifest 的 `identity_status=file_only_identity_unresolved`、`animal_level_statistics_run=false`。没有推断动物、LDN 配对、AIMs 或组间效应。
- 发现并修正文档/显示标签：PSD y 轴单位改为“source unit²/Hz”，频带功率 y 轴优先读取结果中记录的绝对功率单位；连接 metadata `region_summary_shape` 修复为实际 region summary DataFrame shape（只修元数据维度，不改连接数值）。
- 已确认的保存追溯限制：单文件 CLI 的 `config_used.yaml` 是输入配置副本，若使用 `extends` 不会展开父配置；`run_manifest.json` 仅有配置审计、部分参数范围和状态，非完整解析参数快照。部分参数保存在结果表和模块 metadata；项目 result bundle 有独立 effective_parameters。CLI 参数快照不足已写入数据字典/指南，尚未改变保存格式。
- 本次真实 CLI 图共 17 个图类（PNG+SVG），逐一映射到绘图函数与数据字段。目视检查发现文件级 `band_power.png/.svg` 多面板标签拥挤/相邻标题和标签易挤压；数值表不受影响，GUI 总览/比较视图另有交互布局。该绘图布局本轮未重构。
- `.venv` 当前确认 Python 3.11.9、SciPy 1.17.1、MNE 1.12.1、MNE-Connectivity 0.9.0、specparam 2.0.0rc7、PyBispectra 1.3.2、PySide6 6.11.2。项目全量 108 测试通过；仅报告 FOOOF 兼容依赖弃用警告。

## 当前产品范围调整（2026-09-23）

- LUNA 当前软件内范围为项目管理、数据导入与检查、单数据/单状态分析、批量计算、结果保存/恢复、人工复核和每条数据的可视化。
- 已移除当前 GUI 的跨数据 A/B 比较、跨被试配对、组间/组内统计和科研比较绘图入口。单条数据内的通道、频带、脑区和指标视图仍保留。
- 项目管理新增“Filter / export list”工作区：按 group、subject、session、state、condition、结构化时间、检查状态和结果可用性筛选，并导出 CSV/JSON；不进行配对、平均或跨记录计算。
- `comparison.py`、`comparison_snapshots` 表及历史比较文件仍保留为旧项目/外部代码兼容层；当前 GUI 不再创建或加载它们。
- 项目 schema 已升级到 6，增加显式 session 顺序；旧 schema 会迁移到 6，稳定 ID 和已保存结果不变。

## 当前交接审查结果（2026-09-23）

本节覆盖当前工作区的最新事实；下方按日期排列的内容是历史记录，若其中的版本号、测试数量或产品范围与本节冲突，以本节、`docs/HANDOFF.md` 和 `docs/ARCHITECTURE.md` 为准。

1. 当前代码入口已确认：GUI 为 `scripts/run_gui.py` → `lfp_analysis.gui.launch()`；CLI 为 `lfp_analysis.cli:main`；单条与批处理最终复用 `gui_engine.run_gui_analysis()`；无 GUI 结果读取为 `ProjectResults` 和 `scripts/read_project_results.py`。
2. 当前环境已确认：Python 3.11.9；PySide6 6.11.2；Matplotlib 3.11.1；MNE 1.12.1；MNE-Connectivity 0.9.0；specparam 2.0.0rc7；pytest 8.4.2；Ruff 0.16.6。
3. 本次检查执行 `pytest -q`、`ruff check src tests scripts`、`compileall -q src tests scripts`、`pip check` 和 `git diff --check`，结果分别为 103 项通过、静态检查通过、编译通过、依赖无损坏和差异检查通过。FOOOF 兼容后端只有第三方弃用警告。
4. 固定只读 FIF `C:/Users/PC/Documents/ChatGPT/testdata/LID-T80_all_channels-epo.fif` 可读取：21×16×5000、1000 Hz、4.999 s/epoch；本轮读取前后 SHA-256 一致。文件身份未解析，因此不能据此做动物层统计。命令行帮助和结果读取帮助已通过；真实 Windows 桌面鼠标交互、DPI 和多显示器未验证。
5. 已确认 Project Manager 的可恢复草稿语义：编辑即时写入 SQLite，Save 校验并确认 backup 边界；第二个读取者会在 Save 前看到编辑，因此它不是隔离事务。本轮新增正常 Save/Discard、第二读取者、子进程崩溃后重开并恢复后 Save/Discard、目录保护和 schema 5→6 迁移回归，全部通过。仍需产品层明确是否接受这种可见性，或未来另行设计真正隔离的 draft DB。

### 当前状态判定

| 范围 | 状态 | 说明 |
|---|---|---|
| 项目层级、模板、导入和稳定关联 | 已实现并验证 | SQLite schema 6；空状态、重复/增量模板和项目相对路径已有测试/历史实测 |
| Project Manager 左树/右数据列表范围联动 | 已实现并验证（offscreen） | 稳定 ID 过滤项目/subject/session/state/data 节点；空节点保持空；新测试覆盖同名节点、筛选、批处理隔离、导入/重开、改名/删除回退和关闭旧范围窗口 |
| 检查配置、映射、epoch 选择和结果失效 | 已实现但需持续回归 | revision/fingerprint/needs_recompute 已有；真实身份和研究映射仍需人工确认 |
| PSD、频带功率、FOOOF、连接、时间延迟 | 已实现并有文件级/合成验证 | 参数是配置起始值，不代表实验方案确认；不替代动物层结论 |
| 单条/批处理共用核心与结果 bundle | 已实现并验证 | `ProjectBatchRunner` 和 `run_gui_analysis` 共用；需继续覆盖取消/重载边界 |
| 已保存结果恢复、Review、Filter/export | 已实现并有离屏/无 GUI 验证 | 原始源缺失时可浏览可读 bundle；真实桌面交互未完成 |
| 软件内跨数据比较和组统计 | 已取消或被新要求替代 | 旧兼容数据保留，当前 GUI 不提供；外部 API/CSV/JSON 承担下游分析 |
| 行为视频、逐 epoch 同步、spike | 未实现 | 仅保留扩展字段或未来接口 |

### Project Manager 窗口生命周期复核（2026-09-23）

- 用户可见的“关闭 manager 后 Filter/export 仍留在屏幕”在本轮开始前已由现有关闭分支处理；Cancel 也在 `event.ignore()` 后跳过子窗清理。
- 复核发现已接受关闭后只隐藏 Filter/export 和旧 ProjectWorkspace，Qt 对象仍存活并持有旧 ProjectStore。当前已改为 owner 关闭后清理引用并销毁 Filter/export；切换项目时销毁旧 manager/batch/review workspace。活动 batch thread 运行时阻止切换。
- Qt offscreen 回归覆盖关闭/Cancel、单独关窗后重开、Project A→B、活动批处理保护和 Import Preview `state_record_id` 冻结。全量 103 项通过；真实桌面鼠标、系统 DPI、多显示器仍未验证。

## 历史记录：项目管理阶段（2026-09-19）

- 已建立 SQLite 项目索引：项目 → 被试 → session → 状态记录 → 数据单元；关联使用稳定 ID，重命名不改外键。
- 已实现可编辑文件导入预览、SHA-256 内容重复检测、通道映射确认、外部源重定位核验和 Unicode 显示名称。
- 项目管理窗口现在保留结构、模板、导入、归属、概况、筛选/导出清单和“打开分析/加入批处理”；后台批量和结果复核由独立入口打开。跨数据 A/B 比较、配对、组间/组内统计和科研绘图已从当前 GUI 产品范围移除。
- 已实现版本化 `luna-result-bundle/1.0`、原子 manifest 写入、SQLite 索引、无 GUI 读取/长表导出及 legacy run 显式接入接口。
- 已实现从主单份分析参数控件复制批处理计算方案、保存/载入方案、数据单元检查决定独立叠加、冻结快照、逐数据单元错误隔离、取消/恢复和严格指纹复用。
- 已实现按组别、被试、session、状态、条件、结构化时间、检查状态和结果可用性的记录筛选，并可导出 CSV/JSON 清单；同字段为或、跨字段为且，不进行配对或平均。
- 历史 `comparison_snapshots` 表、旧比较文件和 `comparison.py` 读取接口保留用于兼容旧项目/外部代码，但当前 GUI 不再创建、加载或展示跨数据比较。
- 已实现项目树元数据编辑、源文件指纹重定位、前后数据导航和中断批量任务恢复；恢复只重排未完成项目。
- 已实现同一源文件按明确 epoch/时间选择拆分为多个数据单元；完全相同的来源与选择仍按指纹阻止重复。项目模板、任务设置和单数据覆盖均可编辑并冻结为有效参数快照。
- `scripts/create_project_demo.py` 已生成 5 个明确标记的虚拟被试：3 个无歧义 T100、1 个重复 T100、1 个缺失 T100，并包含参数/映射差异和失败任务。

### 本轮验证

- 自动测试 76 项全部通过；Ruff、compileall 和 pip check 通过。
- 固定只读 FIF 通过项目批量路径运行 Quality、PSD、Band Power，并成功由无 GUI API 重载 3 个 schema 1.0 结果包；第二个相同任务命中缓存且没有新增结果。
- 同一只读 FIF 使用明确标记、无生物学含义的 `TEST_R1…TEST_R4` 映射完成 Quality、PSD、Band Power、FOOOF、Connectivity 和 Time Delay；6 个结果包均为 `completed/saved`。
- 同一只读 FIF、同一项目身份与参数下，单份和批量路径的 PSD（67,200 行）及 Band Power（2,016 行）结果表逐列一致；数值比较使用 `rtol=1e-12, atol=0`。
- 旧记录中的 Qt offscreen 页面截图仍保留为历史证据；它们不替代当前交接审查的验证，不把历史 Compare 页面作为当前功能。
- 当前 Computer Use 通道未返回可操作的 Windows 原生应用窗口；原生鼠标交互、125%/150% 系统缩放和多显示器仍未验证。
- 离屏批量导出连接图时观察到既有 Times New Roman 中文缺字警告；图文件成功生成，未隐藏该警告，本轮未改变绘图语义。

## 历史记录：简化项目工作流（2026-09-22）

- 新建项目改为“项目名称＋父目录”，界面预览真实目标文件夹；同名文件夹不覆盖。项目 schema 升级到 2，旧 schema 1 项目在原数据库内非破坏迁移。
- 新导入默认复制到 `data/raw/<SHA-256 前缀>/`，复制后重新核验大小与 SHA-256，数据库保存项目相对路径和原始来源路径；项目整体移动后可以重开。旧外部引用由显式“整理到项目”操作迁移。
- 增加三步结构模板：被试、session、状态/数值时间点；模板可命名保存和再次套用，同名稳定结构复用，不更改已有数据归属。
- 已修复标准 Apply 按钮信号未进入处理函数的问题；模板应用现在同时持久化 SQLite 层级和 `subjects/<被试>/<session>/<状态>/` 目录，空状态显示“未导入数据”，重复应用不重复，增量模板只补缺失节点。
- 多文件/文件夹导入在同一预览表中编辑；选择树节点时继承明确上下文，文件名中的 `T<number>` 只作为可见时间点建议，动物和 session 不静默推断。
- 项目树隐藏 UUID，只显示名称、数量和检查/导入状态；单份工作区增加保存检查、上一份、下一份和下一份待检查导航。
- 固定只读 FIF 实测为 21×16×5000、1000 Hz、105 s。验证项目保存 15 个通道和 epoch `[0,1,2]` 的检查决定，PSD 与 Band Power 批量结果 manifest 均保留该快照；项目移动后无 GUI API 可重载 2 个结果。
- 离屏运行截图位于历史临时目录，包含创建项目、结构模板、导入预览、项目管理、单份检查和批处理；其中旧 A/B 比较截图仅作历史记录，不代表当前产品入口。
- 单独主窗口加载真实 FIF、等待读取线程完成并关闭时正常退出。组合离屏截图工具在统一销毁多个 Qt/Matplotlib 窗口时曾出现一次 Windows 访问冲突；该工具不属于产品运行入口，原生 Computer Use 仍未暴露 Windows 应用窗口，因此真实鼠标、系统 125%/150% DPI 和多显示器验收未完成。

## 历史记录：GUI 复核（2026-09-13）

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

## 历史记录：稳定状态导入与版本化检查（2026-09-22）

- 在 schema 4 阶段，导入已改为只绑定现有 `state_record_id`，不再按显示名称回查或静默新建结构；项目树显示持久化数据子节点，新数据初始为“待检查”。当前 schema 已在后续条目升级为 5。
- 检查记录具有 revision、fingerprint、保存状态和审计历史；保存当前通道/坏道、映射、epoch 原始标识、时间选择、状态与备注。源结构不兼容时不套用旧掩码。
- 计算、保存、当前有效性和人工复核状态独立。检查变化不篡改历史计算状态，只把相关结果标记为 `needs_recompute`；旧成功结果仍可读取。
- 单份与批量结果均保存 `dataset_id`、`analysis_run_id`、冻结检查快照和条件元数据；默认缓存和当前结果查询只使用当前兼容结果，跨数据分析由外部代码负责。
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

## 历史记录：2026-09-23 项目保存与结果恢复状态

- 当时项目数据库 schema 为 5；后续已升级为当前 schema 6。行为评分区分缺失与真实零，视频文件只登记来源，不做视频处理。
- Project Manager 已提供显式 `Save project`/Ctrl+S、脏状态和关闭时 Save/Discard/Cancel。检查自动保存与分析结果自动保存仍是独立流程。
- 主分析 GUI 从项目数据单元打开时，会直接加载已保存的结果 bundle，不自动重新计算；默认选择最新可读取的成功版本，可从“历史版本”选择其他版本，并查看只读参数/检查快照或复制为待运行参数。
- 真实 FIF 项目验证：固定只读 `C:/Users/PC/Documents/ChatGPT/testdata/LID-T80_all_channels-epo.fif` 已用于导入、PSD/Band Power 索引、结果 bundle 恢复和源文件不可用时的结果浏览；未修改源文件。
- 已完成的离屏验证：项目草稿 Save/Discard、行为零/缺失、SQLite backup 恢复、保存结果恢复均通过。自动测试、Ruff、compileall、pip check 和 git diff --check 在本轮末复核。
- 限制：草稿通过项目本地 backup/marker 提供恢复边界，编辑时 SQLite 元数据仍即时写入，尚不是跨进程事务工作区；原生 Windows 鼠标、125%/150% DPI、多显示器和视频逐帧同步未验证。
