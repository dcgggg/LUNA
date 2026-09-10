"""Shared data preparation and plotting helpers for the band-power GUI view.

The helpers in this module never recompute PSD or band power.  They only filter,
aggregate, and draw already saved band-power tables, so changing a display
control is presentation-only and does not change the analysis result.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd
from matplotlib import colors
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties, findfont
from matplotlib.patches import Rectangle

REGION_ORDER = ("M1", "STR", "PF", "SNr")
REGION_COLORS = {
    "M1": "#4472C4",
    "STR": "#70AD47",
    "PF": "#ED7D31",
    "SNr": "#A64D79",
    "未映射": "#7F7F7F",
}


def _empty() -> pd.DataFrame:
    return pd.DataFrame()


def _first_table(tables: dict[str, pd.DataFrame], names: Iterable[str]) -> pd.DataFrame:
    for name in names:
        table = tables.get(name)
        if isinstance(table, pd.DataFrame) and not table.empty:
            return table.copy()
    return _empty()


def _as_text(value: Any, fallback: str = "") -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return fallback
    text = str(value).strip()
    return fallback if text in {"", "nan", "None"} else text


def _physical_sort_key(value: Any) -> tuple[int, float, str]:
    text = _as_text(value)
    try:
        return (0, float(text), text)
    except (TypeError, ValueError):
        return (1, float("inf"), text)


def _band_sort_key(row: pd.Series) -> tuple[float, float, str]:
    return (float(row.get("band_low_hz", np.inf)), float(row.get("band_high_hz", np.inf)), _as_text(row.get("band")))


def _channel_label(row: pd.Series) -> str:
    physical = _as_text(row.get("physical_channel_number"))
    name = _as_text(row.get("channel_name"), "?")
    return f"{physical} {name}" if physical else name


def _metadata_columns(frame: pd.DataFrame) -> list[str]:
    return [column for column in ("channel_name", "physical_channel_number", "region") if column in frame.columns]


def _with_metadata(table: pd.DataFrame) -> pd.DataFrame:
    frame = table.copy()
    if frame.empty:
        return frame
    if "channel_name" not in frame.columns:
        if "channel_array_index" in frame.columns:
            frame["channel_name"] = frame["channel_array_index"].astype(str)
        else:
            frame["channel_name"] = ""
    if "physical_channel_number" not in frame.columns:
        frame["physical_channel_number"] = ""
    if "region" not in frame.columns:
        frame["region"] = ""
    if "status" in frame.columns:
        frame = frame.loc[frame["status"].astype(str).isin({"ok", "", "nan"})].copy()
    frame["region"] = frame["region"].map(lambda value: _as_text(value, "未映射"))
    frame["channel_name"] = frame["channel_name"].map(lambda value: _as_text(value, "?"))
    frame["physical_channel_number"] = frame["physical_channel_number"].map(_as_text)
    frame["band"] = frame["band"].map(lambda value: _as_text(value, "?"))
    frame["band_low_hz"] = pd.to_numeric(frame["band_low_hz"], errors="coerce")
    frame["band_high_hz"] = pd.to_numeric(frame["band_high_hz"], errors="coerce")
    frame["absolute_power"] = pd.to_numeric(frame["absolute_power"], errors="coerce")
    frame["relative_power"] = pd.to_numeric(frame["relative_power"], errors="coerce")
    return frame


def _filtered_epoch_table(
    tables: dict[str, pd.DataFrame],
    selected_channels: Iterable[str] | None = None,
    selected_regions: Iterable[str] | None = None,
    selected_bands: Iterable[str] | None = None,
) -> pd.DataFrame:
    frame = _first_table(tables, ("band_power", "band_power_epoch_channel"))
    if frame.empty:
        frame = _first_table(tables, ("band_power_summary",))
    frame = _with_metadata(frame)
    if frame.empty:
        return frame
    if selected_channels is not None:
        frame = frame.loc[frame["channel_name"].isin({str(value) for value in selected_channels})]
    if selected_regions is not None:
        frame = frame.loc[frame["region"].isin({str(value) for value in selected_regions})]
    if selected_bands is not None:
        frame = frame.loc[frame["band"].isin({str(value) for value in selected_bands})]
    return frame.loc[frame["absolute_power"].notna() | frame["relative_power"].notna()].copy()


def _summary_table(frame: pd.DataFrame, power_kind: str, aggregation: str) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    value_column = "relative_power" if power_kind == "relative" else "absolute_power"
    frame = frame.loc[frame[value_column].notna()].copy()
    if frame.empty:
        return frame
    group_columns = ["channel_name", "physical_channel_number", "region", "band", "band_low_hz", "band_high_hz"]
    group_columns = [column for column in group_columns if column in frame.columns]
    agg_name = "median" if str(aggregation).lower() == "median" else "mean"
    aggregation_spec: dict[str, tuple[str, str]] = {"raw_value": (value_column, agg_name)}
    if "epoch_index" in frame.columns:
        aggregation_spec["n_epochs"] = ("epoch_index", "nunique")
    elif "n_epochs" in frame.columns:
        aggregation_spec["n_epochs"] = ("n_epochs", "max")
    else:
        aggregation_spec["n_epochs"] = ("channel_name", "size")
    summary = frame.groupby(group_columns, dropna=False, as_index=False).agg(**aggregation_spec)
    summary["display_value"] = summary["raw_value"] * (100.0 if power_kind == "relative" else 1.0)
    summary["channel_label"] = summary.apply(_channel_label, axis=1)
    return summary


def prepare_band_power(
    tables: dict[str, pd.DataFrame],
    power_kind: str = "absolute",
    aggregation: str = "mean",
    selected_channels: Iterable[str] | None = None,
    selected_regions: Iterable[str] | None = None,
    selected_bands: Iterable[str] | None = None,
) -> dict[str, pd.DataFrame]:
    """Return filtered epoch values and the display aggregation."""
    epoch = _filtered_epoch_table(tables, selected_channels, selected_regions, selected_bands)
    return {"epoch": epoch, "summary": _summary_table(epoch, power_kind, aggregation)}


def ordered_channels(summary: pd.DataFrame) -> list[dict[str, Any]]:
    if summary.empty:
        return []
    rows = summary[["channel_name", "physical_channel_number", "region", "channel_label"]].drop_duplicates().to_dict("records")
    region_rank = {name: index for index, name in enumerate(REGION_ORDER)}
    rows.sort(
        key=lambda row: (
            region_rank.get(_as_text(row.get("region"), "未映射"), len(REGION_ORDER)),
            _physical_sort_key(row.get("physical_channel_number")),
            _as_text(row.get("channel_name")),
        )
    )
    return rows


def ordered_bands(summary: pd.DataFrame) -> list[dict[str, Any]]:
    if summary.empty:
        return []
    rows = summary[["band", "band_low_hz", "band_high_hz"]].drop_duplicates().to_dict("records")
    rows.sort(key=lambda row: (float(row.get("band_low_hz", np.inf)), float(row.get("band_high_hz", np.inf)), _as_text(row.get("band"))))
    return rows


def power_label(
    power_kind: str,
    denominator_hz: tuple[float, float] | None = None,
    language: str = "zh",
) -> str:
    if power_kind == "relative":
        if language == "en":
            if denominator_hz is None:
                return "Relative power (%)"
            return f"Relative power (%)\nDenominator {denominator_hz[0]:g}–{denominator_hz[1]:g} Hz"
        if denominator_hz is None:
            return "相对功率 (%)"
        return f"相对功率 (%)\n分母 {denominator_hz[0]:g}–{denominator_hz[1]:g} Hz"
    if language == "en":
        return "Absolute power (source unit²)"
    return "绝对功率（原始单位²）"


def band_label(row: dict[str, Any]) -> str:
    return f"{_as_text(row.get('band'))} [{float(row.get('band_low_hz')):g}–{float(row.get('band_high_hz')):g} Hz]"


def _positive_log_values(values: np.ndarray) -> tuple[np.ndarray, colors.LogNorm | None]:
    finite = np.isfinite(values)
    positive = values[finite & (values > 0)]
    if positive.size == 0:
        return np.zeros(values.shape, dtype=bool), None
    vmin = float(np.min(positive))
    vmax = float(np.max(positive))
    if vmax <= vmin:
        vmax = vmin * 1.01
    return finite & (values > 0), colors.LogNorm(vmin=vmin, vmax=vmax)


def _plot_font(language: str = "zh") -> FontProperties:
    """Resolve a concrete font file so GUI redraws do not fall back per label."""
    from matplotlib import font_manager

    preferred = "Times New Roman" if language == "en" else "Microsoft YaHei"
    available = {font.name for font in font_manager.fontManager.ttflist}
    family = preferred if preferred in available else "DejaVu Sans"
    return FontProperties(fname=findfont(FontProperties(family=family), fallback_to_default=True))


def _font_size(font: FontProperties, size: float, weight: str | None = None) -> FontProperties:
    sized = font.copy()
    sized.set_size(size)
    if weight is not None:
        sized.set_weight(weight)
    return sized


def _style_ticks(axis: Axes, font: FontProperties) -> None:
    for label in (*axis.get_xticklabels(), *axis.get_yticklabels()):
        label.set_fontproperties(_font_size(font, 7.5))


def _style_axis_text(axis: Axes, font: FontProperties) -> None:
    axis.title.set_fontproperties(_font_size(font, 9.5))
    axis.xaxis.label.set_fontproperties(_font_size(font, 8.5))
    axis.yaxis.label.set_fontproperties(_font_size(font, 8.5))
    _style_ticks(axis, font)


def plot_overview(
    axis: Axes,
    figure: Figure,
    prepared: dict[str, pd.DataFrame],
    power_kind: str,
    scale: str,
    selected_channel: str | None,
    selected_band: str | None,
    show_values: bool,
    title: str,
    denominator_hz: tuple[float, float] | None = None,
    language: str = "zh",
) -> dict[str, Any]:
    plt_get_viridis(language)
    font = _plot_font(language)
    summary = prepared["summary"]
    axis.set_title(title, fontproperties=font)
    axis.set_xlabel("Frequency bands (Hz)" if language == "en" else "频带（Hz）", fontproperties=font)
    # The y tick labels already carry the actual physical channel number/name;
    # omitting a second vertical y label leaves room for the region side labels.
    axis.set_ylabel("", fontproperties=font)
    if summary.empty:
        axis.text(0.5, 0.5, "当前筛选下没有有效频带功率", ha="center", va="center", transform=axis.transAxes, fontproperties=font)
        _style_axis_text(axis, font)
        return {"channels": [], "bands": [], "log_valid": False}
    channels = ordered_channels(summary)
    bands = ordered_bands(summary)
    channel_names = [row["channel_name"] for row in channels]
    band_names = [row["band"] for row in bands]
    matrix = np.full((len(channels), len(bands)), np.nan, dtype=float)
    channel_index = {name: index for index, name in enumerate(channel_names)}
    band_index = {name: index for index, name in enumerate(band_names)}
    for row in summary.itertuples():
        matrix[channel_index[row.channel_name], band_index[row.band]] = float(row.display_value)
    cmap = plt_get_viridis(language).with_extremes(bad="#bdbdbd")
    log_mask, norm = _positive_log_values(matrix)
    use_log = str(scale).lower() == "log" and power_kind == "absolute"
    plotted = np.ma.masked_invalid(matrix)
    if use_log:
        plotted = np.ma.masked_where(~log_mask, matrix)
    image = axis.imshow(plotted, aspect="auto", cmap=cmap, norm=norm if use_log and norm else None)
    label = power_label(power_kind, denominator_hz, language)
    colorbar = figure.colorbar(image, ax=axis, pad=0.02, fraction=0.045)
    colorbar.set_label(label, fontproperties=_font_size(font, 8.0), labelpad=5)
    colorbar.ax.tick_params(labelsize=7, pad=1)
    for tick in colorbar.ax.get_yticklabels():
        tick.set_fontproperties(_font_size(font, 7.0))
    axis.set_xticks(np.arange(len(bands)), [band_label(row) for row in bands], rotation=28, ha="right")
    axis.set_yticks(np.arange(len(channels)), [row["channel_label"] for row in channels])
    axis.tick_params(axis="both", labelsize=7.5, pad=2)
    _style_ticks(axis, font)
    boundaries: list[tuple[str, float, float]] = []
    start = 0
    while start < len(channels):
        region = _as_text(channels[start].get("region"), "未映射")
        stop = start + 1
        while stop < len(channels) and _as_text(channels[stop].get("region"), "未映射") == region:
            stop += 1
        axis.axhline(stop - 0.5, color="#888888", linewidth=0.7) if stop < len(channels) else None
        boundaries.append((region, start, stop - 1))
        start = stop
    transform = axis.get_yaxis_transform(which="grid")
    for region, first, last in boundaries:
        axis.text(
            -0.105,
            (first + last) / 2,
            region,
            transform=transform,
            ha="center",
            va="center",
            rotation=0,
            fontproperties=_font_size(font, 7.5, "bold"),
            clip_on=False,
        )
    if show_values:
        for row_index in range(matrix.shape[0]):
            for column_index in range(matrix.shape[1]):
                value = matrix[row_index, column_index]
                if np.isfinite(value) and (not use_log or value > 0):
                    axis.text(column_index, row_index, f"{value:.3g}", ha="center", va="center", color="#111111", fontproperties=_font_size(font, 7.0))
    selected_row = channel_index.get(selected_channel) if selected_channel else None
    selected_col = band_index.get(selected_band) if selected_band else None
    if selected_row is not None and selected_col is not None:
        axis.add_patch(Rectangle((selected_col - 0.5, selected_row - 0.5), 1, 1, fill=False, edgecolor="#111111", linewidth=2.0))
    if use_log and np.any(np.isfinite(matrix) & (matrix <= 0)):
        note = "Non-positive values are masked; switch to linear scale" if language == "en" else "非正值按无效值显示；可切换线性尺度"
        axis.text(1.0, 1.02, note, transform=axis.transAxes, ha="right", va="bottom", color="#7a4a00", fontproperties=_font_size(font, 7.0))
    _style_axis_text(axis, font)
    axis.grid(False)
    return {"channels": channels, "bands": bands, "matrix": matrix, "log_valid": bool(np.any(log_mask))}


def plot_comparison(
    axis: Axes,
    prepared: dict[str, pd.DataFrame],
    mode: str,
    power_kind: str,
    scale: str,
    selected_channel: str | None,
    selected_band: str | None,
    show_epoch_distribution: bool,
    title: str,
    denominator_hz: tuple[float, float] | None = None,
    language: str = "zh",
) -> dict[str, Any]:
    plt_get_viridis(language)
    font = _plot_font(language)
    summary = prepared["summary"]
    epoch = prepared["epoch"]
    axis.set_title(title, fontproperties=font)
    axis.set_ylabel(power_label(power_kind, denominator_hz, language), fontproperties=font)
    use_log = str(scale).lower() == "log" and power_kind == "absolute"
    if summary.empty:
        axis.text(0.5, 0.5, "当前筛选下没有有效频带功率", ha="center", va="center", transform=axis.transAxes, fontproperties=font)
        _style_axis_text(axis, font)
        return {"selection_value": np.nan}
    channels = ordered_channels(summary)
    bands = ordered_bands(summary)
    if mode == "channel":
        if selected_band not in {row["band"] for row in bands}:
            selected_band = bands[0]["band"]
        target = summary.loc[summary["band"] == selected_band].copy()
        x_values = [row["channel_name"] for row in channels if row["channel_name"] in set(target["channel_name"])]
        x_index = {name: index for index, name in enumerate(x_values)}
        for region, group in target.groupby("region", sort=False):
            group = group.loc[group["channel_name"].isin(x_index)]
            if group.empty:
                continue
            xs = [x_index[name] for name in group["channel_name"]]
            face = REGION_COLORS.get(_as_text(region, "未映射"), REGION_COLORS["未映射"])
            axis.scatter(xs, group["display_value"], s=46, color=face, label=_as_text(region, "未映射"), zorder=3)
        if show_epoch_distribution and not epoch.empty:
            values = epoch.loc[epoch["band"] == selected_band].copy()
            value_column = "relative_power" if power_kind == "relative" else "absolute_power"
            values["display_value"] = values[value_column] * (100.0 if power_kind == "relative" else 1.0)
            for channel_name, group in values.groupby("channel_name"):
                if channel_name not in x_index:
                    continue
                finite = group["display_value"].to_numpy(float)
                finite = finite[np.isfinite(finite)]
                if use_log:
                    finite = finite[finite > 0]
                if finite.size:
                    jitter = np.linspace(-0.12, 0.12, finite.size)
                    axis.scatter(x_index[channel_name] + jitter, finite, s=14, alpha=0.22, color="#555555", zorder=1)
        axis.set_xticks(np.arange(len(x_values)), [next(row["channel_label"] for row in channels if row["channel_name"] == name) for name in x_values], rotation=45, ha="right")
        axis.set_xlabel("Channels" if language == "en" else "实际通道", fontproperties=font)
        if selected_channel in x_index:
            selected = target.loc[target["channel_name"] == selected_channel]
            if not selected.empty and np.isfinite(selected.iloc[0]["display_value"]) and (not use_log or selected.iloc[0]["display_value"] > 0):
                axis.scatter([x_index[selected_channel]], [selected.iloc[0]["display_value"]], s=110, facecolors="none", edgecolors="#111111", linewidths=1.6, zorder=4)
                selection_value = float(selected.iloc[0]["display_value"])
            else:
                selection_value = np.nan
        else:
            selection_value = np.nan
        if not target.empty:
            axis.legend(frameon=False, prop=_font_size(font, 7.5), ncol=min(4, max(1, target["region"].nunique())), loc="best")
    else:
        if selected_channel not in set(summary["channel_name"]):
            selected_channel = channels[0]["channel_name"]
        target = summary.loc[summary["channel_name"] == selected_channel].copy()
        target = target.sort_values(["band_low_hz", "band_high_hz", "band"])
        x_values = target["band"].astype(str).tolist()
        x_index = {name: index for index, name in enumerate(x_values)}
        base_color = "#4472C4"
        highlight_color = "#C00000"
        colors_for_points = [highlight_color if name == selected_band else base_color for name in x_values]
        axis.scatter(np.arange(len(x_values)), target["display_value"], s=52, color=colors_for_points, zorder=3)
        if show_epoch_distribution and not epoch.empty:
            value_column = "relative_power" if power_kind == "relative" else "absolute_power"
            values = epoch.loc[epoch["channel_name"] == selected_channel].copy()
            values["display_value"] = values[value_column] * (100.0 if power_kind == "relative" else 1.0)
            for band_name, group in values.groupby("band"):
                if band_name not in x_index:
                    continue
                finite = group["display_value"].to_numpy(float)
                finite = finite[np.isfinite(finite)]
                if use_log:
                    finite = finite[finite > 0]
                if finite.size:
                    jitter = np.linspace(-0.12, 0.12, finite.size)
                    axis.scatter(x_index[band_name] + jitter, finite, s=14, alpha=0.22, color="#555555", zorder=1)
        axis.set_xticks(np.arange(len(x_values)), [next(row["band"] for row in bands if row["band"] == name) for name in x_values], rotation=35, ha="right")
        axis.set_xlabel("Frequency bands (Hz)" if language == "en" else "频带（Hz）", fontproperties=font)
        if selected_band in x_index:
            selected = target.loc[target["band"] == selected_band]
            if not selected.empty and np.isfinite(selected.iloc[0]["display_value"]) and (not use_log or selected.iloc[0]["display_value"] > 0):
                axis.scatter([x_index[selected_band]], [selected.iloc[0]["display_value"]], s=120, facecolors="none", edgecolors="#111111", linewidths=1.6, zorder=4)
                selection_value = float(selected.iloc[0]["display_value"])
            else:
                selection_value = np.nan
        else:
            selection_value = np.nan
    if use_log:
        positive = summary["display_value"].to_numpy(float)
        positive = positive[np.isfinite(positive) & (positive > 0)]
        if positive.size:
            axis.set_yscale("log")
        if np.any(np.isfinite(summary["display_value"]) & (summary["display_value"] <= 0)):
            note = "Non-positive values omitted on log axis; switch to linear scale" if language == "en" else "非正值未绘入对数轴；可切换线性尺度"
            axis.text(1.0, 1.02, note, transform=axis.transAxes, ha="right", va="bottom", color="#7a4a00", fontproperties=_font_size(font, 7.0))
    _style_axis_text(axis, font)
    axis.grid(axis="y", color="#dddddd", linewidth=0.5)
    axis.spines[["top", "right"]].set_visible(False)
    return {"selection_value": selection_value, "selected_channel": selected_channel, "selected_band": selected_band}


def plt_get_viridis(language: str = "zh"):
    """Import pyplot lazily and choose a font appropriate for the display language."""
    import matplotlib as mpl
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    available = {font.name for font in font_manager.fontManager.ttflist}
    if language == "en" and "Times New Roman" in available:
        mpl.rcParams["font.family"] = ["Times New Roman"]
    elif "Microsoft YaHei" in available:
        mpl.rcParams["font.family"] = ["Microsoft YaHei"]
    else:
        mpl.rcParams["font.family"] = ["DejaVu Sans"]
    mpl.rcParams["axes.unicode_minus"] = False
    return plt.get_cmap("viridis")
