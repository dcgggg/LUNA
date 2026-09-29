# LUNA 开发交接

核查日期：2026-09-29（北京时间）。本文件给下一次会话或下一模型优先阅读，内容依据当前工作区代码和本次命令结果，不依据聊天历史推断。

## 1. 产品目标与明确边界

LUNA（Local field potential Unified Network Analysis platform）当前目标是管理 project → subject → session → state → data unit，完成数据导入、来源追溯、通道/epoch/时间检查、脑区映射、单条和批量分析、结果保存/恢复、人工复核以及可供外部统计的筛选和导出。已有分析包括 FIF/QC、PSD、频带功率、FOOOF/specparam、功能连接和时间延迟。

软件内已明确取消跨数据 A/B、跨被试配对、组间/组内统计和科研比较绘图。旧 `comparison.py`、`comparison_snapshots` 表和历史比较文件仍作为兼容层，当前 GUI 不应重新提供入口。行为附件、评分和同步字段只表示扩展存储位置；视频处理、逐 epoch 行为同步和 spike 分析尚未实现。

## 2. 当前真实状态

当前版本为 `0.3.0.dev2`，分支 `master`，remote 为 `https://github.com/dcgggg/LUNA.git`。本轮发布前工作区包含 README、GUI/绘图/连接代码、分析帮助、可选依赖诊断、跨平台路径、CI 和测试改动；最终提交 SHA 以发布后的 Git 记录为准。以 `git status --short` 查看精确范围；不得 reset、checkout、清理或覆盖这些修改。

当前项目数据库 schema 为 6。稳定 ID 和父子关系在 SQLite；目录树使用可读名称。导入默认复制到项目 `data/raw/`，以大小和 SHA-256 校验，外部源文件不移动。结果使用 `luna-result-bundle/1.0`，数值文件和 manifest 成功写入后才登记；检查、映射或科学参数变化会把当前结果标为 `needs_recompute`，历史结果仍可读取。

主要状态：项目管理、模板、导入、检查配置、结果 bundle、批处理、Review、Filter/export 已有代码和测试/离屏证据；单条和批处理共用 `gui_engine.run_gui_analysis()`。2026-09-27 固定真实样例文件级完整流程再次运行，21×16×5000、1000 Hz、有效累计时长105秒；animal/session 身份未解析，未运行动物层推断。分析流程指南、字段词典和图表索引现已落地；单文件 CLI 的 `config_used.yaml` 在 `extends` 场景下不是完整展开参数快照，此追溯限制已记录。当前 GUI 的原生 Windows 鼠标、实体 DPI、多显示器和视频同步仍未验证。

## 3. 环境、入口与验证

解释器：`.venv\Scripts\python.exe`；Python 3.11.9。关键版本：NumPy 2.4.6、SciPy 1.17.1、pandas 2.3.3、Matplotlib 3.11.1、MNE 1.12.1、MNE-Connectivity 0.9.0、specparam 2.0.0rc7、FOOOF 1.1.1、PyBispectra 1.3.2、PySide6 6.11.2、pytest 8.4.2、Ruff 0.16.6。独立 wheel 环境解析到 MNE 1.13.2/MNE-Connectivity 0.9.0，相关测试也通过。完整记录和安装指引见 `docs/DEPENDENCIES.md`。

GUI 入口：`scripts/run_gui.py`；CLI：`python -m lfp_analysis.cli`；PyCharm 辅助入口：`scripts/run_single_file.py`；结果读取：`scripts/read_project_results.py` 或 `src/lfp_analysis/results_api.py`。标准验证为：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m compileall -q src tests scripts
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

2026-09-28 Windows x64/Python 3.11 在 `CI=true` 并显式启用 offscreen Qt 测试后，全量124项测试、Ruff、compileall、依赖检查通过；新增 GUI 合成 FIF 导入→PSD→保存→新窗口载入历史结果集成测试通过。Python 3.12.14 的声明 extras 环境曾通过全量120项测试，并对固定 FIF 完成 MIC/MIM/wPLI/dPLI/wPLI²-debiased 计算、保存和重载；使用显式 QC 通道分组，身份未解析。本轮 Python 3.12.14 仅 `.[gui]` 环境完成固定 FIF 加载、PSD-only GUI 计算、结果保存/重载和正常关窗；可选分析方法正确禁用。macOS arm64/x86_64 × Python 3.11/3.12 的 wheel-only 依赖解析已通过，但 macOS 原生安装/运行、远端 CI、真实桌面交互/DPI仍未验证；无其他电脑诊断报告，远端故障根因未确认。细节见 `docs/PROJECT_STATUS.md` 与 `docs/DEV_LOG.md`。

2026-09-29 追加本机复核：当前 Windows x64/Python 3.11 全量129项通过。当前源码 wheel 在全新 Python 3.11 venv 中仅安装 `.[desktop]` 后，`pip check`、安装版七方法诊断、GUI CLI 帮助和 PySide6 offscreen 主窗口创建/关闭均通过；Logo/YAML 资源来自 wheel。另在该干净 wheel venv 用指定只读 FIF 经 GUI 分析核心完成 MIC/MIM/wPLI/dPLI/wPLI²-debiased 计算、结果保存与重载，manifest completed、连接状态 ok；通道仅临时分成非生物学 QC_A/QC_B，身份仍未解析。GitHub workflow 现显式调用独立七方法合成诊断，并保留 macOS arm64/Intel matrix，但当前未提交代码尚未在远端运行。诊断仍报告当前开发环境中 `luna-analysis` 与旧 `mouse-lfp-analysis` 两个 `lfp_analysis` 元数据 owner；代码实际从当前工作区导入，未卸载旧发行包。完整细节见最新 `docs/DEV_LOG.md`。这不是其他电脑或 macOS 验证；用户没有可提供的远端诊断报告。

补充验证：同一全新 wheel 环境安装 `.[desktop,dev]` 后，完整129项测试由该环境 `site-packages` 版本运行并通过（81条 Matplotlib/FOOOF 弃用警告，28.82秒）。这加强 Windows 安装包回归证据，不改变 macOS/外部设备尚未验证的状态。

平台工作流现在会在各 OS/Python job 结束时保留常规诊断和合成连接诊断两个 JSON artifact 7天；工作流尚未推送或运行，不能据此声称已有 macOS 结果。

核心版 wheel 另在临时 venv 验证：无 GUI/连接 extra 时独立诊断仍可运行；连接自检正确报告后端不可用、安装 extra 与非零退出码，未伪报成功。详见 `docs/DEV_LOG.md` 最新条目。

2026-09-29 路径迁移回归补充：发现并修复 Windows 写入的 `\` 相对路径在 POSIX 上无法解析的问题，覆盖项目内 FIF、层级目录、分析索引、manifest 表/数组以及批次目录。旧 Windows 路径读取兼容，新写入统一 `/`；路径仍经过目录边界检查。Windows 本机全量 Qt-offscreen 测试现为132 passed，固定只读 FIF 项目复制后重开成功，旧格式合成结果包移动后表格/数组读取通过。macOS runner/原生 GUI仍未运行；没有其他电脑诊断报告，所以此项是已确认的迁移缺陷修复，不是用户连接故障根因结论。

后续仅 GUI 安装复现验证：Windows x64/Python 3.12.14 隔离环境安装 `.[gui]`（未装 mne-connectivity、pybispectra、specparam、fooof），主窗口从安装 wheel 启动并加载固定 FIF 成功；MIC、TDE、FOOOF 禁用，PSD 可用。PSD-only GUI 分析生成67,200行频谱长表，run manifest 成功，重读保存表和 run 均成功。复现并修正缺少谱参数化包时 FOOOF 仍可勾选，以及 inspect QThread 删除后 MainWindow.closeEvent 对失效包装器调用 `isRunning()` 的问题；两者均有回归证据。见 `docs/DEPENDENCIES.md` 和最新 DEV_LOG。macOS 和目标故障机仍需原生/实际诊断证据。

2026-09-29 最新诊断隐私与安装验证：修复诊断报告可能泄露用户主目录下自定义文件夹名的问题，增加 Windows/POSIX 路径、URL 与启动器名称回归。当前源码 Python 3.11 全量136项通过；最新 wheel 在隔离 Windows Python 3.11/3.12 环境均可安装，Python 3.12 全量136项通过。安装版诊断对固定 FIF 仅读文件头（21×16×5000、1000 Hz）并在合成数据上运行七种连接方法，报告不含输入路径、文件名、通道名或信号样本；源文件哈希不变。无 macOS 或故障电脑报告，远端根因未确认。

补充：最新 Python 3.12.14 wheel 隔离环境亦用固定只读 FIF 完成五种 GUI 连接方法的计算、保存和重载；21 epochs、16输入通道、1000 Hz，分析选8通道临时分为 QC_A/QC_B（仅软件测试标签），连接状态 ok、结果可重载。此为 Windows x64 验证，不是 macOS 验收。

## 2.1 Project Manager 范围联动（2026-09-23）

- 根因确认：旧 `_refresh_data_table()` 对所有树选择都无条件调用 `ProjectStore.data_units()` 全项目查询；项目树的选择信号只更新状态资源面板，没有触发表格刷新。因此左侧节点变化不会缩小右侧范围。
- 修复后，项目/subject/session/state/data 节点用 `project_id`、`subject_id`、`session_id`、`state_record_id`、`data_unit_id` 精确筛选；名称和路径仅作显示，不作为关联键。过滤、搜索和 `Filter/export list` 在基础范围内运行；显式空 ID 集合返回空列表。
- 检查了批处理勾选与表格行选择分离、树刷新保留 stable ID 与展开状态、删除后回退父节点、导入后刷新目标 state。并修复关闭 Project Manager 时其非模态筛选窗口仍残留旧项目的问题。
- `docs/PROJECT_WORKFLOW.md` 增补当前按钮和对话框操作说明。已确认主分析工具栏 `Save Result` 与 `Export Figure` 目前连接同一个导出回调；部分指标还会导出 CSV，两者都不等于自动保存的分析 bundle。没有删除或合并入口，只在 tooltip/文档中说明。
- 新增 `tests/test_project_manager_scope.py` 11 项，覆盖层级范围、同名节点、空 subject/session/state、表格过滤、树/表/批处理状态隔离、导入/重开、改名/删除回退、筛选窗口生命周期、取消关闭、Import Preview 目标冻结、A→B workspace 隔离和保存结果浏览路径。全量测试当前为 103 项。
- 项目/subject/session/state、空节点和真实 FIF 范围截图位于 `C:/Users/PC/AppData/Local/Temp/luna_pm_scope_final_20260923_8dg7mmlu/`。另用隔离合成 bundle 验证打开时直接恢复保存参数且未启动分析，合成结果测试目录为 `C:/Users/PC/AppData/Local/Temp/luna_pm_result_restore_20260923_azqm_gt0/`。
- 限制：截图来自真实 PySide6 控件在 Qt offscreen 中渲染，不是实体桌面截图。桌面控制工具本轮只列出 Codex IAB、未列出 Windows 原生应用窗口；不能声称手动点击或显示器 DPI 验收完成。Project Manager 无动态中英文切换；具体可见按钮清单见 `docs/PROJECT_WORKFLOW.md`。

## 2.2 Project Manager 辅助窗口生命周期（2026-09-23）

- 本轮复核确认：可见的旧 Filter/export 残留已由既有 accepted-close 清理逻辑阻止；未保存时选择 Cancel 会保留 manager 和辅助窗口。
- 仍存在的缺口是 accepted close 仅调用 `close()` 隐藏窗口。Qt offscreen 实测确认旧 `ProjectFilterExportDialog` 仍有效、仍是旧 `ProjectWorkspace` 的 QObject 子对象并保有 ProjectStore；`MainWindow._attach_project()` 清空 Python 字段后，也没有销毁旧 workspace。
- 修复后单独关闭 Filter/export 会清理 owner 引用并设置 `WA_DeleteOnClose`；manager 接受关闭后关闭并 `deleteLater()` 所有其下筛选窗口；A→B 切换对旧 workspace 调用 `deleteLater()`，并立即丢弃 MainWindow 的旧引用。Cancel 路径不触碰辅助窗口。
- 批处理 workspace 的线程运行时拒绝切换项目并明确提示，避免关闭/隐藏仍绑定旧项目的运行窗口。Import Preview 使用 modal exec，选择目标保存在对话行的 `state_record_id` 中；背景树选择变化不改写其目标。
- 新增 4 项生命周期/冻结目标回归（现有 scope 测试文件共 11 项）：accepted close 销毁所有筛选窗、Cancel 保持显示、单独关闭清理引用并可重开、A→B 销毁旧对象并绑定新 store、Import Preview 状态 ID 冻结，以及活动批处理切换拦截均由 offscreen 测试覆盖。
- 本轮全量 pytest 103 项通过；Ruff、compileall、pip check 和 `git diff --check` 通过。未加载真实 FIF，未修改分析逻辑或真实数据。没有运行原生 GUI 手动验收，Windows 鼠标/DPI/多显示器仍未验证。

## 4. 核心文件和数据流

`gui.py` 的 `MainWindow` 负责单条 GUI；`project_gui.py` 的 `ProjectWorkspace` 负责项目管理、模板、导入、批处理/Review/Filter 工作区；`project_store.py` 的 `ProjectStore` 负责 schema/migration、目录和源文件、检查、任务/结果索引与兼容表；`gui_engine.py` 负责任务快照、计算和恢复；`pipeline.py` 是 CLI 单条/批量编排；`project_batch.py` 是项目批处理；`spectral.py`、`parameterization.py`、`connectivity.py`、`time_delay.py` 是计算核心；`result_contract.py` 负责 bundle；`results_api.py` 是无 Qt 读取接口。

保存边界要特别注意：Project Manager 首次编辑前创建 SQLite backup 和 marker，之后编辑即时写入当前 DB；Save 负责校验并清理 backup/marker，Discard 使用 backup 恢复并清理本次安全新增的空目录。因此当前是“可恢复草稿”，不是跨进程事务工作区。检查自动保存和分析结果自动保存独立于项目 Save。

## 5. 最重要的待处理问题

1. P1，Save 语义与用户直觉不完全一致。代码证据：`project_gui.py` 的 `_begin_project_edit()`、`save_project()`、`discard_project_changes()`；本轮已补充并运行正常 Save/Discard、第二读取者、子进程崩溃后重开并恢复后 Save/Discard、目录保护和 schema 5→6 迁移回归。代码行为明确：其他进程在 Save 前能读到写入的 SQLite 元数据。它仍不是隔离草稿；如需事务式可见性，应另行设计 draft DB 并评估迁移风险，不能将当前机制描述为隔离事务。
2. P2，`MainWindow`（约 3200 行/117 方法）、`ProjectWorkspace`（约 1400 行/71 方法）和 `ProjectStore`（约 1780 行/75 方法）职责过重。当前没有仅因规模而确认的结果错误；应在回归测试后，按稳定接口渐进拆出 schema/migration、source import、result index、行为兼容和 GUI task/controller。
3. P2，结果读取 API 已覆盖 bundle 的表/数组/长表，记录筛选可导出 CSV/JSON；但没有在 `ProjectResults` 中发现独立的原始数据窗口提取封装。若产品仍要求外部代码便捷提取原始数据，应先定义路径、指纹和选择快照契约，再加小接口和测试。
4. P2，group/condition 等描述性编辑不应触发重算，代码路径基本如此，但当前缺少明确回归测试证明编辑后结果仍为 current；应补测试而不是先改失效规则。
5. P3，历史文档中存在旧 schema/测试数量和旧路径；本轮已压缩 `DEVELOPMENT.md`，并在 `PROJECT_STATUS.md` 增加当前审查覆盖说明。后续只需按本交接文件维护，不要重复复制旧日志。

## 6. 推荐下一任务和验收

下一步先由产品决策确认“草稿期间第二个读取者可见编辑”是否可接受。若接受，保留现有即时 SQLite 写入＋backup/marker 的可恢复边界；若要求 Save 前对其他读取者不可见，再单独设计隔离 draft DB 和原子提交流程。该重构前置条件是定义崩溃恢复、数据文件复制、外部连接及结果写入如何与草稿协调；不要在缺少决策时改写存储层。

## 7. 可直接复制给下一模型的接手提示词

“请先阅读当前项目的 `AGENTS.md`、`docs/HANDOFF.md`、`docs/PROJECT_STATUS.md`、`docs/ARCHITECTURE.md`、`docs/DEVELOPMENT.md` 和 `docs/DEPENDENCIES.md`，再检查 `git status --short`。连接性本地证据：MNE-Connectivity 是与 MNE-Python 分开的依赖，连接 extra 已明确声明；Windows x64 Python 3.11 和 3.12 的最新 wheel 在隔离环境安装验证，全量 Qt-offscreen 测试136项通过，固定 FIF 的五种连接方法此前已完成保存/重载。安装版 `luna-diagnose --self-test-connectivity` 逐项执行七种 MNE-Connectivity 方法，诊断报告已修复完整路径脱敏。用户没有其他电脑或 Mac 诊断报告，因此远端故障根因未确认。macOS Apple Silicon/Intel、远端 CI 和真实桌面 GUI/DPI仍未验证；不要把它们写成通过。本任务不提交、不推送。”
