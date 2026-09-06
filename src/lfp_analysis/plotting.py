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
