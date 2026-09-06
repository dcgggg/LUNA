# 小鼠多脑区同步 tetrode LFP 分析

这是一个本地、可追溯、模块化的 Python 分析项目。当前仓库已经用用户提供的 T80 FIF 样例完成单文件验证；真实实验登记仍需继续补齐。因此当前实现提供：

- FIF 读取与数据结构核查；
- 物理通道名/编号/脑区映射接口，不按数组位置推断物理通道；
- `events`、`selection`、`drop_log` 原样留存；
- 不连续 epoch 的质量检查和实际有效时长计算；
- 逐 epoch × 通道 Welch PSD、频段绝对/相对功率；
- 文件级结果表、质量汇总和基础 PNG/SVG 图；
- 合成信号标定测试；
- specparam/FOOOF 参数化；基于多个有效 epoch 的 MIC、MIM 和去偏平方 wPLI 连接分析；行为、统计和批量运行接口。

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

### 单文件功能连接

当前配置已根据用户确认的物理通道范围启用四脑区映射：物理 1–4 为 M1、5–8 为 STR、17–20 为 PF、21–24 为 SNr。映射保存在 `metadata/channel_map.csv`；代码按物理通道名匹配，不按数组位置猜测。若换用新数据，先核对该表并将不适用的行留空或另建映射。

运行同一条 `single-file` 命令即可生成连接结果：

```powershell
.\.venv\Scripts\python.exe -m lfp_analysis.cli single-file `
  --input "C:\path\to\your-epochs.fif" `
  --config configs\default.yaml `
  --output results\your-file
```

连接首版在同一文件/记录节点/给药时点内使用全部有效 epoch；不拼接不连续 epoch。默认频率范围为配置中的 2–100 Hz，multitaper 参数、排除的 50/60 Hz 线噪声频点、频段和降维规则都写入 `configs/default.yaml`。这些是可复核的起步设置，不是已经验证的小鼠生理边界。

主要输出包括：

- `connectivity_spectrum.csv`：MIC、MIM 和 `wpli2_debiased` 的完整频谱；MIC 同时保留有符号原值和用于强度展示的绝对值；wPLI 保留有限样本下可能出现的负估计值。
- `connectivity_region_summary.csv`：多变量脑区对结果，以及 wPLI 的逐通道对结果；不把通道对当成动物样本。
- `connectivity_band_summary.csv`：按配置频段汇总的脑区对结果；wPLI 首版使用有效通道对的中位数，同时保留通道对数量。
- `connectivity_redundancy_correlation.csv`、`connectivity_redundancy_singular_values.csv`、`connectivity_rank_summary.csv`：四通道相关矩阵、奇异值/方差贡献和保留维度。
- `connectivity_rank_sensitivity.csv`、`connectivity_stability.csv`、`connectivity_input_checks.csv`：维度敏感性、片段稳定性、数据量/频率边界/质量检查。
- `connectivity_patterns.csv`：MNE 提供的 MIC/MIM 空间 pattern（若可用）；它们不是通道生物学贡献权重。
- `connectivity_failures.csv` 和 `connectivity_metadata.json`：失败原因、有效 epoch 数、有效时长、频率栅格和实际估计设置。
- `figures/connectivity_*.png` 与 `figures/connectivity_*.svg`：冗余/秩图、三种方法频谱、频段矩阵、wPLI 通道对矩阵和秩敏感性图。

当前 Granger/时间反转校正默认关闭；只有在基础连接、有效秩和稳定性检查通过后再扩展。单个未登记动物身份的文件只生成文件级描述性结果，不自动进入动物层统计。

### 批量入口

```powershell
.\.venv\Scripts\python.exe -m lfp_analysis.cli batch \
  --files metadata/files.csv \
  --config configs/default.yaml \
  --output results/batch
```

批量入口只处理登记表中路径存在且身份/键不冲突的文件；所有跳过原因写入运行日志和 `batch_manifest.csv`。

## 已知限制

- T80 样例已经核验 16 个通道名称、MNE 单位和用户确认的物理编号/脑区映射；动物编号、session、给药天数、AIMs 和视频同步仍未登记。
- 采样率、epoch 长度、Welch 窗长/重叠、频段边界以及质量阈值都在配置中作为“起步建议”，不是已确认实验参数。
- 默认不再次滤波、陷波、重参考或强清洗；质量标记不会静默删除数据。
- 参数化是在文件/给药时点内按通道汇总 PSD 上拟合，尚未实现逐 5 秒 epoch 动态拟合。
- 连接已在当前 T80 样例上运行；不会将单个 5 秒 epoch 当成可靠跨 epoch 连接估计。T80 本次重新核验为 21 个有效 epoch、105 s 有效时长，而不是把 5 秒片段拼成连续记录。
- 当前 `mne-connectivity` 为 0.9.0；该版本的 multitaper 结果属性未提供可用的 `n_tapers` 数值，因此结果表保留为空，不自行编造 tapers 数量。
- 当前只有一个身份未解析的 T80 文件，尚未运行 LID/LDN 比较、AIMs 关联或动物层统计；Granger 默认关闭。
- 本阶段不做 LID/LDN 组间推断或 AIMs 统计；这需要真实动物编号、记录节点、实际给药后时间和行为关联信息。

## 官方方法依据

- MNE-Connectivity 的 `spectral_connectivity_epochs` 文档：输入为多个 epoch，频谱连接跨 epoch 估计；单个或很少 epoch 的估计不可靠，结果不能直接作因果解释。
- FOOOF/specparam 文档：模型输入为正确尺度的功率谱，输出非周期背景和周期峰参数；本项目不以一条直线替代参数化模型。
- SciPy `welch` 文档：`nperseg`、`noverlap`、窗口、`scaling` 等均在配置文件中明确记录。
