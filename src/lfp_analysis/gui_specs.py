"""Shared parameter definitions and validation for the desktop GUI.

The GUI uses this module as its single source of truth for editable analysis
parameters.  Display-only settings intentionally do not live here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ParameterDefinition:
    key: str
    label: str
    value_type: str
    default: Any
    unit: str
    minimum: float | None
    maximum: float | None
    algorithms: tuple[str, ...]
    help_text: str
    advanced: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


PARAMETER_DEFINITIONS: tuple[ParameterDefinition, ...] = (
    ParameterDefinition("psd.window", "窗函数", "choice", "hann", "", None, None, ("PSD", "Band Power", "FOOOF"), "实际传给 scipy.signal.welch 的窗定义。", False),
    ParameterDefinition("psd.window_seconds", "Welch 窗长", "float", 1.0, "s", 0.001, 3600.0, ("PSD", "Band Power", "FOOOF"), "按采样率换算为 nperseg；不能超过选定 epoch 内时间窗。", False),
    ParameterDefinition("psd.overlap_percent", "Welch 重叠", "float", 50.0, "%", 0.0, 99.999, ("PSD", "Band Power", "FOOOF"), "换算为 noverlap；必须小于窗长。", False),
    ParameterDefinition("psd.nfft", "FFT 长度", "int", 0, "0=自动", 0, 2_000_000, ("PSD", "Band Power", "FOOOF"), "0 表示使用 nperseg；手动值不能小于 nperseg。零填充不提高真实频谱分辨率。", True),
    ParameterDefinition("psd.detrend", "去趋势", "choice", "constant", "", None, None, ("PSD", "Band Power", "FOOOF"), "Welch 支持的 constant、linear 或 False。", True),
    ParameterDefinition("psd.average", "Welch 子窗平均", "choice", "mean", "", None, None, ("PSD", "Band Power", "FOOOF"), "Welch 内部子窗的 mean 或 median；独立于跨 epoch 汇总。", True),
    ParameterDefinition("psd.epoch_aggregation", "跨 epoch 汇总", "choice", "mean", "", None, None, ("PSD", "Band Power", "FOOOF"), "独立于 Welch 子窗平均；用于通道 PSD 的跨 epoch 汇总。", False),
    ParameterDefinition("psd.fmin_hz", "PSD 最低频率", "float", 1.0, "Hz", 0.0, None, ("PSD", "Band Power", "FOOOF"), "底层 PSD 计算范围，不是仅改变图的显示范围。", False),
    ParameterDefinition("psd.fmax_hz", "PSD 最高频率", "float", 200.0, "Hz", 0.001, None, ("PSD", "Band Power", "FOOOF"), "不得超过 Nyquist 频率。", False),
    ParameterDefinition("parameterization.fit_low_hz", "拟合最低频率", "float", 2.0, "Hz", 0.0, None, ("FOOOF",), "specparam/FOOOF 的输入频率范围；注意 1 Hz 高通边缘。", False),
    ParameterDefinition("parameterization.fit_high_hz", "拟合最高频率", "float", 150.0, "Hz", 0.001, None, ("FOOOF",), "必须位于输入 PSD 的有效频率范围内。", False),
    ParameterDefinition("parameterization.aperiodic_mode", "非周期模式", "choice", "fixed", "", None, None, ("FOOOF",), "默认 fixed；knee 只有后端支持时才开放。", False),
    ParameterDefinition("parameterization.peak_width_low_hz", "峰宽下限", "float", 1.0, "Hz", 0.01, None, ("FOOOF",), "实际后端 peak_width_limits 的下界。", False),
    ParameterDefinition("parameterization.peak_width_high_hz", "峰宽上限", "float", 12.0, "Hz", 0.02, None, ("FOOOF",), "实际后端 peak_width_limits 的上界。", False),
    ParameterDefinition("parameterization.max_n_peaks", "最大峰数", "int", 6, "个", 0, 1000, ("FOOOF",), "允许 0；不提供后端不支持的无限值。", False),
    ParameterDefinition("parameterization.min_peak_height", "最小峰高", "float", 0.0, "log10", 0.0, None, ("FOOOF",), "后端拟合尺度中的阈值，不是线性功率或 dB。", True),
    ParameterDefinition("parameterization.peak_threshold", "峰检测阈值", "float", 2.0, "残差 SD", 0.0, None, ("FOOOF",), "相对于拟合残差波动的峰检测阈值。", True),
    ParameterDefinition("parameterization.min_r_squared", "拟合质量阈值", "float", 0.90, "R²", 0.0, 1.0, ("FOOOF",), "只改变质量标记，不静默删除低质量或无峰结果。", False),
    ParameterDefinition("connectivity.fmin_hz", "连接最低频率", "float", 2.0, "Hz", 0.0, None, ("MIC", "MIM", "wpli2_debiased"), "连接后端的实际 fmin。", False),
    ParameterDefinition("connectivity.fmax_hz", "连接最高频率", "float", 100.0, "Hz", 0.001, None, ("MIC", "MIM", "wpli2_debiased"), "不得超过 Nyquist。", False),
    ParameterDefinition("connectivity.mt_bandwidth_hz", "Multitaper 平滑带宽", "float", 4.0, "Hz", 0.001, None, ("MIC", "MIM", "wpli2_debiased"), "仅在 multitaper 路径中生效。", False),
    ParameterDefinition("connectivity.min_epochs", "最少有效 epoch", "int", 5, "个", 1, 1_000_000, ("MIC", "MIM", "wpli2_debiased"), "少于此值时连接模块返回明确的不足状态。", False),
    ParameterDefinition("connectivity.rank_strategy", "秩策略", "choice", "data_driven_energy_99pct", "", None, None, ("MIC", "MIM"), "自动秩或按每脑区固定秩。", False),
    ParameterDefinition("connectivity.rank_variance_threshold", "秩方差阈值", "float", 0.99, "比例", 0.0, 1.0, ("MIC", "MIM"), "只用于预先定义的秩规则，不依据效应大小挑选。", True),
    ParameterDefinition("connectivity.fixed_rank_M1", "M1 固定秩", "int", 0, "0=自动", 0, 4, ("MIC", "MIM"), "仅 fixed_rank 策略使用；不能超过实际参与的 M1 通道数。", True),
    ParameterDefinition("connectivity.fixed_rank_STR", "STR 固定秩", "int", 0, "0=自动", 0, 4, ("MIC", "MIM"), "仅 fixed_rank 策略使用；不能超过实际参与的 STR 通道数。", True),
    ParameterDefinition("connectivity.fixed_rank_PF", "PF 固定秩", "int", 0, "0=自动", 0, 4, ("MIC", "MIM"), "仅 fixed_rank 策略使用；不能超过实际参与的 PF 通道数。", True),
    ParameterDefinition("connectivity.fixed_rank_SNr", "SNr 固定秩", "int", 0, "0=自动", 0, 4, ("MIC", "MIM"), "仅 fixed_rank 策略使用；不能超过实际参与的 SNr 通道数。", True),
    ParameterDefinition("connectivity.stability_n_subsamples", "稳定性子集次数", "int", 2, "次", 0, 100, ("MIC", "MIM", "wpli2_debiased"), "片段稳定性检查的随机子集次数。", True),
    ParameterDefinition("time_delay.analysis_sfreq_hz", "延迟分析采样率", "float", 200.0, "Hz", 1.0, None, ("Time Delay",), "仅用于 TDE 内部抗混叠降采样，原始 LFP 不修改。", False),
    ParameterDefinition("time_delay.max_delay_ms", "最大延迟窗口", "float", 1000.0, "ms", 1.0, 20_000.0, ("Time Delay",), "生成对称延迟网格；正值表示 seed 领先 target。", False),
    ParameterDefinition("time_delay.fmin_hz", "延迟最低频率", "float", 2.0, "Hz", 0.0, None, ("Time Delay",), "TDE 频率范围。", False),
    ParameterDefinition("time_delay.fmax_hz", "延迟最高频率", "float", 80.0, "Hz", 0.001, None, ("Time Delay",), "不得超过延迟分析 Nyquist。", False),
)


REGION_ORDER = ("M1", "STR", "PF", "SNr")
REGION_PAIRS = tuple((REGION_ORDER[i], REGION_ORDER[j]) for i in range(4) for j in range(i + 1, 4))


def definitions_for(indicators: list[str] | tuple[str, ...]) -> list[ParameterDefinition]:
    selected = set(indicators)
    return [definition for definition in PARAMETER_DEFINITIONS if selected.intersection(definition.algorithms)]


def config_value(config: dict[str, Any], key: str, default: Any = None) -> Any:
    value: Any = config
    for part in key.split("."):
        if not isinstance(value, dict):
            return default
        value = value.get(part, default)
    return value


def set_config_value(config: dict[str, Any], key: str, value: Any) -> None:
    parts = key.split(".")
    target = config
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


def normalize_gui_values(values: dict[str, Any], sfreq: float, n_times: int) -> dict[str, Any]:
    """Convert GUI values to the backend configuration representation."""
    normalized = dict(values)
    psd = normalized.setdefault("psd", {})
    window_seconds = float(psd.get("window_seconds", 1.0))
    nperseg = max(1, round(window_seconds * sfreq))
    overlap = float(psd.get("overlap_percent", 50.0))
    psd["nperseg"] = nperseg
    psd["noverlap"] = round(nperseg * overlap / 100.0)
    psd["nfft"] = None if int(psd.get("nfft", 0) or 0) == 0 else int(psd["nfft"])
    if psd.get("detrend") == "none":
        psd["detrend"] = False
    normalized.setdefault("parameterization", {})["fit_range_hz"] = [
        float(normalized["parameterization"].get("fit_low_hz", 2.0)),
        float(normalized["parameterization"].get("fit_high_hz", 150.0)),
    ]
    normalized["parameterization"]["peak_width_limits_hz"] = [
        float(normalized["parameterization"].get("peak_width_low_hz", 1.0)),
        float(normalized["parameterization"].get("peak_width_high_hz", 12.0)),
    ]
    normalized["parameterization"]["enabled"] = True
    normalized.setdefault("connectivity", {})["enabled"] = True
    normalized.setdefault("time_delay", {})["enabled"] = True
    normalized["_gui_selected_time_samples"] = int(n_times)
    return normalized


def validate_snapshot(
    snapshot: dict[str, Any],
    sfreq: float,
    n_times: int,
    n_epochs: int,
    channel_table: Any,
) -> tuple[list[str], list[str]]:
    """Validate GUI values before any expensive backend call."""
    errors: list[str] = []
    warnings: list[str] = []
    indicators = list(snapshot.get("indicators", []))
    if not indicators:
        errors.append("至少选择一个分析指标。")
    channels = list(snapshot.get("selected_channel_names", []))
    epochs = list(snapshot.get("selected_epoch_indices", []))
    if not channels:
        errors.append("至少选择一个通道。")
    if not epochs:
        errors.append("至少选择一个 epoch。")
    selection = snapshot.get("selection", {})
    start_s = float(selection.get("time_start_s", 0.0))
    end_s = float(selection.get("time_end_s", n_times / sfreq))
    if end_s <= start_s:
        errors.append("epoch 内时间窗的结束时间必须大于开始时间。")
    selected_times = max(0, round((end_s - start_s) * sfreq))
    if selected_times < 2:
        errors.append("选定时间窗至少需要两个采样点。")
    values = snapshot.get("values", {})
    normalized = normalize_gui_values(values, sfreq, selected_times)
    psd = normalized.get("psd", {})
    nperseg = int(psd.get("nperseg", 0))
    noverlap = int(psd.get("noverlap", 0))
    nfft = psd.get("nfft")
    if nperseg > selected_times:
        errors.append(f"Welch 窗长 {nperseg / sfreq:g} s 超过选定时间窗 {selected_times / sfreq:g} s；GUI 不会静默缩短。")
    if noverlap >= nperseg:
        errors.append("Welch 重叠必须小于窗长。")
    if nfft is not None and int(nfft) < nperseg:
        errors.append("FFT 长度不能小于 nperseg。")
    nyquist = sfreq / 2.0
    for section, label in ((psd, "PSD"), (normalized.get("connectivity", {}), "连接"), (normalized.get("time_delay", {}), "时间延迟")):
        if label == "时间延迟":
            section = dict(section)
            analysis_sfreq = float(section.get("analysis_sfreq_hz", sfreq))
            high_limit = analysis_sfreq / 2.0
        else:
            high_limit = nyquist
        if label != "PSD" and label == "连接" and not (set(indicators) & {"MIC", "MIM", "wpli2_debiased"}):
            continue
        if label == "时间延迟" and "Time Delay" not in indicators:
            continue
        low = float(section.get("fmin_hz", 0.0))
        high = float(section.get("fmax_hz", high_limit))
        if low < 0 or high <= low or high > high_limit:
            errors.append(f"{label}频率范围 {low:g}–{high:g} Hz 超出数据支持范围 0–{high_limit:g} Hz。")
    if "FOOOF" in indicators:
        param = normalized.get("parameterization", {})
        low = float(param.get("fit_low_hz", 2.0))
        high = float(param.get("fit_high_hz", 150.0))
        psd_low = float(psd.get("fmin_hz", 1.0))
        psd_high = float(psd.get("fmax_hz", nyquist))
        if low < psd_low or high > psd_high or high <= low:
            errors.append("FOOOF/specparam 拟合范围必须位于 PSD 输入频率范围内。")
        width_low = float(param.get("peak_width_low_hz", 1.0))
        width_high = float(param.get("peak_width_high_hz", 12.0))
        if width_high <= width_low:
            errors.append("峰宽上限必须大于下限。")
        if width_low < 2.0 * sfreq / max(nfft or nperseg, 1):
            warnings.append("峰宽下限接近或小于频谱栅格，峰参数可能不稳定。")
    relative = values.get("relative_power", {})
    denominator_low = float(relative.get("denominator_low_hz", psd.get("fmin_hz", 1.0)))
    denominator_high = float(relative.get("denominator_high_hz", psd.get("fmax_hz", nyquist)))
    if denominator_high <= denominator_low or denominator_low < float(psd.get("fmin_hz", 1.0)) or denominator_high > float(psd.get("fmax_hz", nyquist)):
        errors.append("相对功率分母范围必须位于 PSD 范围内且上限大于下限。")
    for band in values.get("bands", []):
        try:
            band_low = float(band["low_hz"])
            band_high = float(band["high_hz"])
            if band_high <= band_low or band_low < float(psd.get("fmin_hz", 1.0)) or band_high > float(psd.get("fmax_hz", nyquist)):
                errors.append(f"频段 {band.get('name', '')} 不在 PSD 范围内或上下限无效。")
        except (KeyError, TypeError, ValueError):
            errors.append("频段表存在无法解析的行。")
    if set(indicators) & {"MIC", "MIM", "wpli2_debiased"}:
        if len(epochs) < int(normalized.get("connectivity", {}).get("min_epochs", 5)):
            warnings.append("有效 epoch 数少于连接模块的建议最小值，结果将保留但标记为低数据量。")
        region_names = set(channel_table.loc[channel_table["channel_name"].isin(channels), "region"].dropna().astype(str)) if hasattr(channel_table, "loc") else set()
        if len(region_names) < 2:
            errors.append("连接指标至少需要两个已映射脑区的参与通道。")
        if "MIM" in indicators and int(normalized.get("connectivity", {}).get("rank_variance_threshold", 0.99) * 100) <= 0:
            errors.append("MIM 的秩方差阈值必须大于 0。")
        if normalized.get("connectivity", {}).get("rank_strategy") == "fixed_rank":
            selected_regions = channel_table.loc[channel_table["channel_name"].isin(channels)].groupby("region").size().to_dict() if hasattr(channel_table, "loc") else {}
            for region in REGION_ORDER:
                requested = int(normalized.get("connectivity", {}).get(f"fixed_rank_{region}", 0) or 0)
                if requested > int(selected_regions.get(region, 0)):
                    errors.append(f"{region} 固定秩 {requested} 超过当前参与通道数 {selected_regions.get(region, 0)}。")
    if "Time Delay" in indicators and len(epochs) < 2:
        warnings.append("时间延迟分析使用少于两个 epoch，结果可能不稳定。")
    if len(epochs) == n_epochs:
        warnings.append("当前使用全部可选 epoch；质量标记仍会保留，不会静默删除。")
    return errors, warnings


def parameter_schema() -> list[dict[str, Any]]:
    return [definition.as_dict() for definition in PARAMETER_DEFINITIONS]
