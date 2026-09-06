# 小鼠多脑区同步 tetrode LFP 分析

这是一个本地、可追溯、模块化的 Python 分析项目。当前仓库已经用用户提供的 T80 FIF 样例完成单文件验证；真实实验登记仍需继续补齐。因此当前实现提供：

- FIF 读取与数据结构核查；
- 物理通道名/编号/脑区映射接口，不按数组位置推断物理通道；
- `events`、`selection`、`drop_log` 原样留存；
- 不连续 epoch 的质量检查和实际有效时长计算；
- 逐 epoch × 通道 Welch PSD、频段绝对/相对功率；
- 文件级结果表、质量汇总和基础 PNG/SVG 图；
- 合成信号标定测试；
- specparam/FOOOF 参数化、跨 epoch 连接、行为、统计和批量运行接口。

真实实验身份、给药安排、AIMs 和视频同步信息缺失时，代码不会自动补造，也不会将未匹配文件纳入动物层级统计。LDN 保留为独立药物字段，名称、剂量和安排为空时保持为空。

## 当前环境

建议使用当前目录的 Python 3.11 虚拟环境：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[all]"
```

本项目也会记录可复现的锁定依赖：

```powershell
python -m pip freeze | Out-File -Encoding utf8 requirements-lock.txt
```

## 目录约定

```text
data/
  real/                 # 本地真实 FIF；默认不提交
  synthetic/            # 明确标记的合成验证数据
metadata/               # 登记模板、字段字典、通道映射模板
configs/                # 可编辑分析配置
src/lfp_analysis/       # 计算模块和 CLI
notebooks/              # 可逐步执行的 Notebook
tests/                  # 算法和边界测试
results/                # 运行生成，默认不提交
```

## 第一阶段运行

### 合成数据标定

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m lfp_analysis.cli validate-synthetic --output results/synthetic_validation
```

合成数据仅用于测试频率识别、功率积分、epoch 边界和不连续时长处理，不代表实验结果。

### 单文件 FIF

将 FIF 放入 `data/real/`，先编辑 `metadata/channel_map.csv` 和相关登记表，再运行：

```powershell
.\.venv\Scripts\python.exe -m lfp_analysis.cli single-file \
  --input data/real/LID-T80_all_channels-epo.fif \
  --config configs/default.yaml \
  --output results/LID-T80
```

Windows PowerShell 中可把反斜杠续行改为单行命令。若 `animal_id` 等身份字段为空，文件级质量/频谱/参数化仍可运行，但动物层统计会明确标记为不可用。

默认配置已启用 specparam 参数化（fixed、无 knee，拟合范围 2–150 Hz）。该范围和峰参数均只是可编辑的起步配置，不是已确认的生理频段边界。参数化输出包括：

- `parameterization_model.csv`：每个汇总通道一行，含 offset、exponent、峰拟合质量；
- `parameterization_peaks.csv`：周期峰的中心频率、峰高和带宽；
- `parameterization_curves.csv`：观测 PSD、完整模型、非周期背景、周期成分和残差；
- `parameterization_failures.csv`：失败或低质量记录，不静默删除；
- `figures/parameterization_fit.(png|svg)` 和 `figures/parameterization_components.(png|svg)`。

如需使用旧版 FOOOF 后端，把配置中的 `parameterization.backend` 改为 `fooof`；两种后端都写入相同的结果表结构。推荐新项目优先使用 specparam。

### 批量入口

```powershell
.\.venv\Scripts\python.exe -m lfp_analysis.cli batch \
  --files metadata/files.csv \
  --config configs/default.yaml \
  --output results/batch
```

批量入口只处理登记表中路径存在且身份/键不冲突的文件；所有跳过原因写入运行日志和 `batch_manifest.csv`。

## 已知限制

- T80 样例已经核验 16 个通道名称和 MNE 单位，但物理编号/脑区映射、动物编号、session、给药天数、AIMs 和视频同步仍未登记。
- 采样率、epoch 长度、Welch 窗长/重叠、频段边界以及质量阈值都在配置中作为“起步建议”，不是已确认实验参数。
- 默认不再次滤波、陷波、重参考或强清洗；质量标记不会静默删除数据。
- 参数化是在文件/给药时点内按通道汇总 PSD 上拟合，尚未实现逐 5 秒 epoch 动态拟合。
- 连接需要确认 `channel_map.csv` 后运行；不会将单个 5 秒 epoch 当成可靠跨 epoch 连接估计。
- 本阶段不做 LID/LDN 组间推断或 AIMs 统计；这需要真实动物编号、记录节点、实际给药后时间和行为关联信息。

## 官方方法依据

- MNE-Connectivity 的 `spectral_connectivity_epochs` 文档：输入为多个 epoch，频谱连接跨 epoch 估计；单个或很少 epoch 的估计不可靠，结果不能直接作因果解释。
- FOOOF/specparam 文档：模型输入为正确尺度的功率谱，输出非周期背景和周期峰参数；本项目不以一条直线替代参数化模型。
- SciPy `welch` 文档：`nperseg`、`noverlap`、窗口、`scaling` 等均在配置文件中明确记录。
