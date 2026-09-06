# 分阶段实施与验收记录

## 阶段 0：工作区与环境

状态：已完成。

- 当前工作区：`C:\Users\PC\Documents\ChatGPT\LID_Tetrode_Analysis`。
- Python：本地 `.venv`，Python 3.11.9。
- 当前仓库只有本地 Git；本项目不自动上传 GitHub。
- 实际样例文件作为只读输入保留在用户提供的位置，不复制、不覆盖。
- 方法核对：MNE-Connectivity 0.9.0 文档、FOOOF 1.1.1 文档、SciPy Welch 文档。

## 阶段 1：FIF 读取、元数据接口和质量检查

状态：已完成并在真实样例上运行。

真实样例输入：

`C:\Users\PC\Desktop\94\LID-94\T80\LID-T80_all_channels-epo.fif`

核验结果：

- SHA-256：`2751bce6cdad2a17d7ba72978b0b59221f8265dd27d9c77a8e77600ed75a0582`
- 文件大小：6,722,922 bytes。
- 实际数组：`21 × 16 × 5000`；1000 Hz；epoch 时间 0–4.999 s。
- `drop_log` 候选条目 25 个，其中 4 个为 `USER` 删除，保留 21 个 epoch；有效时长 105 s。
- 通道名：`TETFP01–08`、`TETFP17–24`；类型均为 `seeg`；MNE unit code 107（V）。
- 用户随后确认物理编号/脑区映射：1–4=M1、5–8=STR、17–20=PF、21–24=SNr；半球和电极几何仍留空。代码按实际通道名匹配，不按数组位置猜测。
- 质量：0 个 fail epoch×channel 行；1 个 warn 行（TETFP21，saved epoch 14，异常幅度标记）。
- 没有动物身份、session、给药登记或 AIMs，因此未运行动物层统计，也未生成行为结论。

输出目录：

`results/real_LID-T80/`

其中包括 `run_manifest.json`、`epochs_trace.csv`、`traceability/events_raw.json`、`selection.json`、`drop_log.json`、质量表、通道 PSD、频段功率和 PNG/SVG 图。

## 阶段 2：PSD、频段功率和基础图

状态：已完成并在真实样例与合成信号上运行。

- Welch 参数来自 `configs/default.yaml`，暂作为起步建议，不是已确认实验参数。
- 逐 epoch × 通道估计 PSD，再输出通道汇总；无脑区映射时脑区汇总为空。
- PSD/频段结果保留源单位；当前样例为 `V^2/Hz` 和 `V^2`，相对功率为 fraction。
- 合成验证：10 Hz 主峰识别在 10 Hz；有效时长 30 s；频段积分与非有限值跳过均通过测试。

## 阶段 3：specparam/FOOOF 与跨脑区连接

状态：specparam/FOOOF、首版功能连接和 PyBispectra 时间延迟分析已在真实 T80 样例上完成单文件验证。Granger/时间反转校正仍关闭。

- 默认使用 specparam fixed、无 knee 模型，拟合范围为配置中的 2–150 Hz；参数化只接受文件/给药时点内的汇总 PSD，失败记录保留。
- T80 实际结果：16/16 通道拟合成功，95 个周期峰，2,384 行逐频率模型曲线；R²、MAE、offset、exponent 以及峰参数均写入结果表。FOOOF 兼容后端也已用真实 PSD 的两个通道独立验证成功。
- 输出目录：`results/real_LID-T80_parameterized/`，包括 `parameterization_model.csv`、`parameterization_peaks.csv`、`parameterization_curves.csv`、`parameterization_failures.csv` 和 PNG/SVG 拟合图。
- `metadata/channel_map.csv` 已按用户确认的物理编号填入：1–4=M1、5–8=STR、17–20=PF、21–24=SNr；代码按实际通道名匹配。
- 连接估计只跨同一文件/记录节点/给药时点内的有效 epoch，不拼接不连续 epoch；当前 T80 使用 21 个有效 epoch和 105 s 有效时长。
- 使用 MNE-Connectivity 0.9.0 的 multitaper `spectral_connectivity_epochs`：MIC/MIM 为真正的多变量脑区集合估计；wPLI 使用全部跨脑区通道对，脑区汇总首版为有效通道对中位数。
- 当前真实 T80 结果：六组脑区对均生成 MIC、MIM 和 wPLI 频谱；M1/STR/PF 选择维度为3，SNr为2（数据驱动 99% 方差规则）；这些是该文件的质量/降维描述，不是跨动物统计结论。
- MIC 保留有符号原值，同时用绝对值表示连接强度；MIM 保留未归一化原值；wPLI 保留负的有限样本估计，不开平方、不截断为零。
- 已完成输入检查、频率/线噪声标记、epoch 稳定性、秩敏感性和合成信号基础验证；等量抽样在单文件上标记为不适用，因为没有多个条件节点可匹配。
- 时间延迟使用 PyBispectra Method I，并同时计算标准与 bispectral antisymmetrized 结果；所有六组脑区对均保留 16 个跨脑区通道对、7 个配置频段和完整延迟谱。
- TDE 仅在内部使用 `resample_poly` 从 1000 Hz 抗混叠降到 200 Hz；TDE 延迟窗口为 −1000–1000 ms，分辨率 5 ms，FFT 栅格约 0.499 Hz。原始 LFP、PSD、连接分析不受该降采样影响。
- T80 TDE 结果：21 个有效 epoch、105 s 有效时长、0 条 TDE 失败；完整谱 538,944 行，通道对峰汇总 1,344 行，频段/脑区汇总 84 行。质量标记中 55/84 个组合为 `ok`，其余为通道对离散或区域峰与通道对中位数不一致；这些结果仅作方法和质量核查，不作动物层结论。
- 采用 antisymmetrization 是为了检查共同噪声/瞬时混合导致的零延迟偏差；它不等于消除共同参考、信号混合或证明因果方向。正负号仅相对于 seed→target 的时间约定。

真实 T80 输出目录：

`results/real_LID-T80_connectivity/`

重点文件为 `connectivity_spectrum.csv`、`connectivity_region_summary.csv`、`connectivity_band_summary.csv`、`connectivity_rank_summary.csv`、`connectivity_rank_sensitivity.csv`、`connectivity_stability.csv`、`connectivity_input_checks.csv`、`connectivity_failures.csv` 及 `figures/connectivity_*.png|svg`。

## 阶段 4：批量和行为接口

状态：批量入口和节点级行为合并接口已建立，尚未有真实登记数据。

- 行为键为 animal × session × nominal dose time，不复制到 epoch 作为独立行为样本。连接结果已经保留有效 epoch 数和有效时长，可在身份登记后接入同一节点级行为表。
- TDE 结果也保留 animal/session/dose 节点所需的文件级追溯信息；目前尚未生成跨文件统一指标目录和动物层统计。
- 批量入口把无法解析、路径不存在和运行失败写入 `batch_manifest.csv`。

## 阶段 5：动物层比较

状态：未运行。

原因：当前只有一个未登记动物身份的 T80 文件。不能据此进行 LID 进展、LDN 配对、AIMs 关联或组间推断。
