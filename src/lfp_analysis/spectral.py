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


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _frequency_step(freqs: np.ndarray, sfreq: float, n_times: int) -> float:
    if len(freqs) > 1:
        return float(np.median(np.diff(freqs)))
    return float(sfreq / max(n_times, 1))


def _integrate_contiguous_frequency_segments(
    frequencies: np.ndarray,
    powers: np.ndarray,
    mask: np.ndarray,
    expected_step_hz: float,
) -> tuple[float, int, float]:
    """Integrate only contiguous frequency runs; never bridge a masked gap."""
    selected_frequencies = np.asarray(frequencies)[np.asarray(mask, dtype=bool)]
    selected_powers = np.asarray(powers)[np.asarray(mask, dtype=bool)]
    if len(selected_frequencies) < 2:
        return np.nan, 0, np.nan
    split_points = np.flatnonzero(np.diff(selected_frequencies) > max(1.5 * expected_step_hz, np.finfo(float).eps)) + 1
    frequency_runs = np.split(selected_frequencies, split_points)
    power_runs = np.split(selected_powers, split_points)
    integrals = [float(np.trapezoid(run_power, run_frequency)) for run_frequency, run_power in zip(frequency_runs, power_runs, strict=False) if len(run_frequency) >= 2]
    largest_gap = float(np.max(np.diff(selected_frequencies))) if len(selected_frequencies) > 1 else np.nan
    return (float(np.sum(integrals)) if integrals else np.nan), len(integrals), largest_gap


def compute_psd(data: np.ndarray, sfreq: float, ch_names: list[str], config: dict[str, Any]) -> pd.DataFrame:
    """Estimate PSD per epoch and channel with Welch or DPSS multitaper.

    Welch keeps its window/overlap/nfft parameters.  Multitaper uses MNE's
    ``psd_array_multitaper`` and therefore has a native frequency grid of
    approximately ``sfreq / n_times``; its ``bandwidth`` controls smoothing,
    not the frequency-grid spacing.
    """
    psd_cfg = config.get("psd", {})
    method = str(psd_cfg.get("method", "welch")).strip().lower()
    if method not in {"welch", "multitaper"}:
        raise ValueError(f"Unsupported PSD method: {method!r}; choose 'welch' or 'multitaper'.")
    fmin = float(psd_cfg.get("fmin_hz", 1.0))
    fmax = float(psd_cfg.get("fmax_hz", sfreq / 2))
    requested_nperseg = int(psd_cfg.get("nperseg", min(1000, data.shape[-1])))
    requested_noverlap = int(psd_cfg.get("noverlap", requested_nperseg // 2))
    requested_nfft = psd_cfg.get("nfft")
    requested_nfft = None if requested_nfft in (None, "", 0, "0") else int(requested_nfft)
    window = psd_cfg.get("window", "hann")
    detrend = psd_cfg.get("detrend", "constant")
    scaling = psd_cfg.get("scaling", "density")
    multitaper_bandwidth = float(psd_cfg.get("multitaper_bandwidth_hz", 4.0))
    multitaper_adaptive = _as_bool(psd_cfg.get("multitaper_adaptive", False), False)
    multitaper_low_bias = _as_bool(psd_cfg.get("multitaper_low_bias", True), True)
    multitaper_normalization = str(psd_cfg.get("multitaper_normalization", "length"))
    multitaper_remove_dc = _as_bool(psd_cfg.get("multitaper_remove_dc", True), True)
    multitaper_n_jobs_value = psd_cfg.get("multitaper_n_jobs", 1)
    multitaper_n_jobs = None if multitaper_n_jobs_value in (None, "", 0, "0") else int(multitaper_n_jobs_value)
    if method == "multitaper":
        if multitaper_bandwidth <= 0:
            raise ValueError("multitaper_bandwidth_hz must be greater than zero.")
        if multitaper_normalization not in {"length", "full"}:
            raise ValueError("multitaper_normalization must be 'length' or 'full'.")
        try:
            from mne.time_frequency import psd_array_multitaper
        except ImportError as exc:
            raise ImportError("Multitaper PSD requires MNE's psd_array_multitaper.") from exc

    multitaper_batch_results: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}
    multitaper_batch_input_shape = ""
    multitaper_batch_call_count = 0
    if method == "multitaper":
        array_data = np.asarray(data, dtype=float)
        finite_signal_mask = np.all(np.isfinite(array_data), axis=-1)
        finite_positions = np.argwhere(finite_signal_mask)
        multitaper_batch_input_shape = "×".join(str(int(value)) for value in array_data[finite_signal_mask].shape)
        if finite_positions.size:
            batch_power, batch_freqs = psd_array_multitaper(
                array_data[finite_signal_mask],
                sfreq=sfreq,
                fmin=fmin,
                fmax=fmax,
                bandwidth=multitaper_bandwidth,
                adaptive=multitaper_adaptive,
                low_bias=multitaper_low_bias,
                normalization=multitaper_normalization,
                remove_dc=multitaper_remove_dc,
                output="power",
                n_jobs=multitaper_n_jobs,
                verbose=False,
            )
            batch_power = np.asarray(batch_power, dtype=float)
            if batch_power.ndim == 1:
                batch_power = batch_power[np.newaxis, :]
            batch_freqs = np.asarray(batch_freqs, dtype=float).reshape(-1)
            if batch_power.shape[0] != len(finite_positions):
                raise ValueError(
                    "Multitaper batch output does not preserve valid epoch/channel rows: "
                    f"input={len(finite_positions)}, output={batch_power.shape}"
                )
            multitaper_batch_results = {
                (int(position[0]), int(position[1])): (power, batch_freqs)
                for position, power in zip(finite_positions, batch_power, strict=True)
            }
            multitaper_batch_call_count = 1

    method_metadata = {
        "psd_method": method,
        "multitaper_bandwidth_hz": multitaper_bandwidth if method == "multitaper" else np.nan,
        "multitaper_adaptive": multitaper_adaptive if method == "multitaper" else np.nan,
        "multitaper_low_bias": multitaper_low_bias if method == "multitaper" else np.nan,
        "multitaper_normalization": multitaper_normalization if method == "multitaper" else "",
        "multitaper_remove_dc": multitaper_remove_dc if method == "multitaper" else np.nan,
        "multitaper_n_jobs": multitaper_n_jobs if method == "multitaper" else np.nan,
        "multitaper_batch_input_shape": multitaper_batch_input_shape,
        "multitaper_batch_call_count": multitaper_batch_call_count,
        "multitaper_batch_mode": "valid_epoch_channel_batch" if method == "multitaper" else "not_applicable",
    }
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
                        "nfft_used": np.nan,
                        "frequency_resolution_hz": np.nan,
                        **method_metadata,
                    }
                )
                continue
            if method == "multitaper":
                power, freqs = multitaper_batch_results[(epoch_index, channel_index)]
                nperseg = np.nan
                noverlap = np.nan
                nfft_used = np.nan
            else:
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
                nfft_used = requested_nfft if requested_nfft is not None else nperseg
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
                        "nfft_used": nfft_used,
                        "frequency_resolution_hz": _frequency_step(freqs, sfreq, signal.size),
                        **method_metadata,
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
    metadata_columns = [
        column
        for column in (
            "psd_method",
            "frequency_resolution_hz",
            "nperseg_used",
            "noverlap_used",
            "nfft_used",
            "multitaper_bandwidth_hz",
            "multitaper_adaptive",
            "multitaper_low_bias",
            "multitaper_normalization",
            "multitaper_remove_dc",
            "multitaper_n_jobs",
            "multitaper_batch_input_shape",
            "multitaper_batch_call_count",
            "multitaper_batch_mode",
        )
        if column in valid.columns
    ]
    aggregation_spec: dict[str, tuple[str, str]] = {
        "psd_value": ("psd_value", aggregation),
        "psd_sd": ("psd_value", "std"),
        "n_epochs": ("epoch_index", "nunique"),
    }
    aggregation_spec.update({column: (column, "first") for column in metadata_columns})
    channel_summary = (
        valid.groupby(["channel_array_index", "channel_name", "frequency_hz"], as_index=False)
        .agg(**aggregation_spec)
    )
    if channel_table is None or channel_table.empty or "region" not in channel_table:
        region_summary = pd.DataFrame()
    else:
        region_map = channel_table[["channel_name", "region"]].copy()
        region_map["region"] = region_map["region"].fillna("").astype(str)
        region_summary = channel_summary.merge(region_map, on="channel_name", how="left")
        region_summary = region_summary.loc[region_summary["region"].str.strip() != ""]
        region_aggregation: dict[str, tuple[str, str]] = {
            "psd_value": ("psd_value", "mean"),
            "psd_sd_across_channels": ("psd_value", "std"),
            "n_channels": ("channel_name", "nunique"),
            "n_epoch_channel_estimates": ("n_epochs", "sum"),
        }
        region_aggregation.update({column: (column, "first") for column in metadata_columns if column in region_summary.columns})
        region_summary = region_summary.groupby(["region", "frequency_hz"], as_index=False).agg(**region_aggregation)
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
        frequency_step_hz = _frequency_step(frequencies, np.nan, len(frequencies))
        denominator_mask = _band_mask(frequencies, denominator[0], denominator[1], excluded)
        denominator_range = (frequencies >= float(denominator[0])) & (frequencies <= float(denominator[1]))
        excluded_mask = denominator_range & ~denominator_mask
        denominator_power, denominator_segments, denominator_max_gap = _integrate_contiguous_frequency_segments(
            frequencies, powers, denominator_mask, frequency_step_hz
        )
        for band_name, bounds in bands.items():
            mask = _band_mask(frequencies, bounds[0], bounds[1], excluded)
            absolute_power, band_segments, band_max_gap = _integrate_contiguous_frequency_segments(
                frequencies, powers, mask, frequency_step_hz
            )
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
                    "frequency_step_hz": frequency_step_hz,
                    "band_frequency_segments": int(band_segments),
                    "band_max_gap_hz": band_max_gap,
                    "denominator_frequency_segments": int(denominator_segments),
                    "denominator_max_gap_hz": denominator_max_gap,
                    "integration_rule": "trapezoid_on_contiguous_frequency_segments_no_cross_gap",
                    "status": "ok" if np.isfinite(absolute_power) else "insufficient_frequency_bins",
                }
            )
    return pd.DataFrame(rows)
