# LUNA 保存结果与指标数据字典

## 如何定位一条结果

项目结果使用 `luna-result-bundle/1.0`。SQLite 项目索引提供查询，bundle `manifest.json` 保存该次运行的稳定 ID、输入指纹、实际参数、映射、选择、依赖、表/数组坐标与状态。外部 Python 读取优先使用 `lfp_analysis.results_api.ProjectResults`，不要仅按显示名称或文件名配对。

项目层级：`project_id → subject_id → session_id → state_record_id → data_unit_id → analysis_id`。CLI 文件级输出没有自动补齐缺失动物/session 身份。`calculation_status`（是否完成）、`save_status`（是否落盘成功）和 `result_validity`（是否仍与当前检查/参数一致）是不同概念。

## 文件角色

| 文件/对象 | 角色与说明 |
|---|---|
| 输入 FIF | 原始/预处理 epoch 信号来源；读取只读，不由输出目录替换。项目导入策略可复制到项目 data/raw，外部引用不移动。 |
| run_manifest.json / file_manifest.json | 文件级或 GUI 运行身份、输入哈希、结构、实际选区、状态、警告与结果路径索引。 |
| config_used.yaml / effective_parameters | CLI 保存传入配置文件副本；若含 extends，不代表已展开的完整配置。CLI manifest 当前只含配置审计、部分范围和状态；项目 result bundle 的 effective_parameters 才是完整运行参数快照。关键实际参数也分别保存在结果表和模块 metadata。 |
| channel_table.csv | 数组索引、真实通道名、物理通道编号、映射脑区和 MNE 单位码；不可用数组位置猜物理编号。 |
| epochs_trace.csv + traceability/{events_raw,selection,drop_log}.json | 保存 epoch/候选段追溯；原始 events 未被擅自解释为记录时间。 |
| quality_*.csv / inspection_snapshot | 自动检查摘要和用户检查配置；标记与纳入/排除决定要区分。原始文件不因标记而删除。 |
| 科学结果 CSV | 长表保存逐 epoch、通道、频率、脑区对、成分、峰或延迟点的数值与状态。下表列出实际文件级输出及行粒度。 |
| psd_arrays.npz / connectivity_arrays.npz | PSD 数组含 selected_data(epoch,channel,time)、psd(epoch,channel,frequency) 及对应频率/epoch/通道坐标；连接 NPZ 是与 connectivity_spectrum.csv 逐行对齐的一维字段数组，不是 4×4 矩阵。manifest 记录 shape、axes、单位与数值空间。 |
| PNG / SVG 图 | 预览与可编辑矢量图；是数值结果的可视摘要，不替代表格/数组。显示平滑表仅供显示。 |
| project SQLite | 项目层级、导入关联、检查快照、运行索引与筛选；科学结果具体数值以 bundle 表/数组为准。 |
| 缓存/计算调用记录 | 调用记录可说明估计任务和耗时；缓存或临时预览不是独立科学结果。CLI 本次连接估计未使用计算缓存。 |

## 运行清单与身份/状态字段

| 字段 | 含义 |
|---|---|
| `analysis_id / analysis_run_id` | 一次分析运行的稳定标识；重算会创建新运行，不覆盖历史结果。 |
| `project_id / subject_id / session_id / state_record_id / data_unit_id` | 项目层级稳定身份；缺失身份不得由文件名或树节点位置猜补。 |
| `source / file_uid / input_sha256 / data_fingerprint` | 输入路径/文件标识与数据指纹；用于说明结果来源及检查是否为同一输入。 |
| `selection / inspection_snapshot / channel_mapping` | 实际纳入的 epoch、通道/时间选择、检查快照和通道—脑区映射。 |
| `effective_parameters / parameter_fingerprint` | 项目 result bundle 中的生效参数及指纹；单文件 CLI run_manifest 当前可能没有完整快照，需同时核对 config_used、configuration_audit、结果表及模块 metadata。 |
| `dependencies / software_version / schema_version` | 计算环境依赖版本、LUNA 版本和结果契约版本。 |
| `calculation_status / save_status / bundle_complete` | 计算与落盘状态彼此独立；bundle_complete 只有计算完成且保存成功才为真。 |
| `result_validity（项目 SQLite）` | 当前结果是否仍与检查/计算输入一致；needs_recompute 表示需重算，旧 bundle 仍保留。该字段由项目索引管理，不等于历史数据文件损坏。 |
| `tables / arrays / quality_summary / warnings` | 表格、数组、维度/单位、质量摘要与警告路径；manifest 是结果目录索引，不代替具体数值表。 |

## NPZ 数组维度与坐标

| 文件/数组 | 形状与坐标 |
|---|---|
| `selected_data.npz:data` | `(epoch, channel, time)`；同文件保存 `sfreq`、`times`、`epoch_indices` 和 `channel_indices`。|
| `psd_arrays.npz:selected_data` | `(epoch, channel, time)`；数组来自本次选择，另保存 `sfreq`、`epoch_indices` 和 `channel_array_indices`；采样点可按 `sfreq` 换算为 epoch 内相对时间，非零起点需查运行元数据。|
| `psd_arrays.npz:psd` | `(epoch, channel, frequency)`；`frequencies`、`epoch_indices`、`channel_array_indices` 分别标注各轴；值为线性 PSD。|
| `connectivity_arrays.npz` | 多个一维数组按 `connectivity_spectrum.csv` 行顺序逐行对应；同时保存 method、脑区、通道、方向、频率、raw/strength、rank、epoch 数及遮罩标记。需按 CSV 中的身份字段筛选，不能当作三维规则矩阵。|
| TDE | 当前结果以 CSV 长表为主，不生成 TDE NPZ 数组。|

## 文件级 CSV：行粒度与列定义

列名采用代码/实际输出的英文原名。数值科学字段有精确定义；索引、参数、单位、质量及运行字段属于追溯元数据。字段定义可在下列每个表的列清单中查找。

### `batch_manifest.csv`

模块：批量运行元数据。每行：批处理清单中每个输入文件一行。

| 字段 | 含义 |
|---|---|
| `row_index` | 保存数组/表中的零基或明确标注的序号；不等同于物理通道编号或动物编号。 |
| `file_id` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `file_uid` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `file_path` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `status` | 程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。 |
| `reason` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `output_dir` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |

### `metadata_validation.csv`

模块：元数据校验。每行：每条元数据检查发现一行；无问题时为空表但仍保留列名。

| 字段 | 含义 |
|---|---|
| `table` | 发生校验问题的元数据表名；追溯字段，不是科学量。 |
| `severity` | 元数据校验严重级别；具体错误或提醒见 code/message。 |
| `code` | 稳定的元数据校验规则代码；不是生理指标。 |
| `message` | 面向用户的校验问题说明。 |
| `row` | 被校验表中的行定位信息；不是 epoch 或动物样本编号。 |

### `channel_table.csv`

模块：通道与脑区映射。每行：每个文件通道一行。

| 字段 | 含义 |
|---|---|
| `array_index` | 通道在输入数据数组中的零基位置；结合 channel_table 映射到物理通道。 |
| `channel_name` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `mne_channel_type` | MNE 读取到的通道类型标签，不改变实验对象身份。 |
| `mne_unit_code` | MNE 单位枚举码；只有单位映射明确时才可换算。 |
| `physical_channel_number` | 从实际通道名称或已确认映射得到的物理编号，不由数组位置推断。 |
| `region` | 用户确认的通道所属脑区/区域名称；不由数组索引自动推定。 |
| `hemisphere` | 通道映射中记录的侧别标签；未知时留空。 |
| `probe_or_tetrode` | 通道所属探针或 tetrode 的登记标签；缺失不代表不存在。 |
| `mapping_status` | 通道到物理通道/脑区映射的核实状态。 |

### `epochs_trace.csv`

模块：epoch 追溯。每行：每个上游候选 epoch 一行。

| 字段 | 含义 |
|---|---|
| `file_id` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `saved_index` | 保存数组/表中的零基或明确标注的序号；不等同于物理通道编号或动物编号。 |
| `original_candidate_index` | 保存数组/表中的零基或明确标注的序号；不等同于物理通道编号或动物编号。 |
| `events_raw_value` | epoch/原始事件追溯索引或原始值；除非另有已确认时间坐标，不解释为原始记录秒数。 |
| `selection_value` | epoch/原始事件追溯索引或原始值；除非另有已确认时间坐标，不解释为原始记录秒数。 |
| `confirmed_time_start_s` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `confirmed_time_end_s` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `quality_status` | 自动检查的 fail/warn/ok 状态，不等于人工复核结论。 |
| `quality_flags` | 自动检查触发的具体规则标签；空列表不等同于人工确认正常。 |
| `drop_reason` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `time_coordinate_note` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |

### `quality_epoch_channel.csv`

模块：质量检查。每行：每个 epoch×通道一行。

| 字段 | 含义 |
|---|---|
| `epoch_index` | 保存数组/表中的零基或明确标注的序号；不等同于物理通道编号或动物编号。 |
| `channel_array_index` | 通道在当前输入数组中的索引；不等于物理通道编号。 |
| `channel_name` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `finite_sample_count` | 片段中有限（非 NaN/Inf）样本数。 |
| `nonfinite_sample_count` | 片段中 NaN 与 Inf 样本总数。 |
| `std` | 对应信号片段的标准差，单位沿用输入信号。 |
| `max_abs` | 片段绝对幅值最大值，单位沿用输入信号。 |
| `max_abs_robust_z` | 最大绝对稳健标准分，用于异常幅度提示。 |
| `saturation_fraction` | 样本等于该片段最大值或最小值的比例，用于疑似饱和提示。 |
| `line_noise_peak_ratio` | 配置工频候选频率附近峰相对局部 PSD 中位基线的比值。 |
| `quality_status` | 自动检查的 fail/warn/ok 状态，不等于人工复核结论。 |
| `quality_flags` | 自动检查触发的具体规则标签；空列表不等同于人工确认正常。 |
| `issue_score` | 该 epoch×通道触发的质量标记数量，不表示严重程度。 |

### `quality_epoch.csv`

模块：质量检查。每行：每个保存 epoch 一行。

| 字段 | 含义 |
|---|---|
| `epoch_index` | 保存数组/表中的零基或明确标注的序号；不等同于物理通道编号或动物编号。 |
| `n_channels` | 对应文件、脑区或统计行内通道数量；上下文由表名与同一行 region 决定。 |
| `n_fail_channels` | 该 epoch 中被判为 fail 的通道数。 |
| `n_warn_channels` | 该 epoch 中被标为 warn 的通道数。 |
| `min_finite_samples` | 该 epoch 各通道中最少的有限采样点数。 |
| `max_issue_score` | 该 epoch 中单个通道最大的 issue_score；是标记数，不是异常严重程度。 |
| `valid_duration_s` | 对应 epoch 的有限有效样本数除以采样率得到的有效时长（秒）。 |
| `quality_status` | 自动检查的 fail/warn/ok 状态，不等于人工复核结论。 |

### `quality_channel.csv`

模块：质量检查。每行：每个通道一行。

| 字段 | 含义 |
|---|---|
| `channel_array_index` | 通道在当前输入数组中的索引；不等于物理通道编号。 |
| `channel_name` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `n_epochs` | 参与该行汇总/估计的 epoch 数；不是独立动物数。 |
| `n_fail_epochs` | 该通道中包含 fail 标记的 epoch 数；可能与其他通道统计不同。 |
| `n_warn_epochs` | 该通道中包含 warn 标记的 epoch 数。 |
| `mean_std` | 跨 epoch 标准差的均值摘要，单位沿用输入信号。 |
| `max_abs` | 片段绝对幅值最大值，单位沿用输入信号。 |
| `max_issue_score` | 该 epoch 中单个通道最大的 issue_score；是标记数，不是异常严重程度。 |

### `quality_file.csv`

模块：质量检查。每行：每个文件一行。

| 字段 | 含义 |
|---|---|
| `n_epochs` | 参与该行汇总/估计的 epoch 数；不是独立动物数。 |
| `n_channels` | 对应文件、脑区或统计行内通道数量；上下文由表名与同一行 region 决定。 |
| `n_times` | 每段保存的时间样本数。 |
| `sampling_rate_hz` | 输入数据采样率，单位 Hz。 |
| `nominal_duration_s` | 按输入 epoch 数×每 epoch 时长计算的名义累计时长；不表示连续采集时长。 |
| `effective_valid_duration_s` | 质量筛选后有效记录时长（秒）；不表示这些 epoch 首尾连续。 |
| `n_fail_epoch_channel_rows` | 质量表中 fail 状态的 epoch×通道记录数，不是 fail epoch 数或动物数。 |
| `n_warn_epoch_channel_rows` | 质量表中 warn 状态的 epoch×通道记录数。 |
| `n_duplicate_epoch_rows` | 被重复片段检测标记的 epoch 记录数；不自动删除原始 epoch。 |
| `duplicate_epoch_detection` | 本次是否执行重复 epoch 检查；True 不表示发现重复，发现数量另见 n_duplicate_epoch_rows。 |
| `check_frequency_band_hz` | 质量检查针对的频率范围，单位 Hz；不是自动滤波或频段功率范围。 |
| `frequency_band_check_status` | 对该频率范围的质量检查状态/说明，不代表信号已被滤除。 |

### `psd_epoch_channel.csv`

模块：PSD。每行：每个 epoch×通道×频率一行。

| 字段 | 含义 |
|---|---|
| `epoch_index` | 保存数组/表中的零基或明确标注的序号；不等同于物理通道编号或动物编号。 |
| `channel_array_index` | 通道在当前输入数组中的索引；不等于物理通道编号。 |
| `channel_name` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `frequency_hz` | 频率坐标，单位 Hz。 |
| `psd_value` | 线性功率谱密度值；scaling=density 时单位为输入单位²/Hz。 |
| `status` | 程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。 |
| `nperseg_used` | Welch 实际每个子窗样本数，影响频率网格和估计稳定性。 |
| `noverlap_used` | Welch 子窗之间重叠样本数。 |
| `nfft_used` | Welch FFT 点数；零填充可加密频率栅格但不提高真实分辨能力。 |
| `frequency_resolution_hz` | 记录的 PSD 基础频率间隔，单位 Hz；零填充后的网格可能更密但不提高真实分辨能力。 |
| `psd_method` | PSD 估计方法标签，如 Welch 或 multitaper。 |
| `multitaper_bandwidth_hz` | multitaper 平滑带宽，单位 Hz；影响平滑程度与 taper 数。 |
| `multitaper_adaptive` | 是否启用自适应 taper 权重。 |
| `multitaper_low_bias` | 是否启用低偏差 taper 筛选。 |
| `multitaper_normalization` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_remove_dc` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_n_jobs` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_batch_input_shape` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_batch_call_count` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_batch_mode` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `source_unit` | 输入信号单位标签；未知或 MNE 枚举码不应猜成微伏。 |
| `psd_unit` | PSD 单位声明；density 时为输入信号单位平方每 Hz。 |

### `psd_channel_summary.csv`

模块：PSD。每行：每个通道×频率一行。

| 字段 | 含义 |
|---|---|
| `channel_array_index` | 通道在当前输入数组中的索引；不等于物理通道编号。 |
| `channel_name` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `frequency_hz` | 频率坐标，单位 Hz。 |
| `psd_value` | 线性功率谱密度值；scaling=density 时单位为输入单位²/Hz。 |
| `psd_sd` | 各 epoch 在同一通道、同一频率处 PSD 的标准差。 |
| `n_epochs` | 参与该行汇总/估计的 epoch 数；不是独立动物数。 |
| `psd_method` | PSD 估计方法标签，如 Welch 或 multitaper。 |
| `frequency_resolution_hz` | 记录的 PSD 基础频率间隔，单位 Hz；零填充后的网格可能更密但不提高真实分辨能力。 |
| `nperseg_used` | Welch 实际每个子窗样本数，影响频率网格和估计稳定性。 |
| `noverlap_used` | Welch 子窗之间重叠样本数。 |
| `nfft_used` | Welch FFT 点数；零填充可加密频率栅格但不提高真实分辨能力。 |
| `multitaper_bandwidth_hz` | multitaper 平滑带宽，单位 Hz；影响平滑程度与 taper 数。 |
| `multitaper_adaptive` | 是否启用自适应 taper 权重。 |
| `multitaper_low_bias` | 是否启用低偏差 taper 筛选。 |
| `multitaper_normalization` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_remove_dc` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_n_jobs` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_batch_input_shape` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_batch_call_count` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_batch_mode` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `source_unit` | 输入信号单位标签；未知或 MNE 枚举码不应猜成微伏。 |
| `psd_unit` | PSD 单位声明；density 时为输入信号单位平方每 Hz。 |

### `psd_region_summary.csv`

模块：PSD。每行：每个已映射脑区×频率一行。

| 字段 | 含义 |
|---|---|
| `region` | 用户确认的通道所属脑区/区域名称；不由数组索引自动推定。 |
| `frequency_hz` | 频率坐标，单位 Hz。 |
| `psd_value` | 线性功率谱密度值；scaling=density 时单位为输入单位²/Hz。 |
| `psd_sd_across_channels` | 同一脑区同频率的通道 PSD 间标准差，不是动物间误差。 |
| `n_channels` | 对应文件、脑区或统计行内通道数量；上下文由表名与同一行 region 决定。 |
| `n_epoch_channel_estimates` | 该脑区 PSD 汇总中参与的 epoch×通道估计数量，不是独立被试数。 |
| `psd_method` | PSD 估计方法标签，如 Welch 或 multitaper。 |
| `frequency_resolution_hz` | 记录的 PSD 基础频率间隔，单位 Hz；零填充后的网格可能更密但不提高真实分辨能力。 |
| `nperseg_used` | Welch 实际每个子窗样本数，影响频率网格和估计稳定性。 |
| `noverlap_used` | Welch 子窗之间重叠样本数。 |
| `nfft_used` | Welch FFT 点数；零填充可加密频率栅格但不提高真实分辨能力。 |
| `multitaper_bandwidth_hz` | multitaper 平滑带宽，单位 Hz；影响平滑程度与 taper 数。 |
| `multitaper_adaptive` | 是否启用自适应 taper 权重。 |
| `multitaper_low_bias` | 是否启用低偏差 taper 筛选。 |
| `multitaper_normalization` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_remove_dc` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_n_jobs` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_batch_input_shape` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_batch_call_count` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_batch_mode` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `source_unit` | 输入信号单位标签；未知或 MNE 枚举码不应猜成微伏。 |
| `psd_unit` | PSD 单位声明；density 时为输入信号单位平方每 Hz。 |

### `band_power_epoch_channel.csv`

模块：频带功率。每行：每个 epoch×通道×频带一行。

| 字段 | 含义 |
|---|---|
| `epoch_index` | 保存数组/表中的零基或明确标注的序号；不等同于物理通道编号或动物编号。 |
| `channel_array_index` | 通道在当前输入数组中的索引；不等于物理通道编号。 |
| `channel_name` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `band` | 配置中的频带名称；边界以同一行 band_low_hz/band_high_hz 为准。 |
| `band_low_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `band_high_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `absolute_power` | 该 epoch、通道、频带的 PSD 梯形积分，单位为输入单位²。 |
| `relative_power` | 频带绝对功率除以指定分母范围功率；文件中保存比例，GUI 可换算百分数。 |
| `relative_denominator_low_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `relative_denominator_high_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `excluded_frequency_count` | 按配置未参与该频带或分母积分的频率点数。 |
| `frequency_step_hz` | 相邻频点的典型间隔，单位 Hz；不能单独代表谱平滑/实际分辨率。 |
| `band_frequency_segments` | 实际参与频带积分的连续频率区间。 |
| `band_max_gap_hz` | 积分保留频点之间观测到的最大间隙，单位 Hz。 |
| `denominator_frequency_segments` | 实际参与相对功率分母积分的连续频率区间。 |
| `denominator_max_gap_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `integration_rule` | 频带/分母功率积分算法及是否跨缺口的规则标签。 |
| `status` | 程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。 |
| `source_unit` | 输入信号单位标签；未知或 MNE 枚举码不应猜成微伏。 |
| `absolute_power_unit` | 绝对积分功率单位，通常是输入信号单位的平方。 |
| `relative_power_unit` | 相对功率数值单位；fraction 为比例，显示百分数时乘100。 |

### `parameterization_model.csv`

模块：FOOOF/specparam。每行：每个通道一次 PSD 拟合；成功、低质量及失败行均保留。

| 字段 | 含义 |
|---|---|
| `channel_array_index` | 通道在当前输入数组中的索引；不等于物理通道编号。 |
| `channel_name` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `source_unit` | 输入信号单位标签；未知或 MNE 枚举码不应猜成微伏。 |
| `psd_unit` | PSD 单位声明；density 时为输入信号单位平方每 Hz。 |
| `psd_method` | PSD 估计方法标签，如 Welch 或 multitaper。 |
| `frequency_resolution_hz` | 记录的 PSD 基础频率间隔，单位 Hz；零填充后的网格可能更密但不提高真实分辨能力。 |
| `nperseg_used` | Welch 实际每个子窗样本数，影响频率网格和估计稳定性。 |
| `noverlap_used` | Welch 子窗之间重叠样本数。 |
| `nfft_used` | Welch FFT 点数；零填充可加密频率栅格但不提高真实分辨能力。 |
| `multitaper_bandwidth_hz` | multitaper 平滑带宽，单位 Hz；影响平滑程度与 taper 数。 |
| `multitaper_adaptive` | 是否启用自适应 taper 权重。 |
| `multitaper_low_bias` | 是否启用低偏差 taper 筛选。 |
| `multitaper_normalization` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_remove_dc` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_n_jobs` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `backend_requested` | 配置请求的谱参数化后端。 |
| `backend_used` | 实际调用的参数化后端实现/类名。 |
| `aperiodic_mode` | 非周期模型模式（如 fixed/knee），决定模型参数定义。 |
| `fit_status` | 拟合是否成功的状态；失败行保留，不应读取空参数为零。 |
| `fit_quality_status` | 按配置拟合质量门槛得到的状态标签。 |
| `peak_status` | 峰检出状态；区分有效拟合无峰与拟合失败。 |
| `n_peaks` | 该通道拟合实际检出的峰数；零表示拟合成功但未检出峰。 |
| `failure_reason` | 拟合/估计失败原因；状态字段与原因字段需结合查看。 |
| `backend_warning` | 后端兼容或降级提示；须与 backend_used 一起查看。 |
| `r_squared` | 后端拟合优度统计量；不是生理效应量或显著性。 |
| `error` | 后端定义的谱拟合误差，具体标度依赖所用后端版本。 |
| `offset` | 非周期模型的 log10 截距；会随 PSD 功率单位改变。 |
| `exponent` | 非周期固定背景随频率变化的指数斜率参数，无量纲；不能直接等同兴奋/抑制平衡。 |
| `knee` | knee 模型的弯折参数；仅 knee 模式适用，量纲依赖后端模型定义。 |
| `min_r_squared_requested` | 本次拟合配置的最低 R² 质量门槛；是筛查参数，不是显著性阈值。 |
| `min_peak_prominence_requested` | 配置请求的最小峰突出度值；是否真正传入当前后端需查看 min_peak_prominence_status 与 configuration_audit，不能仅凭此列认定它影响了拟合。 |
| `min_peak_prominence_status` | 峰突出度门槛的可用性/检查状态；不是峰功率结果。 |
| `fit_low_hz` | 谱参数化拟合频率下界，单位 Hz。 |
| `fit_high_hz` | 谱参数化拟合频率上界，单位 Hz。 |
| `n_frequency_bins` | 拟合输入中通过有效筛选的频率格点数。 |

### `parameterization_failures.csv`

模块：FOOOF/specparam 失败记录。每行：parameterization_model 中 fit_status 非成功的通道行；无失败时为空表但保留完整列。

| 字段 | 含义 |
|---|---|
| `channel_array_index` | 通道在当前输入数组中的索引；不等于物理通道编号。 |
| `channel_name` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `source_unit` | 输入信号单位标签；未知或 MNE 枚举码不应猜成微伏。 |
| `psd_unit` | PSD 单位声明；density 时为输入信号单位平方每 Hz。 |
| `psd_method` | PSD 估计方法标签，如 Welch 或 multitaper。 |
| `frequency_resolution_hz` | 记录的 PSD 基础频率间隔，单位 Hz；零填充后的网格可能更密但不提高真实分辨能力。 |
| `nperseg_used` | Welch 实际每个子窗样本数，影响频率网格和估计稳定性。 |
| `noverlap_used` | Welch 子窗之间重叠样本数。 |
| `nfft_used` | Welch FFT 点数；零填充可加密频率栅格但不提高真实分辨能力。 |
| `multitaper_bandwidth_hz` | multitaper 平滑带宽，单位 Hz；影响平滑程度与 taper 数。 |
| `multitaper_adaptive` | 是否启用自适应 taper 权重。 |
| `multitaper_low_bias` | 是否启用低偏差 taper 筛选。 |
| `multitaper_normalization` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_remove_dc` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_n_jobs` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `backend_requested` | 配置请求的谱参数化后端。 |
| `backend_used` | 实际调用的参数化后端实现/类名。 |
| `aperiodic_mode` | 非周期模型模式（如 fixed/knee），决定模型参数定义。 |
| `fit_status` | 拟合是否成功的状态；失败行保留，不应读取空参数为零。 |
| `fit_quality_status` | 按配置拟合质量门槛得到的状态标签。 |
| `peak_status` | 峰检出状态；区分有效拟合无峰与拟合失败。 |
| `n_peaks` | 该通道拟合实际检出的峰数；零表示拟合成功但未检出峰。 |
| `failure_reason` | 拟合/估计失败原因；状态字段与原因字段需结合查看。 |
| `backend_warning` | 后端兼容或降级提示；须与 backend_used 一起查看。 |
| `r_squared` | 后端拟合优度统计量；不是生理效应量或显著性。 |
| `error` | 后端定义的谱拟合误差，具体标度依赖所用后端版本。 |
| `offset` | 非周期模型的 log10 截距；会随 PSD 功率单位改变。 |
| `exponent` | 非周期固定背景随频率变化的指数斜率参数，无量纲；不能直接等同兴奋/抑制平衡。 |
| `knee` | knee 模型的弯折参数；仅 knee 模式适用，量纲依赖后端模型定义。 |
| `min_r_squared_requested` | 本次拟合配置的最低 R² 质量门槛；是筛查参数，不是显著性阈值。 |
| `min_peak_prominence_requested` | 配置请求的最小峰突出度值；是否真正传入当前后端需查看 min_peak_prominence_status 与 configuration_audit，不能仅凭此列认定它影响了拟合。 |
| `min_peak_prominence_status` | 峰突出度门槛的可用性/检查状态；不是峰功率结果。 |
| `fit_low_hz` | 谱参数化拟合频率下界，单位 Hz。 |
| `fit_high_hz` | 谱参数化拟合频率上界，单位 Hz。 |
| `n_frequency_bins` | 拟合输入中通过有效筛选的频率格点数。 |

### `parameterization_peaks.csv`

模块：FOOOF/specparam。每行：每个检测到的高斯峰一行。

| 字段 | 含义 |
|---|---|
| `channel_array_index` | 通道在当前输入数组中的索引；不等于物理通道编号。 |
| `channel_name` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `source_unit` | 输入信号单位标签；未知或 MNE 枚举码不应猜成微伏。 |
| `psd_unit` | PSD 单位声明；density 时为输入信号单位平方每 Hz。 |
| `psd_method` | PSD 估计方法标签，如 Welch 或 multitaper。 |
| `frequency_resolution_hz` | 记录的 PSD 基础频率间隔，单位 Hz；零填充后的网格可能更密但不提高真实分辨能力。 |
| `nperseg_used` | Welch 实际每个子窗样本数，影响频率网格和估计稳定性。 |
| `noverlap_used` | Welch 子窗之间重叠样本数。 |
| `nfft_used` | Welch FFT 点数；零填充可加密频率栅格但不提高真实分辨能力。 |
| `multitaper_bandwidth_hz` | multitaper 平滑带宽，单位 Hz；影响平滑程度与 taper 数。 |
| `multitaper_adaptive` | 是否启用自适应 taper 权重。 |
| `multitaper_low_bias` | 是否启用低偏差 taper 筛选。 |
| `multitaper_normalization` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_remove_dc` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_n_jobs` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `peak_index` | 通道内检出峰的零基序号；不同通道同序号不代表同一种振荡。 |
| `center_frequency_hz` | 拟合峰中心频率 CF，单位 Hz。 |
| `peak_height_log10` | 后端导出的峰高度；当前代码按与 peak_power_log10 同一对数功率差解释。 |
| `peak_power_log10` | 拟合峰高于非周期背景的 log10 功率差，不是原始 PSD 峰值或频带积分。 |
| `bandwidth_hz` | 当前结果契约采用高斯 2σ 带宽，单位 Hz；不是 FWHM。 |
| `gaussian_sigma_hz` | 一个拟合高斯峰在该频点的 log10 加性贡献；N 为峰序号，缺少的峰列为空。 |
| `bandwidth_definition` | 带宽字段的算法定义；本项目 FOOOF 峰带宽按 2σ 记录。 |
| `fit_status` | 拟合是否成功的状态；失败行保留，不应读取空参数为零。 |
| `fit_quality_status` | 按配置拟合质量门槛得到的状态标签。 |
| `r_squared` | 后端拟合优度统计量；不是生理效应量或显著性。 |
| `error` | 后端定义的谱拟合误差，具体标度依赖所用后端版本。 |
| `fit_low_hz` | 谱参数化拟合频率下界，单位 Hz。 |
| `fit_high_hz` | 谱参数化拟合频率上界，单位 Hz。 |

### `parameterization_curves.csv`

模块：FOOOF/specparam。每行：每个通道×拟合频率一行。

| 字段 | 含义 |
|---|---|
| `channel_array_index` | 通道在当前输入数组中的索引；不等于物理通道编号。 |
| `channel_name` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `source_unit` | 输入信号单位标签；未知或 MNE 枚举码不应猜成微伏。 |
| `psd_unit` | PSD 单位声明；density 时为输入信号单位平方每 Hz。 |
| `psd_method` | PSD 估计方法标签，如 Welch 或 multitaper。 |
| `frequency_resolution_hz` | 记录的 PSD 基础频率间隔，单位 Hz；零填充后的网格可能更密但不提高真实分辨能力。 |
| `nperseg_used` | Welch 实际每个子窗样本数，影响频率网格和估计稳定性。 |
| `noverlap_used` | Welch 子窗之间重叠样本数。 |
| `nfft_used` | Welch FFT 点数；零填充可加密频率栅格但不提高真实分辨能力。 |
| `multitaper_bandwidth_hz` | multitaper 平滑带宽，单位 Hz；影响平滑程度与 taper 数。 |
| `multitaper_adaptive` | 是否启用自适应 taper 权重。 |
| `multitaper_low_bias` | 是否启用低偏差 taper 筛选。 |
| `multitaper_normalization` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_remove_dc` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `multitaper_n_jobs` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `frequency_hz` | 频率坐标，单位 Hz。 |
| `observed_power` | 进入谱参数化的线性 PSD；单位沿用 PSD。 |
| `observed_log10_power` | 观测 PSD 的 log10 值。 |
| `full_model_power` | 非周期背景与周期峰完整拟合模型反变换到线性功率密度空间的值。 |
| `full_model_log10_power` | 完整模型在 log10 PSD 空间的值。 |
| `aperiodic_power` | 拟合的非周期背景反变换到线性 PSD 空间的值。 |
| `aperiodic_log10_power` | 非周期背景在 log10 PSD 空间的值。 |
| `periodic_component_power` | 完整拟合模型线性功率减非周期背景线性功率；可因拟合重建而为负，不是独立物理振荡谱。 |
| `periodic_component_log10_additive` | 拟合高斯周期峰在 log10 空间的加性和。 |
| `periodic_model_log10` | 同一周期高斯峰加和的模型曲线，处于 log10 功率差空间。 |
| `observed_minus_aperiodic_log10` | log10(观测 PSD) 减 log10(非周期背景)，包含未解释起伏，可能为负。 |
| `reconstructed_gaussian_sum_log10` | 使用真实高斯中心、振幅和 sigma 重建后相加的峰曲线。 |
| `residual_log10` | 观测 log10 PSD 减完整模型 log10 PSD。 |
| `periodic_component_negative` | 线性模型差值在该频点是否为负；不是负的物理功率。 |
| `fit_status` | 拟合是否成功的状态；失败行保留，不应读取空参数为零。 |
| `fit_quality_status` | 按配置拟合质量门槛得到的状态标签。 |
| `backend_used` | 实际调用的参数化后端实现/类名。 |
| `gaussian_0_log10…gaussian_N_log10` | 一个拟合高斯峰在该频点的 log10 加性贡献；N 为峰序号，缺少的峰列为空。 |

### `connectivity_spectrum.csv`

模块：功能连接。每行：连接方向/通道对或多变量区域对×频率×方法×成分一行。

| 字段 | 含义 |
|---|---|
| `region_a` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `region_b` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `seed_region` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `target_region` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `direction_order` | 有向估计的 seed/source 到 target 的输入顺序标签；不是生物因果方向。 |
| `method` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `aggregation_level` | 本行连接是通道对层级还是脑区/多变量汇总层级。 |
| `seed_channel` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `target_channel` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `seed_channels` | seed 侧实际参与估计的通道名称列表。 |
| `target_channels` | target 侧实际参与估计的通道名称列表。 |
| `n_seed_channels` | seed 集合实际参与估计的通道数。 |
| `n_target_channels` | target 集合实际参与估计的通道数。 |
| `rank_seed` | seed 集合在多变量估计中保留的维度数。 |
| `rank_target` | target 集合在多变量估计中保留的维度数。 |
| `component_index` | MIC 分量序号；不自动表示跨频率固定的生理源身份。 |
| `n_components_requested` | MIC 请求提取的连接分量数；不控制 MIM 总相互作用。 |
| `n_components_returned` | 后端实际返回的 MIC 分量数。 |
| `frequency_hz` | 频率坐标，单位 Hz。 |
| `value_raw` | 方法原始输出；符号和值域按 method 定义，不要跨方法直接比较。 |
| `value_nonfinite_type` | 区分有限值、NaN 或 Inf 的类型标签；不是对非有限值的替代。 |
| `value_strength` | 用于展示的强度字段；MIC 为 abs(value_raw)，其他方法保留其方法原生值。 |
| `display_value_definition` | 显示值从原始结果转换而来的规则，如 MIC 取绝对值。 |
| `estimate_note` | 关于原始估计值、符号和值域的补充说明。 |
| `n_epochs` | 参与该行汇总/估计的 epoch 数；不是独立动物数。 |
| `effective_duration_s` | 参与本行计算的有效片段总时长（秒），按保留 epoch 数×每段有效时长计算。 |
| `frequency_is_excluded_line_noise` | 该频率是否被配置为工频排除点。 |
| `spectral_mode` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `mt_bandwidth_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `mt_adaptive` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `mt_low_bias` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `n_tapers` | 实际使用的 DPSS taper 数。 |
| `time_bandwidth_product` | multitaper 时间—带宽积参数。 |
| `n_tapers_note` | 关于 multitaper 实际 taper 数计算或适用性的说明文本。 |
| `estimated_rank_metadata` | 后端返回的 rank 元数据原样记录；需结合 rank_seed/rank_target 读取。 |
| `frequency_grid_hz` | 连接输出频率栅格的典型步长，单位 Hz；不等同于 multitaper 平滑带宽。 |
| `n_channel_pairs_total` | 该脑区对全部可用通道对数量。 |
| `frequency_is_masked_for_analysis` | 该频率在分析汇总中是否被屏蔽。 |
| `frequency_is_masked_for_plot` | 该频率是否仅在绘图显示中被遮罩。 |
| `line_noise_mask_source` | 工频绘图或分析遮罩来源；被遮罩不等于原始数值被删除。 |
| `line_noise_mask_reason` | 工频遮罩理由；与计算缺失、NaN 和估计失败分开。 |

### `connectivity_region_summary.csv`

模块：功能连接。每行：方法×脑区对×频率×MIC成分（若有）一行。

| 字段 | 含义 |
|---|---|
| `method` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `region_a` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `region_b` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `component_index` | MIC 分量序号；不自动表示跨频率固定的生理源身份。 |
| `frequency_hz` | 频率坐标，单位 Hz。 |
| `value_raw` | 方法原始输出；符号和值域按 method 定义，不要跨方法直接比较。 |
| `value_strength` | 用于展示的强度字段；MIC 为 abs(value_raw)，其他方法保留其方法原生值。 |
| `n_channel_pairs` | 参与区域汇总的通道对数，不是动物数。 |
| `n_negative_estimates` | 频带/频率聚合前出现的负有限估计数；对于去偏平方 wPLI 不代表负耦合。 |
| `aggregation_definition` | 跨频率/通道对的实际聚合顺序与函数说明。 |
| `n_epochs` | 参与该行汇总/估计的 epoch 数；不是独立动物数。 |
| `effective_duration_s` | 参与本行计算的有效片段总时长（秒），按保留 epoch 数×每段有效时长计算。 |
| `rank_seed` | seed 集合在多变量估计中保留的维度数。 |
| `rank_target` | target 集合在多变量估计中保留的维度数。 |
| `frequency_is_excluded_line_noise` | 该频率是否被配置为工频排除点。 |
| `spectral_mode` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `mt_bandwidth_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `mt_adaptive` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `mt_low_bias` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `n_tapers` | 实际使用的 DPSS taper 数。 |
| `n_components_requested` | MIC 请求提取的连接分量数；不控制 MIM 总相互作用。 |
| `n_components_returned` | 后端实际返回的 MIC 分量数。 |

### `connectivity_band_summary.csv`

模块：功能连接。每行：方法×脑区对×频带×MIC成分（若有）一行。

| 字段 | 含义 |
|---|---|
| `method` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `region_a` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `region_b` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `component_index` | MIC 分量序号；不自动表示跨频率固定的生理源身份。 |
| `band` | 配置中的频带名称；边界以同一行 band_low_hz/band_high_hz 为准。 |
| `band_low_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `band_high_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `value_raw_or_summary` | 频带汇总表字段；须结合 aggregation_definition、method 和方向字段解释。 |
| `value_strength` | 用于展示的强度字段；MIC 为 abs(value_raw)，其他方法保留其方法原生值。 |
| `aggregation_definition` | 跨频率/通道对的实际聚合顺序与函数说明。 |
| `n_channel_pairs` | 参与区域汇总的通道对数，不是动物数。 |
| `n_frequencies_used` | 频带汇总中实际纳入的频点数。 |
| `n_frequencies_excluded_line_noise` | 因工频规则排除的频点数。 |
| `frequency_coverage_fraction` | 频带中实际纳入频点相对可用频点的覆盖比例。 |
| `n_epochs` | 参与该行汇总/估计的 epoch 数；不是独立动物数。 |
| `effective_duration_s` | 参与本行计算的有效片段总时长（秒），按保留 epoch 数×每段有效时长计算。 |
| `rank_seed` | seed 集合在多变量估计中保留的维度数。 |
| `rank_target` | target 集合在多变量估计中保留的维度数。 |
| `n_components_requested` | MIC 请求提取的连接分量数；不控制 MIM 总相互作用。 |
| `n_components_returned` | 后端实际返回的 MIC 分量数。 |
| `status` | 程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。 |

### `connectivity_channel_pair_band_summary.csv`

模块：功能连接。每行：有序通道对×频带×方法一行。

| 字段 | 含义 |
|---|---|
| `method` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `region_a` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `region_b` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `seed_region` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `target_region` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `direction_order` | 有向估计的 seed/source 到 target 的输入顺序标签；不是生物因果方向。 |
| `seed_channel` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `target_channel` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `band` | 配置中的频带名称；边界以同一行 band_low_hz/band_high_hz 为准。 |
| `band_low_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `band_high_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `value_raw_or_summary` | 频带汇总表字段；须结合 aggregation_definition、method 和方向字段解释。 |
| `value_strength` | 用于展示的强度字段；MIC 为 abs(value_raw)，其他方法保留其方法原生值。 |
| `aggregation_definition` | 跨频率/通道对的实际聚合顺序与函数说明。 |
| `n_frequencies_used` | 频带汇总中实际纳入的频点数。 |
| `n_frequencies_excluded_line_noise` | 因工频规则排除的频点数。 |
| `frequency_coverage_fraction` | 频带中实际纳入频点相对可用频点的覆盖比例。 |
| `n_epochs` | 参与该行汇总/估计的 epoch 数；不是独立动物数。 |
| `effective_duration_s` | 参与本行计算的有效片段总时长（秒），按保留 epoch 数×每段有效时长计算。 |
| `rank_seed` | seed 集合在多变量估计中保留的维度数。 |
| `rank_target` | target 集合在多变量估计中保留的维度数。 |
| `status` | 程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。 |

### `connectivity_patterns.csv`

模块：功能连接诊断。每行：MIC 脑区对×成分×通道×频率×模式角色一行。

| 字段 | 含义 |
|---|---|
| `region_a` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `region_b` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `method` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `component_index` | MIC 分量序号；不自动表示跨频率固定的生理源身份。 |
| `n_components_returned` | 后端实际返回的 MIC 分量数。 |
| `pattern_role` | MIC pattern 属于 seed 侧或 target 侧的角色标签。 |
| `channel_name` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `array_index` | 通道在输入数据数组中的零基位置；结合 channel_table 映射到物理通道。 |
| `frequency_hz` | 频率坐标，单位 Hz。 |
| `pattern_value` | MNE 返回的 MIC 空间模式数值；不是通道贡献率，也不是源定位。 |
| `pattern_note` | MIC pattern 的数据尺度/解释限制说明。 |

### `connectivity_redundancy_correlation.csv`

模块：连接诊断。每行：脑区内通道对一行。

| 字段 | 含义 |
|---|---|
| `region` | 用户确认的通道所属脑区/区域名称；不由数组索引自动推定。 |
| `channel_i` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `channel_j` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `array_index_i` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `array_index_j` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `correlation` | 指定通道样本/片段间的相关系数；用于冗余诊断，不是跨区连接指标。 |
| `n_valid_epochs` | 通过该模块有效性规则的 epoch 数；属于记录内数据量，不是动物样本量。 |
| `effective_valid_duration_s` | 质量筛选后有效记录时长（秒）；不表示这些 epoch 首尾连续。 |

### `connectivity_redundancy_singular_values.csv`

模块：连接诊断。每行：脑区×奇异维度一行。

| 字段 | 含义 |
|---|---|
| `region` | 用户确认的通道所属脑区/区域名称；不由数组索引自动推定。 |
| `component` | 保存数组/表中的零基或明确标注的序号；不等同于物理通道编号或动物编号。 |
| `singular_value` | 多通道数据矩阵的奇异值，描述一个线性数据方向的幅度。 |
| `variance_fraction` | 对应奇异维度占总方差的比例。 |
| `cumulative_variance_fraction` | 截至该奇异维度的累计方差比例。 |
| `numerical_rank` | 按记录的数值容差判断出的矩阵数值秩。 |
| `variance_rank` | 按当前方差比例规则得到的候选维数。 |
| `selected_rank` | 按当前可重复数值规则实际采用的脑区维度数，不等于生理最优维数。 |
| `rank_reason` | 实际选择 rank 的规则/依据说明。 |

### `connectivity_rank_summary.csv`

模块：连接诊断。每行：每个脑区一行。

| 字段 | 含义 |
|---|---|
| `region` | 用户确认的通道所属脑区/区域名称；不由数组索引自动推定。 |
| `channel_names` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `channel_array_indices` | 以分隔字符串保存的通道数组索引；逐项结合通道表映射。 |
| `n_channels` | 对应文件、脑区或统计行内通道数量；上下文由表名与同一行 region 决定。 |
| `n_valid_epochs` | 通过该模块有效性规则的 epoch 数；属于记录内数据量，不是动物样本量。 |
| `effective_valid_duration_s` | 质量筛选后有效记录时长（秒）；不表示这些 epoch 首尾连续。 |
| `n_finite_samples` | 对应对象的数量/样本数；它表示记录内部数量，不自动等于独立动物数。 |
| `numerical_rank` | 按记录的数值容差判断出的矩阵数值秩。 |
| `variance_rank` | 按当前方差比例规则得到的候选维数。 |
| `selected_rank` | 按当前可重复数值规则实际采用的脑区维度数，不等于生理最优维数。 |
| `rank_reason` | 实际选择 rank 的规则/依据说明。 |
| `rank_relative_tolerance` | 数值秩判定采用的相对奇异值容差；是计算规则参数，不是生理阈值。 |
| `rank_variance_threshold` | 自动 rank 候选维数的累计方差比例阈值。 |
| `covariance_condition_number` | 协方差矩阵条件数；较大提示多变量数值估计可能不稳定，不是连接强度。 |
| `all_channels_finite` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |

### `connectivity_rank_sensitivity.csv`

模块：连接诊断。每行：脑区对×方法×rank扰动×成分一行。

| 字段 | 含义 |
|---|---|
| `region_a` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `region_b` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `method` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `component_index` | MIC 分量序号；不自动表示跨频率固定的生理源身份。 |
| `rank_offset` | 敏感性分析中相对基准 rank 的变化量。 |
| `rank_seed` | seed 集合在多变量估计中保留的维度数。 |
| `rank_target` | target 集合在多变量估计中保留的维度数。 |
| `mean_strength_2_100hz` | 对应诊断列定义频率范围内强度的均值；按该行 method 解释。 |
| `max_strength_2_100hz` | 对应诊断列定义频率范围内强度的最大值；不是显著性。 |
| `n_epochs` | 参与该行汇总/估计的 epoch 数；不是独立动物数。 |
| `status` | 程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。 |

### `connectivity_stability.csv`

模块：连接诊断。每行：稳定性检查×子集×脑区对×方法一行。

| 字段 | 含义 |
|---|---|
| `check_type` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `status` | 程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。 |
| `note` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `subset_name` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `region_a` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `region_b` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `method` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `component_index` | MIC 分量序号；不自动表示跨频率固定的生理源身份。 |
| `mean_strength_2_100hz` | 对应诊断列定义频率范围内强度的均值；按该行 method 解释。 |
| `n_epochs` | 参与该行汇总/估计的 epoch 数；不是独立动物数。 |
| `effective_duration_s` | 参与本行计算的有效片段总时长（秒），按保留 epoch 数×每段有效时长计算。 |
| `direction_order` | 有向估计的 seed/source 到 target 的输入顺序标签；不是生物因果方向。 |
| `aggregation_definition` | 跨频率/通道对的实际聚合顺序与函数说明。 |
| `n_channel_pairs` | 参与区域汇总的通道对数，不是动物数。 |

### `connectivity_epoch_profile.csv`

模块：连接诊断。每行：每个候选连接 epoch 一行。

| 字段 | 含义 |
|---|---|
| `epoch_index` | 保存数组/表中的零基或明确标注的序号；不等同于物理通道编号或动物编号。 |
| `signal_rms` | 该连接 epoch 选定信号的均方根幅度摘要。 |
| `robust_z_vs_valid_epochs` | 该片段 RMS 相对有效 epoch 分布的稳健标准分，用于异质性提示，不是统计检验。 |
| `quality_valid_for_connectivity` | 该 epoch 是否符合该连接分析纳入规则；不是独立统计样本标签。 |
| `signal_heterogeneity_flag` | 按配置规则标记的信号异质性提示，需结合原始片段/行为信息复核。 |
| `flag_note` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |

### `connectivity_input_checks.csv`

模块：连接诊断。每行：每项输入检查一行。

| 字段 | 含义 |
|---|---|
| `check` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `value` | 表中保留的数值；请依赖同一行的 method、单位、summary/aggregation 和 status 解释。 |
| `status` | 程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。 |
| `note` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |

### `connectivity_failures.csv`

模块：功能连接。每行：每个失败连接/方法一行；无失败时为空表但保留列定义。

| 字段 | 含义 |
|---|---|
| `region_a` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `region_b` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `method` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `failure_reason` | 拟合/估计失败原因；状态字段与原因字段需结合查看。 |
| `n_epochs` | 参与该行汇总/估计的 epoch 数；不是独立动物数。 |
| `rank_seed` | seed 集合在多变量估计中保留的维度数。 |
| `rank_target` | target 集合在多变量估计中保留的维度数。 |
| `n_components_requested` | MIC 请求提取的连接分量数；不控制 MIM 总相互作用。 |

### `connectivity_frequency_diagnostics.csv`

模块：连接诊断。每行：方法×频率一行。

| 字段 | 含义 |
|---|---|
| `method` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `frequency_hz` | 频率坐标，单位 Hz。 |
| `plot_frequency_index` | 绘图频率轴中的序号；不是物理频率，实际 Hz 见 frequency_hz。 |
| `n_total_values` | 该方法/频率诊断组的总记录值数量。 |
| `n_finite` | 该诊断组中的有限数值数量。 |
| `n_nan` | 该诊断组中的 NaN 数量；不等于真实零连接。 |
| `n_inf` | 该诊断组中的 Inf 数量。 |
| `is_masked` | 频率诊断中该点是否被指定遮罩；原因见 mask_reason。 |
| `mask_reason` | 频率点被遮罩或标记的理由。 |
| `processing_stage` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `mask_source` | 产生频率遮罩的配置/检测来源。 |
| `configuration_key` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |

### `connectivity_roughness.csv`

模块：连接诊断。每行：方法×脑区对×频率段一行。

| 字段 | 含义 |
|---|---|
| `method` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `region_a` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `region_b` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `component_index` | MIC 分量序号；不自动表示跨频率固定的生理源身份。 |
| `n_frequencies` | 该连接曲线所包含的频率点数；实际有效点数见 n_valid_points。 |
| `n_valid_points` | 某诊断/曲线组中通过有限值与遮罩筛选的点数。 |
| `median_abs_adjacent_diff` | 未屏蔽连续频点间相邻差绝对值的中位数，用于粗糙度诊断。 |
| `total_variation` | 未屏蔽连续频率段上的相邻差总变差。 |
| `coefficient_of_variation` | 粗糙度计算中的变异系数诊断值。 |
| `resampling_variability` | 稳定性/重采样诊断中估计变异摘要。 |
| `status` | 程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。 |

### `connectivity_band_cv.csv`

模块：连接诊断。每行：方法×脑区对×频带一行。

| 字段 | 含义 |
|---|---|
| `method` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `region_a` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `region_b` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `component_index` | MIC 分量序号；不自动表示跨频率固定的生理源身份。 |
| `band` | 配置中的频带名称；边界以同一行 band_low_hz/band_high_hz 为准。 |
| `band_low_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `band_high_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `n_valid_points` | 某诊断/曲线组中通过有限值与遮罩筛选的点数。 |
| `band_cv` | 频带内连接频率曲线的变异系数诊断。 |
| `status` | 程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。 |

### `connectivity_estimation_calls.csv`

模块：连接运行追溯。每行：每次后端谱估计调用一行。

| 字段 | 含义 |
|---|---|
| `analysis_task_id` | 一次连接分析任务标识，用于归属后端谱估计调用。 |
| `call_index` | 保存数组/表中的零基或明确标注的序号；不等同于物理通道编号或动物编号。 |
| `call_purpose` | 该谱估计调用的用途，如主估计、rank 或稳定性诊断。 |
| `estimator_api` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `estimator_scope` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `region_pair` | 本次连接估计的脑区对标识；方向由 seed/target 字段定义。 |
| `seed_array_indices` | seed 通道对应输入数组索引列表。 |
| `target_array_indices` | target 通道对应输入数组索引列表。 |
| `seed_channel_count` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `target_channel_count` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `methods` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `input_shape` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `n_epochs` | 参与该行汇总/估计的 epoch 数；不是独立动物数。 |
| `n_channels` | 对应文件、脑区或统计行内通道数量；上下文由表名与同一行 region 决定。 |
| `n_times` | 每段保存的时间样本数。 |
| `epoch_duration_s` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `sfreq_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `fmin_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `fmax_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `mode` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `mt_bandwidth_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `mt_adaptive` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `mt_low_bias` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `n_tapers` | 实际使用的 DPSS taper 数。 |
| `time_bandwidth_product` | multitaper 时间—带宽积参数。 |
| `rank_seed` | seed 集合在多变量估计中保留的维度数。 |
| `rank_target` | target 集合在多变量估计中保留的维度数。 |
| `n_frequencies_returned` | 后端返回的连接频率点数。 |
| `frequency_grid_hz` | 连接输出频率栅格的典型步长，单位 Hz；不等同于 multitaper 平滑带宽。 |
| `cache_hit` | 本次调用是否命中可复用计算缓存；不代表结果质量。 |
| `cache_status` | 计算缓存命中、绕过或失效状态。 |
| `status` | 程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。 |
| `elapsed_s` | 后端调用耗时，单位秒；属于运行追溯，不是科学指标。 |
| `error` | 后端定义的谱拟合误差，具体标度依赖所用后端版本。 |

### `connectivity_metadata.json`

模块：连接元数据。每行：每次连接运行一份配置和形状快照。

| 字段 | 含义 |
|---|---|
| `身份状态、方法、脑区通道集合、rank、频率网格、taper、遮罩策略、有效 epoch/时长、状态及维度` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |

### `time_delay_spectrum.csv`

模块：时间延迟。每行：方法×反对称状态×脑区对×通道对×频带×延迟点一行。

| 字段 | 含义 |
|---|---|
| `region_a` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `region_b` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `method` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `method_name` | TDE 后端方法编号对应的名称；应与 method 及运行版本共同解释。 |
| `antisymmetrized` | 是否使用时间反对称化 TDE 输出；不是输入数据已去除共同参考的保证。 |
| `seed_channel` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `target_channel` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `frequency_band` | TDE 使用的频带标签；边界以 band_low_hz/band_high_hz 为准。 |
| `band_low_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `band_high_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `delay_ms` | 延迟坐标，单位毫秒。 |
| `estimate_strength` | PyBispectra TDE 对该延迟点的算法返回值；非通用概率或0–1连接系数。 |
| `n_epochs` | 参与该行汇总/估计的 epoch 数；不是独立动物数。 |
| `effective_duration_s` | 参与本行计算的有效片段总时长（秒），按保留 epoch 数×每段有效时长计算。 |
| `analysis_sfreq_hz` | TDE 分析实际采样率；可能经抗混叠重采样后低于原采样率。 |
| `n_points` | 延迟曲线或频率分析网格点数；相邻点间距由分辨率字段说明。 |
| `delay_resolution_ms` | 延迟曲线相邻采样点间隔，单位毫秒。 |
| `status` | 程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。 |

### `time_delay_region_spectrum.csv`

模块：时间延迟。每行：方法×反对称状态×脑区对×频带×延迟点一行。

| 字段 | 含义 |
|---|---|
| `region_a` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `region_b` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `method` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `method_name` | TDE 后端方法编号对应的名称；应与 method 及运行版本共同解释。 |
| `antisymmetrized` | 是否使用时间反对称化 TDE 输出；不是输入数据已去除共同参考的保证。 |
| `frequency_band` | TDE 使用的频带标签；边界以 band_low_hz/band_high_hz 为准。 |
| `band_low_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `band_high_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `delay_ms` | 延迟坐标，单位毫秒。 |
| `estimate_strength` | PyBispectra TDE 对该延迟点的算法返回值；非通用概率或0–1连接系数。 |
| `estimate_strength_mean` | 同区域通道对在该延迟点估计值的算术平均。 |
| `estimate_strength_sd` | 同区域通道对在该延迟点估计值的标准差。 |
| `n_channel_pairs` | 参与区域汇总的通道对数，不是动物数。 |
| `n_epochs` | 参与该行汇总/估计的 epoch 数；不是独立动物数。 |
| `effective_duration_s` | 参与本行计算的有效片段总时长（秒），按保留 epoch 数×每段有效时长计算。 |
| `analysis_sfreq_hz` | TDE 分析实际采样率；可能经抗混叠重采样后低于原采样率。 |
| `n_points` | 延迟曲线或频率分析网格点数；相邻点间距由分辨率字段说明。 |
| `delay_resolution_ms` | 延迟曲线相邻采样点间隔，单位毫秒。 |

### `time_delay_channel_pair_summary.csv`

模块：时间延迟。每行：方法×反对称状态×通道对×频带一行。

| 字段 | 含义 |
|---|---|
| `region_a` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `region_b` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `method` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `method_name` | TDE 后端方法编号对应的名称；应与 method 及运行版本共同解释。 |
| `antisymmetrized` | 是否使用时间反对称化 TDE 输出；不是输入数据已去除共同参考的保证。 |
| `seed_channel` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `target_channel` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `frequency_band` | TDE 使用的频带标签；边界以 band_low_hz/band_high_hz 为准。 |
| `band_low_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `band_high_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `peak_delay_ms` | 单通道对延迟曲线达到最大估计强度的位置，单位 ms。 |
| `peak_strength` | 单通道对峰延迟处的 TDE 估计值。 |
| `delay_resolution_ms` | 延迟曲线相邻采样点间隔，单位毫秒。 |
| `direction_relative_to_seed_target` | 峰延迟相对有序 seed/target 输入的先后标签；非因果方向标签。 |
| `n_epochs` | 参与该行汇总/估计的 epoch 数；不是独立动物数。 |
| `effective_duration_s` | 参与本行计算的有效片段总时长（秒），按保留 epoch 数×每段有效时长计算。 |
| `status` | 程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。 |

### `time_delay_band_summary.csv`

模块：时间延迟。每行：方法×反对称状态×脑区对×频带一行。

| 字段 | 含义 |
|---|---|
| `region_a` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `region_b` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `method` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `method_name` | TDE 后端方法编号对应的名称；应与 method 及运行版本共同解释。 |
| `antisymmetrized` | 是否使用时间反对称化 TDE 输出；不是输入数据已去除共同参考的保证。 |
| `frequency_band` | TDE 使用的频带标签；边界以 band_low_hz/band_high_hz 为准。 |
| `band_low_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `band_high_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `region_peak_delay_ms` | 区域中位延迟曲线达到峰值的位置，单位 ms。 |
| `region_peak_strength` | 区域中位延迟曲线峰处的 TDE 估计值。 |
| `channel_pair_median_delay_ms` | 各通道对自身峰延迟的中位数，单位 ms。 |
| `channel_pair_mad_delay_ms` | 通道对峰延迟相对其中位数的绝对偏差中位数（MAD），单位 ms。 |
| `channel_pair_median_peak_strength` | 各有效通道对自身延迟曲线峰强度的中位数；不是动物间汇总。 |
| `n_channel_pairs` | 参与区域汇总的通道对数，不是动物数。 |
| `n_epochs` | 参与该行汇总/估计的 epoch 数；不是独立动物数。 |
| `effective_duration_s` | 参与本行计算的有效片段总时长（秒），按保留 epoch 数×每段有效时长计算。 |
| `delay_resolution_ms` | 延迟曲线相邻采样点间隔，单位毫秒。 |
| `direction_relative_to_seed_target` | 峰延迟相对有序 seed/target 输入的先后标签；非因果方向标签。 |
| `delay_window_min_ms` | 延迟搜索窗口下界，单位 ms。 |
| `delay_window_max_ms` | 延迟搜索窗口上界，单位 ms。 |
| `quality_flag` | 结果质量提醒标签，例如峰触及延迟窗边界；应结合 status 与备注。 |
| `status` | 程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。 |

### `time_delay_input_checks.csv`

模块：时间延迟诊断。每行：每项 TDE 输入检查一行。

| 字段 | 含义 |
|---|---|
| `check` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `value` | 表中保留的数值；请依赖同一行的 method、单位、summary/aggregation 和 status 解释。 |
| `status` | 程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。 |
| `note` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |

### `time_delay_failures.csv`

模块：时间延迟诊断。每行：失败的方法×脑区对×反对称状态一行。

| 字段 | 含义 |
|---|---|
| `region_a` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `region_b` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `method` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `antisymmetrized` | 是否使用时间反对称化 TDE 输出；不是输入数据已去除共同参考的保证。 |
| `failure_reason` | 拟合/估计失败原因；状态字段与原因字段需结合查看。 |
| `n_epochs` | 参与该行汇总/估计的 epoch 数；不是独立动物数。 |

### `time_delay_metadata.json`

模块：时间延迟元数据。每行：每次 TDE 运行一份参数快照。

| 字段 | 含义 |
|---|---|
| `后端版本、重采样、频带、延迟窗、点数/分辨率、方向约定、有效 epoch/时长及状态` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |

### `connectivity_binned_spectrum.csv`

模块：连接频率箱（辅助）。每行：每个方法×脑区/通道对×频率箱一行；关闭箱化时只保存 status 列。

| 字段 | 含义 |
|---|---|
| `method` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `region_a` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `region_b` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `component_index` | MIC 分量序号；不自动表示跨频率固定的生理源身份。 |
| `aggregation_level` | 本行连接是通道对层级还是脑区/多变量汇总层级。 |
| `seed_channel` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `target_channel` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `bin_low_hz` | 频率箱下边界，单位 Hz。 |
| `bin_high_hz` | 频率箱上边界，单位 Hz。 |
| `frequency_hz` | 频率坐标，单位 Hz。 |
| `value_raw_or_summary` | 频带汇总表字段；须结合 aggregation_definition、method 和方向字段解释。 |
| `value_strength` | 用于展示的强度字段；MIC 为 abs(value_raw)，其他方法保留其方法原生值。 |
| `n_frequency_points` | 该频率箱中原有频点数；箱化结果不增加频谱分辨率。 |
| `status` | 程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。 |
| `display_only` | True 表示本行/字段仅供显示或诊断，不应作为主科学结果。 |
| `binning_statistic` | 频率箱内采用的汇总统计量（如均值或中位数）。 |
| `binning_note` | 频率箱处理说明，尤其说明遮罩点不跨接或替代。 |

### `connectivity_display_spectrum.csv`

模块：连接显示辅助。每行：原连接谱每行附加一个显示平滑值；显示平滑关闭时只保存 status 列。

| 字段 | 含义 |
|---|---|
| `region_a` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `region_b` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `seed_region` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `target_region` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `direction_order` | 有向估计的 seed/source 到 target 的输入顺序标签；不是生物因果方向。 |
| `method` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `aggregation_level` | 本行连接是通道对层级还是脑区/多变量汇总层级。 |
| `seed_channel` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `target_channel` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `seed_channels` | seed 侧实际参与估计的通道名称列表。 |
| `target_channels` | target 侧实际参与估计的通道名称列表。 |
| `n_seed_channels` | seed 集合实际参与估计的通道数。 |
| `n_target_channels` | target 集合实际参与估计的通道数。 |
| `rank_seed` | seed 集合在多变量估计中保留的维度数。 |
| `rank_target` | target 集合在多变量估计中保留的维度数。 |
| `component_index` | MIC 分量序号；不自动表示跨频率固定的生理源身份。 |
| `n_components_requested` | MIC 请求提取的连接分量数；不控制 MIM 总相互作用。 |
| `n_components_returned` | 后端实际返回的 MIC 分量数。 |
| `frequency_hz` | 频率坐标，单位 Hz。 |
| `value_raw` | 方法原始输出；符号和值域按 method 定义，不要跨方法直接比较。 |
| `value_nonfinite_type` | 区分有限值、NaN 或 Inf 的类型标签；不是对非有限值的替代。 |
| `value_strength` | 用于展示的强度字段；MIC 为 abs(value_raw)，其他方法保留其方法原生值。 |
| `display_value_definition` | 显示值从原始结果转换而来的规则，如 MIC 取绝对值。 |
| `estimate_note` | 关于原始估计值、符号和值域的补充说明。 |
| `n_epochs` | 参与该行汇总/估计的 epoch 数；不是独立动物数。 |
| `effective_duration_s` | 参与本行计算的有效片段总时长（秒），按保留 epoch 数×每段有效时长计算。 |
| `frequency_is_excluded_line_noise` | 该频率是否被配置为工频排除点。 |
| `spectral_mode` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `mt_bandwidth_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `mt_adaptive` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `mt_low_bias` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `n_tapers` | 实际使用的 DPSS taper 数。 |
| `time_bandwidth_product` | multitaper 时间—带宽积参数。 |
| `n_tapers_note` | 关于 multitaper 实际 taper 数计算或适用性的说明文本。 |
| `estimated_rank_metadata` | 后端返回的 rank 元数据原样记录；需结合 rank_seed/rank_target 读取。 |
| `frequency_grid_hz` | 连接输出频率栅格的典型步长，单位 Hz；不等同于 multitaper 平滑带宽。 |
| `n_channel_pairs_total` | 该脑区对全部可用通道对数量。 |
| `frequency_is_masked_for_analysis` | 该频率在分析汇总中是否被屏蔽。 |
| `frequency_is_masked_for_plot` | 该频率是否仅在绘图显示中被遮罩。 |
| `line_noise_mask_source` | 工频绘图或分析遮罩来源；被遮罩不等于原始数值被删除。 |
| `line_noise_mask_reason` | 工频遮罩理由；与计算缺失、NaN 和估计失败分开。 |
| `display_value_smoothed` | 仅用于显示的平滑连接值；不是原始科学估计，不替代 value_raw/value_strength。 |
| `display_only` | True 表示本行/字段仅供显示或诊断，不应作为主科学结果。 |
| `status` | 程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。 |

### `connectivity_display_roughness.csv`

模块：连接显示辅助。每行：方法×脑区对×成分的显示平滑曲线粗糙度诊断；平滑关闭时只保存 status 列。

| 字段 | 含义 |
|---|---|
| `method` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |
| `region_a` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `region_b` | 映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。 |
| `component_index` | MIC 分量序号；不自动表示跨频率固定的生理源身份。 |
| `n_frequencies` | 该连接曲线所包含的频率点数；实际有效点数见 n_valid_points。 |
| `n_valid_points` | 某诊断/曲线组中通过有限值与遮罩筛选的点数。 |
| `median_abs_adjacent_diff` | 未屏蔽连续频点间相邻差绝对值的中位数，用于粗糙度诊断。 |
| `total_variation` | 未屏蔽连续频率段上的相邻差总变差。 |
| `coefficient_of_variation` | 粗糙度计算中的变异系数诊断值。 |
| `resampling_variability` | 稳定性/重采样诊断中估计变异摘要。 |
| `status` | 程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。 |

### `parameterization_status.csv / connectivity_status.csv / time_delay_status.csv`

模块：模块运行状态。每行：模块关闭时一条状态记录。

| 字段 | 含义 |
|---|---|
| `status` | 程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。 |
| `reason；解释为什么未生成相应科学结果` | 配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。 |

### `band_power_summary.csv（GUI/project）`

模块：频带功率。每行：每个通道×频带一行，epoch 汇总值。

| 字段 | 含义 |
|---|---|
| `channel_array_index` | 通道在当前输入数组中的索引；不等于物理通道编号。 |
| `channel_name` | 来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。 |
| `physical_channel_number` | 从实际通道名称或已确认映射得到的物理编号，不由数组位置推断。 |
| `region` | 用户确认的通道所属脑区/区域名称；不由数组索引自动推定。 |
| `band` | 配置中的频带名称；边界以同一行 band_low_hz/band_high_hz 为准。 |
| `band_low_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `band_high_hz` | 频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。 |
| `absolute_power` | 该 epoch、通道、频带的 PSD 梯形积分，单位为输入单位²。 |
| `relative_power` | 频带绝对功率除以指定分母范围功率；文件中保存比例，GUI 可换算百分数。 |
| `n_epochs` | 参与该行汇总/估计的 epoch 数；不是独立动物数。 |
| `status` | 程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。 |

## 常见读值提醒

- PSD 单位取决于输入信号单位和 `scaling`；只有 density 才是输入单位²/Hz。
- 相对功率文件值是比例，显示为百分比时乘100；分母范围必须一起报告。
- FOOOF/specparam 的 `peak_power_log10` 是峰高于非周期背景的 log10 差；BW 是2σ，不是 FWHM。
- MIC 的 `value_raw` 与 `value_strength=abs(value_raw)` 同时保留；MIM 不截到0–1；wPLI²_debiased 的负估计保留；dPLI 0.5 中性且保留方向。
- TDE 的 `estimate_strength` 是特定 PyBispectra 方法输出；正延迟按项目约定为 seed 领先 target。
- NaN、空峰表、失败状态和实际零值语义不同，不要静默补0。
- 文件级演示记录不自动构成动物样本；group、配对、跨被试统计应在外部按稳定 subject ID 设计。

## 方法与软件来源

- Welch 参数与 PSD 量纲： [SciPy `signal.welch`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.welch.html)
- Epoch 间频谱连接、输入假设及 MIC/MIM： [MNE-Connectivity 0.9.0 `spectral_connectivity_epochs`](https://mne.tools/mne-connectivity/stable/generated/mne_connectivity.spectral_connectivity_epochs.html)；[MIC/MIM 示例](https://mne.tools/mne-connectivity/stable/auto_examples/mic_mim.html)
- PLI、dPLI 与 wPLI 家族： [MNE-Connectivity 相位滞后连接示例](https://mne.tools/mne-connectivity/stable/auto_examples/dpli_wpli_pli.html)
- 当前 specparam 固定/拐点模型与峰拟合： [specparam 2.0.0rc7 `SpectralModel`](https://specparam-tools.github.io/generated/specparam.SpectralModel.html)；[峰参数示例](https://specparam-tools.github.io/auto_examples/models/plot_peak_params.html)
- FOOOF 兼容后端模型解释： [FOOOF 模型教程](https://fooof-tools.github.io/fooof/auto_tutorials/plot_02-FOOOF.html)
- TDE 方法 I 与反对称处理： [PyBispectra 1.3.2 TDE 官方示例](https://pybispectra.readthedocs.io/1.3/auto_examples/plot_compute_tde.html)；[PyBispectra JOSS 论文](https://joss.theoj.org/papers/10.21105/joss.08504)；相关混合噪声方法预印本 [arXiv:2502.17474](https://arxiv.org/abs/2502.17474)。正负号以 LUNA 本地输入顺序、合成方向测试和 `time_delay_metadata.json` 为准。

当前工作区核验的依赖版本：Python 3.11.9、NumPy 2.4.6、SciPy 1.17.1、pandas 2.3.3、Matplotlib 3.11.1、MNE 1.12.1、MNE-Connectivity 0.9.0、specparam 2.0.0rc7、FOOOF 1.1.1、PyBispectra 1.3.2、PySide6 6.11.2。版本会变化，单次分析 manifest 才是该结果的实际版本依据。
