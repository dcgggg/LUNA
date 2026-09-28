# 图表—结果字段—计算函数索引

文件名为文件级 pipeline 的当前命名模式；GUI 项目分析另将同类图放入该 data unit/analysis run 的 figures 目录，并由结果记录索引。PNG 为预览、SVG 为矢量导出。只有本次配置启用且存在相应数据时才生成可选图。

| 图表/文件模式 | 出现条件 | 绘图函数 | 数值来源字段 |
|---|---|---|---|
| **原始波形预览**<br>`raw_waveforms.png / .svg；GUI 原始波形页` | 每次单文件分析；最多显示配置数量的 epoch 和配置秒数。 | `plotting.plot_waveforms；GUI ResultCanvas.show_payload` | `读取的 epoch×channel×time 信号、sfreq、channel_table.channel_name/region` |
| **Epoch × 通道质量热图**<br>`quality_epoch_channel.png / .svg（CLI）；quality.png（GUI 项目结果）及 GUI Quality 页` | 质量检查产生 epoch_channel 表时。 | `plotting.plot_quality_matrix；gui_engine._save_metric_figures（Quality）` | `quality_epoch_channel.epoch_index/channel_name/issue_score/quality_status/quality_flags` |
| **通道 PSD 曲线**<br>`psd_channel.png / .svg（CLI）；psd.png（GUI 项目结果）及 GUI PSD 页` | PSD 模块完成后。 | `plotting.plot_psd；gui_engine._save_metric_figures（PSD）` | `psd_channel_summary.frequency_hz/psd_value/psd_sd/n_epochs/psd_unit` |
| **频带功率通道×频带热图**<br>`GUI Band Power 总览热图；自动导出 band_power_overview` | GUI Band Power 结果可用。 | `band_power_plots.prepare_band_power / plot_overview` | `band_power_epoch_channel.absolute_power/relative_power/band_low_hz/band_high_hz/channel_name/region` |
| **频带功率单一比较图**<br>`GUI Band Power 比较图；自动导出 band_power_compare / band_power_combined` | GUI Band Power 结果可用；比较模式一次只显示一个维度。 | `band_power_plots.plot_comparison` | `band_power_epoch_channel 或 band_power_summary 的 absolute_power/relative_power/n_epochs/channel_name/band` |
| **文件级频带功率柱图**<br>`band_power.png / .svg（CLI）；GUI 自动导出 band_power_overview / band_power_compare / band_power_combined` | 频带功率表非空时。 | `plotting.plot_band_power；gui_engine._save_metric_figures（Band Power）` | `band_power_epoch_channel.absolute_power/band/band_low_hz/band_high_hz/epoch_index` |
| **参数化 PSD 拟合**<br>`parameterization_fit.png / .svg` | 参数化启用且至少有可拟合 PSD 时。 | `plotting.plot_parameterization_fit；fooof_plots.plot_fooof_overview / plot_single_channel_detail` | `parameterization_curves.observed_power/full_model_power/aperiodic_power；parameterization_model.r_squared/error` |
| **FOOOF 六面板通道总览**<br>`GUI fooof_overview.png / .svg` | GUI FOOOF 结果载入且有通道参数/曲线。 | `fooof_plots.plot_fooof_overview` | `parameterization_model.offset/exponent；parameterization_curves.periodic_model_log10；parameterization_peaks.center_frequency_hz/peak_power_log10/bandwidth_hz` |
| **周期模型与残差曲线**<br>`parameterization_components.png / .svg；GUI 周期曲线及周期热图` | 参数化模型产生曲线时。 | `plotting.plot_parameterization_components；fooof_plots.plot_periodic_curves / plot_periodic_heatmap` | `periodic_component_log10_additive/periodic_model_log10/observed_minus_aperiodic_log10/residual_log10/gaussian_N_log10` |
| **非周期参数通道比较**<br>`GUI FOOOF 非周期参数页（散点/表格）` | GUI 载入 FOOOF/specparam 结果时。 | `fooof_plots.plot_aperiodic_details；FooofView 参数页` | `parameterization_model.offset/exponent/knee/r_squared/error/fit_quality_status` |
| **峰参数与峰分布**<br>`GUI FOOOF 峰参数页、峰分布页；fooof_peak_parameters / fooof_peak_distribution` | 至少一条峰记录；无峰通道仍显示状态。 | `fooof_plots.plot_peak_parameters / plot_peak_distribution` | `parameterization_peaks.center_frequency_hz/peak_power_log10/bandwidth_hz/peak_index/fit_quality_status` |
| **周期曲线与周期热图**<br>`GUI fooof_periodic_curves / fooof_periodic_heatmap（PNG/SVG）` | GUI 参数化曲线可用。 | `fooof_plots.plot_periodic_curves / plot_periodic_heatmap` | `periodic_model_log10/observed_minus_aperiodic_log10/frequency_hz/channel_name/periodic_component_negative` |
| **单通道拟合详情**<br>`GUI FOOOF 单通道详情页；fooof_channel_detail` | 选中存在模型/曲线的通道。 | `fooof_plots.plot_single_channel_detail` | `同参数化模型、峰和曲线字段；parameterization_model/peaks/curves` |
| **脑区通道冗余与 rank 诊断**<br>`connectivity_redundancy.png / .svg；GUI MIC 诊断展开区` | 功能连接启用并生成冗余诊断。 | `plotting.plot_connectivity_redundancy；assess_region_redundancy` | `connectivity_redundancy_correlation；connectivity_redundancy_singular_values；connectivity_rank_summary` |
| **功能连接频谱**<br>`connectivity_{method}_spectrum.png / .svg；GUI 单方法频谱及 connectivity_{method}_combined 组合图上半面` | 所选方法在 region_summary 中有结果；每种方法单独生成。 | `plotting.plot_connectivity_spectrum；connectivity_plots.plot_spectrum` | `connectivity_region_summary.method/region_a/region_b/component_index/frequency_hz/value_raw/value_strength` |
| **多频段脑区连接矩阵**<br>`connectivity_band_matrices.png / .svg（CLI）；connectivity_{method}_matrix 单方法矩阵及 combined 组合图下半面（GUI）` | 连接 band_summary 非空；按已配置频带生成面板。 | `plotting.plot_connectivity_band_matrices；connectivity_plots.plot_band_matrices` | `connectivity_band_summary.value_raw_or_summary/value_strength/n_frequencies_used/frequency_coverage_fraction` |
| **通道对连接矩阵**<br>`connectivity_{wpli|dpli|wpli2_debiased|imcoh|coh}_channel_pairs.png / .svg；GUI 通道对页` | 对应双变量方法及通道对结果存在。 | `plotting.plot_connectivity_channel_pairs；connectivity_plots.plot_channel_pair_matrix(es)` | `connectivity_spectrum.seed_channel/target_channel/frequency_hz/value_raw/value_strength；channel_pair_band_summary` |
| **连接 rank 敏感性图**<br>`connectivity_rank_sensitivity.png / .svg` | rank_sensitivity_enabled 且有可估计的替代 rank。 | `plotting.plot_connectivity_rank_sensitivity；_run_rank_sensitivity` | `connectivity_rank_sensitivity.rank_seed/rank_target/mean_strength_2_100hz/max_strength_2_100hz/status` |
| **TDE 延迟曲线**<br>`time_delay_method_{method}_{standard|antisym}_spectrum.png / .svg；GUI 还有 time_delay.png / .svg 汇总导出` | 时间延迟模块完成且有区域曲线。 | `plotting.plot_time_delay_spectrum；time_delay region summary` | `time_delay_region_spectrum.delay_ms/estimate_strength/estimate_strength_mean/estimate_strength_sd/n_channel_pairs` |
| **TDE 峰延迟矩阵**<br>`time_delay_method_{method}_{standard|antisym}_band_matrix.png / .svg；GUI TDE 矩阵` | TDE band_summary 有值时。 | `plotting.plot_time_delay_band_matrix；_band_summary` | `time_delay_band_summary.region_peak_delay_ms/channel_pair_median_delay_ms/channel_pair_mad_delay_ms/quality_flag` |

## 每类图的简明解释

### 原始波形预览

每个小面板对应一个实际通道，横轴是片段内部秒数，纵轴是输入电信号幅值；多条线是若干独立 epoch 的叠加。先看异常尖峰、平直段和通道间量级。显示范围可能只截取每个 epoch 的开头，不代表完整记录。

详细边界：图中没有把不同 epoch 首尾连接；它们是各自独立片段。通道颜色按映射分组，面板名称来自实际通道名。静态图以原采样信号作图，不做额外重参考或平滑；单位由 MNE 通道元数据记录，若未确认不要把数值自行称为 μV。

### Epoch × 通道质量热图

横轴是通道、纵轴是保存后的 epoch 编号；颜色是该单元格触发的质量标记数，而不是信号电压或异常严重程度。先定位颜色较高的格子，再查 quality_flags 了解原因。被标记不表示原始数据被删除。

详细边界：一个格子代表一个 epoch×通道。`issue_score` 是 flags 数量；非有限值/平直信号可形成 fail，其他异常规则多为 warn。空格或 NaN 表示没有对应记录/未计算，不能当作“正常零分”。质量图是检查摘要，不等于自动伪影修复结果。

### 通道 PSD 曲线

每条线对应一个通道，横轴是频率（Hz），纵轴是对数显示的 PSD（输入单位²/Hz）。曲线是跨 epoch 汇总后的谱。先看主要峰和背景形状，再核对频率范围及 PSD 方法；谱峰高不等于神经元放电更多。

详细边界：底层先逐 epoch×通道计算，再逐频率在 epoch 间聚合；不同通道不先平均波形。`psd_sd` 是 epoch 间标准差，若导出图不画误差带，图上只有汇总曲线。Welch 的 nperseg/window/noverlap/nfft 或 multitaper bandwidth/taper、频率网格和 mean/median 汇总都会影响谱。

### 频带功率通道×频带热图

横轴按低到高排列频带，纵轴按实际映射排列通道并按脑区分组；颜色是当前选择的绝对或相对功率。灰格表示缺失/无效值而非零。悬停或数值开关可查看同一通道、同一频带结果。

详细边界：热图单元与比较图使用同一准备后的统计结果；均值/中位数在 epoch 表存在时跨该记录 epochs 汇总。对数热图只适用于绝对功率的正值；非正值按缺失样式处理并提示改用线性。相对功率分母范围显示在色条标签，未作每通道归一化。

### 频带功率单一比较图

比较通道时横轴为通道、纵轴为所选频带的功率；比较频带时横轴为频带、纵轴为所选通道的功率。点/柱按当前汇总显示；若打开 epoch 分布，淡点是同一记录内重复片段，不是被试。

详细边界：散点为汇总值；epoch 分布可选展示同一个通道×频带的 epoch 值，离散摘要描述 epoch 内变化。只有一个汇总数时不造误差条。通道颜色按脑区，频带比较用统一颜色。

### 文件级频带功率柱图

每个小面板是一段频带，横轴是通道，柱高是该通道在该频带的跨 epoch 平均绝对功率。没有误差棒就不要把柱高的不确定性想象出来。积分受频带宽度影响，宽带柱子更高不必然说明该频率振荡更强。

详细边界：每个 epoch 单独由 PSD 积分出绝对功率，随后对每通道、每频带跨 epoch 求均值。柱图并未把四通道先合成脑区信号；颜色仅是分类标签。积分按连续频率段处理，排除频点之间不跨缺口积分。

### 参数化 PSD 拟合

每个小面板对应一个通道：原始汇总 PSD、完整拟合模型和非周期背景；纵轴为对数功率显示。模型是否贴合数据可从三条线的距离和拟合指标查看。拟合优度只说明谱形状拟合程度，不能证明拟合出的成分是真实生理机制。

详细边界：输入为该通道跨 epoch 汇总后的 PSD，而不是每个 5 秒 epoch 分别拟合。曲线在拟合频段内生成；线性单位²/Hz 的 PSD 用对数轴展示。拟合范围、PSD 参数、后端/版本、峰宽与峰数量设置都影响结果。

### FOOOF 六面板通道总览

六个面板依次展示 exponent、offset、所选脑区通道周期曲线，以及选定频带峰的 CF、PW、BW。横轴通道为实际通道名，点是每个通道一次汇总 PSD 拟合。峰数量不同的通道不会被强行一一配对。

详细边界：周期曲线面板显示当前所选区域通道的周期模型；D/E/F 面板按当前峰选择模式与 CF 频段筛选。CF单位Hz、PW为相对背景log10差、BW为2σ Hz。无峰通道保留为空/状态提示，不把空值填0。此图是通道内描述性比较，不含动物层推断。

### 周期模型与残差曲线

横轴是频率，纵轴是 log10 功率差。绿色周期曲线是拟合高斯峰之和；红色残差是观测谱减完整模型。若切换到去背景观测谱，它仍含未解释波动，不是纯振荡。负值表示低于拟合背景或模型，不表示负的物理功率。

详细边界：周期模型是相对非周期基线的对数加性拟合，不要指数化后当作原单位 PSD。每条 Gaussian_N 是一个拟合峰的重建曲线。通道×频率热图用保存的周期模型值，默认不逐通道归一化；色彩表示同一数值空间的差别。

### 非周期参数通道比较

每个点是一个实际通道的一次拟合值；横轴为真实通道标签，纵轴分别是 exponent 或 offset。点的颜色按脑区区分而非被试。先确认通道和拟合质量，再比较同一参数。不同功率单位会改变 offset。

详细边界：该页比较逐通道拟合参数，不是先平均四通道 PSD 再拟合的脑区参数。当前样例固定模型没有 knee，因此该字段为空。当前无逐 epoch FOOOF 拟合，不能将通道点解释为独立动物或 epoch 分布。

### 峰参数与峰分布

中心频率图显示峰在哪里，PW 图显示峰高于拟合背景多少 log10 功率，BW 图显示模型带宽。峰分布图横轴为 CF、纵轴为通道，颜色表示 PW，横线是 CF±BW/2。线段是带宽范围，不是置信区间；不同通道的第一个峰不保证是同一种振荡。

详细边界：选择“频段最强峰”时按该频带 CF 范围内 PW 最大选取；全部峰模式保留每个检测峰。BW 在本项目中为 2σ，不是 FWHM；高斯模型重建使用实际 σ。无峰时 CF/PW/BW 缺失，拟合失败与低质量状态另外标记。

### 周期曲线与周期热图

曲线页可按脑区分面或叠加选择通道，切换去背景观测谱、拟合周期模型或两者。热图以通道为行、频率为列，颜色是拟合周期 log10 加性幅度；默认不逐通道标准化。零线和负值有意义，不应裁成零。

详细边界：去背景观测谱包含周期峰和未解释波动，模型曲线是高斯峰拟合和；二者使用同一 log10 加性尺度但解释不同。若选统一坐标，各脑区共用范围便于比较。热图显示的是拟合周期模型而非原始 PSD，也不等于原始时域 burst。

### 单通道拟合详情

详情图把一个通道的观测谱、完整模型、非周期背景、单峰高斯、周期模型、去背景观测谱和残差分开检查。每条线都来自同一次拟合。重点检查峰是否覆盖谱峰、背景是否合理及残差结构；不要把观测去背景曲线当作模型周期成分。

详细边界：横轴为 Hz；原始/完整/背景 PSD 面板在线性单位²/Hz 数据上使用对数显示，去背景及周期曲线面板使用 log10 加性空间，残差是观测减拟合。拟合范围外不外推。模型表和峰表应与同一 payload/run 对应，质量字段列出失败原因。

### 脑区通道冗余与 rank 诊断

相关矩阵显示同一区域通道两两线性相关；奇异值图显示多通道数据中各独立方向保留的方差比例。先查看是否存在近乎重复通道和很小的维度。数值 rank 规则是计算诊断，不等于找到最佳生理维度。

详细边界：相关矩阵格子是同一记录的通道间相关；奇异值按该脑区通道集合及有效 epochs 计算。`variance_fraction` 与 `cumulative_variance_fraction` 描述方差占比；自动 `selected_rank` 按配置规则生成。窗口条件数高提示多变量估计可能不稳，不表示某通道对动物贡献更大。

### 功能连接频谱

横轴是频率（Hz），纵轴按方法变化；每条线表示一组脑区对，不是单通道。MIC 曲线常显示 |MIC|，MIM 是未归一化原值，wPLI/dPLI 与去偏平方 wPLI 不能共用同一种解释。谱曲线是同一记录内跨有效 epoch 的连接估计，不是逐 epoch 点再当独立样本。

详细边界：多变量 MIC/MIM 使用 seed 与 target 的完整通道集合和显式 rank；双变量方法先保留通道对再形成区域汇总。`n_epochs` 记录参与估计的片段。dPLI 按方向分线；dPLI 不能镜像为普通无向关系。frequency mask/line noise 标记与结果缺失不同。若打开 GUI 的显示平滑，曲线会使用单独的 `display_value_smoothed` 派生列；这是显示辅助，不改变 `value_raw`、主结果 CSV 或频带汇总。颜色代表脑区对类别。

### 多频段脑区连接矩阵

每格是行脑区与列脑区在指定频段的汇总值。对角线 N/A；MIC 通常先取各频率绝对值再汇总，MIM 汇总原始值，dPLI 以0.5为中性。颜色条范围由指标定义或当前结果范围决定；镜像格不一定代表第二次独立计算。

详细边界：面板标题列出频带名和上下界；矩阵来自已保存的频率结果按配置汇总，不对缺失频带外推。MIC/MIM 多变量结果每对区域只有一个多变量估计；通道对方法按配置聚合。dPLI 保留方向语义，未估计的方向格保持缺失。每个矩阵有绑定自身图像对象的色条。

### 通道对连接矩阵

横纵轴分别是 target 与 seed 通道，单格表示跨脑区一对通道的频段汇总连接值。颜色范围遵从当前指标，dPLI 使用0.5中心发散色标。空格代表没有对应估计，不是零连接；通道对是同一只动物/记录内部的重复测量，不是独立动物。

详细边界：通道对矩阵按选择的频带和有序方向构建；wPLI 类是通道对描述性结果，dPLI 的 seed/target 顺序不能交换后还保留同一方向。GUI与静态图可提供不同频带筛选；以图题和导出表的 `frequency_band`/`direction_order` 为准。

### 连接 rank 敏感性图

图中比较不同保留维度下连接强度如何变化，用来检查结果是否依赖 rank。横轴/图例对应维度设定，纵轴是配置频率范围内的强度汇总。变化较大说明估计对降维选择敏感，不应按曲线最高处挑选 rank。

详细边界：每个点/线来自同一数据按规定 rank 重新估计的诊断结果，不是统计显著性检验。不同区域通道集、rank 和 epochs 需查看表格。图中 2–100 Hz 名称仅在该实现输出列如此定义时适用；未覆盖频率或估计失败由 status 保留。

### TDE 延迟曲线

横轴是延迟（ms），纵轴是 PyBispectra 对所选频带的估计强度；每条线对应一个脑区对/频带。曲线最大处是当前算法窗口内的峰。正负方向按 seed-target 约定解释，不是因果箭头；方法和 antisym 状态不同的曲线分开看。

详细边界：CLI/模块曲线在每个延迟点先跨有效通道对汇总中位数，同时保留均值和标准差；每一对数据使用多个有效同步 epoch。x 轴覆盖配置 delay window，点距取决于重采样率和 n_points。峰接近边界可能被截断；不是每个 epoch 独立连接后再平均。GUI 另存的 time_delay.png 仅取前六组脑区对且只筛选 antisymmetrized=True，但没有按 method 和 frequency_band 分组，因此多个方法/频带可能被连入同一条线；该图不适合比较方法/频带，请优先看分方法/状态曲线及 CSV。

### TDE 峰延迟矩阵

每格显示一组脑区对在指定频带中位延迟曲线峰的位置，单位毫秒；正负代表本项目 seed/target 时间先后约定。颜色或格内数值表示延迟而非连接强度。窗口边缘峰和通道对离散较大由质量标记提示。

详细边界：区域峰延迟是区域中位曲线最大点的 delay；另有通道对峰延迟中位数及 MAD，二者不同。矩阵行列方向由 brain-region pair 映射构造；没有结果为缺失，不能填0。反对称版本与标准版本分别展示。

## GUI 可切换结果

GUI 复用保存表格进行显示筛选，不因改变色标、通道、脑区、频带或布局重新计算科学结果；需要重新计算的参数变化会触发相应计算流程。GUI 支持：Band Power 通道×频带热图和单一比较图；FOOOF 总览、非周期参数、周期曲线/热图、峰参数、峰分布和单通道详情；Connectivity 指标频谱、频带脑区矩阵与适用指标的通道对矩阵；Time Delay 延迟曲线及峰延迟矩阵。

本索引覆盖生成器、静态绘图函数和 GUI view 当前实际存在的视图；项目内跨数据组间/组内比较已取消，不在本索引中。

## 方法与软件来源

- Welch 参数与 PSD 量纲： [SciPy `signal.welch`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.welch.html)
- Epoch 间频谱连接、输入假设及 MIC/MIM： [MNE-Connectivity 0.9.0 `spectral_connectivity_epochs`](https://mne.tools/mne-connectivity/stable/generated/mne_connectivity.spectral_connectivity_epochs.html)；[MIC/MIM 示例](https://mne.tools/mne-connectivity/stable/auto_examples/mic_mim.html)
- PLI、dPLI 与 wPLI 家族： [MNE-Connectivity 相位滞后连接示例](https://mne.tools/mne-connectivity/stable/auto_examples/dpli_wpli_pli.html)
- 当前 specparam 固定/拐点模型与峰拟合： [specparam 2.0.0rc7 `SpectralModel`](https://specparam-tools.github.io/generated/specparam.SpectralModel.html)；[峰参数示例](https://specparam-tools.github.io/auto_examples/models/plot_peak_params.html)
- FOOOF 兼容后端模型解释： [FOOOF 模型教程](https://fooof-tools.github.io/fooof/auto_tutorials/plot_02-FOOOF.html)
- TDE 方法 I 与反对称处理： [PyBispectra 1.3.2 TDE 官方示例](https://pybispectra.readthedocs.io/1.3/auto_examples/plot_compute_tde.html)；[PyBispectra JOSS 论文](https://joss.theoj.org/papers/10.21105/joss.08504)；相关混合噪声方法预印本 [arXiv:2502.17474](https://arxiv.org/abs/2502.17474)。正负号以 LUNA 本地输入顺序、合成方向测试和 `time_delay_metadata.json` 为准。

当前工作区核验的依赖版本：Python 3.11.9、NumPy 2.4.6、SciPy 1.17.1、pandas 2.3.3、Matplotlib 3.11.1、MNE 1.12.1、MNE-Connectivity 0.9.0、specparam 2.0.0rc7、FOOOF 1.1.1、PyBispectra 1.3.2、PySide6 6.11.2。版本会变化，单次分析 manifest 才是该结果的实际版本依据。
