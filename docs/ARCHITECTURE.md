# LUNA 架构摘要

最后核查：2026-09-23。本文件描述当前代码的职责边界，不把规划功能当作已实现功能。

## 1. 入口和分层

| 层 | 主要入口 | 职责 |
|---|---|---|
| GUI | `scripts/run_gui.py`、`lfp_analysis.gui.MainWindow` | 文件/项目选择、检查配置、任务状态、绘图与结果复核 |
| GUI 编排 | `gui_engine.py`、`project_gui.py`、`project_batch.py` | 生成任务快照、调度后台任务、单条/批处理、恢复保存结果 |
| 计算核心 | `io.py`、`quality.py`、`spectral.py`、`parameterization.py`、`connectivity.py`、`time_delay.py` | 读取、QC、PSD/频带功率、谱参数化、连接和时间延迟 |
| 持久化 | `project_store.py`、`result_contract.py` | SQLite 层级、导入指纹、检查审计、任务索引、manifest/表/数组 |
| 外部读取 | `results_api.py`、`scripts/read_project_results.py` | 不启动 Qt 查询项目结果、提取表、导出长表 |

`gui.py`、`project_gui.py` 和 `project_store.py` 目前仍是大型聚合文件；这是维护风险，不等于当前计算错误。

## 2. 主要数据流

### 单条分析

FIF → `io.read_fif()`/`gui_engine.inspect_file()` → 通道、epoch、时间和脑区映射检查 → 固定任务参数快照 → `gui_engine.run_gui_analysis()` → 模块结果表/数组/图 → `result_contract` 原子写入 bundle → `ProjectStore` 建立 SQLite 结果索引 → GUI 显示或 `load_saved_run()` 恢复。

### 批量分析

`ProjectBatchRunner.create_job()` 从项目模板、批处理任务和数据单元覆盖生成每条记录的有效参数快照；`run()` 逐 data unit 读取源文件并调用同一 `run_gui_analysis()`。任务状态、错误、取消和可复用结果写入项目索引。数据层顺序执行，避免数据级并行与算法内部并行相乘。

### 外部结果读取

`ProjectResults` 通过 SQLite 找到 `analysis_id` 与 bundle 路径，读取 manifest、表或数组；`extract()` 按 channel、region、region pair 筛选，`to_long_table()` 保留稳定身份、指标、单位、汇总层级和质量字段。当前 GUI 不做跨数据配对、平均、组间统计或科研比较绘图。

## 3. 项目对象和身份

项目层级为：

```text
project → subject → session → state_record → data_unit → analysis_run
```

稳定 ID 和父子关系存入 SQLite；显示名称、文件名和树节点位置不是关联键。session 另有可跨被试匹配的 `session_key` 和显式 `sort_order`。数据单元保存来源路径类型、SHA-256、大小、通道/epoch 结构、检查修订、映射和分析覆盖。

导入默认将源文件复制到项目 `data/raw/`，复制前后校验大小和 SHA-256，保留原始来源路径；外部文件不被移动或改写。移动项目依赖项目相对路径；旧外部引用通过显式整理操作迁移。

## 4. 参数、检查与结果有效性

有效参数优先级为项目分析模板 → 批处理任务 → data unit 覆盖。数据单元检查快照另外冻结选中的通道、原始 epoch 身份、时间选择、脑区映射、检查状态和 revision/fingerprint。影响科学输入的检查、映射或分析参数变化会把当前结果标为 `needs_recompute`，但保留历史 `completed/saved` bundle；描述性 group、condition 等元数据不应无理由触发重算。

分析结果按 `luna-result-bundle/1.0` 保存。数值文件和 manifest 写入成功后才进入 SQLite 结果索引；保存失败不能标为成功。manifest 保留数据身份、参数、软件/依赖版本、通道/频率/时间坐标、选择快照和质量信息。旧 GUI run schema 1/2 可通过兼容读取，旧比较快照仍保留为兼容数据，不作为当前功能入口。

## 5. 项目保存边界

Project Manager 在首次编辑前建立 SQLite backup、恢复 marker 和文件快照；marker 通过临时文件写入、flush/fsync 后原子替换。编辑会即时写入当前数据库，第二个 `ProjectStore` 在 Save 前可见这些值；`Save project` 进行引用校验并清理 backup/marker，`Discard` 从 backup 恢复。异常退出后恢复流程会用初始目录快照识别 marker 尚未记录的新目录；清理只对安全路径调用 `rmdir()`，因此仅删除空目录，非空目录及其内容保留。该机制提供可恢复的草稿边界，但不是跨进程事务工作区。检查自动保存与分析结果自动保存独立于项目结构 Save。

非模态 Filter/export 窗口由创建它的 `ProjectWorkspace` 持有，并冻结项目/范围 ID。单独关闭时清理 owner 引用并在 Qt 延迟删除队列中销毁；ProjectWorkspace 只有在 Save/Discard 接受关闭后才关闭这些窗口，因此 Cancel 不改变辅助窗口状态。`MainWindow._attach_project()` 在切换项目时关闭并销毁旧的 manager/batch/review workspace；若 batch worker 正运行则拒绝切换，避免隐藏仍绑定旧 ProjectStore 的任务窗口。Import Preview、模板、映射和编辑器通过父窗口下的模态 `exec()` 运行；Import Preview 的目标以 state_record_id 冻结，不随背景树选择漂移。

## 6. 当前边界

真实样例的 animal/session/给药和行为身份未解析，不运行动物层推断。行为附件、评分和同步字段目前是结构化扩展存储，不处理视频或自动生成逐 epoch 同步。spike 未分析。Granger/时间反转若配置关闭则不应在状态中伪装为已完成。真实 Windows 原生鼠标、系统 DPI 和多显示器验收未在当前环境完成。
