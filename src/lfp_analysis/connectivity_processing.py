"""Frequency-axis processing and audit helpers for connectivity results.

This module deliberately operates on the long connectivity tables after the
estimator has returned.  It does not replace non-finite values, join epochs,
or alter the raw connectivity values.  Display-only products are returned in
separate tables and are never used for band statistics.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d


def _float(value: Any, default: float = np.nan) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def resolve_line_noise_settings(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return one transparent line-noise policy with legacy compatibility.

    New configurations use ``connectivity.line_noise``.  Older configurations
    using ``exclude_line_noise_hz`` remain valid and take precedence when the
    new block is absent.  ``mask_width_hz`` is the full width of each excluded
    interval, so a 1 Hz setting means centre +/- 0.5 Hz.
    """
    conn = (config or {}).get("connectivity", {}) or {}
    nested = conn.get("line_noise")
    if isinstance(nested, dict):
        centre = _float(nested.get("frequency_hz", 50.0), 50.0)
        width = max(0.0, _float(nested.get("mask_width_hz", 1.0), 1.0))
        centres = [centre] if np.isfinite(centre) and centre > 0 else []
        if bool(nested.get("harmonics", False)) and centres:
            # Harmonics are generated later only when they are inside the
            # estimator frequency range; keeping the list explicit makes the
            # policy auditable and prevents a hidden 60 Hz default.
            fmax = _float(conn.get("fmax_hz", np.inf), np.inf)
            for multiplier in range(2, 100):
                harmonic = centre * multiplier
                if harmonic > fmax + width / 2:
                    break
                centres.append(harmonic)
        return {
            "centres_hz": centres,
            "mask_width_hz": width,
            "half_width_hz": width / 2.0,
            "mask_for_analysis": bool(nested.get("mask_for_analysis", True)),
            "mask_for_plot": bool(nested.get("mask_for_plot", True)),
            "mask_source": "connectivity.line_noise",
            "configuration_key": "connectivity.line_noise",
            "harmonics": bool(nested.get("harmonics", False)),
        }
    if "exclude_line_noise_hz" in conn:
        centres = [_float(value) for value in conn.get("exclude_line_noise_hz", [])]
        centres = [value for value in centres if np.isfinite(value) and value > 0]
        half_width = max(0.0, _float(conn.get("line_noise_half_width_hz", 0.5), 0.5))
        return {
            "centres_hz": centres,
            "mask_width_hz": 2.0 * half_width,
            "half_width_hz": half_width,
            "mask_for_analysis": True,
            "mask_for_plot": True,
            "mask_source": "legacy connectivity.exclude_line_noise_hz",
            "configuration_key": "connectivity.exclude_line_noise_hz",
            "harmonics": False,
        }
    return {
        "centres_hz": [50.0],
        "mask_width_hz": 1.0,
        "half_width_hz": 0.5,
        "mask_for_analysis": True,
        "mask_for_plot": True,
        "mask_source": "built-in default",
        "configuration_key": "connectivity.line_noise",
        "harmonics": False,
    }


def frequency_mask(frequencies: Any, config: dict[str, Any] | None = None, *, purpose: str = "analysis") -> np.ndarray:
    """Return a boolean mask without changing the frequency or value arrays."""
    values = np.asarray(frequencies, dtype=float)
    settings = resolve_line_noise_settings(config)
    enabled = settings["mask_for_analysis"] if purpose == "analysis" else settings["mask_for_plot"]
    mask = np.zeros(values.shape, dtype=bool)
    if not enabled:
        return mask
    for centre in settings["centres_hz"]:
        mask |= np.isfinite(values) & (np.abs(values - centre) <= settings["half_width_hz"] + 1.0e-12)
    return mask


def validate_frequency_axis(frequencies: Any, expected: Any | None = None, *, tolerance_hz: float = 1.0e-9) -> dict[str, Any]:
    """Validate and describe a finite, strictly increasing frequency grid."""
    values = np.asarray(frequencies, dtype=float)
    if values.ndim != 1 or values.size == 0:
        raise ValueError(f"Connectivity frequency axis must be a non-empty 1-D array; got {values.shape}")
    if not np.all(np.isfinite(values)):
        raise ValueError("Connectivity frequency axis contains NaN or Inf")
    differences = np.diff(values)
    if np.any(differences <= 0):
        raise ValueError("Connectivity frequency axis must be strictly increasing with no duplicate bins")
    result: dict[str, Any] = {
        "n_frequencies": int(values.size),
        "frequency_min_hz": float(values[0]),
        "frequency_max_hz": float(values[-1]),
        "frequency_step_hz": float(np.median(differences)) if differences.size else np.nan,
        "frequency_step_min_hz": float(np.min(differences)) if differences.size else np.nan,
        "frequency_step_max_hz": float(np.max(differences)) if differences.size else np.nan,
        "is_uniform": bool(np.allclose(differences, np.median(differences), rtol=0.0, atol=tolerance_hz)),
    }
    if expected is not None:
        expected_values = np.asarray(expected, dtype=float)
        if expected_values.shape != values.shape or not np.allclose(values, expected_values, rtol=0.0, atol=tolerance_hz):
            raise ValueError("Connectivity frequency axes do not align within the configured tolerance")
    return result


def frequency_alignment_index(source: Any, target: Any, *, tolerance_hz: float = 1.0e-6) -> np.ndarray:
    """Map target frequencies to source bins using an explicit tolerance."""
    source_values = np.asarray(source, dtype=float)
    target_values = np.asarray(target, dtype=float)
    validate_frequency_axis(source_values)
    validate_frequency_axis(target_values)
    indices = np.searchsorted(source_values, target_values)
    indices = np.clip(indices, 0, len(source_values) - 1)
    left = np.maximum(indices - 1, 0)
    choose_left = np.abs(source_values[left] - target_values) < np.abs(source_values[indices] - target_values)
    result = np.where(choose_left, left, indices)
    if np.any(np.abs(source_values[result] - target_values) > tolerance_hz):
        raise ValueError("Frequency axes cannot be aligned within tolerance")
    return result.astype(int)


def _value_column(frame: pd.DataFrame) -> str:
    return "value_strength" if "value_strength" in frame.columns else "value_raw"


def diagnose_frequency_table(spectrum: pd.DataFrame, config: dict[str, Any] | None = None, *, processing_stage: str = "post_estimation") -> pd.DataFrame:
    """Create one audit row per method/frequency for the saved raw spectrum."""
    columns = [
        "method", "frequency_hz", "plot_frequency_index", "n_total_values", "n_finite", "n_nan", "n_inf",
        "is_masked", "mask_reason", "processing_stage", "mask_source", "configuration_key",
    ]
    if not isinstance(spectrum, pd.DataFrame) or spectrum.empty or "frequency_hz" not in spectrum:
        return pd.DataFrame(columns=columns)
    settings = resolve_line_noise_settings(config)
    working = spectrum.copy()
    working["_frequency"] = pd.to_numeric(working["frequency_hz"], errors="coerce")
    value_column = _value_column(working)
    working["_value"] = pd.to_numeric(working.get(value_column, np.nan), errors="coerce")
    if "frequency_is_masked_for_plot" in working or "frequency_is_masked_for_analysis" in working:
        plot_mask = working.get("frequency_is_masked_for_plot", pd.Series(False, index=working.index)).astype("boolean").fillna(False).astype(bool)
        analysis_mask = working.get("frequency_is_masked_for_analysis", pd.Series(False, index=working.index)).astype("boolean").fillna(False).astype(bool)
        masked = plot_mask | analysis_mask
    elif "frequency_is_excluded_line_noise" in working:
        masked = working["frequency_is_excluded_line_noise"].astype("boolean").fillna(False).astype(bool)
    else:
        masked = pd.Series(frequency_mask(working["_frequency"].to_numpy(float), config, purpose="plot"), index=working.index)
    working["_masked"] = masked
    frequency_index: dict[tuple[str, float], int] = {}
    for method, group in working.groupby("method", dropna=False, sort=True):
        ordered = np.sort(group["_frequency"].dropna().unique())
        frequency_index.update({(str(method), float(value)): index for index, value in enumerate(ordered)})
    rows: list[dict[str, Any]] = []
    group_columns = ["method", "_frequency"]
    for (method, frequency), group in working.groupby(group_columns, dropna=False, sort=True):
        values = group["_value"].to_numpy(float)
        if "value_nonfinite_type" in group:
            nonfinite_type = group["value_nonfinite_type"].astype(str).str.lower()
            n_inf = int(nonfinite_type.eq("inf").sum())
            n_nan = int(nonfinite_type.eq("nan").sum())
        else:
            n_nan = int(np.isnan(values).sum())
            n_inf = int(np.isinf(values).sum())
        is_masked = bool(group["_masked"].any())
        if n_nan or n_inf:
            stage = "post_estimation_row_materialization"
            reason = "estimator output or row materialization is non-finite"
        elif is_masked:
            stage = "post_estimation_line_noise_annotation"
            reason = "configured line-noise interval; raw value retained"
        else:
            stage = processing_stage
            reason = ""
        rows.append({
            "method": str(method),
            "frequency_hz": float(frequency) if np.isfinite(frequency) else np.nan,
            "plot_frequency_index": frequency_index.get((str(method), float(frequency)), np.nan) if np.isfinite(frequency) else np.nan,
            "n_total_values": len(values),
            "n_finite": int(np.isfinite(values).sum()),
            "n_nan": n_nan,
            "n_inf": n_inf,
            "is_masked": is_masked,
            "mask_reason": reason,
            "processing_stage": stage,
            "mask_source": settings["mask_source"] if is_masked else "",
            "configuration_key": settings["configuration_key"] if is_masked else "",
        })
    return pd.DataFrame(rows, columns=columns)


def _segments(frequencies: np.ndarray, valid: np.ndarray) -> list[np.ndarray]:
    indices = np.flatnonzero(valid)
    if len(indices) == 0:
        return []
    if len(indices) == 1:
        return [indices]
    steps = np.diff(frequencies)
    nominal = float(np.median(steps)) if steps.size else np.inf
    breaks = np.flatnonzero(np.diff(indices) > 1)
    if np.isfinite(nominal) and nominal > 0:
        breaks = np.unique(np.r_[breaks, np.flatnonzero(np.diff(frequencies[indices]) > nominal * 1.5)])
    return [part for part in np.split(indices, breaks + 1) if len(part)]


def quantify_roughness(spectrum: pd.DataFrame) -> pd.DataFrame:
    """Quantify jaggedness on raw, unmasked values without smoothing them."""
    columns = [
        "method", "region_a", "region_b", "component_index", "n_frequencies",
        "n_valid_points", "median_abs_adjacent_diff", "total_variation",
        "coefficient_of_variation", "resampling_variability", "status",
    ]
    if not isinstance(spectrum, pd.DataFrame) or spectrum.empty:
        return pd.DataFrame(columns=columns)
    value_column = _value_column(spectrum)
    group_columns = [column for column in ("method", "region_a", "region_b", "component_index") if column in spectrum.columns]
    rows: list[dict[str, Any]] = []
    for keys, group in spectrum.groupby(group_columns, dropna=False, sort=False):
        key_values = (keys,) if not isinstance(keys, tuple) else keys
        values = group.sort_values("frequency_hz")
        frequencies = pd.to_numeric(values["frequency_hz"], errors="coerce").to_numpy(float)
        signal = pd.to_numeric(values[value_column], errors="coerce").to_numpy(float)
        mask = values.get("frequency_is_masked_for_plot", values.get("frequency_is_excluded_line_noise", pd.Series(False, index=values.index))).fillna(False).to_numpy(bool)
        valid = np.isfinite(frequencies) & np.isfinite(signal) & ~mask
        differences: list[np.ndarray] = []
        even_differences: list[np.ndarray] = []
        odd_differences: list[np.ndarray] = []
        for segment in _segments(frequencies, valid):
            segment_values = signal[segment]
            if len(segment_values) > 1:
                differences.append(np.abs(np.diff(segment_values)))
            if len(segment_values) > 3:
                even_differences.append(np.abs(np.diff(segment_values[::2])))
                odd_differences.append(np.abs(np.diff(segment_values[1::2])))
        adjacent = np.concatenate(differences) if differences else np.asarray([], dtype=float)
        valid_values = signal[valid]
        mean_abs = float(np.mean(np.abs(valid_values))) if len(valid_values) else np.nan
        cv = float(np.std(valid_values) / mean_abs) if len(valid_values) and mean_abs > 0 else np.nan
        even = np.concatenate(even_differences) if even_differences else np.asarray([], dtype=float)
        odd = np.concatenate(odd_differences) if odd_differences else np.asarray([], dtype=float)
        reference = float(np.median(adjacent)) if len(adjacent) else np.nan
        resampling = float(abs(np.median(even) - np.median(odd)) / max(abs(reference), 1.0e-30)) if len(even) and len(odd) and np.isfinite(reference) else np.nan
        row = dict(zip(group_columns, key_values, strict=True))
        row.update({
            "n_frequencies": len(frequencies),
            "n_valid_points": int(valid.sum()),
            "median_abs_adjacent_diff": float(np.median(adjacent)) if len(adjacent) else np.nan,
            "total_variation": float(np.sum(adjacent)) if len(adjacent) else np.nan,
            "coefficient_of_variation": cv,
            "resampling_variability": resampling,
            "status": "ok" if len(valid_values) > 1 else "insufficient_valid_points",
        })
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def quantify_band_cv(spectrum: pd.DataFrame, config: dict[str, Any] | None = None) -> pd.DataFrame:
    """Report within-band coefficient of variation on raw unmasked values."""
    columns = ["method", "region_a", "region_b", "component_index", "band", "band_low_hz", "band_high_hz", "n_valid_points", "band_cv", "status"]
    if not isinstance(spectrum, pd.DataFrame) or spectrum.empty:
        return pd.DataFrame(columns=columns)
    bands = ((config or {}).get("bands", {}) or {})
    if not bands:
        return pd.DataFrame(columns=columns)
    value_column = _value_column(spectrum)
    group_columns = [column for column in ("method", "region_a", "region_b", "component_index") if column in spectrum.columns]
    rows: list[dict[str, Any]] = []
    for keys, group in spectrum.groupby(group_columns, dropna=False, sort=False):
        key_values = (keys,) if not isinstance(keys, tuple) else keys
        frequencies = pd.to_numeric(group["frequency_hz"], errors="coerce")
        values = pd.to_numeric(group[value_column], errors="coerce")
        if "frequency_is_masked_for_plot" in group:
            masked = group["frequency_is_masked_for_plot"].astype("boolean").fillna(False)
        else:
            masked = group.get("frequency_is_excluded_line_noise", pd.Series(False, index=group.index)).astype("boolean").fillna(False)
        for band, bounds in bands.items():
            selected = (frequencies >= float(bounds[0])) & (frequencies <= float(bounds[1])) & ~masked
            finite = values.loc[selected].to_numpy(float)
            finite = finite[np.isfinite(finite)]
            mean_abs = float(np.mean(np.abs(finite))) if len(finite) else np.nan
            cv = float(np.std(finite) / mean_abs) if len(finite) and mean_abs > 0 else np.nan
            row = dict(zip(group_columns, key_values, strict=True))
            row.update({"band": str(band), "band_low_hz": float(bounds[0]), "band_high_hz": float(bounds[1]), "n_valid_points": len(finite), "band_cv": cv, "status": "ok" if len(finite) >= 2 else "insufficient_valid_points"})
            rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def bin_spectrum(spectrum: pd.DataFrame, config: dict[str, Any] | None = None) -> pd.DataFrame:
    """Optionally bin frequencies, refusing to cross masked or invalid bins."""
    conn = (config or {}).get("connectivity", {}) or {}
    settings = conn.get("frequency_binning", {}) or {}
    if not bool(settings.get("enabled", False)):
        return pd.DataFrame()
    width = _float(settings.get("width_hz", 1.0), 1.0)
    if not np.isfinite(width) or width <= 0 or not isinstance(spectrum, pd.DataFrame) or spectrum.empty:
        return pd.DataFrame()
    value_column = _value_column(spectrum)
    group_columns = [column for column in ("method", "region_a", "region_b", "component_index", "aggregation_level", "seed_channel", "target_channel") if column in spectrum.columns]
    rows: list[dict[str, Any]] = []
    for keys, group in spectrum.groupby(group_columns, dropna=False, sort=False):
        key_values = (keys,) if not isinstance(keys, tuple) else keys
        work = group.copy()
        work["_frequency"] = pd.to_numeric(work["frequency_hz"], errors="coerce")
        work["_value"] = pd.to_numeric(work[value_column], errors="coerce")
        if "frequency_is_masked_for_analysis" in work:
            work["_masked"] = work["frequency_is_masked_for_analysis"].astype("boolean").fillna(False).astype(bool)
        elif "frequency_is_excluded_line_noise" in work and work["frequency_is_excluded_line_noise"].astype("boolean").fillna(False).any():
            work["_masked"] = work["frequency_is_excluded_line_noise"].astype("boolean").fillna(False).astype(bool)
        else:
            work["_masked"] = frequency_mask(work["_frequency"].to_numpy(float), config, purpose="analysis")
        work["_bin"] = np.floor(work["_frequency"] / width).astype("Int64")
        for bin_index, bin_group in work.groupby("_bin", dropna=False, sort=True):
            if pd.isna(bin_index):
                continue
            has_mask = bool(bin_group["_masked"].any())
            finite = np.isfinite(bin_group["_value"].to_numpy(float))
            status = "masked_frequency_bin" if has_mask else ("nonfinite_frequency_bin" if not np.all(finite) else "ok")
            usable = bin_group.loc[~bin_group["_masked"] & np.isfinite(bin_group["_value"]), "_value"]
            statistic = str(settings.get("statistic", "median")).lower()
            value = float(usable.mean() if statistic == "mean" else usable.median()) if status == "ok" and not usable.empty else np.nan
            row = dict(zip(group_columns, key_values, strict=True))
            low = float(bin_index) * width
            row.update({"bin_low_hz": low, "bin_high_hz": low + width, "frequency_hz": low + width / 2.0, "value_raw_or_summary": value, "value_strength": value, "n_frequency_points": len(bin_group), "status": status, "display_only": False, "binning_statistic": statistic, "binning_note": "masked bins are not bridged or replaced"})
            rows.append(row)
    return pd.DataFrame(rows)


def smooth_for_display(spectrum: pd.DataFrame, config: dict[str, Any] | None = None, *, enabled: bool | None = None) -> pd.DataFrame:
    """Return a separate display-only table smoothed within valid segments."""
    vis = ((config or {}).get("visualization", {}) or {}).get("connectivity", {}) or {}
    smoothing = vis.get("display_smoothing", {}) or {}
    is_enabled = bool(smoothing.get("enabled", False)) if enabled is None else bool(enabled)
    if not is_enabled or not isinstance(spectrum, pd.DataFrame) or spectrum.empty:
        return pd.DataFrame()
    sigma_hz = max(0.0, _float(smoothing.get("sigma_hz", 0.5), 0.5))
    value_column = _value_column(spectrum)
    group_columns = [column for column in ("method", "region_a", "region_b", "component_index", "aggregation_level", "seed_channel", "target_channel") if column in spectrum.columns]
    output = spectrum.copy()
    output["display_value_smoothed"] = np.nan
    output["display_only"] = True
    for _, group in output.groupby(group_columns, dropna=False, sort=False):
        indices = group.sort_values("frequency_hz").index.to_numpy()
        frequencies = pd.to_numeric(output.loc[indices, "frequency_hz"], errors="coerce").to_numpy(float)
        raw = pd.to_numeric(output.loc[indices, value_column], errors="coerce").to_numpy(float)
        if "frequency_is_masked_for_plot" in output:
            mask = output.loc[indices, "frequency_is_masked_for_plot"].astype("boolean").fillna(False).to_numpy(bool)
        elif "frequency_is_excluded_line_noise" in output and output["frequency_is_excluded_line_noise"].astype("boolean").fillna(False).any():
            mask = output.loc[indices, "frequency_is_excluded_line_noise"].astype("boolean").fillna(False).to_numpy(bool)
        else:
            mask = frequency_mask(frequencies, config, purpose="plot")
        valid = np.isfinite(frequencies) & np.isfinite(raw) & ~mask
        step = float(np.median(np.diff(frequencies))) if len(frequencies) > 1 else np.nan
        sigma_bins = sigma_hz / step if np.isfinite(step) and step > 0 else 0.0
        smoothed = np.full(raw.shape, np.nan, dtype=float)
        for segment in _segments(frequencies, valid):
            segment_values = raw[segment]
            smoothed[segment] = gaussian_filter1d(segment_values, sigma=sigma_bins, mode="nearest") if sigma_bins > 0 else segment_values
        output.loc[indices, "display_value_smoothed"] = smoothed
    return output


def estimate_multitaper_metadata(n_times: int, sfreq: float, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Record the actual DPSS taper count when the installed MNE exposes it."""
    conn = (config or {}).get("connectivity", {}) or {}
    if str(conn.get("mode", "multitaper")).lower() != "multitaper":
        return {"n_tapers": np.nan, "time_bandwidth_product": np.nan, "n_tapers_note": "not applicable; mode is not multitaper"}
    bandwidth = _float(conn.get("mt_bandwidth_hz", 4.0), 4.0)
    try:
        from mne.time_frequency.multitaper import _compute_mt_params

        tapers, _, _ = _compute_mt_params(int(n_times), float(sfreq), bandwidth, bool(conn.get("mt_low_bias", True)), bool(conn.get("mt_adaptive", False)))
        return {"n_tapers": len(tapers), "time_bandwidth_product": float(bandwidth * n_times / (2.0 * sfreq)), "n_tapers_note": "computed from the installed MNE DPSS parameter helper"}
    except Exception as exc:  # noqa: BLE001 - metadata must not block analysis
        return {"n_tapers": np.nan, "time_bandwidth_product": float(bandwidth * n_times / (2.0 * sfreq)), "n_tapers_note": f"unavailable from installed MNE helper: {type(exc).__name__}: {exc}"}
