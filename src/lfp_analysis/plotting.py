from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _save(fig: plt.Figure, output_base: str | Path, dpi: int = 150) -> tuple[Path, Path]:
    base = Path(output_base)
    base.parent.mkdir(parents=True, exist_ok=True)
    png = base.with_suffix(".png")
    svg = base.with_suffix(".svg")
    fig.savefig(png, dpi=dpi, bbox_inches="tight")
    fig.savefig(svg, bbox_inches="tight")
    plt.close(fig)
    return png, svg


def plot_waveforms(
    data: np.ndarray,
    sfreq: float,
    ch_names: list[str],
    output_base: str | Path,
    max_epochs: int = 6,
    seconds: float = 1.0,
    title_prefix: str = "LFP raw waveform preview",
) -> tuple[Path, Path]:
    n_epochs = min(max_epochs, data.shape[0])
    n_samples = min(data.shape[-1], max(1, int(seconds * sfreq)))
    times = np.arange(n_samples) / sfreq
    fig, axes = plt.subplots(len(ch_names), 1, figsize=(12, max(6, 1.6 * len(ch_names))), sharex=True)
    axes = np.atleast_1d(axes)
    for channel_index, (axis, name) in enumerate(zip(axes, ch_names)):
        for epoch_index in range(n_epochs):
            axis.plot(times, data[epoch_index, channel_index, :n_samples], linewidth=0.6, alpha=0.6)
        axis.set_ylabel(name, fontsize=8)
        axis.grid(True, color="#dddddd", linewidth=0.4)
    axes[-1].set_xlabel("Within-epoch time (s)")
    fig.suptitle(f"{title_prefix}; n_epochs={n_epochs}; n_channels={len(ch_names)}")
    fig.tight_layout()
    return _save(fig, output_base)


def plot_quality_matrix(quality: pd.DataFrame, output_base: str | Path, dpi: int = 150) -> tuple[Path, Path]:
    matrix = quality.pivot(index="epoch_index", columns="channel_name", values="issue_score")
    fig, axis = plt.subplots(figsize=(max(8, 0.6 * len(matrix.columns)), 5))
    image = axis.imshow(matrix.to_numpy(), aspect="auto", interpolation="nearest", cmap="YlOrRd")
    axis.set_xlabel("Channel name")
    axis.set_ylabel("Saved epoch index")
    axis.set_title("Epoch × channel quality issue score; 0=none, higher=more flags")
    axis.set_xticks(np.arange(len(matrix.columns)), matrix.columns, rotation=90, fontsize=7)
    axis.set_yticks(np.arange(len(matrix.index)), matrix.index)
    fig.colorbar(image, ax=axis, label="Number of quality flags")
    fig.tight_layout()
    return _save(fig, output_base, dpi=dpi)


def plot_psd(psd_summary: pd.DataFrame, output_base: str | Path, dpi: int = 150, title: str = "Channel PSD") -> tuple[Path, Path]:
    fig, axis = plt.subplots(figsize=(11, 6))
    if psd_summary.empty:
        axis.text(0.5, 0.5, "No valid PSD estimates", ha="center", va="center")
    else:
        for channel_name, group in psd_summary.groupby("channel_name", sort=False):
            axis.plot(group["frequency_hz"], group["psd_value"], linewidth=0.8, label=channel_name)
        axis.set_yscale("log")
        axis.legend(ncol=2, fontsize=7)
    axis.set_xlabel("Frequency (Hz)")
    axis.set_ylabel("PSD (power²/Hz in source unit)")
    axis.set_title(title)
    axis.grid(True, which="both", color="#dddddd", linewidth=0.4)
    fig.tight_layout()
    return _save(fig, output_base, dpi=dpi)


def plot_band_power(band_power: pd.DataFrame, output_base: str | Path, dpi: int = 150) -> tuple[Path, Path]:
    bands = list(band_power["band"].dropna().unique()) if not band_power.empty else []
    fig, axes = plt.subplots(max(1, len(bands)), 1, figsize=(12, max(4, 3.2 * len(bands))), squeeze=False)
    axes = axes[:, 0]
    for axis, band in zip(axes, bands):
        subset = band_power.loc[band_power["band"] == band]
        summary = subset.groupby("channel_name", as_index=False)["absolute_power"].mean()
        axis.bar(summary["channel_name"], summary["absolute_power"], color="#4472C4")
        axis.set_title(f"Band power: {band}")
        axis.set_ylabel("Absolute power")
        axis.tick_params(axis="x", rotation=90)
        axis.grid(axis="y", color="#dddddd", linewidth=0.4)
    if not bands:
        axes[0].text(0.5, 0.5, "No valid band-power estimates", ha="center", va="center")
    fig.suptitle("Channel-level band power; bars summarize epochs within this file")
    fig.tight_layout()
    return _save(fig, output_base, dpi=dpi)


def _parameterization_grid(curves: pd.DataFrame, models: pd.DataFrame) -> tuple[list[str], int, int]:
    channels = list(models.get("channel_name", pd.Series(dtype=str)).dropna().astype(str))
    if not channels and not curves.empty:
        channels = list(curves["channel_name"].dropna().astype(str).unique())
    n_channels = len(channels)
    n_columns = min(4, max(1, n_channels))
    n_rows = max(1, int(np.ceil(n_channels / n_columns)))
    return channels, n_rows, n_columns


def plot_parameterization_fit(
    curves: pd.DataFrame,
    models: pd.DataFrame,
    output_base: str | Path,
    dpi: int = 150,
) -> tuple[Path, Path]:
    """Plot observed PSD, full model and aperiodic background per channel."""
    channels, n_rows, n_columns = _parameterization_grid(curves, models)
    fig, axes = plt.subplots(n_rows, n_columns, figsize=(4.0 * n_columns, 2.8 * n_rows), squeeze=False, sharex=False)
    axes_flat = axes.ravel()
    for panel_index, channel_name in enumerate(channels):
        axis = axes_flat[panel_index]
        group = curves.loc[curves["channel_name"].astype(str) == channel_name].sort_values("frequency_hz")
        model = models.loc[models["channel_name"].astype(str) == channel_name]
        if group.empty:
            axis.text(0.5, 0.5, "No valid fitted curve", ha="center", va="center", transform=axis.transAxes)
            axis.set_title(channel_name, fontsize=9)
            continue
        axis.plot(group["frequency_hz"], group["observed_power"], color="#1f77b4", linewidth=0.8, label="Observed PSD")
        axis.plot(group["frequency_hz"], group["full_model_power"], color="#ff7f0e", linewidth=1.0, label="Full model")
        axis.plot(group["frequency_hz"], group["aperiodic_power"], color="#666666", linestyle="--", linewidth=0.8, label="Aperiodic")
        axis.set_yscale("log")
        axis.grid(True, which="both", color="#dddddd", linewidth=0.35)
        axis.set_title(channel_name, fontsize=9)
        if not model.empty and pd.notna(model["r_squared"].iloc[0]):
            axis.text(0.98, 0.04, f"R²={model['r_squared'].iloc[0]:.3f}", transform=axis.transAxes, ha="right", fontsize=7)
        if panel_index == 0:
            axis.legend(fontsize=7, loc="best")
    for axis in axes_flat[len(channels):]:
        axis.axis("off")
    for axis in axes[-1, :]:
        axis.set_xlabel("Frequency (Hz)")
    for axis in axes[:, 0]:
        axis.set_ylabel("PSD (source unit²/Hz)")
    fig.suptitle("specparam/FOOOF parameterization: observed PSD, full model and aperiodic background")
    fig.tight_layout()
    return _save(fig, output_base, dpi=dpi)


def plot_parameterization_components(
    curves: pd.DataFrame,
    models: pd.DataFrame,
    output_base: str | Path,
    dpi: int = 150,
) -> tuple[Path, Path]:
    """Plot additive periodic component and log10 residual per channel."""
    channels, n_rows, n_columns = _parameterization_grid(curves, models)
    fig, axes = plt.subplots(n_rows, n_columns, figsize=(4.0 * n_columns, 2.8 * n_rows), squeeze=False, sharex=False)
    axes_flat = axes.ravel()
    for panel_index, channel_name in enumerate(channels):
        axis = axes_flat[panel_index]
        group = curves.loc[curves["channel_name"].astype(str) == channel_name].sort_values("frequency_hz")
        model = models.loc[models["channel_name"].astype(str) == channel_name]
        if group.empty:
            axis.text(0.5, 0.5, "No valid fitted curve", ha="center", va="center", transform=axis.transAxes)
            axis.set_title(channel_name, fontsize=9)
            continue
        axis.plot(
            group["frequency_hz"],
            group["periodic_component_log10_additive"],
            color="#2ca02c",
            linewidth=0.8,
            label="Periodic component (log10 additive)",
        )
        axis.plot(group["frequency_hz"], group["residual_log10"], color="#d62728", linewidth=0.7, label="Residual")
        axis.axhline(0.0, color="#444444", linewidth=0.6)
        axis.grid(True, color="#dddddd", linewidth=0.35)
        axis.set_title(channel_name, fontsize=9)
        if not model.empty and pd.notna(model["error"].iloc[0]):
            axis.text(0.98, 0.04, f"MAE={model['error'].iloc[0]:.3f}", transform=axis.transAxes, ha="right", fontsize=7)
        if panel_index == 0:
            axis.legend(fontsize=7, loc="best")
    for axis in axes_flat[len(channels):]:
        axis.axis("off")
    for axis in axes[-1, :]:
        axis.set_xlabel("Frequency (Hz)")
    for axis in axes[:, 0]:
        axis.set_ylabel("Log10 additive / residual")
    fig.suptitle("specparam/FOOOF parameterization: periodic component and residual")
    fig.tight_layout()
    return _save(fig, output_base, dpi=dpi)


def plot_connectivity_redundancy(
    correlation: pd.DataFrame,
    singular_values: pd.DataFrame,
    rank_summary: pd.DataFrame,
    output_base: str | Path,
    dpi: int = 150,
) -> tuple[Path, Path]:
    regions = list(rank_summary.get("region", pd.Series(dtype=str)).astype(str))
    n_columns = max(1, min(4, len(regions)))
    n_rows = 2
    fig, axes = plt.subplots(n_rows, n_columns, figsize=(3.4 * n_columns, 6.0), squeeze=False)
    for index, region in enumerate(regions):
        axis_corr = axes[0, index]
        matrix = correlation.loc[correlation["region"].astype(str) == region].pivot(index="channel_i", columns="channel_j", values="correlation")
        image = axis_corr.imshow(matrix.to_numpy(float), vmin=-1.0, vmax=1.0, cmap="coolwarm", interpolation="nearest")
        axis_corr.set_title(f"{region} correlation")
        axis_corr.set_xticks(np.arange(len(matrix.columns)), matrix.columns, rotation=90, fontsize=7)
        axis_corr.set_yticks(np.arange(len(matrix.index)), matrix.index, fontsize=7)
        axis_corr.set_xlabel("Channel")
        axis_corr.set_ylabel("Channel")
        row = rank_summary.loc[rank_summary["region"].astype(str) == region].iloc[0]
        axis_corr.text(0.02, 0.02, f"selected rank={int(row['selected_rank'])}\nnumerical={int(row['numerical_rank'])}", transform=axis_corr.transAxes, fontsize=7, color="#333333", bbox={"facecolor": "white", "alpha": 0.75, "pad": 2})
        fig.colorbar(image, ax=axis_corr, fraction=0.046, pad=0.04, label="Correlation")
        axis_svd = axes[1, index]
        values = singular_values.loc[singular_values["region"].astype(str) == region]
        axis_svd.bar(values["component"], values["variance_fraction"], color="#4472C4")
        axis_svd.plot(values["component"], values["cumulative_variance_fraction"], color="#ED7D31", marker="o", linewidth=1.0, label="Cumulative")
        axis_svd.axhline(float(row["rank_variance_threshold"]), color="#666666", linestyle="--", linewidth=0.8, label="Configured threshold")
        axis_svd.set_title(f"{region} singular dimensions")
        axis_svd.set_xlabel("Component")
        axis_svd.set_ylabel("Variance fraction")
        axis_svd.set_ylim(0, 1.05)
        axis_svd.grid(axis="y", color="#dddddd", linewidth=0.4)
        if index == 0:
            axis_svd.legend(fontsize=7)
    for axis in axes[:, len(regions) :].ravel():
        axis.axis("off")
    fig.suptitle("Within-region channel redundancy and selected multivariate rank")
    fig.tight_layout()
    return _save(fig, output_base, dpi=dpi)


def plot_connectivity_spectrum(
    region_summary: pd.DataFrame,
    method: str,
    output_base: str | Path,
    dpi: int = 150,
) -> tuple[Path, Path]:
    pairs = list(region_summary.loc[region_summary["method"] == method, ["region_a", "region_b"]].drop_duplicates().itertuples(index=False, name=None))
    n_columns = 3
    n_rows = max(1, int(np.ceil(len(pairs) / n_columns)))
    fig, axes = plt.subplots(n_rows, n_columns, figsize=(4.2 * n_columns, 2.8 * n_rows), squeeze=False)
    ylabel = {"mic": "|MIC| (A.U.)", "mim": "MIM (raw, unnormalised)", "wpli": "wPLI (0–1)", "dpli": "dPLI (0–1; 0.5 neutral)", "wpli2_debiased": "wPLI²_debiased (raw)"}.get(method, f"{method} (raw)")
    color = {"mic": "#4472C4", "mim": "#ED7D31", "wpli": "#3A7D44", "dpli": "#8C2D04", "wpli2_debiased": "#70AD47"}.get(method, "#4472C4")
    for index, (region_a, region_b) in enumerate(pairs):
        axis = axes.ravel()[index]
        subset = region_summary.loc[(region_summary["method"] == method) & (region_summary["region_a"] == region_a) & (region_summary["region_b"] == region_b)].sort_values("frequency_hz")
        axis.plot(subset["frequency_hz"], subset["value_strength"], color=color, linewidth=0.9)
        for line in (50.0, 60.0):
            axis.axvline(line, color="#999999", linestyle=":", linewidth=0.6)
        axis.set_title(f"{region_a}–{region_b}")
        axis.set_xlabel("Frequency (Hz)")
        axis.set_ylabel(ylabel)
        if method in {"wpli", "dpli"}:
            axis.set_ylim(0.0, 1.0)
        if method == "dpli":
            axis.axhline(0.5, color="#666666", linestyle=":", linewidth=0.6)
        axis.grid(True, color="#dddddd", linewidth=0.4)
    for axis in axes.ravel()[len(pairs) :]:
        axis.axis("off")
    fig.suptitle(f"{method}: six brain-region pair spectra; region-level description, line-noise markers at 50/60 Hz")
    fig.tight_layout()
    return _save(fig, output_base, dpi=dpi)


def plot_connectivity_band_matrices(
    band_summary: pd.DataFrame,
    output_base: str | Path,
    dpi: int = 150,
) -> tuple[Path, Path]:
    observed_regions = list(dict.fromkeys(
        list(band_summary.get("region_a", pd.Series(dtype=str)).dropna().astype(str))
        + list(band_summary.get("region_b", pd.Series(dtype=str)).dropna().astype(str))
    ))
    default_order = [region for region in ("M1", "STR", "PF", "SNr") if region in observed_regions]
    regions = default_order + [region for region in observed_regions if region not in default_order]
    bands = list(band_summary.get("band", pd.Series(dtype=str)).dropna().unique())
    methods = [method for method in ("mic", "mim", "wpli", "dpli", "wpli2_debiased") if method in set(band_summary.get("method", pd.Series(dtype=str)))]
    if not regions or not bands or not methods:
        fig, axis = plt.subplots(figsize=(7, 4))
        axis.text(0.5, 0.5, "No band-level connectivity estimates", ha="center", va="center")
        axis.axis("off")
        return _save(fig, output_base, dpi=dpi)
    fig, axes = plt.subplots(len(methods), len(bands), figsize=(3.0 * len(bands), 3.0 * len(methods)), squeeze=False)
    for method_index, method in enumerate(methods):
        method_data = band_summary.loc[band_summary["method"] == method]
        values = method_data["value_strength"].to_numpy(float)
        finite = values[np.isfinite(values)]
        vmin, vmax = (float(np.min(finite)), float(np.max(finite))) if finite.size else (0.0, 1.0)
        if vmin == vmax:
            vmin, vmax = vmin - 1e-12, vmax + 1e-12
        for band_index, band in enumerate(bands):
            axis = axes[method_index, band_index]
            subset = method_data.loc[method_data["band"] == band]
            matrix = pd.DataFrame(np.nan, index=regions, columns=regions)
            for _, row in subset.iterrows():
                matrix.loc[row["region_a"], row["region_b"]] = row["value_strength"]
                if method != "dpli":
                    matrix.loc[row["region_b"], row["region_a"]] = row["value_strength"]
            if method == "dpli":
                image = axis.imshow(matrix.to_numpy(float), vmin=0.0, vmax=1.0, cmap="RdBu_r", interpolation="nearest")
            else:
                image = axis.imshow(matrix.to_numpy(float), vmin=vmin, vmax=vmax, cmap="viridis", interpolation="nearest")
            axis.set_title(f"{method}\n{band}", fontsize=8)
            axis.set_xticks(np.arange(len(regions)), regions, rotation=45, ha="right", fontsize=7)
            axis.set_yticks(np.arange(len(regions)), regions, fontsize=7)
            axis.set_xlabel("Diagonal: N/A", fontsize=7)
            for i in range(len(regions)):
                for j in range(len(regions)):
                    if i != j and np.isfinite(matrix.iloc[i, j]):
                        axis.text(j, i, f"{matrix.iloc[i, j]:.3g}", ha="center", va="center", fontsize=7, color="white")
            fig.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    fig.suptitle("Region-level connectivity by configured band; each method has its own colour scale")
    fig.tight_layout()
    return _save(fig, output_base, dpi=dpi)


def plot_connectivity_channel_pairs(
    spectrum: pd.DataFrame,
    output_base: str | Path,
    dpi: int = 150,
    method: str = "wpli2_debiased",
) -> tuple[Path, Path]:
    if spectrum.empty or not {"method", "aggregation_level", "frequency_is_excluded_line_noise"}.issubset(spectrum.columns):
        fig, axis = plt.subplots(figsize=(7, 4))
        axis.text(0.5, 0.5, "No channel-pair connectivity estimates", ha="center", va="center")
        axis.axis("off")
        return _save(fig, output_base, dpi=dpi)
    subset = spectrum.loc[(spectrum["method"] == method) & (spectrum["aggregation_level"] == "cross_region_channel_pair") & ~spectrum["frequency_is_excluded_line_noise"]].copy()
    pairs = list(subset[["region_a", "region_b"]].drop_duplicates().itertuples(index=False, name=None))
    n_columns = 3
    n_rows = max(1, int(np.ceil(len(pairs) / n_columns)))
    fig, axes = plt.subplots(n_rows, n_columns, figsize=(4.0 * n_columns, 3.4 * n_rows), squeeze=False)
    for index, (region_a, region_b) in enumerate(pairs):
        axis = axes.ravel()[index]
        group = subset.loc[(subset["region_a"] == region_a) & (subset["region_b"] == region_b)]
        pair_values = group.groupby(["seed_channel", "target_channel"], as_index=False)["value_raw"].mean()
        matrix = pair_values.pivot(index="seed_channel", columns="target_channel", values="value_raw")
        image = axis.imshow(matrix.to_numpy(float), cmap="RdBu_r" if method == "dpli" else "viridis", vmin=0.0 if method == "dpli" else None, vmax=1.0 if method == "dpli" else None, interpolation="nearest")
        axis.set_title(f"{region_a}–{region_b}; frequency mean")
        axis.set_xticks(np.arange(len(matrix.columns)), matrix.columns, rotation=90, fontsize=7)
        axis.set_yticks(np.arange(len(matrix.index)), matrix.index, fontsize=7)
        axis.set_xlabel("Target channel")
        axis.set_ylabel("Seed channel")
        fig.colorbar(image, ax=axis, fraction=0.046, pad=0.04, label="dPLI (0.5 neutral)" if method == "dpli" else f"{method} raw")
    for axis in axes.ravel()[len(pairs) :]:
        axis.axis("off")
    fig.suptitle(f"Cross-region channel-pair {method}; all valid channel pairs retained")
    fig.tight_layout()
    return _save(fig, output_base, dpi=dpi)


def plot_connectivity_rank_sensitivity(
    sensitivity: pd.DataFrame,
    output_base: str | Path,
    dpi: int = 150,
) -> tuple[Path, Path]:
    pairs = list(sensitivity[["region_a", "region_b"]].dropna().drop_duplicates().itertuples(index=False, name=None)) if {"region_a", "region_b"}.issubset(sensitivity.columns) else []
    fig, axes = plt.subplots(max(1, int(np.ceil(len(pairs) / 3))), 3, figsize=(12, 3.0 * max(1, int(np.ceil(len(pairs) / 3)))), squeeze=False)
    for index, (region_a, region_b) in enumerate(pairs):
        axis = axes.ravel()[index]
        group = sensitivity.loc[(sensitivity["region_a"] == region_a) & (sensitivity["region_b"] == region_b)]
        for method, color in (("mic", "#4472C4"), ("mim", "#ED7D31")):
            method_group = group.loc[(group["method"] == method) & (group["status"] == "ok")].sort_values("rank_offset")
            axis.plot(method_group["rank_offset"], method_group["mean_strength_2_100hz"], marker="o", color=color, label=method)
        axis.axvline(0, color="#666666", linestyle="--", linewidth=0.7)
        axis.set_title(f"{region_a}–{region_b}")
        axis.set_xlabel("Rank offset from selected rule")
        axis.set_ylabel("Mean strength, 2–100 Hz")
        axis.grid(axis="y", color="#dddddd", linewidth=0.4)
        if index == 0:
            axis.legend(fontsize=8)
    for axis in axes.ravel()[len(pairs) :]:
        axis.axis("off")
    fig.suptitle("MIC/MIM sensitivity to fixed rank offsets; this is not significance testing")
    fig.tight_layout()
    return _save(fig, output_base, dpi=dpi)


def plot_time_delay_spectrum(
    region_spectrum: pd.DataFrame,
    method: int,
    antisymmetrized: bool,
    output_base: str | Path,
    dpi: int = 150,
) -> tuple[Path, Path]:
    subset = region_spectrum.loc[
        (region_spectrum["method"] == method)
        & (region_spectrum["antisymmetrized"].astype(bool) == bool(antisymmetrized))
    ].copy()
    pairs = list(subset[["region_a", "region_b"]].drop_duplicates().itertuples(index=False, name=None)) if not subset.empty else []
    n_columns = 3
    n_rows = max(1, int(np.ceil(len(pairs) / n_columns)))
    fig, axes = plt.subplots(n_rows, n_columns, figsize=(4.2 * n_columns, 2.9 * n_rows), squeeze=False)
    for index, (region_a, region_b) in enumerate(pairs):
        axis = axes.ravel()[index]
        pair = subset.loc[(subset["region_a"] == region_a) & (subset["region_b"] == region_b)]
        for band, band_data in pair.groupby("frequency_band", sort=False):
            band_data = band_data.sort_values("delay_ms")
            axis.plot(band_data["delay_ms"], band_data["estimate_strength"], linewidth=0.9, label=str(band))
            peak = band_data.loc[band_data["estimate_strength"].idxmax()]
            axis.plot(peak["delay_ms"], peak["estimate_strength"], "o", markersize=3)
        axis.axvline(0, color="#666666", linestyle="--", linewidth=0.7)
        axis.set_title(f"{region_a}–{region_b}")
        axis.set_xlabel("Delay (ms); positive = seed leads target")
        axis.set_ylabel("TDE estimate strength")
        axis.grid(True, color="#dddddd", linewidth=0.4)
        if index == 0:
            axis.legend(fontsize=7, ncol=2)
    for axis in axes.ravel()[len(pairs) :]:
        axis.axis("off")
    mode = "antisymmetrized" if antisymmetrized else "standard"
    fig.suptitle(f"PyBispectra TDE method {method} ({mode}); region-median spectra")
    fig.tight_layout()
    return _save(fig, output_base, dpi=dpi)


def plot_time_delay_band_matrix(
    band_summary: pd.DataFrame,
    method: int,
    antisymmetrized: bool,
    output_base: str | Path,
    dpi: int = 150,
) -> tuple[Path, Path]:
    subset = band_summary.loc[
        (band_summary["method"] == method)
        & (band_summary["antisymmetrized"].astype(bool) == bool(antisymmetrized))
    ].copy()
    bands = list(subset.get("frequency_band", pd.Series(dtype=str)).dropna().unique()) if not subset.empty else []
    observed_regions = list(dict.fromkeys(
        list(subset.get("region_a", pd.Series(dtype=str)).dropna().astype(str))
        + list(subset.get("region_b", pd.Series(dtype=str)).dropna().astype(str))
    ))
    default_order = [region for region in ("M1", "STR", "PF", "SNr") if region in observed_regions]
    regions = default_order + [region for region in observed_regions if region not in default_order]
    if not bands or not regions:
        fig, axis = plt.subplots(figsize=(7, 4))
        axis.text(0.5, 0.5, "No time-delay band estimates", ha="center", va="center")
        axis.axis("off")
        return _save(fig, output_base, dpi=dpi)
    fig, axes = plt.subplots(1, len(bands), figsize=(3.0 * len(bands), 3.0), squeeze=False)
    values = subset["region_peak_delay_ms"].to_numpy(float)
    finite = values[np.isfinite(values)]
    vmax = float(np.max(np.abs(finite))) if finite.size else 1.0
    vmax = max(vmax, 1.0)
    for band_index, band in enumerate(bands):
        axis = axes[0, band_index]
        matrix = pd.DataFrame(np.nan, index=regions, columns=regions)
        for _, row in subset.loc[subset["frequency_band"] == band].iterrows():
            matrix.loc[row["region_a"], row["region_b"]] = row["region_peak_delay_ms"]
            matrix.loc[row["region_b"], row["region_a"]] = -row["region_peak_delay_ms"]
        image = axis.imshow(matrix.to_numpy(float), vmin=-vmax, vmax=vmax, cmap="coolwarm", interpolation="nearest")
        axis.set_title(str(band), fontsize=8)
        axis.set_xticks(np.arange(len(regions)), regions, rotation=45, ha="right", fontsize=7)
        axis.set_yticks(np.arange(len(regions)), regions, fontsize=7)
        axis.set_xlabel("ms; diagonal N/A", fontsize=7)
        for i in range(len(regions)):
            for j in range(len(regions)):
                if i != j and np.isfinite(matrix.iloc[i, j]):
                    axis.text(j, i, f"{matrix.iloc[i, j]:.0f}", ha="center", va="center", fontsize=7, color="black")
        fig.colorbar(image, ax=axis, fraction=0.046, pad=0.04, label="Peak delay (ms)")
    mode = "antisymmetrized" if antisymmetrized else "standard"
    fig.suptitle(f"PyBispectra TDE method {method} ({mode}); signed seed-to-target delay")
    fig.tight_layout()
    return _save(fig, output_base, dpi=dpi)
