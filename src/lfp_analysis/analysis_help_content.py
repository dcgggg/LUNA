"""Canonical Chinese explanations used by the GUI and generated user docs.

Keep descriptions tied to the current implementation.  The documentation
builder copies these records into ``docs/``; the GUI reads the same records.
"""

from __future__ import annotations

from typing import Any

HELP_TOPICS: dict[str, dict[str, str]] = {
    "workflow": {
        "title": "分析流程总览",
        "short": "LUNA 先读取 FIF 中已经保存的分段信号，再核对通道、采样率、坏值和质量标记；之后按所选模块计算并保存表格、数组、参数快照和图。一个 epoch 是一段独立的小记录，不等于连续记录。文件级结果不能替代动物层统计。",
        "detail": """### 数据怎样流动

`FIF → 读取与通道表 → 检查/人工选择 → 有效数据快照 → 质量、PSD、频带功率、谱参数化、功能连接或时间延迟 → 结果表/数组/图 → manifest 与项目索引`。

读取器保留 MNE Epochs 的事件值、selection 和 drop_log，不将事件数值擅自换算为原始记录时间。质量检查本身只标记，不改写输入；当前连接和时间延迟路径会按明确规则排除 fail/非有限数据，warn 数据不会自动等同于失败。每个图都要结合其模块实际使用的筛选、映射与有效参数解释。

LUNA 的项目层级为项目、被试、session、state record、data unit。分析结果以稳定 ID 关联，不以文件名当动物身份。动物编号、实验阶段、真实给药时间或行为评分缺失时保持缺失。当前 GUI 不提供跨数据组间/组内比较；行为视频的逐 epoch 对齐也尚未实现。"""
    },
    "raw_quality": {
        "title": "原始信号与质量检查",
        "short": "原始波形图显示各实际通道的电压随 epoch 内时间变化；质量热图按 epoch 和通道标出自动检查发现的问题。先核对通道标签、幅度单位和异常位置。标记提示需要复核，不等于原始数据已被删除，也不能仅凭波形更平滑判断信号更真实。",
        "detail": """### 波形图

文件级图按通道分面；横轴是 epoch 内时间（秒），纵轴是输入信号幅值。线条是配置允许展示的若干 epoch；同一坐标上的多线表示片段叠加，不表示连续时间。当前静态预览不人为加通道偏移或重参考。GUI 中若启用显示偏移/归一化，应以当前视图标题和导出说明为准；这类显示处理不能当作原始振幅。

### 质量热图和质量表

热图横轴为通道名、纵轴为保存后的 epoch 索引，颜色是 `issue_score`（该 epoch×通道被触发的标记数量），不是严重度分数。`quality_status=fail` 当前由非有限值或平直信号等失败条件产生；warn 表示异常幅度、疑似饱和、工频峰或重复片段等提醒。`quality_flags` 列保存具体原因。热图空白/灰色不能自行理解为零电压。

质量统计中的 `max_abs`、标准差和饱和比例是检查量，不是疾病指标。人工排除配置保存在检查快照中；排除只影响本次分析选择，不会从原始 FIF 擦除 epoch/通道。质量阈值、工频检查范围和纳入的 epoch/channel 会改变检查结论。"""
    },
    "psd": {
        "title": "PSD 功率谱",
        "short": "PSD 把信号按振动快慢（频率）展开：横轴是 Hz，纵轴是每 Hz 对应的功率密度。曲线来自单通道；同一通道跨 epoch 的 PSD 先按配置取均值或中位数。峰表示该频率附近的谱能量较高，不等于神经元放电更多或脑区功能更强。",
        "detail": """### 计算与尺度

当前实现逐 epoch、逐通道估计 PSD，支持 SciPy Welch 与 MNE multitaper。Welch 将片段分窗、加窗并对周期图平均；`nperseg` 决定基础频率间隔约 `sfreq/nperseg`，`nfft` 零填充可让绘图网格更密，但不会增加真实分辨能力。Multitaper 的输出网格约为 `sfreq/n_times`，带宽控制谱平滑而不是频率网格间距。图表使用对数纵轴；CSV 中 `psd_value` 保持线性值。

`scaling=density` 时单位为输入单位²/Hz；若 MNE 单位码无法确认，输出标记为 `mne_unit_code:…` 或 `unknown`，不得自行换算为微伏。`psd_channel_summary.psd_sd` 是 epoch 间标准差；GUI 的 PSD 图默认显示汇总曲线，若显示带状范围需核对页面定义，不能把标准差称为动物间置信区间。脑区 PSD 是各通道 PSD 汇总，不是先把原始通道波形平均后再计算。

Welch 窗、窗长、重叠、FFT 长度、detrend、平均法；multitaper 带宽、taper 选项；频率上下限、epoch 集合和汇总方法都会影响曲线。谱高低可能受参考、电极、噪声、滤波和单位影响；PSD 不能单独证明振荡机制或神经元放电率。"""
    },
    "band_power": {
        "title": "频带功率",
        "short": "热图每格是一个实际通道在一个频带的功率；横轴频带、纵轴通道，颜色表示绝对或相对功率。比较图可固定频带比较通道，或固定通道比较频带。频带功率来自 PSD 对频率积分，不是峰高；频带宽度不同会影响积分结果。",
        "detail": """### 定义与图形层级

绝对功率按 epoch×通道×频带计算：在频带内对 PSD 频点做梯形积分；若排除了工频点，会拆成连续频率段分别积分，不跨缺口连线。单位为输入单位²。相对功率等于该频带积分除以配置分母频段（当前样例为 1–100 Hz）的 PSD 积分，输出表以 fraction 保存，界面可显示百分比。分母范围、频带上下界、排除点和积分网格均随结果保存。

GUI 默认按用户选择的均值或中位数跨 epoch 汇总。同一通道若显示 epoch 分布，每个散点是该记录内一个 epoch，不是一个动物。柱/点图的误差信息（若开启）描述 epoch 内分布而非动物间置信区间。文件级静态导出中的柱高是跨 epoch 均值且没有虚构误差条。区域筛选只是筛选映射到该区域的通道；当前总览不将四个通道的原始波形平均。

缺失值保持缺失；被对数显示掩蔽的非正值不是零功率。边界、频率步长、PSD 方法、汇总方式和相对功率分母会改变数值。宽频带的积分偏大可能只是带宽覆盖更多频点，不能直接称为振荡更强。"""
    },
    "parameterization": {
        "title": "FOOOF / specparam 谱参数化",
        "short": "参数化图把每个通道的汇总 PSD 拆成平滑的非周期背景和拟合的周期峰。CF 是峰中心频率，PW 是峰相对背景的 log10 功率高度，BW 是模型宽度。拟合只是对谱形状的描述；拟合好不等于某种生理机制已被证明。",
        "detail": """### 曲线与参数

输入是每通道已经汇总的线性 PSD；拟合后端在 log10 功率空间工作。`observed_power` 是输入 PSD；`full_model_power` 是完整模型反变换到线性 PSD 单位；`aperiodic_power` 是背景反变换；`observed_minus_aperiodic_log10` 是 log10(观测 PSD)−log10(非周期背景)，保留噪声及未解释起伏，可能为负，不能叫“纯振荡信号”；`periodic_model_log10`/`periodic_component_log10_additive` 是拟合高斯峰在 log10 空间的加和，不是具有 PSD 物理单位的独立振荡谱；`residual_log10` 是观测 log10 PSD−完整拟合模型。

offset 是 log10 背景截距，依赖功率单位；exponent 描述固定模型中背景随频率下降的斜率，是无量纲拟合参数，不等于兴奋/抑制平衡。knee 仅在 knee 模型中出现；当前样例使用 fixed，因此 knee 为空。`center_frequency_hz` 为 CF；`peak_power_log10`/`peak_height_log10` 为高于拟合背景的 log10 高度，不是原始 PSD 峰值，也不是频带积分。多峰重叠时它不必等于单个高斯的振幅。

本地代码统一将 `bandwidth_hz` 定义为 2σ，不是 FWHM；`gaussian_sigma_hz` 是重建高斯用的标准差。每个真实峰一行，未检出峰不会补造零峰；拟合失败与有效拟合但无峰由 `fit_status` 和 `peak_status` 区分。低质量状态仍保留。R² 和 error 只评价拟合与输入谱的一致程度。拟合频率范围、PSD 方法/平均、峰宽限制、最大峰数、峰阈值和后端版本会影响结果。"""
    },
    "connectivity": {
        "title": "功能连接：MIC、MIM、wPLI、dPLI",
        "short": "连接谱描述同一记录、同一时点内两组信号的频率相关关系。横轴为 Hz，纵轴含义由具体指标决定；脑区矩阵格子汇总对应脑区对。连接不是解剖连线，也不能单独证明因果。跨 epoch 方法用多个同步 epoch 估计同一状态，不能把每个 epoch 当独立连接样本。",
        "detail": """### 多变量与通道对指标

MIC 是最大化虚部相干（Maximized Imaginary part of Coherency），把 seed 脑区的一组通道与 target 脑区的一组通道作为多变量集合。CSV `value_raw` 保存带符号的分量，`value_strength`/界面 |MIC| 保存绝对值；频带汇总先逐频率取绝对值再汇总，避免正负抵消。MIC 成分序号是频率/拟合问题中的分量索引，不应跨频率自动视为同一生理源。

MIM（Multivariate Interaction Measure）汇总多变量相互作用，当前保存未归一化原值，可大于 1；它与 MIC 的数学定义不同，但同一谱数据上二者不是彼此独立的实验重复证据。

wPLI（weighted Phase Lag Index）按跨通道对估计，常规 wPLI 理论范围 0–1。`wpli2_debiased` 是去偏平方 wPLI，仍以平方量保存；有限样本估计可为负，负数不表示负向耦合，也不应截零或开平方。dPLI（directed Phase Lag Index）按有序 seed→target 估计，范围 0–1，0.5 是中性；当前实现用 `heaviside(imag(CSD), 0.5)`，反向顺序单独计算。偏离0.5表示估计中的相位先后偏向，不是因果方向。

连接矩阵的行是 seed、列是 target；对角线 N/A。MIC 绝对值、MIM 和对称通道对强度矩阵可镜像显示，镜像不是第二次估计；dPLI 保留方向，通常不可按对称矩阵理解。工频屏蔽、显示遮罩、NaN/Inf、估计失败是不同状态；线噪声区不会跨越插值。MNE 估计依赖同一记录内多个可视为同一状态的 epochs、rank、通道集、时间窗、multitaper 平滑与频段。

四脑区共有六个跨区组合。四通道集合的 MIC/MIM 是多变量结果，不是16条通道对的简单平均；wPLI/dPLI 通道对结果才逐对保留后作明确区域汇总。虚部/相位滞后指标仍不能完全消除共同参考、共同驱动或信号混合。"""
    },
    "time_delay": {
        "title": "时间延迟分析（TDE）",
        "short": "TDE 曲线把估计的耦合强度放在不同时间延迟上；横轴为毫秒、纵轴为 PyBispectra 输出的估计强度。正值按本项目约定表示 seed 相对领先 target，负值表示 target 相对领先 seed。峰位置是算法定义的最强延迟，不是生物学因果证明。",
        "detail": """### 曲线、矩阵与汇总

分析按脑区内全部有效跨区通道对计算，跨同一记录的有效 epoch；各 epoch 独立保持，不拼接。区域延迟曲线在每个频带、延迟点对通道对估计取中位数，并同时保存 mean/SD；图中的线是该区域对曲线。频带矩阵保存该区域中位曲线最大值所在延迟；另存每个通道对峰延迟的中位数与 MAD。不同统计量不要混称为同一个“平均延迟”。

`delay_ms`、`peak_delay_ms` 与 `region_peak_delay_ms` 单位为毫秒；`estimate_strength` 是 PyBispectra 方法1在该延迟点的返回值，不是通用0–1连接概率。当前代码把正延迟定义为 seed channel/region 领先 target，负值为 target 领先 seed；该解释依赖有序输入和已验证的本地约定。时间反对称/antisymmetrized 输出单独标记，目的是对同时混合成分提供敏感性视角，但不保证去除共同参考或共同驱动。

矩阵对角线不适用；区域的反向显示可只是方向展示，只有代码实际计算的反向次序才算另一估计。峰落在搜索窗口边缘、通道对延迟离散较大时由 `quality_flag` 提醒。结果受频带、延迟窗、点数/分辨率、分析采样率、重采样滤波、通道集合和 epochs 影响。"""
    },
    "saved_results": {
        "title": "保存文件、重载与状态",
        "short": "原始 FIF、检查快照、科学结果和图片是不同文件。项目结果通过 manifest 中的稳定项目/被试/session/state/data/analysis ID 关联；历史运行不覆盖当前结果。优先用 `ProjectResults` 或 manifest 指定的文件读取，不要靠目录名或文件名猜身份。",
        "detail": """### 文件之间的关系

单文件 CLI 在输出目录写 `run_manifest.json`、`config_used.yaml`、通道与 epoch 追溯表、质量/PSD/频带/参数化/连接/TDE CSV、模块 metadata JSON、`traceability/events_raw.json`、`selection.json`、`drop_log.json`，以及 PNG/SVG 图。CLI 分析目录不会另存一份原始 FIF，也不会把 FIF 中不连续 epochs 拼成连续记录。需注意：CLI 的 `config_used.yaml` 是输入配置副本；若含 `extends`，它没有展开父配置。CLI manifest 目前记录配置审计、少数关键范围和状态，但不是所有解析后参数的完整快照；部分参数散布在科学表和模块 metadata。项目 result bundle 的 manifest 保存独立的有效参数快照。当前 CLI 参数快照完整性属于已确认的追溯限制。

项目模式的新导入文件按项目规则存到项目数据目录（或保留历史显式外部引用）；检查决定在 project SQLite 元数据中关联 data unit。每次分析生成独立 `luna-result-bundle/1.0`：manifest 记录稳定 ID、来源指纹、有效参数及指纹、检查快照、映射、依赖版本、质量状态、表格/数组路径、维度、单位与数值空间。CSV 保存长表；NPZ 保存需要的数组，例如 PSD `(epoch, channel, frequency)` 和连接频谱数组；SQLite 是查询索引，bundle manifest 是该运行的结果快照。

`calculation_status`、`save_status` 和 `result_validity` 是不同状态：计算完成不等于保存成功；保存历史结果后来因影响计算的检查/参数改变而可标为 `needs_recompute`，旧版本仍保留。重算生成新 `analysis_id`，这是版本追溯而不是重复覆盖。原 FIF 丢失时，只要 bundle 文件完整且格式可读，表格/数组仍可由 `ProjectResults` 加载；依赖时域信号的重算或重新检查则需要原文件。文件级 CLI 的 `configuration_audit` 会标出未传入后端的兼容参数；不能仅凭配置文件里出现某参数，就认定本次计算使用了它。

外部分析首选 `lfp_analysis.results_api.ProjectResults` 的 `list/manifest/table/array/extract/to_long_table`。单文件 CLI 的 CSV 可直接读，但文件级记录身份未注册时不可升级成动物样本。行为视频、epoch 对齐和内置跨被试统计当前尚未实现。"""
    },
}


FIGURES: list[dict[str, Any]] = [
    {
        "title": "原始波形预览", "topic": "raw_quality", "files": "raw_waveforms.png / .svg；GUI 原始波形页",
        "condition": "每次单文件分析；最多显示配置数量的 epoch 和配置秒数。",
        "function": "plotting.plot_waveforms；GUI ResultCanvas.show_payload",
        "fields": "读取的 epoch×channel×time 信号、sfreq、channel_table.channel_name/region",
        "short": "每个小面板对应一个实际通道，横轴是片段内部秒数，纵轴是输入电信号幅值；多条线是若干独立 epoch 的叠加。先看异常尖峰、平直段和通道间量级。显示范围可能只截取每个 epoch 的开头，不代表完整记录。",
        "detail": "图中没有把不同 epoch 首尾连接；它们是各自独立片段。通道颜色按映射分组，面板名称来自实际通道名。静态图以原采样信号作图，不做额外重参考或平滑；单位由 MNE 通道元数据记录，若未确认不要把数值自行称为 μV。",
    },
    {
        "title": "Epoch × 通道质量热图", "topic": "raw_quality", "files": "quality_epoch_channel.png / .svg（CLI）；quality.png（GUI 项目结果）及 GUI Quality 页",
        "condition": "质量检查产生 epoch_channel 表时。",
        "function": "plotting.plot_quality_matrix；gui_engine._save_metric_figures（Quality）",
        "fields": "quality_epoch_channel.epoch_index/channel_name/issue_score/quality_status/quality_flags",
        "short": "横轴是通道、纵轴是保存后的 epoch 编号；颜色是该单元格触发的质量标记数，而不是信号电压或异常严重程度。先定位颜色较高的格子，再查 quality_flags 了解原因。被标记不表示原始数据被删除。",
        "detail": "一个格子代表一个 epoch×通道。`issue_score` 是 flags 数量；非有限值/平直信号可形成 fail，其他异常规则多为 warn。空格或 NaN 表示没有对应记录/未计算，不能当作“正常零分”。质量图是检查摘要，不等于自动伪影修复结果。",
    },
    {
        "title": "通道 PSD 曲线", "topic": "psd", "files": "psd_channel.png / .svg（CLI）；psd.png（GUI 项目结果）及 GUI PSD 页",
        "condition": "PSD 模块完成后。",
        "function": "plotting.plot_psd；gui_engine._save_metric_figures（PSD）",
        "fields": "psd_channel_summary.frequency_hz/psd_value/psd_sd/n_epochs/psd_unit",
        "short": "每条线对应一个通道，横轴是频率（Hz），纵轴是对数显示的 PSD（输入单位²/Hz）。曲线是跨 epoch 汇总后的谱。先看主要峰和背景形状，再核对频率范围及 PSD 方法；谱峰高不等于神经元放电更多。",
        "detail": "底层先逐 epoch×通道计算，再逐频率在 epoch 间聚合；不同通道不先平均波形。`psd_sd` 是 epoch 间标准差，若导出图不画误差带，图上只有汇总曲线。Welch 的 nperseg/window/noverlap/nfft 或 multitaper bandwidth/taper、频率网格和 mean/median 汇总都会影响谱。",
    },
    {
        "title": "频带功率通道×频带热图", "topic": "band_power", "files": "GUI Band Power 总览热图；自动导出 band_power_overview",
        "condition": "GUI Band Power 结果可用。",
        "function": "band_power_plots.prepare_band_power / plot_overview",
        "fields": "band_power_epoch_channel.absolute_power/relative_power/band_low_hz/band_high_hz/channel_name/region",
        "short": "横轴按低到高排列频带，纵轴按实际映射排列通道并按脑区分组；颜色是当前选择的绝对或相对功率。灰格表示缺失/无效值而非零。悬停或数值开关可查看同一通道、同一频带结果。",
        "detail": "热图单元与比较图使用同一准备后的统计结果；均值/中位数在 epoch 表存在时跨该记录 epochs 汇总。对数热图只适用于绝对功率的正值；非正值按缺失样式处理并提示改用线性。相对功率分母范围显示在色条标签，未作每通道归一化。",
    },
    {
        "title": "频带功率单一比较图", "topic": "band_power", "files": "GUI Band Power 比较图；自动导出 band_power_compare / band_power_combined",
        "condition": "GUI Band Power 结果可用；比较模式一次只显示一个维度。",
        "function": "band_power_plots.plot_comparison",
        "fields": "band_power_epoch_channel 或 band_power_summary 的 absolute_power/relative_power/n_epochs/channel_name/band",
        "short": "比较通道时横轴为通道、纵轴为所选频带的功率；比较频带时横轴为频带、纵轴为所选通道的功率。点/柱按当前汇总显示；若打开 epoch 分布，淡点是同一记录内重复片段，不是被试。",
        "detail": "散点为汇总值；epoch 分布可选展示同一个通道×频带的 epoch 值，离散摘要描述 epoch 内变化。只有一个汇总数时不造误差条。通道颜色按脑区，频带比较用统一颜色。",
    },
    {
        "title": "文件级频带功率柱图", "topic": "band_power", "files": "band_power.png / .svg（CLI）；GUI 自动导出 band_power_overview / band_power_compare / band_power_combined",
        "condition": "频带功率表非空时。",
        "function": "plotting.plot_band_power；gui_engine._save_metric_figures（Band Power）",
        "fields": "band_power_epoch_channel.absolute_power/band/band_low_hz/band_high_hz/epoch_index",
        "short": "每个小面板是一段频带，横轴是通道，柱高是该通道在该频带的跨 epoch 平均绝对功率。没有误差棒就不要把柱高的不确定性想象出来。积分受频带宽度影响，宽带柱子更高不必然说明该频率振荡更强。",
        "detail": "每个 epoch 单独由 PSD 积分出绝对功率，随后对每通道、每频带跨 epoch 求均值。柱图并未把四通道先合成脑区信号；颜色仅是分类标签。积分按连续频率段处理，排除频点之间不跨缺口积分。",
    },
    {
        "title": "参数化 PSD 拟合", "topic": "parameterization", "files": "parameterization_fit.png / .svg",
        "condition": "参数化启用且至少有可拟合 PSD 时。",
        "function": "plotting.plot_parameterization_fit；fooof_plots.plot_fooof_overview / plot_single_channel_detail",
        "fields": "parameterization_curves.observed_power/full_model_power/aperiodic_power；parameterization_model.r_squared/error",
        "short": "每个小面板对应一个通道：原始汇总 PSD、完整拟合模型和非周期背景；纵轴为对数功率显示。模型是否贴合数据可从三条线的距离和拟合指标查看。拟合优度只说明谱形状拟合程度，不能证明拟合出的成分是真实生理机制。",
        "detail": "输入为该通道跨 epoch 汇总后的 PSD，而不是每个 5 秒 epoch 分别拟合。曲线在拟合频段内生成；线性单位²/Hz 的 PSD 用对数轴展示。拟合范围、PSD 参数、后端/版本、峰宽与峰数量设置都影响结果。",
    },
    {
        "title": "FOOOF 六面板通道总览", "topic": "parameterization", "files": "GUI fooof_overview.png / .svg",
        "condition": "GUI FOOOF 结果载入且有通道参数/曲线。",
        "function": "fooof_plots.plot_fooof_overview",
        "fields": "parameterization_model.offset/exponent；parameterization_curves.periodic_model_log10；parameterization_peaks.center_frequency_hz/peak_power_log10/bandwidth_hz",
        "short": "六个面板依次展示 exponent、offset、所选脑区通道周期曲线，以及选定频带峰的 CF、PW、BW。横轴通道为实际通道名，点是每个通道一次汇总 PSD 拟合。峰数量不同的通道不会被强行一一配对。",
        "detail": "周期曲线面板显示当前所选区域通道的周期模型；D/E/F 面板按当前峰选择模式与 CF 频段筛选。CF单位Hz、PW为相对背景log10差、BW为2σ Hz。无峰通道保留为空/状态提示，不把空值填0。此图是通道内描述性比较，不含动物层推断。",
    },
    {
        "title": "周期模型与残差曲线", "topic": "parameterization", "files": "parameterization_components.png / .svg；GUI 周期曲线及周期热图",
        "condition": "参数化模型产生曲线时。",
        "function": "plotting.plot_parameterization_components；fooof_plots.plot_periodic_curves / plot_periodic_heatmap",
        "fields": "periodic_component_log10_additive/periodic_model_log10/observed_minus_aperiodic_log10/residual_log10/gaussian_N_log10",
        "short": "横轴是频率，纵轴是 log10 功率差。绿色周期曲线是拟合高斯峰之和；红色残差是观测谱减完整模型。若切换到去背景观测谱，它仍含未解释波动，不是纯振荡。负值表示低于拟合背景或模型，不表示负的物理功率。",
        "detail": "周期模型是相对非周期基线的对数加性拟合，不要指数化后当作原单位 PSD。每条 Gaussian_N 是一个拟合峰的重建曲线。通道×频率热图用保存的周期模型值，默认不逐通道归一化；色彩表示同一数值空间的差别。",
    },
    {
        "title": "非周期参数通道比较", "topic": "parameterization", "files": "GUI FOOOF 非周期参数页（散点/表格）",
        "condition": "GUI 载入 FOOOF/specparam 结果时。",
        "function": "fooof_plots.plot_aperiodic_details；FooofView 参数页",
        "fields": "parameterization_model.offset/exponent/knee/r_squared/error/fit_quality_status",
        "short": "每个点是一个实际通道的一次拟合值；横轴为真实通道标签，纵轴分别是 exponent 或 offset。点的颜色按脑区区分而非被试。先确认通道和拟合质量，再比较同一参数。不同功率单位会改变 offset。",
        "detail": "该页比较逐通道拟合参数，不是先平均四通道 PSD 再拟合的脑区参数。当前样例固定模型没有 knee，因此该字段为空。当前无逐 epoch FOOOF 拟合，不能将通道点解释为独立动物或 epoch 分布。",
    },
    {
        "title": "峰参数与峰分布", "topic": "parameterization", "files": "GUI FOOOF 峰参数页、峰分布页；fooof_peak_parameters / fooof_peak_distribution",
        "condition": "至少一条峰记录；无峰通道仍显示状态。",
        "function": "fooof_plots.plot_peak_parameters / plot_peak_distribution",
        "fields": "parameterization_peaks.center_frequency_hz/peak_power_log10/bandwidth_hz/peak_index/fit_quality_status",
        "short": "中心频率图显示峰在哪里，PW 图显示峰高于拟合背景多少 log10 功率，BW 图显示模型带宽。峰分布图横轴为 CF、纵轴为通道，颜色表示 PW，横线是 CF±BW/2。线段是带宽范围，不是置信区间；不同通道的第一个峰不保证是同一种振荡。",
        "detail": "选择“频段最强峰”时按该频带 CF 范围内 PW 最大选取；全部峰模式保留每个检测峰。BW 在本项目中为 2σ，不是 FWHM；高斯模型重建使用实际 σ。无峰时 CF/PW/BW 缺失，拟合失败与低质量状态另外标记。",
    },
    {
        "title": "周期曲线与周期热图", "topic": "parameterization", "files": "GUI fooof_periodic_curves / fooof_periodic_heatmap（PNG/SVG）",
        "condition": "GUI 参数化曲线可用。",
        "function": "fooof_plots.plot_periodic_curves / plot_periodic_heatmap",
        "fields": "periodic_model_log10/observed_minus_aperiodic_log10/frequency_hz/channel_name/periodic_component_negative",
        "short": "曲线页可按脑区分面或叠加选择通道，切换去背景观测谱、拟合周期模型或两者。热图以通道为行、频率为列，颜色是拟合周期 log10 加性幅度；默认不逐通道标准化。零线和负值有意义，不应裁成零。",
        "detail": "去背景观测谱包含周期峰和未解释波动，模型曲线是高斯峰拟合和；二者使用同一 log10 加性尺度但解释不同。若选统一坐标，各脑区共用范围便于比较。热图显示的是拟合周期模型而非原始 PSD，也不等于原始时域 burst。",
    },
    {
        "title": "单通道拟合详情", "topic": "parameterization", "files": "GUI FOOOF 单通道详情页；fooof_channel_detail",
        "condition": "选中存在模型/曲线的通道。",
        "function": "fooof_plots.plot_single_channel_detail",
        "fields": "同参数化模型、峰和曲线字段；parameterization_model/peaks/curves",
        "short": "详情图把一个通道的观测谱、完整模型、非周期背景、单峰高斯、周期模型、去背景观测谱和残差分开检查。每条线都来自同一次拟合。重点检查峰是否覆盖谱峰、背景是否合理及残差结构；不要把观测去背景曲线当作模型周期成分。",
        "detail": "横轴为 Hz；原始/完整/背景 PSD 面板在线性单位²/Hz 数据上使用对数显示，去背景及周期曲线面板使用 log10 加性空间，残差是观测减拟合。拟合范围外不外推。模型表和峰表应与同一 payload/run 对应，质量字段列出失败原因。",
    },
    {
        "title": "脑区通道冗余与 rank 诊断", "topic": "connectivity", "files": "connectivity_redundancy.png / .svg；GUI MIC 诊断展开区",
        "condition": "功能连接启用并生成冗余诊断。",
        "function": "plotting.plot_connectivity_redundancy；assess_region_redundancy",
        "fields": "connectivity_redundancy_correlation；connectivity_redundancy_singular_values；connectivity_rank_summary",
        "short": "相关矩阵显示同一区域通道两两线性相关；奇异值图显示多通道数据中各独立方向保留的方差比例。先查看是否存在近乎重复通道和很小的维度。数值 rank 规则是计算诊断，不等于找到最佳生理维度。",
        "detail": "相关矩阵格子是同一记录的通道间相关；奇异值按该脑区通道集合及有效 epochs 计算。`variance_fraction` 与 `cumulative_variance_fraction` 描述方差占比；自动 `selected_rank` 按配置规则生成。窗口条件数高提示多变量估计可能不稳，不表示某通道对动物贡献更大。",
    },
    {
        "title": "功能连接频谱", "topic": "connectivity", "files": "connectivity_{method}_spectrum.png / .svg；GUI 单方法频谱及 connectivity_{method}_combined 组合图上半面",
        "condition": "所选方法在 region_summary 中有结果；每种方法单独生成。",
        "function": "plotting.plot_connectivity_spectrum；connectivity_plots.plot_spectrum",
        "fields": "connectivity_region_summary.method/region_a/region_b/component_index/frequency_hz/value_raw/value_strength",
        "short": "横轴是频率（Hz），纵轴按方法变化；每条线表示一组脑区对，不是单通道。MIC 曲线常显示 |MIC|，MIM 是未归一化原值，wPLI/dPLI 与去偏平方 wPLI 不能共用同一种解释。谱曲线是同一记录内跨有效 epoch 的连接估计，不是逐 epoch 点再当独立样本。",
        "detail": "多变量 MIC/MIM 使用 seed 与 target 的完整通道集合和显式 rank；双变量方法先保留通道对再形成区域汇总。`n_epochs` 记录参与估计的片段。dPLI 按方向分线；dPLI 不能镜像为普通无向关系。frequency mask/line noise 标记与结果缺失不同。若打开 GUI 的显示平滑，曲线会使用单独的 `display_value_smoothed` 派生列；这是显示辅助，不改变 `value_raw`、主结果 CSV 或频带汇总。颜色代表脑区对类别。",
    },
    {
        "title": "多频段脑区连接矩阵", "topic": "connectivity", "files": "connectivity_band_matrices.png / .svg（CLI）；connectivity_{method}_matrix 单方法矩阵及 combined 组合图下半面（GUI）",
        "condition": "连接 band_summary 非空；按已配置频带生成面板。",
        "function": "plotting.plot_connectivity_band_matrices；connectivity_plots.plot_band_matrices",
        "fields": "connectivity_band_summary.value_raw_or_summary/value_strength/n_frequencies_used/frequency_coverage_fraction",
        "short": "每格是行脑区与列脑区在指定频段的汇总值。对角线 N/A；MIC 通常先取各频率绝对值再汇总，MIM 汇总原始值，dPLI 以0.5为中性。颜色条范围由指标定义或当前结果范围决定；镜像格不一定代表第二次独立计算。",
        "detail": "面板标题列出频带名和上下界；矩阵来自已保存的频率结果按配置汇总，不对缺失频带外推。MIC/MIM 多变量结果每对区域只有一个多变量估计；通道对方法按配置聚合。dPLI 保留方向语义，未估计的方向格保持缺失。每个矩阵有绑定自身图像对象的色条。",
    },
    {
        "title": "通道对连接矩阵", "topic": "connectivity", "files": "connectivity_{wpli|dpli|wpli2_debiased|imcoh|coh}_channel_pairs.png / .svg；GUI 通道对页",
        "condition": "对应双变量方法及通道对结果存在。",
        "function": "plotting.plot_connectivity_channel_pairs；connectivity_plots.plot_channel_pair_matrix(es)",
        "fields": "connectivity_spectrum.seed_channel/target_channel/frequency_hz/value_raw/value_strength；channel_pair_band_summary",
        "short": "横纵轴分别是 target 与 seed 通道，单格表示跨脑区一对通道的频段汇总连接值。颜色范围遵从当前指标，dPLI 使用0.5中心发散色标。空格代表没有对应估计，不是零连接；通道对是同一只动物/记录内部的重复测量，不是独立动物。",
        "detail": "通道对矩阵按选择的频带和有序方向构建；wPLI 类是通道对描述性结果，dPLI 的 seed/target 顺序不能交换后还保留同一方向。GUI与静态图可提供不同频带筛选；以图题和导出表的 `frequency_band`/`direction_order` 为准。",
    },
    {
        "title": "连接 rank 敏感性图", "topic": "connectivity", "files": "connectivity_rank_sensitivity.png / .svg",
        "condition": "rank_sensitivity_enabled 且有可估计的替代 rank。",
        "function": "plotting.plot_connectivity_rank_sensitivity；_run_rank_sensitivity",
        "fields": "connectivity_rank_sensitivity.rank_seed/rank_target/mean_strength_2_100hz/max_strength_2_100hz/status",
        "short": "图中比较不同保留维度下连接强度如何变化，用来检查结果是否依赖 rank。横轴/图例对应维度设定，纵轴是配置频率范围内的强度汇总。变化较大说明估计对降维选择敏感，不应按曲线最高处挑选 rank。",
        "detail": "每个点/线来自同一数据按规定 rank 重新估计的诊断结果，不是统计显著性检验。不同区域通道集、rank 和 epochs 需查看表格。图中 2–100 Hz 名称仅在该实现输出列如此定义时适用；未覆盖频率或估计失败由 status 保留。",
    },
    {
        "title": "TDE 延迟曲线", "topic": "time_delay", "files": "time_delay_method_{method}_{standard|antisym}_spectrum.png / .svg；GUI 还有 time_delay.png / .svg 汇总导出",
        "condition": "时间延迟模块完成且有区域曲线。",
        "function": "plotting.plot_time_delay_spectrum；time_delay region summary",
        "fields": "time_delay_region_spectrum.delay_ms/estimate_strength/estimate_strength_mean/estimate_strength_sd/n_channel_pairs",
        "short": "横轴是延迟（ms），纵轴是 PyBispectra 对所选频带的估计强度；每条线对应一个脑区对/频带。曲线最大处是当前算法窗口内的峰。正负方向按 seed-target 约定解释，不是因果箭头；方法和 antisym 状态不同的曲线分开看。",
        "detail": "CLI/模块曲线在每个延迟点先跨有效通道对汇总中位数，同时保留均值和标准差；每一对数据使用多个有效同步 epoch。x 轴覆盖配置 delay window，点距取决于重采样率和 n_points。峰接近边界可能被截断；不是每个 epoch 独立连接后再平均。GUI 另存的 time_delay.png 仅取前六组脑区对且只筛选 antisymmetrized=True，但没有按 method 和 frequency_band 分组，因此多个方法/频带可能被连入同一条线；该图不适合比较方法/频带，请优先看分方法/状态曲线及 CSV。",
    },
    {
        "title": "TDE 峰延迟矩阵", "topic": "time_delay", "files": "time_delay_method_{method}_{standard|antisym}_band_matrix.png / .svg；GUI TDE 矩阵",
        "condition": "TDE band_summary 有值时。",
        "function": "plotting.plot_time_delay_band_matrix；_band_summary",
        "fields": "time_delay_band_summary.region_peak_delay_ms/channel_pair_median_delay_ms/channel_pair_mad_delay_ms/quality_flag",
        "short": "每格显示一组脑区对在指定频带中位延迟曲线峰的位置，单位毫秒；正负代表本项目 seed/target 时间先后约定。颜色或格内数值表示延迟而非连接强度。窗口边缘峰和通道对离散较大由质量标记提示。",
        "detail": "区域峰延迟是区域中位曲线最大点的 delay；另有通道对峰延迟中位数及 MAD，二者不同。矩阵行列方向由 brain-region pair 映射构造；没有结果为缺失，不能填0。反对称版本与标准版本分别展示。",
    },
]


# Exact standalone file-level CSV schemas observed from the pipeline output;
# project bundles write the corresponding module tables under their manifest.
TABLE_SCHEMAS: dict[str, dict[str, str]] = {
    "batch_manifest.csv": {"grain": "批处理清单中每个输入文件一行", "module": "批量运行元数据", "fields": "row_index,file_id,file_uid,file_path,status,reason,output_dir"},
    "metadata_validation.csv": {"grain": "每条元数据检查发现一行；无问题时为空表但仍保留列名", "module": "元数据校验", "fields": "table,severity,code,message,row"},
    "channel_table.csv": {"grain": "每个文件通道一行", "module": "通道与脑区映射", "fields": "array_index,channel_name,mne_channel_type,mne_unit_code,physical_channel_number,region,hemisphere,probe_or_tetrode,mapping_status"},
    "epochs_trace.csv": {"grain": "每个上游候选 epoch 一行", "module": "epoch 追溯", "fields": "file_id,saved_index,original_candidate_index,events_raw_value,selection_value,confirmed_time_start_s,confirmed_time_end_s,quality_status,quality_flags,drop_reason,time_coordinate_note"},
    "quality_epoch_channel.csv": {"grain": "每个 epoch×通道一行", "module": "质量检查", "fields": "epoch_index,channel_array_index,channel_name,finite_sample_count,nonfinite_sample_count,std,max_abs,max_abs_robust_z,saturation_fraction,line_noise_peak_ratio,quality_status,quality_flags,issue_score"},
    "quality_epoch.csv": {"grain": "每个保存 epoch 一行", "module": "质量检查", "fields": "epoch_index,n_channels,n_fail_channels,n_warn_channels,min_finite_samples,max_issue_score,valid_duration_s,quality_status"},
    "quality_channel.csv": {"grain": "每个通道一行", "module": "质量检查", "fields": "channel_array_index,channel_name,n_epochs,n_fail_epochs,n_warn_epochs,mean_std,max_abs,max_issue_score"},
    "quality_file.csv": {"grain": "每个文件一行", "module": "质量检查", "fields": "n_epochs,n_channels,n_times,sampling_rate_hz,nominal_duration_s,effective_valid_duration_s,n_fail_epoch_channel_rows,n_warn_epoch_channel_rows,n_duplicate_epoch_rows,duplicate_epoch_detection,check_frequency_band_hz,frequency_band_check_status"},
    "psd_epoch_channel.csv": {"grain": "每个 epoch×通道×频率一行", "module": "PSD", "fields": "epoch_index,channel_array_index,channel_name,frequency_hz,psd_value,status,nperseg_used,noverlap_used,nfft_used,frequency_resolution_hz,psd_method,multitaper_bandwidth_hz,multitaper_adaptive,multitaper_low_bias,multitaper_normalization,multitaper_remove_dc,multitaper_n_jobs,multitaper_batch_input_shape,multitaper_batch_call_count,multitaper_batch_mode,source_unit,psd_unit"},
    "psd_channel_summary.csv": {"grain": "每个通道×频率一行", "module": "PSD", "fields": "channel_array_index,channel_name,frequency_hz,psd_value,psd_sd,n_epochs,psd_method,frequency_resolution_hz,nperseg_used,noverlap_used,nfft_used,multitaper_bandwidth_hz,multitaper_adaptive,multitaper_low_bias,multitaper_normalization,multitaper_remove_dc,multitaper_n_jobs,multitaper_batch_input_shape,multitaper_batch_call_count,multitaper_batch_mode,source_unit,psd_unit"},
    "psd_region_summary.csv": {"grain": "每个已映射脑区×频率一行", "module": "PSD", "fields": "region,frequency_hz,psd_value,psd_sd_across_channels,n_channels,n_epoch_channel_estimates,psd_method,frequency_resolution_hz,nperseg_used,noverlap_used,nfft_used,multitaper_bandwidth_hz,multitaper_adaptive,multitaper_low_bias,multitaper_normalization,multitaper_remove_dc,multitaper_n_jobs,multitaper_batch_input_shape,multitaper_batch_call_count,multitaper_batch_mode,source_unit,psd_unit"},
    "band_power_epoch_channel.csv": {"grain": "每个 epoch×通道×频带一行", "module": "频带功率", "fields": "epoch_index,channel_array_index,channel_name,band,band_low_hz,band_high_hz,absolute_power,relative_power,relative_denominator_low_hz,relative_denominator_high_hz,excluded_frequency_count,frequency_step_hz,band_frequency_segments,band_max_gap_hz,denominator_frequency_segments,denominator_max_gap_hz,integration_rule,status,source_unit,absolute_power_unit,relative_power_unit"},
    "parameterization_model.csv": {"grain": "每个通道一次 PSD 拟合；成功、低质量及失败行均保留", "module": "FOOOF/specparam", "fields": "channel_array_index,channel_name,source_unit,psd_unit,psd_method,frequency_resolution_hz,nperseg_used,noverlap_used,nfft_used,multitaper_bandwidth_hz,multitaper_adaptive,multitaper_low_bias,multitaper_normalization,multitaper_remove_dc,multitaper_n_jobs,backend_requested,backend_used,aperiodic_mode,fit_status,fit_quality_status,peak_status,n_peaks,failure_reason,backend_warning,r_squared,error,offset,exponent,knee,min_r_squared_requested,min_peak_prominence_requested,min_peak_prominence_status,fit_low_hz,fit_high_hz,n_frequency_bins"},
    "parameterization_failures.csv": {"grain": "parameterization_model 中 fit_status 非成功的通道行；无失败时为空表但保留完整列", "module": "FOOOF/specparam 失败记录", "fields": "channel_array_index,channel_name,source_unit,psd_unit,psd_method,frequency_resolution_hz,nperseg_used,noverlap_used,nfft_used,multitaper_bandwidth_hz,multitaper_adaptive,multitaper_low_bias,multitaper_normalization,multitaper_remove_dc,multitaper_n_jobs,backend_requested,backend_used,aperiodic_mode,fit_status,fit_quality_status,peak_status,n_peaks,failure_reason,backend_warning,r_squared,error,offset,exponent,knee,min_r_squared_requested,min_peak_prominence_requested,min_peak_prominence_status,fit_low_hz,fit_high_hz,n_frequency_bins"},
    "parameterization_peaks.csv": {"grain": "每个检测到的高斯峰一行", "module": "FOOOF/specparam", "fields": "channel_array_index,channel_name,source_unit,psd_unit,psd_method,frequency_resolution_hz,nperseg_used,noverlap_used,nfft_used,multitaper_bandwidth_hz,multitaper_adaptive,multitaper_low_bias,multitaper_normalization,multitaper_remove_dc,multitaper_n_jobs,peak_index,center_frequency_hz,peak_height_log10,peak_power_log10,bandwidth_hz,gaussian_sigma_hz,bandwidth_definition,fit_status,fit_quality_status,r_squared,error,fit_low_hz,fit_high_hz"},
    "parameterization_curves.csv": {"grain": "每个通道×拟合频率一行", "module": "FOOOF/specparam", "fields": "channel_array_index,channel_name,source_unit,psd_unit,psd_method,frequency_resolution_hz,nperseg_used,noverlap_used,nfft_used,multitaper_bandwidth_hz,multitaper_adaptive,multitaper_low_bias,multitaper_normalization,multitaper_remove_dc,multitaper_n_jobs,frequency_hz,observed_power,observed_log10_power,full_model_power,full_model_log10_power,aperiodic_power,aperiodic_log10_power,periodic_component_power,periodic_component_log10_additive,periodic_model_log10,observed_minus_aperiodic_log10,reconstructed_gaussian_sum_log10,residual_log10,periodic_component_negative,fit_status,fit_quality_status,backend_used,gaussian_0_log10…gaussian_N_log10"},
    "connectivity_spectrum.csv": {"grain": "连接方向/通道对或多变量区域对×频率×方法×成分一行", "module": "功能连接", "fields": "region_a,region_b,seed_region,target_region,direction_order,method,aggregation_level,seed_channel,target_channel,seed_channels,target_channels,n_seed_channels,n_target_channels,rank_seed,rank_target,component_index,n_components_requested,n_components_returned,frequency_hz,value_raw,value_nonfinite_type,value_strength,display_value_definition,estimate_note,n_epochs,effective_duration_s,frequency_is_excluded_line_noise,spectral_mode,mt_bandwidth_hz,mt_adaptive,mt_low_bias,n_tapers,time_bandwidth_product,n_tapers_note,estimated_rank_metadata,frequency_grid_hz,n_channel_pairs_total,frequency_is_masked_for_analysis,frequency_is_masked_for_plot,line_noise_mask_source,line_noise_mask_reason"},
    "connectivity_region_summary.csv": {"grain": "方法×脑区对×频率×MIC成分（若有）一行", "module": "功能连接", "fields": "method,region_a,region_b,component_index,frequency_hz,value_raw,value_strength,n_channel_pairs,n_negative_estimates,aggregation_definition,n_epochs,effective_duration_s,rank_seed,rank_target,frequency_is_excluded_line_noise,spectral_mode,mt_bandwidth_hz,mt_adaptive,mt_low_bias,n_tapers,n_components_requested,n_components_returned"},
    "connectivity_band_summary.csv": {"grain": "方法×脑区对×频带×MIC成分（若有）一行", "module": "功能连接", "fields": "method,region_a,region_b,component_index,band,band_low_hz,band_high_hz,value_raw_or_summary,value_strength,aggregation_definition,n_channel_pairs,n_frequencies_used,n_frequencies_excluded_line_noise,frequency_coverage_fraction,n_epochs,effective_duration_s,rank_seed,rank_target,n_components_requested,n_components_returned,status"},
    "connectivity_channel_pair_band_summary.csv": {"grain": "有序通道对×频带×方法一行", "module": "功能连接", "fields": "method,region_a,region_b,seed_region,target_region,direction_order,seed_channel,target_channel,band,band_low_hz,band_high_hz,value_raw_or_summary,value_strength,aggregation_definition,n_frequencies_used,n_frequencies_excluded_line_noise,frequency_coverage_fraction,n_epochs,effective_duration_s,rank_seed,rank_target,status"},
    "connectivity_patterns.csv": {"grain": "MIC 脑区对×成分×通道×频率×模式角色一行", "module": "功能连接诊断", "fields": "region_a,region_b,method,component_index,n_components_returned,pattern_role,channel_name,array_index,frequency_hz,pattern_value,pattern_note"},
    "connectivity_redundancy_correlation.csv": {"grain": "脑区内通道对一行", "module": "连接诊断", "fields": "region,channel_i,channel_j,array_index_i,array_index_j,correlation,n_valid_epochs,effective_valid_duration_s"},
    "connectivity_redundancy_singular_values.csv": {"grain": "脑区×奇异维度一行", "module": "连接诊断", "fields": "region,component,singular_value,variance_fraction,cumulative_variance_fraction,numerical_rank,variance_rank,selected_rank,rank_reason"},
    "connectivity_rank_summary.csv": {"grain": "每个脑区一行", "module": "连接诊断", "fields": "region,channel_names,channel_array_indices,n_channels,n_valid_epochs,effective_valid_duration_s,n_finite_samples,numerical_rank,variance_rank,selected_rank,rank_reason,rank_relative_tolerance,rank_variance_threshold,covariance_condition_number,all_channels_finite"},
    "connectivity_rank_sensitivity.csv": {"grain": "脑区对×方法×rank扰动×成分一行", "module": "连接诊断", "fields": "region_a,region_b,method,component_index,rank_offset,rank_seed,rank_target,mean_strength_2_100hz,max_strength_2_100hz,n_epochs,status"},
    "connectivity_stability.csv": {"grain": "稳定性检查×子集×脑区对×方法一行", "module": "连接诊断", "fields": "check_type,status,note,subset_name,region_a,region_b,method,component_index,mean_strength_2_100hz,n_epochs,effective_duration_s,direction_order,aggregation_definition,n_channel_pairs"},
    "connectivity_epoch_profile.csv": {"grain": "每个候选连接 epoch 一行", "module": "连接诊断", "fields": "epoch_index,signal_rms,robust_z_vs_valid_epochs,quality_valid_for_connectivity,signal_heterogeneity_flag,flag_note"},
    "connectivity_input_checks.csv": {"grain": "每项输入检查一行", "module": "连接诊断", "fields": "check,value,status,note"},
    "connectivity_failures.csv": {"grain": "每个失败连接/方法一行；无失败时为空表但保留列定义", "module": "功能连接", "fields": "region_a,region_b,method,failure_reason,n_epochs,rank_seed,rank_target,n_components_requested"},
    "connectivity_frequency_diagnostics.csv": {"grain": "方法×频率一行", "module": "连接诊断", "fields": "method,frequency_hz,plot_frequency_index,n_total_values,n_finite,n_nan,n_inf,is_masked,mask_reason,processing_stage,mask_source,configuration_key"},
    "connectivity_roughness.csv": {"grain": "方法×脑区对×频率段一行", "module": "连接诊断", "fields": "method,region_a,region_b,component_index,n_frequencies,n_valid_points,median_abs_adjacent_diff,total_variation,coefficient_of_variation,resampling_variability,status"},
    "connectivity_band_cv.csv": {"grain": "方法×脑区对×频带一行", "module": "连接诊断", "fields": "method,region_a,region_b,component_index,band,band_low_hz,band_high_hz,n_valid_points,band_cv,status"},
    "connectivity_estimation_calls.csv": {"grain": "每次后端谱估计调用一行", "module": "连接运行追溯", "fields": "analysis_task_id,call_index,call_purpose,estimator_api,estimator_scope,region_pair,seed_array_indices,target_array_indices,seed_channel_count,target_channel_count,methods,input_shape,n_epochs,n_channels,n_times,epoch_duration_s,sfreq_hz,fmin_hz,fmax_hz,mode,mt_bandwidth_hz,mt_adaptive,mt_low_bias,n_tapers,time_bandwidth_product,rank_seed,rank_target,n_frequencies_returned,frequency_grid_hz,cache_hit,cache_status,status,elapsed_s,error"},
    "connectivity_metadata.json": {"grain": "每次连接运行一份配置和形状快照", "module": "连接元数据", "fields": "身份状态、方法、脑区通道集合、rank、频率网格、taper、遮罩策略、有效 epoch/时长、状态及维度"},
    "time_delay_spectrum.csv": {"grain": "方法×反对称状态×脑区对×通道对×频带×延迟点一行", "module": "时间延迟", "fields": "region_a,region_b,method,method_name,antisymmetrized,seed_channel,target_channel,frequency_band,band_low_hz,band_high_hz,delay_ms,estimate_strength,n_epochs,effective_duration_s,analysis_sfreq_hz,n_points,delay_resolution_ms,status"},
    "time_delay_region_spectrum.csv": {"grain": "方法×反对称状态×脑区对×频带×延迟点一行", "module": "时间延迟", "fields": "region_a,region_b,method,method_name,antisymmetrized,frequency_band,band_low_hz,band_high_hz,delay_ms,estimate_strength,estimate_strength_mean,estimate_strength_sd,n_channel_pairs,n_epochs,effective_duration_s,analysis_sfreq_hz,n_points,delay_resolution_ms"},
    "time_delay_channel_pair_summary.csv": {"grain": "方法×反对称状态×通道对×频带一行", "module": "时间延迟", "fields": "region_a,region_b,method,method_name,antisymmetrized,seed_channel,target_channel,frequency_band,band_low_hz,band_high_hz,peak_delay_ms,peak_strength,delay_resolution_ms,direction_relative_to_seed_target,n_epochs,effective_duration_s,status"},
    "time_delay_band_summary.csv": {"grain": "方法×反对称状态×脑区对×频带一行", "module": "时间延迟", "fields": "region_a,region_b,method,method_name,antisymmetrized,frequency_band,band_low_hz,band_high_hz,region_peak_delay_ms,region_peak_strength,channel_pair_median_delay_ms,channel_pair_mad_delay_ms,channel_pair_median_peak_strength,n_channel_pairs,n_epochs,effective_duration_s,delay_resolution_ms,direction_relative_to_seed_target,delay_window_min_ms,delay_window_max_ms,quality_flag,status"},
    "time_delay_input_checks.csv": {"grain": "每项 TDE 输入检查一行", "module": "时间延迟诊断", "fields": "check,value,status,note"},
    "time_delay_failures.csv": {"grain": "失败的方法×脑区对×反对称状态一行", "module": "时间延迟诊断", "fields": "region_a,region_b,method,antisymmetrized,failure_reason,n_epochs"},
    "time_delay_metadata.json": {"grain": "每次 TDE 运行一份参数快照", "module": "时间延迟元数据", "fields": "后端版本、重采样、频带、延迟窗、点数/分辨率、方向约定、有效 epoch/时长及状态"},
    "connectivity_binned_spectrum.csv": {"grain": "每个方法×脑区/通道对×频率箱一行；关闭箱化时只保存 status 列", "module": "连接频率箱（辅助）", "fields": "method,region_a,region_b,component_index,aggregation_level,seed_channel,target_channel,bin_low_hz,bin_high_hz,frequency_hz,value_raw_or_summary,value_strength,n_frequency_points,status,display_only,binning_statistic,binning_note"},
    "connectivity_display_spectrum.csv": {"grain": "原连接谱每行附加一个显示平滑值；显示平滑关闭时只保存 status 列", "module": "连接显示辅助", "fields": "region_a,region_b,seed_region,target_region,direction_order,method,aggregation_level,seed_channel,target_channel,seed_channels,target_channels,n_seed_channels,n_target_channels,rank_seed,rank_target,component_index,n_components_requested,n_components_returned,frequency_hz,value_raw,value_nonfinite_type,value_strength,display_value_definition,estimate_note,n_epochs,effective_duration_s,frequency_is_excluded_line_noise,spectral_mode,mt_bandwidth_hz,mt_adaptive,mt_low_bias,n_tapers,time_bandwidth_product,n_tapers_note,estimated_rank_metadata,frequency_grid_hz,n_channel_pairs_total,frequency_is_masked_for_analysis,frequency_is_masked_for_plot,line_noise_mask_source,line_noise_mask_reason,display_value_smoothed,display_only,status"},
    "connectivity_display_roughness.csv": {"grain": "方法×脑区对×成分的显示平滑曲线粗糙度诊断；平滑关闭时只保存 status 列", "module": "连接显示辅助", "fields": "method,region_a,region_b,component_index,n_frequencies,n_valid_points,median_abs_adjacent_diff,total_variation,coefficient_of_variation,resampling_variability,status"},
    "parameterization_status.csv / connectivity_status.csv / time_delay_status.csv": {"grain": "模块关闭时一条状态记录", "module": "模块运行状态", "fields": "status,reason；解释为什么未生成相应科学结果"},
    "band_power_summary.csv（GUI/project）": {"grain": "每个通道×频带一行，epoch 汇总值", "module": "频带功率", "fields": "channel_array_index,channel_name,physical_channel_number,region,band,band_low_hz,band_high_hz,absolute_power,relative_power,n_epochs,status"},
}


FIELD_DESCRIPTIONS: dict[str, str] = {
    "table": "发生校验问题的元数据表名；追溯字段，不是科学量。",
    "severity": "元数据校验严重级别；具体错误或提醒见 code/message。",
    "code": "稳定的元数据校验规则代码；不是生理指标。",
    "message": "面向用户的校验问题说明。",
    "row": "被校验表中的行定位信息；不是 epoch 或动物样本编号。",
    "region": "用户确认的通道所属脑区/区域名称；不由数组索引自动推定。",
    "hemisphere": "通道映射中记录的侧别标签；未知时留空。",
    "probe_or_tetrode": "通道所属探针或 tetrode 的登记标签；缺失不代表不存在。",
    "mapping_status": "通道到物理通道/脑区映射的核实状态。",
    "max_issue_score": "该 epoch 中单个通道最大的 issue_score；是标记数，不是异常严重程度。",
    "duplicate_epoch_detection": "本次是否执行重复 epoch 检查；True 不表示发现重复，发现数量另见 n_duplicate_epoch_rows。",
    "check_frequency_band_hz": "质量检查针对的频率范围，单位 Hz；不是自动滤波或频段功率范围。",
    "frequency_band_check_status": "对该频率范围的质量检查状态/说明，不代表信号已被滤除。",
    "n_fail_epoch_channel_rows": "质量表中 fail 状态的 epoch×通道记录数，不是 fail epoch 数或动物数。",
    "n_warn_epoch_channel_rows": "质量表中 warn 状态的 epoch×通道记录数。",
    "n_duplicate_epoch_rows": "被重复片段检测标记的 epoch 记录数；不自动删除原始 epoch。",
    "min_finite_samples": "该 epoch 各通道中最少的有限采样点数。",
    "n_fail_channels": "该 epoch 中被判为 fail 的通道数。",
    "n_warn_channels": "该 epoch 中被标为 warn 的通道数。",
    "n_fail_epochs": "该通道中包含 fail 标记的 epoch 数；可能与其他通道统计不同。",
    "n_warn_epochs": "该通道中包含 warn 标记的 epoch 数。",
    "n_epoch_channel_estimates": "该脑区 PSD 汇总中参与的 epoch×通道估计数量，不是独立被试数。",
    "nominal_duration_s": "按输入 epoch 数×每 epoch 时长计算的名义累计时长；不表示连续采集时长。",
    "n_valid_epochs": "通过该模块有效性规则的 epoch 数；属于记录内数据量，不是动物样本量。",
    "n_frequency_points": "该频率箱中原有频点数；箱化结果不增加频谱分辨率。",
    "bin_low_hz": "频率箱下边界，单位 Hz。",
    "bin_high_hz": "频率箱上边界，单位 Hz。",
    "binning_statistic": "频率箱内采用的汇总统计量（如均值或中位数）。",
    "binning_note": "频率箱处理说明，尤其说明遮罩点不跨接或替代。",
    "display_value_smoothed": "仅用于显示的平滑连接值；不是原始科学估计，不替代 value_raw/value_strength。",
    "display_only": "True 表示本行/字段仅供显示或诊断，不应作为主科学结果。",
    "band": "配置中的频带名称；边界以同一行 band_low_hz/band_high_hz 为准。",
    "frequency_band": "TDE 使用的频带标签；边界以 band_low_hz/band_high_hz 为准。",
    "bandwidth_definition": "带宽字段的算法定义；本项目 FOOOF 峰带宽按 2σ 记录。",
    "min_r_squared_requested": "本次拟合配置的最低 R² 质量门槛；是筛查参数，不是显著性阈值。",
    "min_peak_prominence_requested": "配置请求的最小峰突出度值；是否真正传入当前后端需查看 min_peak_prominence_status 与 configuration_audit，不能仅凭此列认定它影响了拟合。",
    "min_peak_prominence_status": "峰突出度门槛的可用性/检查状态；不是峰功率结果。",
    "fit_low_hz": "谱参数化拟合频率下界，单位 Hz。",
    "fit_high_hz": "谱参数化拟合频率上界，单位 Hz。",
    "method_name": "TDE 后端方法编号对应的名称；应与 method 及运行版本共同解释。",
    "antisymmetrized": "是否使用时间反对称化 TDE 输出；不是输入数据已去除共同参考的保证。",
    "n_tapers_note": "关于 multitaper 实际 taper 数计算或适用性的说明文本。",
    "estimated_rank_metadata": "后端返回的 rank 元数据原样记录；需结合 rank_seed/rank_target 读取。",
    "n_seed_channels": "seed 集合实际参与估计的通道数。",
    "n_target_channels": "target 集合实际参与估计的通道数。",
    "channel_array_indices": "以分隔字符串保存的通道数组索引；逐项结合通道表映射。",
    "region_pair": "本次连接估计的脑区对标识；方向由 seed/target 字段定义。",
    "frequency_grid_hz": "连接输出频率栅格的典型步长，单位 Hz；不等同于 multitaper 平滑带宽。",
    "n_valid_points": "某诊断/曲线组中通过有限值与遮罩筛选的点数。",
    "n_frequencies": "该连接曲线所包含的频率点数；实际有效点数见 n_valid_points。",
    "n_frequencies_returned": "后端返回的连接频率点数。",
    "n_total_values": "该方法/频率诊断组的总记录值数量。",
    "n_finite": "该诊断组中的有限数值数量。",
    "n_nan": "该诊断组中的 NaN 数量；不等于真实零连接。",
    "n_inf": "该诊断组中的 Inf 数量。",
    "n_points": "延迟曲线或频率分析网格点数；相邻点间距由分辨率字段说明。",
    "plot_frequency_index": "绘图频率轴中的序号；不是物理频率，实际 Hz 见 frequency_hz。",
    "is_masked": "频率诊断中该点是否被指定遮罩；原因见 mask_reason。",
    "mask_reason": "频率点被遮罩或标记的理由。",
    "mask_source": "产生频率遮罩的配置/检测来源。",
    "line_noise_mask_source": "工频绘图或分析遮罩来源；被遮罩不等于原始数值被删除。",
    "line_noise_mask_reason": "工频遮罩理由；与计算缺失、NaN 和估计失败分开。",
    "robust_z_vs_valid_epochs": "该片段 RMS 相对有效 epoch 分布的稳健标准分，用于异质性提示，不是统计检验。",
    "channel_pair_median_peak_strength": "各有效通道对自身延迟曲线峰强度的中位数；不是动物间汇总。",
    "quality_flag": "结果质量提醒标签，例如峰触及延迟窗边界；应结合 status 与备注。",
    "rank_offset": "敏感性分析中相对基准 rank 的变化量。",
    "rank_reason": "实际选择 rank 的规则/依据说明。",
    "rank_relative_tolerance": "数值秩判定采用的相对奇异值容差；是计算规则参数，不是生理阈值。",
    "rank_variance_threshold": "自动 rank 候选维数的累计方差比例阈值。",
    "array_index": "通道在输入数据数组中的零基位置；结合 channel_table 映射到物理通道。",
    "channel_array_index": "通道在当前输入数组中的索引；不等于物理通道编号。",
    "physical_channel_number": "从实际通道名称或已确认映射得到的物理编号，不由数组位置推断。",
    "mne_channel_type": "MNE 读取到的通道类型标签，不改变实验对象身份。",
    "mne_unit_code": "MNE 单位枚举码；只有单位映射明确时才可换算。",
    "issue_score": "该 epoch×通道触发的质量标记数量，不表示严重程度。",
    "quality_flags": "自动检查触发的具体规则标签；空列表不等同于人工确认正常。",
    "quality_status": "自动检查的 fail/warn/ok 状态，不等于人工复核结论。",
    "finite_sample_count": "片段中有限（非 NaN/Inf）样本数。",
    "nonfinite_sample_count": "片段中 NaN 与 Inf 样本总数。",
    "quality_valid_for_connectivity": "该 epoch 是否符合该连接分析纳入规则；不是独立统计样本标签。",
    "signal_heterogeneity_flag": "按配置规则标记的信号异质性提示，需结合原始片段/行为信息复核。",
    "pattern_value": "MNE 返回的 MIC 空间模式数值；不是通道贡献率，也不是源定位。",
    "pattern_role": "MIC pattern 属于 seed 侧或 target 侧的角色标签。",
    "covariance_condition_number": "协方差矩阵条件数；较大提示多变量数值估计可能不稳定，不是连接强度。",
    "mean_strength_2_100hz": "对应诊断列定义频率范围内强度的均值；按该行 method 解释。",
    "max_strength_2_100hz": "对应诊断列定义频率范围内强度的最大值；不是显著性。",
    "mean_std": "跨 epoch 标准差的均值摘要，单位沿用输入信号。",
    "peak_index": "通道内检出峰的零基序号；不同通道同序号不代表同一种振荡。",
    "fit_status": "拟合是否成功的状态；失败行保留，不应读取空参数为零。",
    "aperiodic_mode": "非周期模型模式（如 fixed/knee），决定模型参数定义。",
    "backend_requested": "配置请求的谱参数化后端。",
    "backend_used": "实际调用的参数化后端实现/类名。",
    "backend_warning": "后端兼容或降级提示；须与 backend_used 一起查看。",
    "psd_method": "PSD 估计方法标签，如 Welch 或 multitaper。",
    "psd_unit": "PSD 单位声明；density 时为输入信号单位平方每 Hz。",
    "source_unit": "输入信号单位标签；未知或 MNE 枚举码不应猜成微伏。",
    "nperseg_used": "Welch 实际每个子窗样本数，影响频率网格和估计稳定性。",
    "noverlap_used": "Welch 子窗之间重叠样本数。",
    "nfft_used": "Welch FFT 点数；零填充可加密频率栅格但不提高真实分辨能力。",
    "multitaper_bandwidth_hz": "multitaper 平滑带宽，单位 Hz；影响平滑程度与 taper 数。",
    "multitaper_adaptive": "是否启用自适应 taper 权重。",
    "multitaper_low_bias": "是否启用低偏差 taper 筛选。",
    "n_tapers": "实际使用的 DPSS taper 数。",
    "time_bandwidth_product": "multitaper 时间—带宽积参数。",
    "relative_power_unit": "相对功率数值单位；fraction 为比例，显示百分数时乘100。",
    "absolute_power_unit": "绝对积分功率单位，通常是输入信号单位的平方。",
    "band_frequency_segments": "实际参与频带积分的连续频率区间。",
    "denominator_frequency_segments": "实际参与相对功率分母积分的连续频率区间。",
    "pattern_note": "MIC pattern 的数据尺度/解释限制说明。",
    "aggregation_level": "本行连接是通道对层级还是脑区/多变量汇总层级。",
    "direction_order": "有向估计的 seed/source 到 target 的输入顺序标签；不是生物因果方向。",
    "seed_channels": "seed 侧实际参与估计的通道名称列表。",
    "target_channels": "target 侧实际参与估计的通道名称列表。",
    "seed_array_indices": "seed 通道对应输入数组索引列表。",
    "target_array_indices": "target 通道对应输入数组索引列表。",
    "display_value_definition": "显示值从原始结果转换而来的规则，如 MIC 取绝对值。",
    "estimate_note": "关于原始估计值、符号和值域的补充说明。",
    "cache_hit": "本次调用是否命中可复用计算缓存；不代表结果质量。",
    "cache_status": "计算缓存命中、绕过或失效状态。",
    "elapsed_s": "后端调用耗时，单位秒；属于运行追溯，不是科学指标。",
    "analysis_task_id": "一次连接分析任务标识，用于归属后端谱估计调用。",
    "call_purpose": "该谱估计调用的用途，如主估计、rank 或稳定性诊断。",
    "failure_reason": "拟合/估计失败原因；状态字段与原因字段需结合查看。",
    "n_frequency_bins": "拟合输入中通过有效筛选的频率格点数。",
    "delay_window_min_ms": "延迟搜索窗口下界，单位 ms。",
    "delay_window_max_ms": "延迟搜索窗口上界，单位 ms。",
    "analysis_sfreq_hz": "TDE 分析实际采样率；可能经抗混叠重采样后低于原采样率。",
    "psd_value": "线性功率谱密度值；scaling=density 时单位为输入单位²/Hz。",
    "psd_sd": "各 epoch 在同一通道、同一频率处 PSD 的标准差。",
    "psd_sd_across_channels": "同一脑区同频率的通道 PSD 间标准差，不是动物间误差。",
    "absolute_power": "该 epoch、通道、频带的 PSD 梯形积分，单位为输入单位²。",
    "relative_power": "频带绝对功率除以指定分母范围功率；文件中保存比例，GUI 可换算百分数。",
    "observed_power": "进入谱参数化的线性 PSD；单位沿用 PSD。",
    "observed_log10_power": "观测 PSD 的 log10 值。",
    "full_model_power": "非周期背景与周期峰完整拟合模型反变换到线性功率密度空间的值。",
    "full_model_log10_power": "完整模型在 log10 PSD 空间的值。",
    "aperiodic_power": "拟合的非周期背景反变换到线性 PSD 空间的值。",
    "aperiodic_log10_power": "非周期背景在 log10 PSD 空间的值。",
    "periodic_component_power": "完整拟合模型线性功率减非周期背景线性功率；可因拟合重建而为负，不是独立物理振荡谱。",
    "periodic_component_log10_additive": "拟合高斯周期峰在 log10 空间的加性和。",
    "periodic_model_log10": "同一周期高斯峰加和的模型曲线，处于 log10 功率差空间。",
    "observed_minus_aperiodic_log10": "log10(观测 PSD) 减 log10(非周期背景)，包含未解释起伏，可能为负。",
    "reconstructed_gaussian_sum_log10": "使用真实高斯中心、振幅和 sigma 重建后相加的峰曲线。",
    "residual_log10": "观测 log10 PSD 减完整模型 log10 PSD。",
    "offset": "非周期模型的 log10 截距；会随 PSD 功率单位改变。",
    "exponent": "非周期固定背景随频率变化的指数斜率参数，无量纲；不能直接等同兴奋/抑制平衡。",
    "knee": "knee 模型的弯折参数；仅 knee 模式适用，量纲依赖后端模型定义。",
    "r_squared": "后端拟合优度统计量；不是生理效应量或显著性。",
    "error": "后端定义的谱拟合误差，具体标度依赖所用后端版本。",
    "center_frequency_hz": "拟合峰中心频率 CF，单位 Hz。",
    "peak_power_log10": "拟合峰高于非周期背景的 log10 功率差，不是原始 PSD 峰值或频带积分。",
    "peak_height_log10": "后端导出的峰高度；当前代码按与 peak_power_log10 同一对数功率差解释。",
    "bandwidth_hz": "当前结果契约采用高斯 2σ 带宽，单位 Hz；不是 FWHM。",
    "gaussian_sigma_hz": "重建高斯峰使用的标准差 σ，单位 Hz。",
    "value_raw": "方法原始输出；符号和值域按 method 定义，不要跨方法直接比较。",
    "value_strength": "用于展示的强度字段；MIC 为 abs(value_raw)，其他方法保留其方法原生值。",
    "value_raw_or_summary": "频带汇总表字段；须结合 aggregation_definition、method 和方向字段解释。",
    "estimate_strength": "PyBispectra TDE 对该延迟点的算法返回值；非通用概率或0–1连接系数。",
    "estimate_strength_mean": "同区域通道对在该延迟点估计值的算术平均。",
    "estimate_strength_sd": "同区域通道对在该延迟点估计值的标准差。",
    "peak_delay_ms": "单通道对延迟曲线达到最大估计强度的位置，单位 ms。",
    "region_peak_delay_ms": "区域中位延迟曲线达到峰值的位置，单位 ms。",
    "channel_pair_median_delay_ms": "各通道对自身峰延迟的中位数，单位 ms。",
    "channel_pair_mad_delay_ms": "通道对峰延迟相对其中位数的绝对偏差中位数（MAD），单位 ms。",
    "region_peak_strength": "区域中位延迟曲线峰处的 TDE 估计值。",
    "peak_strength": "单通道对峰延迟处的 TDE 估计值。",
    "signal_rms": "该连接 epoch 选定信号的均方根幅度摘要。",
    "std": "对应信号片段的标准差，单位沿用输入信号。",
    "max_abs": "片段绝对幅值最大值，单位沿用输入信号。",
    "max_abs_robust_z": "最大绝对稳健标准分，用于异常幅度提示。",
    "saturation_fraction": "样本等于该片段最大值或最小值的比例，用于疑似饱和提示。",
    "line_noise_peak_ratio": "配置工频候选频率附近峰相对局部 PSD 中位基线的比值。",
    "correlation": "指定通道样本/片段间的相关系数；用于冗余诊断，不是跨区连接指标。",
    "singular_value": "多通道数据矩阵的奇异值，描述一个线性数据方向的幅度。",
    "variance_fraction": "对应奇异维度占总方差的比例。",
    "cumulative_variance_fraction": "截至该奇异维度的累计方差比例。",
    "band_cv": "频带内连接频率曲线的变异系数诊断。",
    "median_abs_adjacent_diff": "未屏蔽连续频点间相邻差绝对值的中位数，用于粗糙度诊断。",
    "total_variation": "未屏蔽连续频率段上的相邻差总变差。",
    "coefficient_of_variation": "粗糙度计算中的变异系数诊断值。",
    "resampling_variability": "稳定性/重采样诊断中估计变异摘要。",
    "band_max_gap_hz": "积分保留频点之间观测到的最大间隙，单位 Hz。",
    "frequency_coverage_fraction": "频带中实际纳入频点相对可用频点的覆盖比例。",
    "frequency_hz": "频率坐标，单位 Hz。",
    "frequency_step_hz": "相邻频点的典型间隔，单位 Hz；不能单独代表谱平滑/实际分辨率。",
    "frequency_resolution_hz": "记录的 PSD 基础频率间隔，单位 Hz；零填充后的网格可能更密但不提高真实分辨能力。",
    "delay_ms": "延迟坐标，单位毫秒。",
    "delay_resolution_ms": "延迟曲线相邻采样点间隔，单位毫秒。",
    "n_epochs": "参与该行汇总/估计的 epoch 数；不是独立动物数。",
    "effective_duration_s": "参与本行计算的有效片段总时长（秒），按保留 epoch 数×每段有效时长计算。",
    "effective_valid_duration_s": "质量筛选后有效记录时长（秒）；不表示这些 epoch 首尾连续。",
    "valid_duration_s": "对应 epoch 的有限有效样本数除以采样率得到的有效时长（秒）。",
    "sampling_rate_hz": "输入数据采样率，单位 Hz。",
    "n_times": "每段保存的时间样本数。",
    "n_channels": "对应文件、脑区或统计行内通道数量；上下文由表名与同一行 region 决定。",
    "value_nonfinite_type": "区分有限值、NaN 或 Inf 的类型标签；不是对非有限值的替代。",
    "frequency_is_excluded_line_noise": "该频率是否被配置为工频排除点。",
    "frequency_is_masked_for_analysis": "该频率在分析汇总中是否被屏蔽。",
    "frequency_is_masked_for_plot": "该频率是否仅在绘图显示中被遮罩。",
    "rank_seed": "seed 集合在多变量估计中保留的维度数。",
    "rank_target": "target 集合在多变量估计中保留的维度数。",
    "selected_rank": "按当前可重复数值规则实际采用的脑区维度数，不等于生理最优维数。",
    "numerical_rank": "按记录的数值容差判断出的矩阵数值秩。",
    "variance_rank": "按当前方差比例规则得到的候选维数。",
    "n_components_requested": "MIC 请求提取的连接分量数；不控制 MIM 总相互作用。",
    "n_components_returned": "后端实际返回的 MIC 分量数。",
    "component_index": "MIC 分量序号；不自动表示跨频率固定的生理源身份。",
    "n_frequencies_used": "频带汇总中实际纳入的频点数。",
    "n_frequencies_excluded_line_noise": "因工频规则排除的频点数。",
    "integration_rule": "频带/分母功率积分算法及是否跨缺口的规则标签。",
    "excluded_frequency_count": "按配置未参与该频带或分母积分的频率点数。",
    "periodic_component_negative": "线性模型差值在该频点是否为负；不是负的物理功率。",
    "direction_relative_to_seed_target": "峰延迟相对有序 seed/target 输入的先后标签；非因果方向标签。",
    "n_channel_pairs": "参与区域汇总的通道对数，不是动物数。",
    "n_channel_pairs_total": "该脑区对全部可用通道对数量。",
    "n_negative_estimates": "频带/频率聚合前出现的负有限估计数；对于去偏平方 wPLI 不代表负耦合。",
    "aggregation_definition": "跨频率/通道对的实际聚合顺序与函数说明。",
    "fit_quality_status": "按配置拟合质量门槛得到的状态标签。",
    "peak_status": "峰检出状态；区分有效拟合无峰与拟合失败。",
    "n_peaks": "该通道拟合实际检出的峰数；零表示拟合成功但未检出峰。",
}


def field_description(name: str) -> str:
    """Describe exact scientific fields and common metadata fields."""
    if name in FIELD_DESCRIPTIONS:
        return FIELD_DESCRIPTIONS[name]
    if name.endswith(("_hz", "_high_hz", "_low_hz")):
        return "频率或频带边界，单位 Hz；边界具体含义由字段名前缀决定。"
    if name.endswith("_ms"):
        return "时间延迟、分辨率或延迟窗参数，单位毫秒；方向解释遵循该结果的 seed/target 约定。"
    if name.startswith("n_"):
        return "对应对象的数量/样本数；它表示记录内部数量，不自动等于独立动物数。"
    if name.endswith("_status") or name in {"status", "quality_flag", "quality_status", "fit_status", "fit_quality_status"}:
        return "程序状态或质量标签；不是科学测量值。具体状态字符串应结合对应失败/质量表解释。"
    if name.endswith("_unit") or name in {"source_unit", "psd_unit"}:
        return "对应结果值的物理单位声明；若来源单位未确认，可能是 unknown 或 MNE 单位码。"
    if name.endswith("_index") or name in {"component", "component_index", "peak_index", "array_index"}:
        return "保存数组/表中的零基或明确标注的序号；不等同于物理通道编号或动物编号。"
    if name in {"region_a", "region_b", "seed_region", "target_region", "region_pair", "direction_order"}:
        return "映射后的脑区/方向身份；seed 与 target 是估计中的有序两侧，不自动表示因果方向。"
    if name in {"channel_name", "seed_channel", "target_channel", "channel_i", "channel_j", "channel_names"}:
        return "来自通道表的实际通道名称；数组位置与物理通道编号由 channel_table 映射。"
    if name in {"epoch_index", "saved_index", "original_candidate_index", "selection_value", "events_raw_value"}:
        return "epoch/原始事件追溯索引或原始值；除非另有已确认时间坐标，不解释为原始记录秒数。"
    if name in {"fit_status", "peak_status", "quality_status", "mapping_status", "status"}:
        return "计算或审核状态标签；需与对应失败原因、质量标记字段一起读取。"
    if name in {"value", "value_raw_or_summary"}:
        return "表中保留的数值；请依赖同一行的 method、单位、summary/aggregation 和 status 解释。"
    return "配置、来源、维度、质量或审计字段；它用于追溯计算上下文，不是独立生物学测量。"


def render_topic(topic_id: str) -> str:
    topic = HELP_TOPICS[topic_id]
    figure_rows = [item for item in FIGURES if item["topic"] == topic_id]
    lines = [f"# {topic['title']}", "", "## 快速读法", "", topic["short"], "", "## 详细说明", "", topic["detail"]]
    if figure_rows:
        lines.extend(["", "## 本主题下的实际图表", ""])
        for item in figure_rows:
            lines.extend([f"### {item['title']}", "", item["short"], "", item["detail"]])
    return "\n".join(lines).strip() + "\n"
