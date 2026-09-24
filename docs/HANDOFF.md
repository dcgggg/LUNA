# LUNA 开发交接

核查日期：2026-09-23（北京时间）。本文件给下一次会话或下一模型优先阅读，内容依据当前工作区代码和本次命令结果，不依据聊天历史推断。

## 1. 产品目标与明确边界

LUNA（Local field potential Unified Network Analysis platform）当前目标是管理 project → subject → session → state → data unit，完成数据导入、来源追溯、通道/epoch/时间检查、脑区映射、单条和批量分析、结果保存/恢复、人工复核以及可供外部统计的筛选和导出。已有分析包括 FIF/QC、PSD、频带功率、FOOOF/specparam、功能连接和时间延迟。

软件内已明确取消跨数据 A/B、跨被试配对、组间/组内统计和科研比较绘图。旧 `comparison.py`、`comparison_snapshots` 表和历史比较文件仍作为兼容层，当前 GUI 不应重新提供入口。行为附件、评分和同步字段只表示扩展存储位置；视频处理、逐 epoch 行为同步和 spike 分析尚未实现。

## 2. 当前真实状态

当前版本为 `0.3.0.dev1`，分支 `master`，remote 为 `https://github.com/dcgggg/LUNA.git`。本次发布前工作区存在未提交修改，涉及 AGENTS/README/CHANGELOG、docs、`src/lfp_analysis/gui.py`、`project_gui.py`、`project_store.py`、`tests/test_project_store.py`，并有未跟踪 `docs/ARCHITECTURE.md`、`tests/test_project_draft.py`、`tests/test_project_manager_scope.py` 和 `docs/screenshots/`；最终提交 SHA 以发布后的 Git 记录为准。不得 reset、checkout、清理或覆盖这些修改。

当前项目数据库 schema 为 6。稳定 ID 和父子关系在 SQLite；目录树使用可读名称。导入默认复制到项目 `data/raw/`，以大小和 SHA-256 校验，外部源文件不移动。结果使用 `luna-result-bundle/1.0`，数值文件和 manifest 成功写入后才登记；检查、映射或科学参数变化会把当前结果标为 `needs_recompute`，历史结果仍可读取。

主要状态：项目管理、模板、导入、检查配置、结果 bundle、批处理、Review、Filter/export 已有代码和测试/离屏证据；单条和批处理共用 `gui_engine.run_gui_analysis()`。固定真实样例的文件级运行已验证，但其 animal/session/给药/行为身份未解析，不能做动物层推断。当前 GUI 的原生 Windows 鼠标、实体 DPI、多显示器和视频同步仍未验证。

## 3. 环境、入口与验证

解释器：`.venv\Scripts\python.exe`；Python 3.11.9。关键版本：NumPy 2.4.6、SciPy 1.17.1、pandas 2.3.3、Matplotlib 3.11.1、MNE 1.12.1、MNE-Connectivity 0.9.0、specparam 2.0.0rc7、FOOOF 1.1.1、PyBispectra 1.3.2、PySide6 6.11.2、pytest 8.4.2、Ruff 0.16.6。

GUI 入口：`scripts/run_gui.py`；CLI：`python -m lfp_analysis.cli`；PyCharm 辅助入口：`scripts/run_single_file.py`；结果读取：`scripts/read_project_results.py` 或 `src/lfp_analysis/results_api.py`。标准验证为：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m compileall -q src tests scripts
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

本次结果为 103 项测试通过，Ruff、compileall、pip check、diff check 通过；仅有 FOOOF 第三方弃用警告。固定只读测试文件 `C:\Users\PC\Documents\ChatGPT\testdata\LID-T80_all_channels-epo.fif` 读取为 21×16×5000、1000 Hz、4 个非空 `drop_log` 条目、有效时长 105 s；本轮读取前后 SHA-256 一致，文件身份仍未解析。项目管理范围联动在 Qt offscreen 中有交互测试和真实样例只读登记/打开信号验证；当前 Computer Use 没有暴露原生 Windows 应用窗口，因此实体鼠标和 DPI 仍未验证。

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

“请先阅读当前项目的 `AGENTS.md`、`docs/HANDOFF.md`、`docs/PROJECT_STATUS.md`、`docs/ARCHITECTURE.md` 和 `docs/DEVELOPMENT.md`，再检查 `git status --short`。Project Manager 的可恢复草稿回归已覆盖崩溃、重开、第二读取者、目录保护和 schema 5→6 迁移。先由产品明确草稿期间第二读取者可见元数据是否可接受；若要求 Save 前隔离，再设计单独 draft DB/提交流程，写明数据文件、结果写入、异常恢复的边界并增补测试。不要改分析算法、默认参数或真实 FIF，不要未经授权 commit/push。”
