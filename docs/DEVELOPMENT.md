# LUNA 本地开发与验证指南

本文件只记录当前可复现的入口、环境和验证边界。历史实现过程保留在 `docs/DEV_LOG.md`；当前功能状态以 `docs/PROJECT_STATUS.md` 和 `docs/HANDOFF.md` 为准。

## 1. 工作区与版本

项目根目录：`C:/Users/PC/Documents/ChatGPT/LID_Tetrode_Analysis`。

当前分支为 `master`，项目版本为 `0.3.0.dev2`；remote `origin` 指向 `https://github.com/dcgggg/LUNA.git`。本轮发布前工作区含项目 GUI、绘图、帮助文档、可选依赖诊断、跨平台路径和测试修改；最终提交 SHA 以发布后的 Git 记录为准。不得 reset、checkout、清理或覆盖这些修改；精确范围以 `git status --short` 为准。

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

中文分析读图说明和数据字典的唯一内容源为 `src/lfp_analysis/analysis_help_content.py`；更新后运行：

```powershell
.\.venv\Scripts\python.exe scripts/build_analysis_docs.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_analysis_help.py
```

## 跨系统项目路径

项目数据库与保存清单中的内部相对路径写为 `/` 分隔。读取器通过 `lfp_analysis.portable_paths` 同时接受旧 Windows `\` 路径，并拒绝绝对路径、`..` 与通过符号链接逃离项目目录的目标。移动整个项目时，项目内部复制的数据和 LUNA 结果可随项目重载；数据库若记录外部源文件，则仍须在新电脑显式重新定位，不能用同名文件自动替代。具体回归与平台限制见 `docs/PROJECT_STATUS.md` 最新的项目迁移条目。

GUI 的“如何读图”按钮及帮助菜单读取同一内容源，不需要联网或调用模型服务。

2026-09-28 本轮核实：项目 `.venv` Python 3.11 当前全量124项通过（含显式启用 Qt offscreen 窗口测试），Ruff、compileall、pip check、`git diff --check` 通过；另创建临时 Python 3.12.14 x64 环境，按 `.[desktop,dev]` 安装后既有全量120项测试、Ruff、compileall、依赖一致性均通过。固定只读文件 `C:/Users/PC/Documents/ChatGPT/testdata/LID-T80_all_channels-epo.fif` 哈希为 `2751bce6cdad2a17d7ba72978b0b59221f8265dd27d9c77a8e77600ed75a0582`，21×16×5000、1000 Hz，动物身份未解析。Python 3.12 环境又以显式 QC 通道分组运行 MIC/MIM/wPLI/dPLI/wPLI²-debiased，保存并重载完整连接 CSV 成功；样例源哈希未变。仅 GUI 的 Python 3.12 环境未安装所有可选分析后端，但 GUI PSD 分析、结果表与 manifest 保存/重载和关窗均通过。FOOOF 弃用、Matplotlib Qt 高 DPI 枚举弃用及连接表混合 metadata 的 pandas `DtypeWarning` 均如实保留。没有 macOS 主机；macOS 原生 GUI/数据流程仍未验证。

2026-09-28 补充跨平台依赖解析：临时 uv 解析器以 `--only-binary :all:` 分别为 macOS arm64/x86_64、Python 3.11/3.12 解析 `.[desktop,dev]`，四种目标均成功（每种52个包）。这是当前包索引下的预编译发行件解析证据，不代表这些 wheel 已在 macOS 安装、导入或运行。详见 `docs/DEPENDENCIES.md`。

2026-09-28 补充可选后端缺失行为：Windows x64/Python 3.12.14 临时 `.[gui]` 环境实际未安装 mne-connectivity、pybispectra、specparam、fooof，offscreen MainWindow 与固定只读 FIF 读取通过；MIC、TDE、FOOOF 禁用，PSD可用。完整错误诊断及本次修复见 `docs/DEV_LOG.md`。

2026-09-28 补充 CI 的 GUI 覆盖：原有四项 Qt 窗口测试曾在 `CI=true` 时无条件跳过。现在需设置 `LUNA_RUN_QT_TESTS=1` 才在 CI offscreen 环境启用，GitHub Actions 已设置该开关；新增合成 FIF GUI 集成检查，覆盖 MainWindow 异步导入、运行 PSD、保存结果并在新窗口载入历史结果。本机以 `CI=true`, `QT_QPA_PLATFORM=offscreen`, `LUNA_RUN_QT_TESTS=1` 执行全量 124 项通过。此为 Windows 本机 offscreen 证据，Mac runner 尚未运行。

2026-09-29 补充：当前 Windows x64/Python 3.11 全量 129 项通过；诊断器按 PySide6 子模块 API 核验 QtCore/QtWidgets。新增 `luna-diagnose --self-test-connectivity` 合成 smoke test，执行七种 MNE-Connectivity 方法并区分缺依赖/计算失败。当前 wheel 在全新 Python 3.11 venv 中仅安装 `.[desktop]` 后，`pip check`、诊断、GUI CLI 帮助和 PySide6 offscreen 主窗口创建/关闭通过，Logo/YAML 资源可用；同一隔离环境又用固定 FIF 完成五种 GUI 连接方法计算、保存和重载，身份未解析、通道使用临时 QC 标签。另一次纯诊断参数传入 FIF 时仅核对文件头，未载入样本。Ruff、compileall、pip check、git diff --check 通过；Mac 和远端故障机仍未验证。详情见 `docs/DEPENDENCIES.md` 与 `docs/DEV_LOG.md`。

2026-09-29 补充安装包回归：在全新 Windows wheel venv 中确认测试导入路径指向安装后的 `site-packages`，运行完整测试套件 129 passed、81 warnings（Matplotlib Qt 高 DPI 与 FOOOF 上游弃用，28.82秒）。这不是 macOS 或其他电脑验证。

2026-09-29 CI诊断附件：平台 smoke matrix 在每个 job 结束后上传脱敏的常规诊断与合成连接诊断 JSON，按 OS/Python 版本分开、保留7天。工作流仍是本地未提交改动，需远端触发后才能验证实际上传。

2026-09-29 核心版缺可选依赖验证：干净 Windows wheel venv 仅安装核心包时，`python -m lfp_analysis.diagnostics` 正常运行；连接自检标记 `dependency_unavailable`、指出 `.[connectivity]` 并退出2。`pip check` 通过，未读取真实数据。

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
