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
- 物理编号/脑区映射仍未在登记表确认，输出中留空；没有按数组位置或名称自动推断。
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

状态：接口已建立，默认关闭，尚未对真实样例作科研解释。

- 参数化只接受文件/给药时点内的汇总 PSD；失败记录保留。
- 连接需确认 `channel_map.csv` 后运行；连接估计只跨有效 epoch，不拼接不连续 epoch。
- 真实样例当前没有脑区映射，因此不应运行六组脑区连接结果。

## 阶段 4：批量和行为接口

状态：批量入口和节点级行为合并接口已建立，尚未有真实登记数据。

- 行为键为 animal × session × nominal dose time，不复制到 epoch 作为独立行为样本。
- 批量入口把无法解析、路径不存在和运行失败写入 `batch_manifest.csv`。

## 阶段 5：动物层比较

状态：未运行。

原因：当前只有一个未登记动物身份的 T80 文件。不能据此进行 LID 进展、LDN 配对、AIMs 关联或组间推断。

