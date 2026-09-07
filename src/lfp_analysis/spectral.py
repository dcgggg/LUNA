from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import welch


def _band_mask(freqs: np.ndarray, low: float, high: float, excluded: list[float]) -> np.ndarray:
    mask = (freqs >= float(low)) & (freqs <= float(high))
    for line_hz in excluded:
        mask &= np.abs(freqs - float(line_hz)) > 0.5
    return mask


def compute_psd(data: np.ndarray, sfreq: float, ch_names: list[str], config: dict[str, Any]) -> pd.DataFrame:
    """Estimate PSD per epoch and channel with configurable Welch parameters."""
    psd_cfg = config.get("psd", {})
    fmin = float(psd_cfg.get("fmin_hz", 1.0))
    fmax = float(psd_cfg.get("fmax_hz", sfreq / 2))
    requested_nperseg = int(psd_cfg.get("nperseg", min(1000, data.shape[-1])))
    requested_noverlap = int(psd_cfg.get("noverlap", requested_nperseg // 2))
    requested_nfft = psd_cfg.get("nfft")
    requested_nfft = None if requested_nfft in (None, "", 0, "0") else int(requested_nfft)
    window = psd_cfg.get("window", "hann")
    detrend = psd_cfg.get("detrend", "constant")
    scaling = psd_cfg.get("scaling", "density")
    rows: list[dict[str, Any]] = []
    for epoch_index, epoch in enumerate(np.asarray(data, dtype=float)):
        for channel_index, channel_name in enumerate(ch_names):
            signal = epoch[channel_index]
            if not np.all(np.isfinite(signal)):
                rows.append(
                    {
                        "epoch_index": epoch_index,
                        "channel_array_index": channel_index,
                        "channel_name": channel_name,
                        "frequency_hz": np.nan,
                        "psd_value": np.nan,
                        "status": "skipped_nonfinite",
                        "nperseg_used": np.nan,
                        "noverlap_used": np.nan,
                    }
                )
                continue
            nperseg = min(requested_nperseg, signal.size)
            noverlap = min(requested_noverlap, max(nperseg - 1, 0))
            freqs, power = welch(
                signal,
                fs=sfreq,
                window=window,
                nperseg=nperseg,
                noverlap=noverlap,
                nfft=requested_nfft,
                detrend=detrend,
                scaling=scaling,
                average=psd_cfg.get("average", "mean"),
            )
            keep = (freqs >= fmin) & (freqs <= fmax)
            for frequency, value in zip(freqs[keep], power[keep]):
                rows.append(
                    {
                        "epoch_index": epoch_index,
                        "channel_array_index": channel_index,
                        "channel_name": channel_name,
                        "frequency_hz": float(frequency),
                        "psd_value": float(value),
                        "status": "ok",
                        "nperseg_used": nperseg,
                        "noverlap_used": noverlap,
                    }
                )
    return pd.DataFrame(rows)


def summarize_psd(
    psd: pd.DataFrame,
    channel_table: pd.DataFrame | None = None,
    epoch_aggregation: str = "mean",
) -> dict[str, pd.DataFrame]:
    valid = psd.loc[psd["status"] == "ok"].copy()
    aggregation = "median" if str(epoch_aggregation).lower() == "median" else "mean"
    channel_summary = (
        valid.groupby(["channel_array_index", "channel_name", "frequency_hz"], as_index=False)
        .agg(
            psd_value=("psd_value", aggregation),
            psd_sd=("psd_value", "std"),
            n_epochs=("epoch_index", "nunique"),
        )
    )
    if channel_table is None or channel_table.empty or "region" not in channel_table:
        region_summary = pd.DataFrame()
    else:
        region_map = channel_table[["channel_name", "region"]].copy()
        region_map["region"] = region_map["region"].fillna("").astype(str)
        region_summary = channel_summary.merge(region_map, on="channel_name", how="left")
        region_summary = region_summary.loc[region_summary["region"].str.strip() != ""]
        region_summary = (
            region_summary.groupby(["region", "frequency_hz"], as_index=False)
            .agg(
                psd_value=("psd_value", "mean"),
                psd_sd_across_channels=("psd_value", "std"),
                n_channels=("channel_name", "nunique"),
                n_epoch_channel_estimates=("n_epochs", "sum"),
            )
        )
    return {"channel": channel_summary, "region": region_summary}


def compute_band_power(psd: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    bands = config.get("bands", {})
    relative_cfg = config.get("relative_power", {})
    denominator = relative_cfg.get("denominator_hz", [1.0, 100.0])
    excluded = [float(item) for item in relative_cfg.get("exclude_line_noise_hz", [])]
    valid = psd.loc[psd["status"] == "ok"].copy()
    rows: list[dict[str, Any]] = []
    group_keys = ["epoch_index", "channel_array_index", "channel_name"]
    for key, group in valid.groupby(group_keys, dropna=False):
        group = group.sort_values("frequency_hz")
        frequencies = group["frequency_hz"].to_numpy(float)
        powers = group["psd_value"].to_numpy(float)
        denominator_mask = _band_mask(frequencies, denominator[0], denominator[1], excluded)
        denominator_range = (frequencies >= float(denominator[0])) & (frequencies <= float(denominator[1]))
        excluded_mask = denominator_range & ~denominator_mask
        denominator_power = (
            float(np.trapezoid(powers[denominator_mask], frequencies[denominator_mask]))
            if np.sum(denominator_mask) >= 2
            else np.nan
        )
        for band_name, bounds in bands.items():
            mask = _band_mask(frequencies, bounds[0], bounds[1], excluded)
            absolute_power = float(np.trapezoid(powers[mask], frequencies[mask])) if np.sum(mask) >= 2 else np.nan
            relative_power = absolute_power / denominator_power if denominator_power > 0 else np.nan
            rows.append(
                {
                    "epoch_index": key[0],
                    "channel_array_index": key[1],
                    "channel_name": key[2],
                    "band": band_name,
                    "band_low_hz": float(bounds[0]),
                    "band_high_hz": float(bounds[1]),
                    "absolute_power": absolute_power,
                    "relative_power": relative_power,
                    "relative_denominator_low_hz": float(denominator[0]),
                    "relative_denominator_high_hz": float(denominator[1]),
                    "excluded_frequency_count": int(np.sum(excluded_mask)),
                    "status": "ok" if np.isfinite(absolute_power) else "insufficient_frequency_bins",
                }
            )
    return pd.DataFrame(rows)
