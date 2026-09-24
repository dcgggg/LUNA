# LUNA 本地开发与验证指南

本文件只记录当前可复现的入口、环境和验证边界。历史实现过程保留在 `docs/DEV_LOG.md`；当前功能状态以 `docs/PROJECT_STATUS.md` 和 `docs/HANDOFF.md` 为准。

## 1. 工作区与版本

项目根目录：`C:/Users/PC/Documents/ChatGPT/LID_Tetrode_Analysis`。

当前分支为 `master`，版本为 `0.3.0.dev1`。本地工作区存在本次发布前的未提交修改，接手时不得 reset、checkout、清理或覆盖；最终提交 SHA 以发布后的 Git 记录为准。当前修改涉及 `AGENTS.md`、README、CHANGELOG、项目文档、`gui.py`、`project_gui.py`、`project_store.py`、项目存储测试以及未跟踪的 `docs/screenshots/`；具体以 `git status --short` 为准。

## 2. 环境

解释器：

```powershell
Set-Location C:/Users/PC/Documents/ChatGPT/LID_Tetrode_Analysis
.\.venv\Scripts\python.exe
```

项目要求 Python `>=3.11,<3.13`。本次核实版本为：Python 3.11.9、NumPy 2.4.6、SciPy 1.17.1、pandas 2.3.3、Matplotlib 3.11.1、MNE 1.12.1、MNE-Connectivity 0.9.0、specparam 2.0.0rc7、FOOOF 1.1.1、PyBispectra 1.3.2、PySide6 6.11.2、pytest 8.4.2、Ruff 0.16.6。依赖范围和可选组见 `pyproject.toml`，锁定快照见 `requirements-lock.txt`。

## 3. 入口与验证

GUI：

```powershell
.\.venv\Scripts\python.exe scripts/run_gui.py --help
.\.venv\Scripts\python.exe scripts/run_gui.py --input C:/path/to/file-epo.fif
```

命令行：

```powershell
.\.venv\Scripts\python.exe -m lfp_analysis.cli --help
.\.venv\Scripts\python.exe -m lfp_analysis.cli single-file --input C:/path/to/file-epo.fif --config configs/default.yaml --output C:/Temp/luna_run
.\.venv\Scripts\python.exe -m lfp_analysis.cli batch --help
```

无 GUI 结果读取：

```powershell
.\.venv\Scripts\python.exe scripts/read_project_results.py C:/path/to/luna_project --module PSD
```

标准检查：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m compileall -q src tests scripts
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

最近一轮核实上述检查均通过：103 项测试通过，Ruff、compileall、pip check 和 `git diff --check` 通过；FOOOF 兼容后端有第三方弃用警告。`scripts/run_gui.py --help`、`scripts/read_project_results.py --help` 通过。固定只读文件为 `C:/Users/PC/Documents/ChatGPT/testdata/LID-T80_all_channels-epo.fif`，历史读取结果为 21×16×5000、1000 Hz、4.999 s/epoch，4 个非空 `drop_log` 条目，身份仍未解析。真实 Windows 鼠标、系统 DPI 和多显示器不在本环境的验证范围内。

## 4. 主要调用链

`scripts/run_gui.py` 进入 `lfp_analysis.gui.launch()`；`MainWindow` 负责控件、项目入口、后台任务和结果页面，耗时工作通过 `gui_engine.py` 编排。CLI 和项目批处理分别进入 `pipeline.py` 与 `project_batch.py`，最终复用 `gui_engine.run_gui_analysis()`。数值核心在 `spectral.py`、`parameterization.py`、`connectivity.py`、`time_delay.py` 和 `quality.py`；绘图在各模块的 `*_plots.py` 及 GUI view 类中。

数据流为：FIF → `io.py` 读取与结构指纹 → 质量/检查快照和通道映射 → 任务参数快照 → 公共计算核心 → 结果表/数组/manifest → `ProjectStore` SQLite 索引 → GUI 恢复或 `ProjectResults`/CSV/JSON 外部读取。单条与批处理不应各自复制算法。

## 5. 项目数据与保存边界

项目层级为 project → subject → session → state record → data unit，稳定 ID 保存在 SQLite，目录树显示可读名称。导入默认复制到项目 `data/raw/` 并校验大小和 SHA-256；源文件不移动、不覆盖。schema 当前为 6，旧项目按迁移逻辑读取。

项目管理编辑前创建本地 SQLite backup 和日志 marker，编辑内容会即时写入当前数据库；`Save project` 当前承担校验、清理备份并确认草稿的作用，`Discard` 使用备份恢复并清理本次新建的安全空目录。这是可恢复草稿边界，不是跨进程事务工作区。检查记录和分析结果自动保存是独立流程。分析结果使用 `luna-result-bundle/1.0`，manifest 与数值文件完成后才索引为成功；检查/映射等科学输入变化会把当前结果标为 `needs_recompute`，历史 bundle 保留。

参数优先级为项目模板 → 批处理任务 → 数据单元覆盖；通道、epoch、时间和 mapping 由数据单元检查快照注入。显示参数不应触发重算，影响科学结果的参数变化必须失效相关结果。

## 6. 产品范围与边界

当前 GUI 支持项目管理、模板/导入、数据检查、PSD、频带功率、FOOOF/specparam、功能连接、时间延迟、批处理、结果复核、结果恢复和记录筛选/导出。当前 GUI 已取消跨数据 A/B、跨被试配对、组间/组内统计和跨记录科研比较；旧 `comparison.py`、比较表和历史文件仅作兼容读取。组级统计由外部脚本或 notebook 通过保存结果完成。行为附件、评分和同步字段是扩展存储位置，不代表已实现视频处理或逐 epoch 同步。spike 不在当前分析范围内。

## 7. 接手规则

先读 `docs/HANDOFF.md`、`docs/PROJECT_STATUS.md`、`docs/ARCHITECTURE.md` 和本文件，再查看 `git status --short`。不要把历史 DEV_LOG、截图或聊天需求当作当前实现证明；任何新结论都要说明代码证据、运行证据和未验证边界。提交或推送必须得到当前任务的明确授权。
