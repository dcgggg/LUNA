"""Preparation and plotting helpers for interactive FOOOF/specparam views.

This module only filters and visualizes saved parameterization tables.  It does
not fit spectra and never treats a channel, epoch, or peak as an animal-level
observation.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd
from matplotlib import colors
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties

from .band_power_plots import REGION_ORDER, _plot_font
from .colors import DEFAULT_COLOR_TEMPLATE, channel_color


def _tr(language: str, zh: str, en: str) -> str:
    """Return display text without forcing Chinese glyphs into English figures."""
    return en if str(language).lower() == "en" else zh


def _region_text(value: Any, language: str = "zh") -> str:
    return _text(value, _tr(language, "未映射", "Unmapped"))


def _text(value: Any, fallback: str = "") -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return fallback
    result = str(value).strip()
    return fallback if result in {"", "nan", "None"} else result


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _physical_sort_key(value: Any) -> tuple[int, float, str]:
    text = _text(value)
    try:
        return (0, float(text), text)
    except (TypeError, ValueError):
        return (1, float("inf"), text)


def normalize_bands(bands: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if isinstance(bands, dict):
        iterable = [{"name": name, "low_hz": values[0], "high_hz": values[1]} for name, values in bands.items()]
    elif isinstance(bands, list):
        iterable = bands
    else:
        iterable = []
    for item in iterable:
        if not isinstance(item, dict):
            continue
        try:
            name = _text(item.get("name"), "band")
            low = float(item.get("low_hz"))
            high = float(item.get("high_hz"))
        except (TypeError, ValueError):
            continue
        if np.isfinite(low) and np.isfinite(high) and high > low:
            result.append({"name": name, "low_hz": low, "high_hz": high})
    result.sort(key=lambda row: (row["low_hz"], row["high_hz"], row["name"]))
    return result


def _channel_metadata(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    table = tables.get("channel_table", pd.DataFrame())
    if not isinstance(table, pd.DataFrame) or table.empty:
        return pd.DataFrame(columns=["channel_array_index", "channel_name", "physical_channel_number", "region"])
    output = table.copy()
    if "array_index" in output.columns:
        output = output.rename(columns={"array_index": "channel_array_index"})
    for column in ("channel_array_index", "channel_name", "physical_channel_number", "region"):
        if column not in output.columns:
            output[column] = ""
    return output[["channel_array_index", "channel_name", "physical_channel_number", "region"]].drop_duplicates()


def _with_metadata(table: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
    frame = table.copy() if isinstance(table, pd.DataFrame) else pd.DataFrame()
    if frame.empty:
        return frame
    for column in ("channel_array_index", "channel_name", "physical_channel_number", "region"):
        if column not in frame.columns:
            frame[column] = ""
    frame["channel_array_index"] = frame["channel_array_index"].map(_text)
    frame["channel_name"] = frame["channel_name"].map(_text)
    frame["physical_channel_number"] = frame["physical_channel_number"].map(_text)
    frame["region"] = frame["region"].map(lambda value: _text(value, "未映射"))
    if not metadata.empty:
        meta = metadata.copy()
        meta["channel_array_index"] = meta["channel_array_index"].map(_text)
        meta["channel_name"] = meta["channel_name"].map(_text)
        by_index = meta.loc[meta["channel_array_index"].ne("")].drop_duplicates("channel_array_index").set_index("channel_array_index").to_dict("index")
        by_name = meta.loc[meta["channel_name"].ne("")].drop_duplicates("channel_name").set_index("channel_name").to_dict("index")
        for index, row in frame.iterrows():
            item = by_index.get(row["channel_array_index"]) or by_name.get(row["channel_name"])
            if not item:
                continue
            for column in ("channel_name", "physical_channel_number", "region"):
                current = _text(row[column])
                if (not current or current == "未映射") and _text(item.get(column)):
                    frame.at[index, column] = _text(item.get(column))
    frame["channel_label"] = frame.apply(
        lambda row: f"{_text(row['physical_channel_number'])} {_text(row['channel_name'], '?')}" if _text(row["physical_channel_number"]) else _text(row["channel_name"], "?"),
        axis=1,
    )
    return frame


def _normalize_curves(curves: pd.DataFrame) -> pd.DataFrame:
    frame = curves.copy()
    if frame.empty:
        return frame
    numeric_columns = (
        "frequency_hz",
        "observed_power",
        "observed_log10_power",
        "full_model_power",
        "full_model_log10_power",
        "aperiodic_power",
        "aperiodic_log10_power",
        "periodic_component_log10_additive",
        "periodic_model_log10",
        "observed_minus_aperiodic_log10",
        "residual_log10",
    )
    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "periodic_model_log10" not in frame.columns and "periodic_component_log10_additive" in frame.columns:
        frame["periodic_model_log10"] = frame["periodic_component_log10_additive"]
    if "observed_power" not in frame.columns and "observed_log10_power" in frame.columns:
        frame["observed_power"] = np.power(10.0, frame["observed_log10_power"])
    if "aperiodic_power" not in frame.columns and "aperiodic_log10_power" in frame.columns:
        frame["aperiodic_power"] = np.power(10.0, frame["aperiodic_log10_power"])
    if "full_model_log10_power" not in frame.columns and {"aperiodic_log10_power", "periodic_model_log10"}.issubset(frame.columns):
        frame["full_model_log10_power"] = frame["aperiodic_log10_power"] + frame["periodic_model_log10"]
    if "full_model_power" not in frame.columns and "full_model_log10_power" in frame.columns:
        frame["full_model_power"] = np.power(10.0, frame["full_model_log10_power"])
    if "observed_minus_aperiodic_log10" not in frame.columns and {"observed_log10_power", "aperiodic_log10_power"}.issubset(frame.columns):
        frame["observed_minus_aperiodic_log10"] = frame["observed_log10_power"] - frame["aperiodic_log10_power"]
    return frame


def _normalize_peak_bandwidth(peaks: pd.DataFrame) -> pd.DataFrame:
    """Expose BW as the FOOOF two-sided width, including legacy CSVs.

    Older saved project outputs stored the backend Gaussian sigma directly in
    ``bandwidth_hz``.  New outputs carry ``bandwidth_definition`` explicitly;
    legacy rows are converted once on load so the GUI and exports use one
    unambiguous definition.
    """
    frame = peaks.copy()
    if frame.empty or "bandwidth_hz" not in frame.columns:
        return frame
    if "bandwidth_definition" not in frame.columns:
        frame["bandwidth_definition"] = "legacy_backend_sigma_converted_to_2sigma"
        frame["bandwidth_hz"] = pd.to_numeric(frame["bandwidth_hz"], errors="coerce") * 2.0
    else:
        definition = frame["bandwidth_definition"].astype(str)
        legacy = definition.isin({"", "nan", "None", "backend_sigma", "legacy_backend_sigma"})
        if legacy.any():
            frame.loc[legacy, "bandwidth_hz"] = pd.to_numeric(frame.loc[legacy, "bandwidth_hz"], errors="coerce") * 2.0
            frame.loc[legacy, "bandwidth_definition"] = "legacy_backend_sigma_converted_to_2sigma"
    if "gaussian_sigma_hz" not in frame.columns:
        frame["gaussian_sigma_hz"] = pd.to_numeric(frame["bandwidth_hz"], errors="coerce") / 2.0
    return frame


def _add_reconstructed_gaussians(curves: pd.DataFrame, peaks: pd.DataFrame) -> pd.DataFrame:
    """Rebuild per-peak log10 Gaussians for older saved curve tables."""
    frame = curves.copy()
    if frame.empty or peaks.empty:
        return frame
    for row in peaks.to_dict("records"):
        channel = _text(row.get("channel_name"))
        center = _number(row.get("center_frequency_hz"))
        height = _number(row.get("peak_power_log10", row.get("peak_height_log10")))
        bandwidth = _number(row.get("bandwidth_hz"))
        peak_index = row.get("peak_index")
        if not channel or not np.isfinite(center) or not np.isfinite(height) or not np.isfinite(bandwidth) or bandwidth <= 0:
            continue
        try:
            column = f"gaussian_{int(peak_index)}_log10"
        except (TypeError, ValueError):
            continue
        mask = frame["channel_name"].astype(str) == channel
        frequency = frame.loc[mask, "frequency_hz"].to_numpy(float)
        # BW is 2 sigma in the FOOOF convention; height is the log10 Gaussian
        # amplitude above the aperiodic background, not a linear PSD value.
        frame.loc[mask, column] = height * np.exp(-0.5 * ((frequency - center) / (bandwidth / 2.0)) ** 2)
    return frame


def ordered_channels(models: pd.DataFrame, curves: pd.DataFrame | None = None) -> list[dict[str, Any]]:
    frames = [models]
    if isinstance(curves, pd.DataFrame) and not curves.empty:
        frames.append(curves)
    frame = pd.concat([item for item in frames if isinstance(item, pd.DataFrame) and not item.empty], ignore_index=True) if any(isinstance(item, pd.DataFrame) and not item.empty for item in frames) else pd.DataFrame()
    if frame.empty:
        return []
    columns = ["channel_name", "channel_array_index", "physical_channel_number", "region", "channel_label"]
    rows = frame[[column for column in columns if column in frame.columns]].drop_duplicates(subset=["channel_name"]).to_dict("records")
    region_names = list(dict.fromkeys(_text(row.get("region"), "未映射") for row in rows))
    rank = {name: index for index, name in enumerate(REGION_ORDER)} if set(region_names).issubset(set(REGION_ORDER)) else {name: index for index, name in enumerate(region_names)}
    rows.sort(key=lambda row: (rank.get(_text(row.get("region"), "未映射"), len(REGION_ORDER)), _physical_sort_key(row.get("physical_channel_number")), _text(row.get("channel_name"))))
    return rows


def peak_band_mask(peaks: pd.DataFrame, band: dict[str, Any] | None) -> pd.Series:
    if peaks.empty or band is None:
        return pd.Series(True, index=peaks.index)
    cf = pd.to_numeric(peaks["center_frequency_hz"], errors="coerce")
    # Frequency bands use left-closed, right-open boundaries.  Adjacent bands
    # therefore cannot duplicate a peak exactly on a shared boundary.
    return cf.ge(float(band["low_hz"])) & cf.lt(float(band["high_hz"]))


def _representative_peaks(models: pd.DataFrame, peaks: pd.DataFrame, band: dict[str, Any] | None) -> pd.DataFrame:
    if models.empty:
        return pd.DataFrame()
    candidates = peaks.loc[peak_band_mask(peaks, band)].copy() if band is not None else peaks.copy()
    rows: list[dict[str, Any]] = []
    for model in models.to_dict("records"):
        name = _text(model.get("channel_name"))
        available = candidates.loc[candidates["channel_name"].astype(str) == name] if not candidates.empty else pd.DataFrame()
        if not available.empty:
            available = available.sort_values(["peak_power_log10", "center_frequency_hz"], ascending=[False, True], na_position="last")
            row = available.iloc[0].to_dict()
            row["selection_rule"] = "max_peak_power_log10_in_band"
            row["peak_selection_status"] = "representative_peak"
            rows.append(row)
            continue
        row = {key: value for key, value in model.items() if key not in {"n_peaks", "peak_status"}}
        row.update(
            {
                "peak_index": np.nan,
                "center_frequency_hz": np.nan,
                "peak_power_log10": np.nan,
                "peak_height_log10": np.nan,
                "bandwidth_hz": np.nan,
                "selection_rule": "max_peak_power_log10_in_band",
                "peak_selection_status": "fit_failed" if _text(model.get("fit_status")) != "ok" else "no_peak_in_band",
            }
        )
        if (
            band is not None
            and np.isfinite(_number(model.get("fit_low_hz")))
            and np.isfinite(_number(model.get("fit_high_hz")))
            and (float(band["low_hz"]) < _number(model.get("fit_low_hz")) or float(band["high_hz"]) > _number(model.get("fit_high_hz")))
        ):
            row["peak_selection_status"] = "fit_range_not_covering_band"
        rows.append(row)
    return pd.DataFrame(rows)


def prepare_fooof(
    tables: dict[str, pd.DataFrame],
    bands: Any,
    selected_channels: Iterable[str] | None = None,
    selected_regions: Iterable[str] | None = None,
    quality_only: bool = False,
    selected_band: str | None = None,
    peak_mode: str = "representative",
) -> dict[str, Any]:
    metadata = _channel_metadata(tables)
    models = _with_metadata(tables.get("model", pd.DataFrame()), metadata)
    peaks = _normalize_peak_bandwidth(_with_metadata(tables.get("peaks", pd.DataFrame()), metadata))
    curves = _normalize_curves(_with_metadata(tables.get("curves", pd.DataFrame()), metadata))
    if peaks.empty and not len(peaks.columns):
        peaks = pd.DataFrame(columns=["channel_name", "channel_array_index", "physical_channel_number", "region", "peak_index", "center_frequency_hz", "peak_power_log10", "bandwidth_hz"])
    if models.empty:
        models = pd.DataFrame(columns=["channel_name", "channel_array_index", "physical_channel_number", "region", "channel_label", "fit_status", "fit_quality_status"])
    for frame in (models, peaks):
        for column in ("r_squared", "error", "offset", "exponent", "knee", "fit_low_hz", "fit_high_hz", "center_frequency_hz", "peak_height_log10", "peak_power_log10", "bandwidth_hz"):
            if column in frame.columns:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "peak_power_log10" not in peaks.columns and "peak_height_log10" in peaks.columns:
        peaks["peak_power_log10"] = peaks["peak_height_log10"]
    curves = _add_reconstructed_gaussians(curves, peaks)
    if "n_peaks" not in models.columns:
        counts = peaks.groupby("channel_name").size() if not peaks.empty else pd.Series(dtype=int)
        models["n_peaks"] = models["channel_name"].map(counts).fillna(0).astype(int)
    if "peak_status" not in models.columns:
        models["peak_status"] = np.where(models["fit_status"].astype(str).eq("ok"), np.where(models["n_peaks"] > 0, "peaks_detected", "no_peaks_detected"), "fit_failed")
    channel_set = None if selected_channels is None else {str(value) for value in selected_channels}
    region_set = None if selected_regions is None else {str(value) for value in selected_regions}
    for frame in (models, peaks, curves):
        if frame.empty:
            continue
        if channel_set is not None:
            frame.drop(frame.index[~frame["channel_name"].astype(str).isin(channel_set)], inplace=True)
        if region_set is not None:
            frame.drop(frame.index[~frame["region"].astype(str).isin(region_set)], inplace=True)
    if quality_only and not models.empty:
        valid_channels = set(models.loc[(models["fit_status"].astype(str) == "ok") & (models["fit_quality_status"].astype(str) == "pass"), "channel_name"].astype(str))
        models = models.loc[models["channel_name"].astype(str).isin(valid_channels)].copy()
        peaks = peaks.loc[peaks["channel_name"].astype(str).isin(valid_channels)].copy()
        curves = curves.loc[curves["channel_name"].astype(str).isin(valid_channels)].copy()
    band_options = normalize_bands(bands)
    band = next((item for item in band_options if item["name"] == selected_band), None)
    peaks_all = peaks.copy()
    peaks_filtered = peaks.loc[peak_band_mask(peaks, band)].copy() if band is not None else peaks.copy()
    peaks_display = _representative_peaks(models, peaks, band) if peak_mode == "representative" else peaks_filtered.copy()
    return {
        "models": models.reset_index(drop=True),
        "peaks_all": peaks_all.reset_index(drop=True),
        "peaks_filtered": peaks_filtered.reset_index(drop=True),
        "peaks_display": peaks_display.reset_index(drop=True),
        "curves": curves.reset_index(drop=True),
        "bands": band_options,
        "selected_band": band,
        "peak_mode": peak_mode,
    }


def _style_axis(axis: Axes, font: FontProperties, font_size: int = 9) -> None:
    axis.title.set_fontproperties(font)
    axis.xaxis.label.set_fontproperties(font)
    axis.yaxis.label.set_fontproperties(font)
    for label in (*axis.get_xticklabels(), *axis.get_yticklabels()):
        label.set_fontproperties(font)
        label.set_fontsize(font_size)
    axis.spines[["top", "right"]].set_visible(False)
    axis.grid(axis="y", color="#dddddd", linewidth=0.45)


def _channel_x(axis: Axes, channels: list[dict[str, Any]]) -> dict[str, int]:
    x_index = {str(row["channel_name"]): index for index, row in enumerate(channels)}
    axis.set_xticks(np.arange(len(channels)), [row["channel_label"] for row in channels], rotation=45, ha="right")
    return x_index


def _scatter_parameter(axis: Axes, models: pd.DataFrame, channels: list[dict[str, Any]], column: str, title: str, ylabel: str, selected_channel: str | None, show_legend: bool, font: FontProperties, font_size: int, language: str = "zh", color_template: str = DEFAULT_COLOR_TEMPLATE) -> None:
    x_index = _channel_x(axis, channels)
    if not models.empty and column in models.columns:
        for region, group in models.groupby("region", sort=False):
            valid = group[column].notna()
            if valid.any():
                xs = [x_index.get(str(name), np.nan) for name in group.loc[valid, "channel_name"]]
                colors_for_points = [channel_color(name, region, color_template) for name in group.loc[valid, "channel_name"]]
                axis.scatter(xs, group.loc[valid, column], color=colors_for_points, s=34, label=_region_text(region, language), zorder=3)
        if selected_channel in x_index:
            selected = models.loc[models["channel_name"].astype(str) == str(selected_channel), column]
            selected = selected.dropna()
            if not selected.empty:
                axis.scatter([x_index[str(selected_channel)]], [float(selected.iloc[0])], s=95, facecolors="none", edgecolors="#111111", linewidths=1.5, zorder=4)
        for row in models.itertuples():
            value = getattr(row, column, np.nan)
            if pd.isna(value) and str(row.channel_name) in x_index:
                status = _text(getattr(row, "fit_status", ""), _tr(language, "无结果", "no result"))
                axis.text(x_index[str(row.channel_name)], 0.02, status, transform=axis.get_xaxis_transform(), rotation=90, ha="center", va="bottom", fontsize=max(7, font_size - 2), color="#9a3d00", fontproperties=font)
    axis.set_title(title, fontproperties=font)
    axis.set_ylabel(ylabel, fontproperties=font)
    if show_legend and not models.empty:
        axis.legend(frameon=False, prop=font, fontsize=font_size - 1, ncol=1, loc="upper left", bbox_to_anchor=(1.01, 1.0), borderaxespad=0.0)
    _style_axis(axis, font, font_size)


def plot_fooof_overview(
    figure: Figure,
    axes: np.ndarray,
    prepared: dict[str, Any],
    selected_region: str,
    selected_channel: str | None,
    curve_mode: str,
    unified_axis: bool,
    show_legend: bool,
    font_size: int = 9,
    language: str = "zh",
    color_template: str = DEFAULT_COLOR_TEMPLATE,
) -> dict[str, Any]:
    font = _plot_font(language)
    models = prepared["models"]
    curves = prepared["curves"]
    peaks = prepared["peaks_display"]
    channels = ordered_channels(models, curves)
    selected_band = prepared.get("selected_band")
    band_text = _tr(language, "全部拟合范围", "Full fit range") if selected_band is None else f"{selected_band['name']} [{selected_band['low_hz']:g}–{selected_band['high_hz']:g} Hz]"
    axes_flat = np.asarray(axes, dtype=object).ravel()
    _scatter_parameter(axes_flat[0], models, channels, "exponent", _tr(language, "A 非周期 exponent", "A Aperiodic exponent"), "Exponent", selected_channel, show_legend, font, font_size, language, color_template)
    _scatter_parameter(axes_flat[1], models, channels, "offset", _tr(language, "B 非周期 offset", "B Aperiodic offset"), "Offset (log10 PSD)", selected_channel, False, font, font_size, language, color_template)
    curve_axis = axes_flat[2]
    region_channels = [row for row in channels if selected_region in {"全部", "All"} or _text(row.get("region"), "未映射") == selected_region]
    x_frequency = curves.loc[curves["channel_name"].astype(str).isin([str(row["channel_name"]) for row in region_channels])]
    for channel in region_channels:
        group = x_frequency.loc[x_frequency["channel_name"].astype(str) == str(channel["channel_name"])].sort_values("frequency_hz")
        if group.empty:
            continue
        color = channel_color(channel.get("channel_name"), channel.get("region"), color_template)
        linestyle = ("-", "--", ":", "-.")[region_channels.index(channel) % 4]
        if curve_mode in {"observed", "overlay"}:
            curve_axis.plot(group["frequency_hz"], group["observed_minus_aperiodic_log10"], color=color, alpha=0.38 if curve_mode == "overlay" else 0.75, linewidth=0.8, linestyle=linestyle, label=f"{channel['channel_label']} {_tr(language, '观测', 'observed')}" if curve_mode == "observed" else "_nolegend_")
        if curve_mode in {"model", "overlay"}:
            curve_axis.plot(group["frequency_hz"], group["periodic_model_log10"], color=color, alpha=0.95, linewidth=1.3, linestyle=linestyle, label=f"{channel['channel_label']} {_tr(language, '模型', 'model')}" if curve_mode == "model" else channel["channel_label"])
    curve_axis.axhline(0.0, color="#555555", linewidth=0.6)
    curve_axis.set_title(f"C {_tr(language, '周期成分曲线', 'Periodic component curves')} | {selected_region} | {curve_mode}", fontproperties=font)
    curve_axis.set_xlabel("Frequency (Hz)", fontproperties=font)
    curve_axis.set_ylabel("Log10 additive above aperiodic", fontproperties=font)
    if show_legend and curve_axis.get_legend_handles_labels()[1]:
        curve_axis.legend(frameon=False, prop=font, fontsize=font_size - 1, ncol=1, loc="upper left", bbox_to_anchor=(1.01, 1.0), borderaxespad=0.0)
    if curve_mode == "overlay":
        curve_axis.text(0.02, 0.98, _tr(language, "淡线=去背景观测谱；实线=拟合周期成分", "faint=observed minus aperiodic; solid=fitted periodic model"), transform=curve_axis.transAxes, va="top", fontproperties=font, fontsize=max(7, font_size - 1))
    _style_axis(curve_axis, font, font_size)
    metric_specs = (("center_frequency_hz", _tr(language, "D 峰中心频率 CF", "D Peak center frequency CF"), "CF (Hz)"), ("peak_power_log10", _tr(language, "E 峰功率 PW", "E Peak power PW"), "PW (log10 above background)"), ("bandwidth_hz", _tr(language, "F 峰带宽 BW", "F Peak bandwidth BW"), "BW (Hz)"))
    x_index = _channel_x(axes_flat[3], channels)
    for metric_index, (axis, (column, title, ylabel)) in enumerate(zip(axes_flat[3:], metric_specs, strict=False)):
        plotted = False
        if not peaks.empty and column in peaks.columns:
            for region, group in peaks.groupby("region", sort=False):
                valid = group[column].notna()
                if not valid.any():
                    continue
                plotted = True
                xs = [x_index.get(str(name), np.nan) for name in group.loc[valid, "channel_name"]]
                if prepared.get("peak_mode") == "all":
                    xs = [value + ((int(index) % 3) - 1) * 0.08 for value, index in zip(xs, group.loc[valid, "peak_index"], strict=False)]
                colors_for_points = [channel_color(name, region, color_template) for name in group.loc[valid, "channel_name"]]
                axis.scatter(xs, group.loc[valid, column], color=colors_for_points, s=30, alpha=0.82, label=_region_text(region, language), zorder=3)
        axis.set_title(f"{title} | {band_text}", fontproperties=font, fontsize=font_size)
        axis.set_ylabel(ylabel, fontproperties=font)
        _channel_x(axis, channels)
        if show_legend and axis.collections and metric_index == 0:
            axis.legend(frameon=False, prop=font, fontsize=font_size - 1, ncol=1, loc="upper left", bbox_to_anchor=(1.01, 1.0), borderaxespad=0.0)
        if not plotted:
            axis.text(
                0.5,
                0.5,
                _tr(language, "该频段未检出峰\nCF / PW / BW 保留缺失", "No peak detected in this band\nCF / PW / BW remain missing"),
                ha="center",
                va="center",
                transform=axis.transAxes,
                fontproperties=font,
                fontsize=font_size,
            )
        _style_axis(axis, font, font_size)
    figure.suptitle(_tr(language, "FOOOF/specparam 通道比较总览", "FOOOF/specparam channel comparison overview"), fontproperties=font, fontsize=font_size + 2)
    figure.subplots_adjust(left=0.07, right=0.88, bottom=0.18, top=0.86, wspace=0.48, hspace=0.78)
    return {"channels": channels, "peaks": peaks, "band_text": band_text}


def plot_aperiodic_details(figure: Figure, axes: np.ndarray, prepared: dict[str, Any], selected_channel: str | None, show_legend: bool, font_size: int = 9, language: str = "zh", color_template: str = DEFAULT_COLOR_TEMPLATE) -> None:
    font = _plot_font(language)
    channels = ordered_channels(prepared["models"], prepared["curves"])
    _scatter_parameter(axes[0], prepared["models"], channels, "exponent", _tr(language, "非周期 exponent", "Aperiodic exponent"), "Exponent", selected_channel, show_legend, font, font_size, language, color_template)
    _scatter_parameter(axes[1], prepared["models"], channels, "offset", _tr(language, "非周期 offset", "Aperiodic offset"), "Offset (log10 PSD)", selected_channel, False, font, font_size, language, color_template)
    figure.suptitle(_tr(language, "非周期参数比较；通道为重复测量单位", "Aperiodic parameter comparison; channels are repeated measurements"), fontproperties=font, fontsize=font_size + 2)
    figure.subplots_adjust(left=0.08, right=0.82, bottom=0.20, top=0.84, wspace=0.48)


def _plot_curve_group(axis: Axes, curves: pd.DataFrame, channel_rows: list[dict[str, Any]], curve_mode: str, unified_axis: bool, show_legend: bool, font: FontProperties, font_size: int, language: str = "zh", color_template: str = DEFAULT_COLOR_TEMPLATE) -> None:
    all_values: list[np.ndarray] = []
    for index, channel in enumerate(channel_rows):
        group = curves.loc[curves["channel_name"].astype(str) == str(channel["channel_name"])].sort_values("frequency_hz")
        if group.empty:
            continue
        color = channel_color(channel.get("channel_name"), channel.get("region"), color_template)
        linestyle = ("-", "--", ":", "-.")[index % 4]
        if curve_mode in {"observed", "overlay"}:
            values = group["observed_minus_aperiodic_log10"].to_numpy(float)
            axis.plot(group["frequency_hz"], values, color=color, alpha=0.38 if curve_mode == "overlay" else 0.8, linewidth=0.85, linestyle=linestyle, label=f"{channel['channel_label']} {_tr(language, '观测', 'observed')}" if curve_mode == "observed" else "_nolegend_")
            all_values.append(values[np.isfinite(values)])
        if curve_mode in {"model", "overlay"}:
            values = group["periodic_model_log10"].to_numpy(float)
            axis.plot(group["frequency_hz"], values, color=color, alpha=0.95, linewidth=1.35, linestyle=linestyle, label=f"{channel['channel_label']} {_tr(language, '模型', 'model')}" if curve_mode == "model" else channel["channel_label"])
            all_values.append(values[np.isfinite(values)])
    axis.axhline(0.0, color="#555555", linewidth=0.6)
    axis.set_xlabel("Frequency (Hz)", fontproperties=font)
    axis.set_ylabel(_tr(language, "非周期背景以上的 log10 加性量", "Log10 additive above aperiodic"), fontproperties=font)
    if show_legend and axis.get_legend_handles_labels()[1]:
        axis.legend(frameon=False, prop=font, fontsize=font_size - 1, ncol=1, loc="upper left", bbox_to_anchor=(1.01, 1.0), borderaxespad=0.0)
    if curve_mode == "overlay":
        axis.text(0.02, 0.98, _tr(language, "淡线=去背景观测谱；实线=拟合周期成分", "faint=observed minus aperiodic; solid=fitted periodic model"), transform=axis.transAxes, va="top", fontproperties=font, fontsize=max(7, font_size - 1))
    if unified_axis and all_values:
        finite = np.concatenate(all_values)
        if finite.size:
            margin = max(0.05, float(np.nanmax(finite) - np.nanmin(finite)) * 0.08)
            axis.set_ylim(float(np.nanmin(finite) - margin), float(np.nanmax(finite) + margin))
    _style_axis(axis, font, font_size)


def plot_periodic_curves(figure: Figure, selected_layout: str, prepared: dict[str, Any], selected_region: str, selected_channels: list[str], curve_mode: str, unified_axis: bool, show_legend: bool, font_size: int = 9, language: str = "zh", color_template: str = DEFAULT_COLOR_TEMPLATE) -> list[Axes]:
    font = _plot_font(language)
    channels = ordered_channels(prepared["models"], prepared["curves"])
    if selected_layout == "region":
        figure.clear()
        regions: list[str] = []
        for row in channels:
            region = _text(row.get("region"), "未映射")
            if region not in regions:
                regions.append(region)
        # Keep small sets wide and readable: 1x1 for one region, 1xN for
        # two-to-five regions, then wrap at five columns.  The GUI can place
        # this figure in a horizontal scroll area when N is large.
        n_regions = len(regions)
        if n_regions == 0:
            axis = figure.add_subplot(111)
            axis.text(0.5, 0.5, _tr(language, "当前筛选下没有可显示的脑区曲线", "No region curves available for the current selection"), ha="center", va="center", transform=axis.transAxes, fontproperties=font)
            axis.set_axis_off()
            figure.suptitle(_tr(language, "周期成分曲线比较", "Periodic component curve comparison"), fontproperties=font, fontsize=font_size + 2)
            return [axis]
        if n_regions <= 5:
            n_columns, n_rows = max(1, n_regions), 1
        else:
            n_columns, n_rows = 5, int(np.ceil(n_regions / 5))
        figure.set_size_inches(max(5.0 * n_columns, 10.0), max(3.6 * n_rows, 4.3), forward=False)
        axes = np.asarray(figure.subplots(n_rows, n_columns), dtype=object).ravel()
        for axis, region in zip(axes, regions, strict=False):
            rows = [row for row in channels if _text(row.get("region"), "未映射") == region]
            _plot_curve_group(axis, prepared["curves"], rows, curve_mode, unified_axis, show_legend, font, font_size, language, color_template)
            axis.set_title(region, fontproperties=font)
        for axis in axes[len(regions) :]:
            axis.set_visible(False)
        figure.suptitle(f"{_tr(language, '周期成分曲线比较', 'Periodic component curve comparison')} | {curve_mode}", fontproperties=font, fontsize=font_size + 2)
    else:
        figure.clear()
        axes = np.asarray([figure.add_subplot(111)], dtype=object)
        rows = [row for row in channels if row["channel_name"] in set(selected_channels)]
        _plot_curve_group(axes[0], prepared["curves"], rows, curve_mode, unified_axis, show_legend, font, font_size, language, color_template)
        axes[0].set_title(f"{_tr(language, '选定通道周期曲线', 'Selected-channel periodic curves')} | {curve_mode}", fontproperties=font)
    figure.subplots_adjust(left=0.08, right=0.86, bottom=0.16, top=0.84, wspace=0.30, hspace=0.42)
    return [axis for axis in axes if axis.get_visible()]


def plot_periodic_heatmap(figure: Figure, prepared: dict[str, Any], font_size: int = 9, language: str = "zh") -> None:
    font = _plot_font(language)
    figure.clear()
    axis = figure.add_subplot(111)
    curves = prepared["curves"]
    channels = ordered_channels(prepared["models"], curves)
    if curves.empty or not channels:
        axis.text(0.5, 0.5, _tr(language, "没有可显示的周期曲线", "No periodic curves available"), ha="center", va="center", transform=axis.transAxes, fontproperties=font)
        return
    frequencies = np.sort(curves["frequency_hz"].dropna().unique())
    matrix = np.full((len(channels), len(frequencies)), np.nan, dtype=float)
    channel_index = {str(row["channel_name"]): index for index, row in enumerate(channels)}
    frequency_index = {float(value): index for index, value in enumerate(frequencies)}
    for row in curves.itertuples():
        if str(row.channel_name) in channel_index and float(row.frequency_hz) in frequency_index:
            matrix[channel_index[str(row.channel_name)], frequency_index[float(row.frequency_hz)]] = float(row.periodic_model_log10)
    cmap = plt_get_viridis(language).with_extremes(bad="#bdbdbd")
    image = axis.imshow(np.ma.masked_invalid(matrix), aspect="auto", cmap=cmap, extent=(frequencies[0], frequencies[-1], len(channels) - 0.5, -0.5))
    colorbar = figure.colorbar(image, ax=axis)
    colorbar.set_label(_tr(language, "周期模型（log10 加性量）", "Periodic model (log10 additive)"), fontproperties=font)
    axis.set_yticks(np.arange(len(channels)), [row["channel_label"] for row in channels])
    axis.invert_yaxis()
    axis.set_xlabel("Frequency (Hz)", fontproperties=font)
    axis.set_ylabel("Channel", fontproperties=font)
    axis.set_title(_tr(language, "通道 × 频率周期成分热图；未逐通道归一化", "Channel × frequency periodic component heatmap; no per-channel normalization"), fontproperties=font)
    _style_axis(axis, font, font_size)
    for tick in colorbar.ax.get_yticklabels():
        tick.set_fontproperties(font)
    figure.subplots_adjust(left=0.07, right=0.86, bottom=0.20, top=0.82, wspace=0.48)


def plot_peak_parameters(figure: Figure, prepared: dict[str, Any], selected_channel: str | None, show_legend: bool, font_size: int = 9, language: str = "zh", color_template: str = DEFAULT_COLOR_TEMPLATE) -> None:
    font = _plot_font(language)
    figure.clear()
    axes = np.asarray(figure.subplots(1, 3), dtype=object).ravel()
    channels = ordered_channels(prepared["models"], prepared["curves"])
    peaks = prepared["peaks_display"]
    band = prepared.get("selected_band")
    band_text = _tr(language, "全部拟合范围", "Full fit range") if band is None else f"{band['name']} [{band['low_hz']:g}–{band['high_hz']:g} Hz]"
    specs = (("center_frequency_hz", "CF (Hz)", _tr(language, "中心频率 CF", "Peak center frequency CF")), ("peak_power_log10", "PW (log10 above background)", _tr(language, "峰功率 PW", "Peak power PW")), ("bandwidth_hz", "BW (Hz; FOOOF BW=2σ)", _tr(language, "峰带宽 BW", "Peak bandwidth BW")))
    x_index = {str(row["channel_name"]): index for index, row in enumerate(channels)}
    for axis, (column, ylabel, title) in zip(axes, specs, strict=False):
        plotted = False
        if not peaks.empty:
            for region, group in peaks.groupby("region", sort=False):
                valid = group[column].notna()
                if valid.any():
                    plotted = True
                    xs = [x_index.get(str(name), np.nan) for name in group.loc[valid, "channel_name"]]
                    colors_for_points = [channel_color(name, region, color_template) for name in group.loc[valid, "channel_name"]]
                    axis.scatter(xs, group.loc[valid, column], color=colors_for_points, s=34, label=_region_text(region, language), zorder=3)
        if selected_channel in x_index:
            selected = peaks.loc[peaks["channel_name"].astype(str) == str(selected_channel), column].dropna() if not peaks.empty else pd.Series(dtype=float)
            if not selected.empty:
                axis.scatter([x_index[str(selected_channel)]] * len(selected), selected, s=90, facecolors="none", edgecolors="#111111", zorder=4)
        axis.set_title(f"{title}\n{band_text}", fontproperties=font, fontsize=font_size)
        axis.set_ylabel(ylabel, fontproperties=font)
        axis.set_xticks(np.arange(len(channels)), [row["channel_label"] for row in channels], rotation=45, ha="right")
        if show_legend and axis.collections:
            axis.legend(frameon=False, prop=font, fontsize=font_size - 1, ncol=2)
        if not plotted:
            axis.text(0.5, 0.5, _tr(language, "该频段未检出峰\nCF / PW / BW 保留缺失", "No peak detected in this band\nCF / PW / BW remain missing"), ha="center", va="center", transform=axis.transAxes, fontproperties=font, fontsize=font_size)
        _style_axis(axis, font, font_size)
    figure.subplots_adjust(left=0.08, right=0.84, bottom=0.22, top=0.82, wspace=0.48)


def plot_peak_distribution(figure: Figure, prepared: dict[str, Any], font_size: int = 9, language: str = "zh") -> list[dict[str, Any]]:
    font = _plot_font(language)
    figure.clear()
    axis = figure.add_subplot(111)
    channels = ordered_channels(prepared["models"], prepared["curves"])
    peaks = prepared["peaks_display"]
    points: list[dict[str, Any]] = []
    x_index = {str(row["channel_name"]): index for index, row in enumerate(channels)}
    if not peaks.empty:
        norm_values = peaks["peak_power_log10"].to_numpy(float)
        finite = norm_values[np.isfinite(norm_values)]
        norm = colors.Normalize(vmin=float(np.min(finite)), vmax=float(np.max(finite)) if finite.size and float(np.max(finite)) > float(np.min(finite)) else float(np.min(finite) + 1.0)) if finite.size else colors.Normalize(0.0, 1.0)
        cmap = plt_get_viridis(language)
        segments: list[list[tuple[float, float]]] = []
        segment_colors: list[Any] = []
        for row in peaks.to_dict("records"):
            channel = str(row.get("channel_name"))
            cf = _number(row.get("center_frequency_hz"))
            bw = _number(row.get("bandwidth_hz"))
            pw = _number(row.get("peak_power_log10"))
            if channel not in x_index or not np.isfinite(cf):
                continue
            y = float(x_index[channel])
            if np.isfinite(bw) and bw > 0:
                segments.append([(cf - bw / 2.0, y), (cf + bw / 2.0, y)])
                segment_colors.append(cmap(norm(pw)) if np.isfinite(pw) else "#999999")
            axis.scatter([cf], [y], color=[cmap(norm(pw)) if np.isfinite(pw) else "#999999"], s=38, zorder=3)
            points.append(row)
        if segments:
            axis.add_collection(LineCollection(segments, colors=segment_colors, linewidths=2.0, alpha=0.7, zorder=2))
        scalar = plt_get_viridis(language)
        # A small ScalarMappable keeps the colorbar tied to PW without adding
        # another data transformation.
        from matplotlib.cm import ScalarMappable

        colorbar = figure.colorbar(ScalarMappable(norm=norm, cmap=scalar), ax=axis)
        colorbar.set_label("PW (log10 above background)", fontproperties=font)
    axis.set_yticks(np.arange(len(channels)), [row["channel_label"] for row in channels])
    axis.set_xlabel("Peak center frequency CF (Hz)", fontproperties=font)
    axis.set_ylabel("Channel", fontproperties=font)
    axis.set_title(_tr(language, "峰分布；水平线段为 CF ± BW/2，不是置信区间", "Peak distribution; horizontal segments are CF ± BW/2, not confidence intervals"), fontproperties=font)
    _style_axis(axis, font, font_size)
    return points


def _gaussian_columns(curves: pd.DataFrame) -> list[str]:
    return sorted([column for column in curves.columns if str(column).startswith("gaussian_") and str(column).endswith("_log10")], key=lambda value: int(str(value).split("_")[1]))


def plot_single_channel_detail(figure: Figure, prepared: dict[str, Any], channel_name: str | None, show_legend: bool, font_size: int = 9, language: str = "zh") -> pd.DataFrame:
    font = _plot_font(language)
    figure.clear()
    axes = np.asarray(figure.subplots(2, 2), dtype=object).ravel()
    if not channel_name:
        axes[0].text(0.5, 0.5, _tr(language, "请选择通道", "Select a channel"), ha="center", va="center", transform=axes[0].transAxes, fontproperties=font)
        return pd.DataFrame()
    curves = prepared["curves"].loc[prepared["curves"]["channel_name"].astype(str) == str(channel_name)].sort_values("frequency_hz")
    model = prepared["models"].loc[prepared["models"]["channel_name"].astype(str) == str(channel_name)]
    peaks = prepared["peaks_all"].loc[prepared["peaks_all"]["channel_name"].astype(str) == str(channel_name)]
    if curves.empty:
        axes[0].text(0.5, 0.5, _tr(language, "该通道没有有效拟合曲线", "No valid fitted curves for this channel"), ha="center", va="center", transform=axes[0].transAxes, fontproperties=font)
        return peaks
    axes[0].plot(curves["frequency_hz"], curves["observed_power"], color="#1f77b4", linewidth=0.8, label="Input PSD")
    axes[0].plot(curves["frequency_hz"], curves["full_model_power"], color="#ff7f0e", linewidth=1.1, label="Full model")
    axes[0].plot(curves["frequency_hz"], curves["aperiodic_power"], color="#666666", linestyle="--", linewidth=0.9, label="Aperiodic background")
    axes[0].set_yscale("log")
    axes[0].set_ylabel("PSD (source unit²/Hz)", fontproperties=font)
    axes[0].set_title(_tr(language, "输入 PSD、完整模型和非周期背景", "Input PSD, full model, and aperiodic background"), fontproperties=font)
    axes[1].plot(curves["frequency_hz"], curves["observed_minus_aperiodic_log10"], color="#1f77b4", alpha=0.55, linewidth=0.8, label="Observed minus aperiodic")
    axes[1].plot(curves["frequency_hz"], curves["periodic_model_log10"], color="#2ca02c", linewidth=1.2, label="Fitted periodic model")
    axes[1].plot(curves["frequency_hz"], curves["residual_log10"], color="#d62728", linewidth=0.75, label="Residual")
    axes[1].axhline(0.0, color="#555555", linewidth=0.6)
    axes[1].set_ylabel("Log10 additive scale", fontproperties=font)
    axes[1].set_title(_tr(language, "去背景观测谱与拟合周期成分", "Observed-minus-aperiodic spectrum and fitted periodic component"), fontproperties=font)
    gaussian_columns = _gaussian_columns(curves)
    for index, column in enumerate(gaussian_columns):
        axes[2].plot(curves["frequency_hz"], curves[column], linewidth=0.75, alpha=0.75, label=f"Gaussian {index}")
    axes[2].plot(curves["frequency_hz"], curves["periodic_model_log10"], color="#111111", linewidth=1.35, label="Gaussian sum / periodic model")
    axes[2].axhline(0.0, color="#555555", linewidth=0.6)
    axes[2].set_ylabel("Log10 additive scale", fontproperties=font)
    axes[2].set_title(_tr(language, "独立高斯峰及其叠加模型", "Individual Gaussian peaks and their sum"), fontproperties=font)
    if not model.empty:
        row = model.iloc[0]
        details = [
            f"fit={_text(row.get('fit_status'), 'unknown')}",
            f"quality={_text(row.get('fit_quality_status'), 'unknown')}",
            f"R²={_number(row.get('r_squared')):.4g}" if np.isfinite(_number(row.get("r_squared"))) else "R²=—",
            f"MAE={_number(row.get('error')):.4g}" if np.isfinite(_number(row.get("error"))) else "MAE=—",
            f"offset={_number(row.get('offset')):.4g}" if np.isfinite(_number(row.get("offset"))) else "offset=—",
            f"exponent={_number(row.get('exponent')):.4g}" if np.isfinite(_number(row.get("exponent"))) else "exponent=—",
            f"knee={_number(row.get('knee')):.4g}" if np.isfinite(_number(row.get("knee"))) else "knee=—",
            f"peaks={int(row.get('n_peaks', len(peaks)))}",
        ]
        axes[3].axis("off")
        axes[3].text(0.02, 0.98, "\n".join(details), va="top", transform=axes[3].transAxes, fontproperties=font, fontsize=font_size)
    for axis in axes[:3]:
        axis.set_xlabel("Frequency (Hz)", fontproperties=font)
        if show_legend:
            axis.legend(frameon=False, prop=font, fontsize=font_size - 1, ncol=2)
        _style_axis(axis, font, font_size)
    axes[3].set_title(_tr(language, "拟合质量与非周期参数", "Fit quality and aperiodic parameters"), fontproperties=font)
    figure.suptitle(f"{_tr(language, '单通道拟合详情', 'Single-channel fit detail')} | {channel_name}", fontproperties=font, fontsize=font_size + 2)
    figure.subplots_adjust(left=0.08, right=0.84, bottom=0.13, top=0.88, wspace=0.30, hspace=0.38)
    return peaks


def plt_get_viridis(language: str = "zh"):
    import matplotlib.pyplot as plt

    return plt.get_cmap("viridis")
