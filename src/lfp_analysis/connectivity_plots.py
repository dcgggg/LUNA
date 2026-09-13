"""Compact visualisations for multivariate and bivariate connectivity results.

The plotting layer consumes saved tables only. It never recomputes a
connectivity estimate, so display changes cannot alter the underlying run.
"""

from __future__ import annotations

from typing import Any

import matplotlib
import numpy as np
import pandas as pd
from matplotlib.colors import Normalize, TwoSlopeNorm

matplotlib.rcParams["font.sans-serif"] = ["Noto Sans SC", "Microsoft YaHei", "SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

REGION_ORDER = ("M1", "STR", "PF", "SNr")
REGION_PAIRS = tuple((REGION_ORDER[i], REGION_ORDER[j]) for i in range(4) for j in range(i + 1, 4))
METHOD_ORDER = ("mic", "mim", "wpli", "dpli", "wpli2_debiased", "imcoh", "coh")
METHOD_LABELS = {
    "mic": "MIC（多变量）",
    "mim": "MIM（多变量）",
    "wpli": "wPLI（通道对平均）",
    "dpli": "dPLI（通道对平均）",
    "wpli2_debiased": "wPLI²_debiased（通道对平均）",
    "imcoh": "imcoh（通道对平均）",
    "coh": "coherence（通道对平均）",
}
PAIR_COLORS = {
    "M1–STR": "#386cb0",
    "M1–PF": "#f58231",
    "M1–SNr": "#7b3294",
    "STR–PF": "#008837",
    "STR–SNr": "#e08214",
    "PF–SNr": "#c51b7d",
}


def pair_label(region_a: str, region_b: str) -> str:
    return f"{region_a}–{region_b}"


def infer_region_order(tables: dict[str, Any], preferred: list[str] | tuple[str, ...] | None = None) -> list[str]:
    """Infer display order from the saved mapping/result, not array position."""
    result: list[str] = []
    for value in preferred or []:
        name = str(value).strip()
        if name and name not in result:
            result.append(name)
    channel_table = tables.get("channel_table", pd.DataFrame()) if isinstance(tables, dict) else pd.DataFrame()
    if isinstance(channel_table, pd.DataFrame) and "region" in channel_table:
        for value in channel_table["region"].tolist():
            name = "" if pd.isna(value) else str(value).strip()
            if name and name not in result:
                result.append(name)
    for table_name in ("region_summary", "band_summary", "spectrum", "region_spectrum"):
        frame = tables.get(table_name, pd.DataFrame()) if isinstance(tables, dict) else pd.DataFrame()
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        for column in ("region_a", "region_b"):
            if column not in frame:
                continue
            for value in frame[column].tolist():
                name = "" if pd.isna(value) else str(value).strip()
                if name and name not in result:
                    result.append(name)
    # Preserve the historical default order only when those are the actual
    # regions; arbitrary experiment names remain in mapping/result order.
    if set(result).issubset(set(REGION_ORDER)) and result:
        return [region for region in REGION_ORDER if region in result]
    return result


def _oriented_pair(region_a: Any, region_b: Any) -> tuple[str, str]:
    return str(region_a), str(region_b)


def _pair_key(region_a: Any, region_b: Any, order: list[str] | tuple[str, ...] | None = None) -> tuple[str, str]:
    values = {str(region_a), str(region_b)}
    source_order = list(order or REGION_ORDER)
    for pair in ((source_order[i], source_order[j]) for i in range(len(source_order)) for j in range(i + 1, len(source_order))):
        if set(pair) == values:
            return pair
    return (str(region_a), str(region_b))


def _selected_pair_keys(selected_pairs: list[Any] | tuple[Any, ...] | None, order: list[str] | tuple[str, ...] | None = None) -> set[tuple[str, str]] | None:
    if selected_pairs is None:
        return None
    keys: set[tuple[str, str]] = set()
    for item in selected_pairs:
        if isinstance(item, str):
            parts = [part.strip() for part in item.replace("–", "-").split("-") if part.strip()]
        else:
            parts = [str(part).strip() for part in item]
        if len(parts) == 2:
            keys.add(_pair_key(parts[0], parts[1], order))
    return keys


def _component_mask(frame: pd.DataFrame, method: str, component_index: int) -> pd.Series:
    if method != "mic" or "component_index" not in frame.columns:
        return pd.Series(True, index=frame.index)
    values = pd.to_numeric(frame["component_index"], errors="coerce")
    return values.eq(int(component_index))


def _method_table(frame: Any, method: str, component_index: int) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    result = frame.loc[frame.get("method", pd.Series(index=frame.index)).astype(str).str.lower().eq(method)].copy()
    return result.loc[_component_mask(result, method, component_index)].copy()


def prepare_connectivity(
    tables: dict[str, Any],
    metric: str = "mic",
    component_index: int | None = 1,
    selected_pairs: list[Any] | tuple[Any, ...] | None = None,
    exact_direction: bool = False,
    display_region_order: list[str] | tuple[str, ...] | None = None,
) -> dict[str, pd.DataFrame | str | int]:
    """Select a saved metric/component without changing numeric values."""
    method = str(metric).strip().lower()
    if method not in set(METHOD_ORDER):
        raise ValueError(f"Unsupported connectivity method: {method}")
    component_value = 1 if component_index in (None, "") else int(component_index)
    region_display_order = infer_region_order(tables, display_region_order)
    allowed = _selected_pair_keys(selected_pairs, region_display_order)
    spectrum = _method_table(tables.get("region_summary", pd.DataFrame()), method, component_value)
    channel_spectrum = _method_table(tables.get("spectrum", pd.DataFrame()), method, component_value)
    if not channel_spectrum.empty and "aggregation_level" in channel_spectrum:
        channel_spectrum = channel_spectrum.loc[channel_spectrum["aggregation_level"].astype(str).eq("cross_region_channel_pair")].copy()
    bands = _method_table(tables.get("band_summary", pd.DataFrame()), method, component_value)
    channel_pair_bands = _method_table(tables.get("channel_pair_band_summary", pd.DataFrame()), method, component_value)
    display_spectrum = _method_table(tables.get("display_spectrum", pd.DataFrame()), method, component_value)
    selected_tables = {
        "spectrum": spectrum,
        "channel_spectrum": channel_spectrum,
        "bands": bands,
        "channel_pair_bands": channel_pair_bands,
        "display_spectrum": display_spectrum,
    }
    for table_name, frame in selected_tables.items():
        if frame.empty:
            continue
        if not {"region_a", "region_b"}.issubset(frame.columns):
            selected_tables[table_name] = frame.iloc[0:0].copy()
            continue
        # Keep one oriented pair per input row.  Building this before the
        # selection is safe because the same positional mask is then applied
        # to both the frame and this array; no index-based re-alignment can
        # attach a label from an excluded row to a retained value.
        oriented = [
            _oriented_pair(row.region_a, row.region_b)
            for row in frame[["region_a", "region_b"]].itertuples(index=False)
        ]
        if exact_direction and method == "dpli" and selected_pairs is not None:
            exact = {_oriented_pair(item[0], item[1]) for item in selected_pairs if not isinstance(item, str) and len(item) == 2}
            keep = np.asarray([pair in exact for pair in oriented], dtype=bool)
        else:
            keep = np.asarray(
                [allowed is None or _pair_key(pair[0], pair[1], region_display_order) in allowed for pair in oriented],
                dtype=bool,
            )
        filtered = frame.loc[keep].copy()
        filtered_oriented = [oriented[index] for index in np.flatnonzero(keep)]
        filtered["pair_label"] = [pair_label(*pair) for pair in filtered_oriented]
        filtered["display_pair_label"] = [
            f"{pair[0]}→{pair[1]}" if method == "dpli" else pair_label(*_pair_key(*pair, region_display_order)) for pair in filtered_oriented
        ]
        if method == "mic":
            filtered["display_value"] = np.abs(pd.to_numeric(filtered.get("value_raw", np.nan), errors="coerce"))
        elif "value_raw_or_summary" in filtered.columns:
            filtered["display_value"] = pd.to_numeric(filtered["value_raw_or_summary"], errors="coerce")
        else:
            filtered["display_value"] = pd.to_numeric(filtered.get("value_raw", np.nan), errors="coerce")
        selected_tables[table_name] = filtered
    spectrum = selected_tables["spectrum"]
    channel_spectrum = selected_tables["channel_spectrum"]
    bands = selected_tables["bands"]
    channel_pair_bands = selected_tables["channel_pair_bands"]
    display_spectrum = selected_tables["display_spectrum"]
    return {
        "spectrum": spectrum,
        "channel_spectrum": channel_spectrum,
        "bands": bands,
        "channel_pair_bands": channel_pair_bands,
        "display_spectrum": display_spectrum,
        "method": method,
        "component_index": component_value,
        "region_order": region_display_order,
        "selected_pairs_empty": bool(selected_pairs is not None and len(selected_pairs) == 0),
    }


def _axis_empty(axis: Any, message: str) -> None:
    axis.text(0.5, 0.5, message, ha="center", va="center", transform=axis.transAxes, color="#555555")
    axis.set_axis_off()


def _band_text(band: dict[str, Any] | None) -> str:
    if not band:
        return ""
    return f"；频段 {band.get('name', '')} [{float(band.get('low_hz', 0)):g}–{float(band.get('high_hz', 0)):g} Hz]"


def _normalize_bands(selected_band: Any) -> list[dict[str, Any]]:
    """Accept the old single-band argument and the new multi-band selection."""
    if isinstance(selected_band, dict):
        return [selected_band]
    if isinstance(selected_band, (list, tuple)):
        return [band for band in selected_band if isinstance(band, dict)]
    return []


def _bands_text(selected_band: Any) -> str:
    bands = _normalize_bands(selected_band)
    if not bands:
        return ""
    labels = ", ".join(f"{band.get('name', '')} [{float(band.get('low_hz', 0)):g}–{float(band.get('high_hz', 0)):g} Hz]" for band in bands)
    return f"；显示频段：{labels}"


def method_label(method: str) -> str:
    return METHOD_LABELS.get(str(method).lower(), str(method).upper())


def plot_spectrum(
    axis: Any,
    prepared: dict[str, Any],
    selected_band: dict[str, Any] | list[dict[str, Any]] | None = None,
    scale: str = "linear",
    title_prefix: str = "",
    font_size: int = 9,
    view_mode: str = "full_highlight",
    display_smoothing: bool = False,
    show_line_noise_markers: bool = False,
    exclude_line_noise: bool = False,
) -> None:
    """Draw an existing connectivity spectrum without changing its values.

    ``frequency_is_masked_for_plot`` and the historical
    ``frequency_is_excluded_line_noise`` columns are annotations in saved
    tables.  They are intentionally not applied to the plotted y-values by
    default: a plot annotation must not silently turn a finite estimator
    result into a visual gap.  ``exclude_line_noise`` is an explicit,
    display-only choice that inserts NaNs at annotated bins.  The independent
    ``show_line_noise_markers`` switch only adds shaded annotations.
    """
    axis.clear()
    axis.set_axis_on()
    frame = prepared.get("spectrum", pd.DataFrame())
    method = str(prepared.get("method", "mic"))
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        _axis_empty(axis, f"没有可显示的 {method_label(method)} 结果")
        return
    raw_frame = frame
    smooth_frame = prepared.get("display_spectrum", pd.DataFrame())
    use_smoothing = bool(display_smoothing and isinstance(smooth_frame, pd.DataFrame) and not smooth_frame.empty and "display_value_smoothed" in smooth_frame)
    label_column = "display_pair_label" if method == "dpli" else "pair_label"
    for label, group in frame.groupby(label_column, sort=False):
        group = group.sort_values("frequency_hz")
        x = pd.to_numeric(group["frequency_hz"], errors="coerce").to_numpy(float)
        y = pd.to_numeric(group["display_value"], errors="coerce").to_numpy(float)
        mask_column = "frequency_is_masked_for_plot" if "frequency_is_masked_for_plot" in group else "frequency_is_excluded_line_noise"
        line_noise_mask = (
            np.asarray(group[mask_column].fillna(False), dtype=bool)
            if mask_column in group
            else np.zeros(len(group), dtype=bool)
        )
        if exclude_line_noise:
            y[line_noise_mask] = np.nan
        linestyle = "--" if method == "dpli" and str(label).split("→", 1)[0] != str(label).split("→", 1)[-1] and "→" in str(label) else "-"
        color = PAIR_COLORS.get(str(group["pair_label"].iloc[0]), "#555555")
        if use_smoothing:
            axis.plot(x, y, linewidth=0.75, linestyle=linestyle, color=color, alpha=0.28, label="_nolegend_")
            smooth_group = smooth_frame.loc[smooth_frame[label_column].astype(str).eq(str(label))].sort_values("frequency_hz")
            smooth_x = pd.to_numeric(smooth_group["frequency_hz"], errors="coerce").to_numpy(float)
            smooth_y = pd.to_numeric(smooth_group["display_value_smoothed"], errors="coerce").to_numpy(float)
            smooth_mask_column = "frequency_is_masked_for_plot" if "frequency_is_masked_for_plot" in smooth_group else "frequency_is_excluded_line_noise"
            if exclude_line_noise and smooth_mask_column in smooth_group:
                smooth_y[np.asarray(smooth_group[smooth_mask_column].fillna(False), dtype=bool)] = np.nan
            axis.plot(smooth_x, smooth_y, linewidth=1.35, linestyle=linestyle, color=color, label=f"{label}（display smooth）")
        else:
            axis.plot(x, y, linewidth=1.15, linestyle=linestyle, color=color, label=str(label))
    bands = _normalize_bands(selected_band)
    for index, band in enumerate(bands):
        axis.axvspan(float(band["low_hz"]), float(band["high_hz"]), color="#999999", alpha=0.12, label="显示频段" if index == 0 else "_nolegend_")
    if show_line_noise_markers:
        mask_values = pd.to_numeric(raw_frame.get("frequency_hz", pd.Series(dtype=float)), errors="coerce").to_numpy(float)
        mask_column = "frequency_is_masked_for_plot" if "frequency_is_masked_for_plot" in raw_frame else "frequency_is_excluded_line_noise"
        mask_values_flag = raw_frame.get(mask_column, pd.Series(False, index=raw_frame.index)).fillna(False).to_numpy(bool)
        masked_frequencies = np.sort(np.unique(mask_values[mask_values_flag & np.isfinite(mask_values)]))
        if len(masked_frequencies):
            steps = np.diff(masked_frequencies)
            split = np.flatnonzero(steps > (np.median(np.diff(np.sort(np.unique(mask_values)))) * 1.5 if len(np.unique(mask_values)) > 1 else np.inf))
            for index, values in enumerate(np.split(masked_frequencies, split + 1)):
                if len(values):
                    axis.axvspan(float(values[0]), float(values[-1]), color="#777777", alpha=0.10, label="工频标记" if index == 0 else "_nolegend_")
    if str(scale).lower() == "log":
        axis.set_yscale("log")
        ylabel = f"{method_label(method)}（log scale）"
    else:
        axis.set_yscale("linear")
        ylabel = {
            "mic": "|MIC|",
            "mim": "MIM（raw，未归一化）",
            "wpli": "wPLI（0–1）",
            "dpli": "dPLI（0–1；0.5=中性）",
            "wpli2_debiased": "wPLI²_debiased（raw）",
        }.get(method, f"{method_label(method)}（raw）")
    axis.set_ylabel(ylabel)
    if method in {"wpli", "dpli"} and str(scale).lower() != "log":
        axis.set_ylim(0.0, 1.0)
    if method == "dpli":
        axis.axhline(0.5, color="#555555", linewidth=0.75, linestyle=":", label="dPLI 中性 0.5")
    mode = str(view_mode).lower()
    if mode == "selected_band" and bands:
        low = min(float(band["low_hz"]) for band in bands)
        high = max(float(band["high_hz"]) for band in bands)
        axis.set_xlim(low, high)
        view_title = "仅显示选定频段"
    else:
        view_title = "全频谱（标记选定频段）"
    axis.set_xlabel("频率（Hz）")
    smoothing_note = "；仅显示平滑曲线（原始值另存）" if use_smoothing else ""
    axis.set_title(f"{title_prefix}{method_label(method)} 频谱｜{view_title}{_bands_text(selected_band)}{smoothing_note}", fontsize=font_size + 1)
    axis.grid(True, color="#dddddd", linewidth=0.45, alpha=0.8)
    axis.legend(fontsize=max(7, font_size - 1), frameon=False, ncol=2)
    axis.tick_params(labelsize=font_size)


def _frame_value(row: Any, method: str) -> float:
    column = "value_strength" if method == "mic" else "value_raw_or_summary"
    value = getattr(row, column, np.nan)
    numeric = pd.to_numeric(value, errors="coerce")
    return float(numeric) if np.isfinite(numeric) else np.nan


def _matrix_values(frame: pd.DataFrame, method: str, selected_band: dict[str, Any] | None, region_display_order: list[str] | tuple[str, ...] | None = None) -> tuple[np.ndarray, dict[tuple[int, int], tuple[str, str]]]:
    regions = list(region_display_order or infer_region_order({"band_summary": frame}))
    if not regions:
        regions = list(REGION_ORDER)
    matrix = np.full((len(regions), len(regions)), np.nan, dtype=float)
    lookup: dict[tuple[int, int], tuple[str, str]] = {}
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return matrix, lookup
    working = frame.copy()
    if selected_band and "band" in working:
        working = working.loc[working["band"].astype(str).eq(str(selected_band.get("name", "")))]
    for row in working.itertuples(index=False):
        oriented = _oriented_pair(getattr(row, "region_a", ""), getattr(row, "region_b", ""))
        if method == "dpli":
            if oriented[0] not in regions or oriented[1] not in regions or oriented[0] == oriented[1]:
                continue
            i, j = regions.index(oriented[0]), regions.index(oriented[1])
            matrix[i, j] = _frame_value(row, method)
            lookup[(i, j)] = oriented
            continue
        key = _pair_key(*oriented, regions)
        if key not in {(regions[i], regions[j]) for i in range(len(regions)) for j in range(i + 1, len(regions))}:
            continue
        value = _frame_value(row, method)
        i, j = regions.index(key[0]), regions.index(key[1])
        matrix[i, j] = value
        matrix[j, i] = value
        lookup[(i, j)] = key
        lookup[(j, i)] = key
    return matrix, lookup


def _matrix_style(method: str, finite: np.ndarray) -> tuple[Any, str]:
    if method == "dpli":
        return TwoSlopeNorm(vmin=0.0, vcenter=0.5, vmax=1.0), "dPLI scale 0–1；0.5 中性"
    if method == "wpli":
        return Normalize(vmin=0.0, vmax=1.0), "wPLI scale 0–1"
    if method == "mic" and np.nanmax(finite) <= 1.0:
        return Normalize(vmin=0.0, vmax=1.0), "|MIC| scale 0–1"
    low = 0.0 if np.nanmin(finite) >= 0 else float(np.nanmin(finite))
    high = float(np.nanmax(finite))
    if high <= low:
        high = low + 1.0
    return Normalize(vmin=low, vmax=high), "raw scale"


def _matrix_colorbar_label(method: str) -> str:
    """Return the value semantics shown beside every matrix colorbar."""
    if method == "dpli":
        return "dPLI（0.5 中性）"
    if method == "wpli":
        return "wPLI"
    if method == "mic":
        return "|MIC|"
    return "MIM/raw"


def plot_matrix(
    axis: Any,
    figure: Any,
    prepared: dict[str, Any],
    selected_band: dict[str, Any] | None = None,
    scale: str = "linear",
    title_prefix: str = "",
    font_size: int = 9,
) -> dict[str, Any]:
    axis.clear()
    axis.set_axis_on()
    method = str(prepared.get("method", "mic"))
    matrix, lookup = _matrix_values(prepared.get("bands", pd.DataFrame()), method, selected_band, prepared.get("region_order"))
    if not np.isfinite(matrix).any():
        _axis_empty(axis, f"当前频段没有可显示的 {method_label(method)} 结果")
        return {"pair_lookup": lookup, "matrix": matrix, "level": "region"}
    cmap_name = "RdBu_r" if method == "dpli" else "viridis"
    cmap = matplotlib.colormaps.get_cmap(cmap_name).with_extremes(bad="#d9d9d9")
    finite = matrix[np.isfinite(matrix)]
    norm, scale_note = _matrix_style(method, finite)
    image = axis.imshow(matrix, cmap=cmap, norm=norm, interpolation="nearest", aspect="auto")
    regions = list(prepared.get("region_order") or REGION_ORDER)
    axis.set_xticks(range(len(regions)), regions, fontsize=font_size)
    axis.set_yticks(range(len(regions)), regions, fontsize=font_size)
    axis.set_xlabel("列：target 脑区", fontsize=font_size)
    axis.set_ylabel("行：seed 脑区", fontsize=font_size)
    axis.set_title(f"{title_prefix}{method_label(method)} 当前频段脑区矩阵（{scale_note}）{_band_text(selected_band)}", fontsize=font_size + 1)
    for i in range(len(regions)):
        for j in range(len(regions)):
            if i == j:
                text, color = "N/A", "#555555"
            elif np.isfinite(matrix[i, j]):
                text, color = f"{matrix[i, j]:.3g}", "white" if norm(matrix[i, j]) > 0.55 else "black"
            else:
                text, color = "—", "#666666"
            axis.text(j, i, text, ha="center", va="center", fontsize=max(7, font_size - 1), color=color)
    if getattr(axis, "_connectivity_colorbar", None) is not None:
        try:
            axis._connectivity_colorbar.remove()
        except (AttributeError, ValueError):
            pass
    axis._connectivity_colorbar = figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    axis._connectivity_colorbar.ax.tick_params(labelsize=max(7, font_size - 1))
    axis._connectivity_colorbar.set_label("dPLI（0.5 中性）" if method == "dpli" else ("wPLI" if method == "wpli" else ("|MIC|" if method == "mic" else "MIM/raw")), fontsize=font_size)
    axis.grid(False)
    return {"pair_lookup": lookup, "matrix": matrix, "level": "region"}


def plot_band_matrices(
    figure: Any,
    prepared: dict[str, Any],
    selected_bands: list[dict[str, Any]] | None = None,
    scale: str = "linear",
    title_prefix: str = "",
    font_size: int = 9,
) -> dict[str, Any]:
    """Draw selected brain-region matrices with one cax per matrix.

    A single normalization is shared by comparable panels, while every
    matrix owns an independent colorbar axis.  This keeps the color mapping
    comparable without allowing a shared colorbar to collide with the grid.
    """
    if hasattr(figure, "set_layout_engine"):
        # The nested GridSpec owns all spacing, including every cax.  Disable
        # any rcParams/autolayout engine so export and Qt rendering agree.
        figure.set_layout_engine(None)
    figure.clear()
    method = str(prepared.get("method", "mic"))
    bands = [band for band in (selected_bands or []) if isinstance(band, dict)]
    if not bands:
        axes = figure.subplots(1, 1, squeeze=False)
        _axis_empty(axes[0, 0], "请至少勾选一个频段")
        return {"level": "region_multi", "axis_lookup": {}, "matrices": {}}
    matrices: list[tuple[dict[str, Any], np.ndarray, dict[tuple[int, int], tuple[str, str]]]] = []
    for band in bands:
        matrix, lookup = _matrix_values(prepared.get("bands", pd.DataFrame()), method, band, prepared.get("region_order"))
        matrices.append((band, matrix, lookup))
    finite_values = [matrix[np.isfinite(matrix)] for _, matrix, _ in matrices if np.isfinite(matrix).any()]
    n_rows = max(1, int(np.ceil(len(matrices) / 2)))
    outer = figure.add_gridspec(
        n_rows,
        2,
        left=0.10,
        right=0.94,
        bottom=0.12,
        top=0.84,
        wspace=0.52,
        hspace=0.58,
    )
    axes: list[Any] = []
    colorbar_axes: list[Any] = []
    if finite_values:
        finite = np.concatenate(finite_values)
        norm, scale_note = _matrix_style(method, finite)
        cmap_name = "RdBu_r" if method == "dpli" else "viridis"
        cmap = matplotlib.colormaps.get_cmap(cmap_name).with_extremes(bad="#d9d9d9")
        axis_lookup: dict[int, dict[str, Any]] = {}
        for index, (band, matrix, lookup) in enumerate(matrices):
            row_index, column_index = divmod(index, 2)
            panel = outer[row_index, column_index].subgridspec(1, 2, width_ratios=[1.0, 0.13], wspace=0.24)
            axis = figure.add_subplot(panel[0, 0])
            cax = figure.add_subplot(panel[0, 1])
            axes.append(axis)
            colorbar_axes.append(cax)
            image = axis.imshow(matrix, cmap=cmap, norm=norm, interpolation="nearest", aspect="auto")
            regions = list(prepared.get("region_order") or REGION_ORDER)
            axis.set_xticks(range(len(regions)), regions, fontsize=font_size)
            axis.set_yticks(range(len(regions)), regions, fontsize=font_size)
            axis.set_xlabel("Target", fontsize=font_size)
            axis.set_ylabel("Seed", fontsize=font_size)
            axis.set_title(f"{band.get('name', '')} [{float(band.get('low_hz', 0)):g}–{float(band.get('high_hz', 0)):g} Hz]", fontsize=font_size)
            for i in range(len(regions)):
                for j in range(len(regions)):
                    if i == j:
                        text, color = "N/A", "#555555"
                    elif np.isfinite(matrix[i, j]):
                        text, color = f"{matrix[i, j]:.3g}", "white" if norm(matrix[i, j]) > 0.55 else "black"
                    else:
                        text, color = "—", "#666666"
                    axis.text(j, i, text, ha="center", va="center", fontsize=max(7, font_size - 1), color=color)
            axis.grid(False)
            axis_lookup[id(axis)] = {"pair_lookup": lookup, "band": band}
            colorbar = figure.colorbar(image, cax=cax)
            colorbar.ax.tick_params(labelsize=max(7, font_size - 1), pad=2)
            colorbar.set_label(_matrix_colorbar_label(method), fontsize=font_size, labelpad=4)
    else:
        axis_lookup = {}
        panel = outer[0, 0].subgridspec(1, 2, width_ratios=[1.0, 0.13], wspace=0.24)
        axis = figure.add_subplot(panel[0, 0])
        cax = figure.add_subplot(panel[0, 1])
        axes.append(axis)
        colorbar_axes.append(cax)
        cax.set_visible(False)
        _axis_empty(axis, f"当前频段没有可显示的 {method_label(method)} 结果")
    figure.suptitle(f"{title_prefix}{method_label(method)} 多频段脑区矩阵", fontsize=font_size + 1)
    return {
        "level": "region_multi",
        "axis_lookup": axis_lookup,
        "matrices": {str(band.get("name", "")): matrix for band, matrix, _ in matrices},
        "scale_note": scale_note if finite_values else "",
        "colorbar_axes": colorbar_axes,
    }


def _channel_pair_matrix_values(
    frame: pd.DataFrame,
    method: str,
    selected_band: dict[str, Any] | None,
    region_pair: tuple[str, str],
    swap: bool,
) -> tuple[np.ndarray, list[str], list[str], dict[tuple[int, int], tuple[str, str]]]:
    empty = np.full((0, 0), np.nan, dtype=float)
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return empty, [], [], {}
    a, b = region_pair
    requested = (b, a) if method == "dpli" and swap else (a, b)
    if method == "dpli":
        working = frame.loc[(frame["region_a"].astype(str) == requested[0]) & (frame["region_b"].astype(str) == requested[1])].copy()
    else:
        canonical = _pair_key(a, b)
        working = frame.loc[(frame["region_a"].astype(str) == canonical[0]) & (frame["region_b"].astype(str) == canonical[1])].copy()
    if selected_band and "band" in working:
        working = working.loc[working["band"].astype(str).eq(str(selected_band.get("name", "")))]
    if working.empty:
        return empty, [], [], {}
    row_channels = list(dict.fromkeys(working["seed_channel"].astype(str)))
    col_channels = list(dict.fromkeys(working["target_channel"].astype(str)))
    values = np.full((len(row_channels), len(col_channels)), np.nan, dtype=float)
    for row in working.itertuples(index=False):
        i, j = row_channels.index(str(row.seed_channel)), col_channels.index(str(row.target_channel))
        numeric = pd.to_numeric(getattr(row, "value_raw_or_summary", np.nan), errors="coerce")
        values[i, j] = float(numeric) if np.isfinite(numeric) else np.nan
    if swap and method != "dpli":
        values = values.T
        row_channels, col_channels = col_channels, row_channels
    lookup = {(i, j): (row_channels[i], col_channels[j]) for i in range(len(row_channels)) for j in range(len(col_channels)) if np.isfinite(values[i, j])}
    return values, row_channels, col_channels, lookup


def plot_channel_pair_matrix(
    axis: Any,
    figure: Any,
    prepared: dict[str, Any],
    selected_band: dict[str, Any] | None,
    region_pair: tuple[str, str] | None,
    swap: bool = False,
    font_size: int = 9,
) -> dict[str, Any]:
    axis.clear()
    axis.set_axis_on()
    method = str(prepared.get("method", "wpli"))
    if region_pair is None:
        _axis_empty(axis, "请先选择一组脑区对")
        return {"level": "channel_pair", "channel_pair_lookup": {}}
    values, rows, columns, lookup = _channel_pair_matrix_values(prepared.get("channel_pair_bands", pd.DataFrame()), method, selected_band, region_pair, swap)
    if values.size == 0 or not np.isfinite(values).any():
        _axis_empty(axis, "当前脑区对没有可显示的通道对频段结果")
        return {"level": "channel_pair", "channel_pair_lookup": lookup, "matrix": values, "region_pair": region_pair, "swap": swap}
    cmap_name = "RdBu_r" if method == "dpli" else "viridis"
    cmap = matplotlib.colormaps.get_cmap(cmap_name).with_extremes(bad="#d9d9d9")
    finite = values[np.isfinite(values)]
    norm, scale_note = _matrix_style(method, finite)
    image = axis.imshow(values, cmap=cmap, norm=norm, interpolation="nearest", aspect="auto")
    axis.set_xticks(range(len(columns)), columns, rotation=45, ha="right", fontsize=font_size)
    axis.set_yticks(range(len(rows)), rows, fontsize=font_size)
    direction = "dPLI 有序 seed→target" if method == "dpli" else "通道对频段汇总"
    axis.set_xlabel("列：target 通道", fontsize=font_size)
    axis.set_ylabel("行：seed 通道", fontsize=font_size)
    axis.set_title(f"{method_label(method)} {region_pair[0]}–{region_pair[1]} 通道对矩阵（{scale_note}；{direction}）{_band_text(selected_band)}", fontsize=font_size + 1)
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            if np.isfinite(values[i, j]):
                color = "white" if norm(values[i, j]) > 0.55 else "black"
                axis.text(j, i, f"{values[i, j]:.3g}", ha="center", va="center", fontsize=max(7, font_size - 1), color=color)
    if getattr(axis, "_connectivity_colorbar", None) is not None:
        try:
            axis._connectivity_colorbar.remove()
        except (AttributeError, ValueError):
            pass
    axis._connectivity_colorbar = figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    axis._connectivity_colorbar.ax.tick_params(labelsize=max(7, font_size - 1))
    axis._connectivity_colorbar.set_label("dPLI（0.5 中性）" if method == "dpli" else method_label(method), fontsize=font_size)
    axis.grid(False)
    return {"level": "channel_pair", "channel_pair_lookup": lookup, "matrix": values, "region_pair": region_pair, "swap": swap}


def plot_channel_pair_matrices(
    figure: Any,
    prepared: dict[str, Any],
    selected_bands: list[dict[str, Any]] | None,
    region_pair: tuple[str, str] | None,
    swap: bool = False,
    font_size: int = 9,
) -> dict[str, Any]:
    """Draw channel-pair matrices with one independently placed cax each."""
    if hasattr(figure, "set_layout_engine"):
        # Keep the channel-pair export on the same explicit layout strategy as
        # the multi-band region matrices.
        figure.set_layout_engine(None)
    figure.clear()
    method = str(prepared.get("method", "wpli"))
    bands = [band for band in (selected_bands or []) if isinstance(band, dict)]
    if region_pair is None:
        axes = figure.subplots(1, 1, squeeze=False)
        _axis_empty(axes[0, 0], "请先选择一组脑区对")
        return {"level": "channel_pair_multi", "axis_lookup": {}}
    if not bands:
        axes = figure.subplots(1, 1, squeeze=False)
        _axis_empty(axes[0, 0], "请至少勾选一个频段")
        return {"level": "channel_pair_multi", "axis_lookup": {}, "region_pair": region_pair, "swap": swap}
    matrices: list[tuple[dict[str, Any], np.ndarray, list[str], list[str], dict[tuple[int, int], tuple[str, str]]]] = []
    for band in bands:
        values, rows, columns, lookup = _channel_pair_matrix_values(prepared.get("channel_pair_bands", pd.DataFrame()), method, band, region_pair, swap)
        matrices.append((band, values, rows, columns, lookup))
    finite_values = [values[np.isfinite(values)] for _, values, _, _, _ in matrices if values.size and np.isfinite(values).any()]
    n_rows = max(1, int(np.ceil(len(matrices) / 2)))
    outer = figure.add_gridspec(
        n_rows,
        2,
        left=0.12,
        right=0.94,
        bottom=0.14,
        top=0.84,
        wspace=0.56,
        hspace=0.66,
    )
    axes: list[Any] = []
    colorbar_axes: list[Any] = []
    axis_lookup: dict[int, dict[str, Any]] = {}
    if finite_values:
        norm, _scale_note = _matrix_style(method, np.concatenate(finite_values))
        cmap_name = "RdBu_r" if method == "dpli" else "viridis"
        cmap = matplotlib.colormaps.get_cmap(cmap_name).with_extremes(bad="#d9d9d9")
        for index, (band, values, rows, columns, lookup) in enumerate(matrices):
            row_index, column_index = divmod(index, 2)
            panel = outer[row_index, column_index].subgridspec(1, 2, width_ratios=[1.0, 0.13], wspace=0.24)
            axis = figure.add_subplot(panel[0, 0])
            cax = figure.add_subplot(panel[0, 1])
            axes.append(axis)
            colorbar_axes.append(cax)
            image = axis.imshow(values, cmap=cmap, norm=norm, interpolation="nearest", aspect="auto")
            axis.set_xticks(range(len(columns)), columns, rotation=45, ha="right", fontsize=font_size)
            axis.set_yticks(range(len(rows)), rows, fontsize=font_size)
            axis.set_xlabel("Target channel", fontsize=font_size)
            axis.set_ylabel("Seed channel", fontsize=font_size)
            axis.set_title(f"{band.get('name', '')} [{float(band.get('low_hz', 0)):g}–{float(band.get('high_hz', 0)):g} Hz]", fontsize=font_size)
            for i in range(values.shape[0]):
                for j in range(values.shape[1]):
                    if np.isfinite(values[i, j]):
                        color = "white" if norm(values[i, j]) > 0.55 else "black"
                        axis.text(j, i, f"{values[i, j]:.3g}", ha="center", va="center", fontsize=max(7, font_size - 1), color=color)
            axis.grid(False)
            axis_lookup[id(axis)] = {"channel_pair_lookup": lookup, "band": band}
            colorbar = figure.colorbar(image, cax=cax)
            colorbar.ax.tick_params(labelsize=max(7, font_size - 1), pad=2)
            colorbar.set_label(_matrix_colorbar_label(method), fontsize=font_size, labelpad=4)
    else:
        panel = outer[0, 0].subgridspec(1, 2, width_ratios=[1.0, 0.13], wspace=0.24)
        axis = figure.add_subplot(panel[0, 0])
        cax = figure.add_subplot(panel[0, 1])
        axes.append(axis)
        colorbar_axes.append(cax)
        cax.set_visible(False)
        _axis_empty(axis, "当前频段没有可显示的通道对结果")
    figure.suptitle(f"{method_label(method)} {region_pair[0]}–{region_pair[1]} 多频段通道对矩阵", fontsize=font_size + 1)
    return {
        "level": "channel_pair_multi",
        "axis_lookup": axis_lookup,
        "region_pair": region_pair,
        "swap": swap,
        "colorbar_axes": colorbar_axes,
    }


def available_methods(tables: dict[str, Any]) -> list[str]:
    frame = tables.get("region_summary", pd.DataFrame())
    if not isinstance(frame, pd.DataFrame) or frame.empty or "method" not in frame:
        return []
    available = {str(value).lower() for value in frame["method"].dropna()}
    return [method for method in METHOD_ORDER if method in available]


def available_components(tables: dict[str, Any]) -> list[int]:
    frame = tables.get("region_summary", pd.DataFrame())
    if not isinstance(frame, pd.DataFrame) or frame.empty or "component_index" not in frame:
        return [1]
    values = pd.to_numeric(frame.loc[frame["method"].astype(str).str.lower().eq("mic"), "component_index"], errors="coerce").dropna()
    components = sorted({int(value) for value in values})
    return components or [1]


def available_bands(tables: dict[str, Any]) -> list[dict[str, Any]]:
    frame = tables.get("band_summary", pd.DataFrame())
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return []
    columns = {"band", "band_low_hz", "band_high_hz"}
    if not columns.issubset(frame.columns):
        return []
    return [
        {"name": str(row.band), "low_hz": float(row.band_low_hz), "high_hz": float(row.band_high_hz)}
        for row in frame[["band", "band_low_hz", "band_high_hz"]].drop_duplicates().sort_values(["band_low_hz", "band_high_hz"]).itertuples(index=False)
    ]
