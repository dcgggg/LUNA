from __future__ import annotations

from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd

REGION_ORDER = ("M1", "STR", "PF", "SNr")
MULTIVARIATE_METHODS = ("mic", "mim")
BIVARIATE_METHODS = ("wpli2_debiased", "imcoh", "coh")
FAILURE_COLUMNS = ["region_a", "region_b", "method", "failure_reason", "n_epochs", "rank_seed", "rank_target"]


def _region_sort_key(region: str) -> tuple[int, str]:
    try:
        return REGION_ORDER.index(region), region
    except ValueError:
        return len(REGION_ORDER), region


def _as_float(value: Any, default: float = np.nan) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def _finite_epoch_mask(data: np.ndarray, quality_epoch: pd.DataFrame) -> tuple[np.ndarray, int]:
    quality_status = quality_epoch.get("quality_status", pd.Series("pass", index=range(len(data))))
    quality_valid = quality_status.astype(str).ne("fail").to_numpy()
    finite_valid = np.all(np.isfinite(data), axis=(1, 2))
    return quality_valid & finite_valid, int(np.sum(~finite_valid))


def _channel_groups(channel_table: pd.DataFrame) -> dict[str, pd.DataFrame]:
    mapped = channel_table.copy()
    mapped["region"] = mapped["region"].fillna("").astype(str).str.strip()
    mapped = mapped.loc[mapped["region"].ne("")].copy()
    groups: dict[str, pd.DataFrame] = {}
    for region in sorted(mapped["region"].unique(), key=_region_sort_key):
        groups[region] = mapped.loc[mapped["region"] == region].sort_values("array_index").reset_index(drop=True)
    return groups


def region_channel_pairs(channel_table: pd.DataFrame) -> pd.DataFrame:
    """Return all cross-region channel pairs using the confirmed mapping table."""
    groups = _channel_groups(channel_table)
    pairs: list[dict[str, Any]] = []
    for region_a, region_b in combinations(groups, 2):
        for _, row_a in groups[region_a].iterrows():
            for _, row_b in groups[region_b].iterrows():
                pairs.append(
                    {
                        "region_a": region_a,
                        "region_b": region_b,
                        "seed_array_index": int(row_a["array_index"]),
                        "target_array_index": int(row_b["array_index"]),
                        "seed_channel": row_a["channel_name"],
                        "target_channel": row_b["channel_name"],
                    }
                )
    return pd.DataFrame(pairs)


def selected_region_pairs(region_names: list[str] | tuple[str, ...], config: dict[str, Any]) -> list[tuple[str, str]]:
    """Return configured region pairs while preserving the canonical order."""
    configured = config.get("connectivity", {}).get("selected_region_pairs")
    all_pairs = list(combinations(region_names, 2))
    if not configured:
        return all_pairs
    allowed: set[frozenset[str]] = set()
    for item in configured:
        if isinstance(item, str):
            parts = [part.strip() for part in item.replace("–", "-").split("-") if part.strip()]
        else:
            parts = [str(part).strip() for part in item]
        if len(parts) == 2:
            allowed.add(frozenset(parts))
    return [(region_a, region_b) for region_a, region_b in all_pairs if frozenset((region_a, region_b)) in allowed]


def assess_region_redundancy(
    data: np.ndarray,
    sfreq: float,
    channel_table: pd.DataFrame,
    valid_epoch: np.ndarray,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Profile within-region redundancy and choose a reproducible rank.

    The default rule is independent of connectivity effect size: retain the first
    number of singular dimensions reaching the configured variance threshold,
    bounded by a numerical-rank test based on a relative singular-value cutoff.
    """
    conn_cfg = config.get("connectivity", {})
    tolerance = float(conn_cfg.get("rank_relative_tolerance", 1.0e-6))
    variance_threshold = float(conn_cfg.get("rank_variance_threshold", 0.99))
    fixed_rank = conn_cfg.get("fixed_rank_by_region", {}) or {}
    groups = _channel_groups(channel_table)
    corr_rows: list[dict[str, Any]] = []
    singular_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    rank_map: dict[str, int] = {}
    region_indices: dict[str, np.ndarray] = {}
    duration = float(np.sum(valid_epoch) * data.shape[-1] / sfreq)

    for region, group in groups.items():
        indices = group["array_index"].to_numpy(dtype=int)
        region_indices[region] = indices
        values = np.asarray(data[valid_epoch][:, indices, :], dtype=float).transpose(1, 0, 2).reshape(len(indices), -1)
        finite_columns = np.all(np.isfinite(values), axis=0)
        values = values[:, finite_columns]
        values = values - np.mean(values, axis=1, keepdims=True)
        with np.errstate(invalid="ignore", divide="ignore"):
            correlation = np.corrcoef(values)
        if len(indices) == 1:
            correlation = np.ones((1, 1), dtype=float)
        singular_values = np.linalg.svd(values, compute_uv=False) if values.size else np.zeros(0, dtype=float)
        if singular_values.size and singular_values[0] > 0:
            relative_rank = int(np.sum(singular_values > singular_values[0] * tolerance))
            variance_fraction = singular_values**2 / np.sum(singular_values**2)
        else:
            relative_rank = 0
            variance_fraction = np.zeros_like(singular_values)
        cumulative = np.cumsum(variance_fraction)
        variance_rank = int(np.searchsorted(cumulative, variance_threshold) + 1) if cumulative.size else 0
        numerical_rank = max(1, min(len(indices), relative_rank)) if len(indices) else 0
        variance_rank = max(1, min(len(indices), variance_rank)) if len(indices) else 0
        configured_rank = fixed_rank.get(region)
        if configured_rank not in (None, "", "nan"):
            selected_rank = max(1, min(len(indices), int(configured_rank)))
            rank_reason = "fixed_rank_by_region"
        else:
            selected_rank = max(1, min(numerical_rank, variance_rank)) if len(indices) else 0
            rank_reason = "min(numerical_rank, components_reaching_variance_threshold)"
        rank_map[region] = selected_rank
        covariance = np.cov(values) if values.shape[1] > 1 else np.zeros((len(indices), len(indices)))
        covariance_condition = _as_float(np.linalg.cond(covariance)) if covariance.size else np.nan
        summary_rows.append(
            {
                "region": region,
                "channel_names": "|".join(group["channel_name"].astype(str)),
                "channel_array_indices": "|".join(group["array_index"].astype(str)),
                "n_channels": len(indices),
                "n_valid_epochs": int(np.sum(valid_epoch)),
                "effective_valid_duration_s": duration,
                "n_finite_samples": int(values.shape[1]),
                "numerical_rank": numerical_rank,
                "variance_rank": variance_rank,
                "selected_rank": selected_rank,
                "rank_reason": rank_reason,
                "rank_relative_tolerance": tolerance,
                "rank_variance_threshold": variance_threshold,
                "covariance_condition_number": covariance_condition,
                "all_channels_finite": bool(np.all(np.isfinite(values))),
            }
        )
        for channel_i, name_i in enumerate(group["channel_name"]):
            for channel_j, name_j in enumerate(group["channel_name"]):
                corr_rows.append(
                    {
                        "region": region,
                        "channel_i": name_i,
                        "channel_j": name_j,
                        "array_index_i": int(group.iloc[channel_i]["array_index"]),
                        "array_index_j": int(group.iloc[channel_j]["array_index"]),
                        "correlation": float(correlation[channel_i, channel_j]) if np.isfinite(correlation[channel_i, channel_j]) else np.nan,
                        "n_valid_epochs": int(np.sum(valid_epoch)),
                        "effective_valid_duration_s": duration,
                    }
                )
        for component, (singular, fraction, cumulative_fraction) in enumerate(zip(singular_values, variance_fraction, cumulative), start=1):
            singular_rows.append(
                {
                    "region": region,
                    "component": component,
                    "singular_value": float(singular),
                    "variance_fraction": float(fraction),
                    "cumulative_variance_fraction": float(cumulative_fraction),
                    "numerical_rank": numerical_rank,
                    "variance_rank": variance_rank,
                    "selected_rank": selected_rank,
                    "rank_reason": rank_reason,
                }
            )
    return {
        "correlation": pd.DataFrame(corr_rows),
        "singular_values": pd.DataFrame(singular_rows),
        "summary": pd.DataFrame(summary_rows),
        "rank_map": rank_map,
        "region_indices": region_indices,
        "groups": groups,
    }


def _connectivity_kwargs(sfreq: float, config: dict[str, Any]) -> dict[str, Any]:
    conn_cfg = config.get("connectivity", {})
    kwargs: dict[str, Any] = {
        "sfreq": float(sfreq),
        "mode": str(conn_cfg.get("mode", "multitaper")),
        "fmin": float(conn_cfg.get("fmin_hz", 2.0)),
        "fmax": float(conn_cfg.get("fmax_hz", 100.0)),
        "fdecim": int(conn_cfg.get("fdecim", 1)),
        "faverage": False,
        "verbose": False,
    }
    if kwargs["mode"] == "multitaper":
        kwargs.update(
            {
                "mt_bandwidth": float(conn_cfg.get("mt_bandwidth_hz", 4.0)),
                "mt_adaptive": bool(conn_cfg.get("mt_adaptive", False)),
                "mt_low_bias": bool(conn_cfg.get("mt_low_bias", True)),
            }
        )
    return kwargs


def _load_connectivity_api() -> Any:
    try:
        from mne_connectivity import spectral_connectivity_epochs
    except ImportError as exc:
        raise ImportError(f"Install mne-connectivity for connectivity analysis: {exc}") from exc
    return spectral_connectivity_epochs


def _estimate_multivariate(
    data: np.ndarray,
    sfreq: float,
    seed_indices: np.ndarray,
    target_indices: np.ndarray,
    rank_seed: int,
    rank_target: int,
    config: dict[str, Any],
) -> list[Any]:
    estimator = _load_connectivity_api()
    return _as_list(
        estimator(
            data,
            method=list(MULTIVARIATE_METHODS),
            indices=(np.asarray([seed_indices], dtype=int), np.asarray([target_indices], dtype=int)),
            rank=(np.asarray([rank_seed], dtype=int), np.asarray([rank_target], dtype=int)),
            **_connectivity_kwargs(sfreq, config),
        )
    )


def _estimate_bivariate(
    data: np.ndarray,
    sfreq: float,
    seed_indices: np.ndarray,
    target_indices: np.ndarray,
    methods: list[str],
    config: dict[str, Any],
) -> list[Any]:
    if not methods:
        return []
    estimator = _load_connectivity_api()
    pair_seed = np.repeat(seed_indices, len(target_indices)).astype(int)
    pair_target = np.tile(target_indices, len(seed_indices)).astype(int)
    return _as_list(
        estimator(
            data,
            method=methods if len(methods) > 1 else methods[0],
            indices=(pair_seed, pair_target),
            rank=None,
            **_connectivity_kwargs(sfreq, config),
        )
    )


def _connection_values(connection: Any) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(connection.get_data(), dtype=float)
    if values.ndim == 1:
        values = values[None, :]
    while values.ndim > 2:
        values = values[..., 0]
    frequencies = np.asarray(connection.freqs, dtype=float)
    return values, frequencies


def _line_noise_mask(frequencies: np.ndarray, config: dict[str, Any]) -> np.ndarray:
    conn_cfg = config.get("connectivity", {})
    lines = [float(value) for value in conn_cfg.get("exclude_line_noise_hz", [])]
    half_width = float(conn_cfg.get("line_noise_half_width_hz", 0.5))
    mask = np.zeros(frequencies.shape, dtype=bool)
    for line in lines:
        mask |= np.abs(frequencies - line) <= half_width
    return mask


def _method_display_definition(method: str) -> tuple[str, str]:
    if method == "mic":
        return "abs(value_raw)", "MIC raw sign retained; strength is absolute value"
    if method == "mim":
        return "value_raw", "MIM raw unnormalised value; values >1 are retained"
    if method == "wpli2_debiased":
        return "value_raw", "wpli2_debiased raw value; negative finite estimates retained"
    return "value_raw", "raw auxiliary bivariate estimate"


def _base_row(
    region_a: str,
    region_b: str,
    seed_group: pd.DataFrame,
    target_group: pd.DataFrame,
    method: str,
    frequency: float,
    value: float,
    n_epochs: int,
    effective_duration: float,
    rank_seed: int,
    rank_target: int,
    spectral_meta: dict[str, Any],
    aggregation_level: str,
    seed_channel: str = "",
    target_channel: str = "",
) -> dict[str, Any]:
    definition, note = _method_display_definition(method)
    return {
        "region_a": region_a,
        "region_b": region_b,
        "method": method,
        "aggregation_level": aggregation_level,
        "seed_channel": seed_channel,
        "target_channel": target_channel,
        "seed_channels": "|".join(seed_group["channel_name"].astype(str)),
        "target_channels": "|".join(target_group["channel_name"].astype(str)),
        "n_seed_channels": len(seed_group),
        "n_target_channels": len(target_group),
        "rank_seed": rank_seed,
        "rank_target": rank_target,
        "frequency_hz": float(frequency),
        "value_raw": float(value) if np.isfinite(value) else np.nan,
        "value_strength": abs(float(value)) if method == "mic" and np.isfinite(value) else (float(value) if np.isfinite(value) else np.nan),
        "display_value_definition": definition,
        "estimate_note": note,
        "n_epochs": n_epochs,
        "effective_duration_s": effective_duration,
        "frequency_is_excluded_line_noise": False,
        **spectral_meta,
    }


def _spectral_meta(connection: Any, config: dict[str, Any]) -> dict[str, Any]:
    attrs = getattr(connection, "attrs", {}) or {}
    conn_cfg = config.get("connectivity", {})
    rank = attrs.get("rank")
    frequencies = np.asarray(connection.freqs, dtype=float)
    return {
        "spectral_mode": str(conn_cfg.get("mode", "multitaper")),
        "mt_bandwidth_hz": _as_float(conn_cfg.get("mt_bandwidth_hz")),
        "mt_adaptive": bool(conn_cfg.get("mt_adaptive", False)),
        "mt_low_bias": bool(conn_cfg.get("mt_low_bias", True)),
        "n_tapers": _as_float(attrs.get("n_tapers")),
        "estimated_rank_metadata": str(rank),
        "frequency_grid_hz": float(np.median(np.diff(frequencies))) if len(frequencies) > 1 else np.nan,
    }


def _pattern_rows(connection: Any, region_a: str, region_b: str, seed_group: pd.DataFrame, target_group: pd.DataFrame) -> list[dict[str, Any]]:
    patterns = getattr(connection, "attrs", {}).get("patterns")
    if patterns is None:
        return []
    array = np.asarray(patterns, dtype=float)
    if array.ndim != 4:
        return []
    rows: list[dict[str, Any]] = []
    for side, group in enumerate((seed_group, target_group)):
        if side >= array.shape[0]:
            continue
        side_array = array[side]
        if side_array.ndim == 3:
            side_array = side_array[0]
        for channel_index, channel_name in enumerate(group["channel_name"]):
            if channel_index >= side_array.shape[0]:
                continue
            for frequency_index, value in enumerate(side_array[channel_index]):
                rows.append(
                    {
                        "region_a": region_a,
                        "region_b": region_b,
                        "method": "mic",
                        "pattern_role": "seed" if side == 0 else "target",
                        "channel_name": channel_name,
                        "array_index": int(group.iloc[channel_index]["array_index"]),
                        "frequency_hz": float(connection.freqs[frequency_index]),
                        "pattern_value": float(value),
                        "pattern_note": "official MIC spatial pattern; not a direct biological contribution weight",
                    }
                )
    return rows


def _summarize_region_spectrum(spectrum: pd.DataFrame) -> pd.DataFrame:
    if spectrum.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for keys, group in spectrum.groupby(["method", "region_a", "region_b", "frequency_hz"], dropna=False):
        method, region_a, region_b, frequency = keys
        if group["aggregation_level"].iloc[0] == "multivariate_region_pair":
            value = float(group["value_raw"].iloc[0])
            strength = abs(value) if method == "mic" else value
            n_pairs = np.nan
            n_negative = int(np.sum(group["value_raw"] < 0))
        else:
            value = float(group["value_raw"].median())
            strength = value
            n_pairs = int(group["value_raw"].notna().sum())
            n_negative = int(np.sum(group["value_raw"] < 0))
        first = group.iloc[0]
        rows.append(
            {
                "method": method,
                "region_a": region_a,
                "region_b": region_b,
                "frequency_hz": float(frequency),
                "value_raw": value,
                "value_strength": strength,
                "n_channel_pairs": n_pairs,
                "n_negative_estimates": n_negative,
                "aggregation_definition": "multivariate result" if group["aggregation_level"].iloc[0] == "multivariate_region_pair" else "median across valid cross-region channel pairs",
                "n_epochs": first["n_epochs"],
                "effective_duration_s": first["effective_duration_s"],
                "rank_seed": first["rank_seed"],
                "rank_target": first["rank_target"],
                "frequency_is_excluded_line_noise": first["frequency_is_excluded_line_noise"],
                "spectral_mode": first["spectral_mode"],
                "mt_bandwidth_hz": first["mt_bandwidth_hz"],
                "n_tapers": first["n_tapers"],
            }
        )
    return pd.DataFrame(rows)


def _band_summary(spectrum: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    if spectrum.empty:
        return pd.DataFrame()
    bands = config.get("bands", {})
    rows: list[dict[str, Any]] = []
    for (method, region_a, region_b), group in spectrum.groupby(["method", "region_a", "region_b"], dropna=False):
        for band, bounds in bands.items():
            in_band = group.loc[(group["frequency_hz"] >= float(bounds[0])) & (group["frequency_hz"] <= float(bounds[1]))].copy()
            used = in_band.loc[~in_band["frequency_is_excluded_line_noise"]].copy()
            if used.empty:
                rows.append({"method": method, "region_a": region_a, "region_b": region_b, "band": band, "band_low_hz": bounds[0], "band_high_hz": bounds[1], "status": "no_frequency_bins_in_range"})
                continue
            if method == "wpli2_debiased":
                per_pair = used.groupby(["seed_channel", "target_channel"], dropna=False)["value_raw"].mean()
                value = float(per_pair.median())
                definition = "mean_across_frequency_then_median_across_channel_pairs"
                n_pairs = int(per_pair.size)
            elif method == "mic":
                value = float(np.mean(np.abs(used["value_raw"])))
                definition = "mean_absolute_MIC_across_frequency"
                n_pairs = np.nan
            else:
                value = float(np.mean(used["value_raw"]))
                definition = "mean_raw_value_across_frequency"
                n_pairs = np.nan
            first = used.iloc[0]
            rows.append(
                {
                    "method": method,
                    "region_a": region_a,
                    "region_b": region_b,
                    "band": band,
                    "band_low_hz": float(bounds[0]),
                    "band_high_hz": float(bounds[1]),
                    "value_raw_or_summary": value,
                    "value_strength": value,
                    "aggregation_definition": definition,
                    "n_channel_pairs": n_pairs,
                    "n_frequencies_used": int(used["frequency_hz"].nunique()),
                    "n_frequencies_excluded_line_noise": int(in_band["frequency_is_excluded_line_noise"].sum()),
                    "frequency_coverage_fraction": float(used["frequency_hz"].nunique() / max(1, in_band["frequency_hz"].nunique())),
                    "n_epochs": first["n_epochs"],
                    "effective_duration_s": first["effective_duration_s"],
                    "rank_seed": first["rank_seed"],
                    "rank_target": first["rank_target"],
                    "status": "ok",
                }
            )
    return pd.DataFrame(rows)


def _connectivity_input_checks(data: np.ndarray, sfreq: float, quality_epoch: pd.DataFrame, valid_epoch: np.ndarray, config: dict[str, Any], n_nonfinite_epochs: int) -> pd.DataFrame:
    conn_cfg = config.get("connectivity", {})
    expected = config.get("expected_data", {})
    fmin = float(conn_cfg.get("fmin_hz", 2.0))
    fmax = float(conn_cfg.get("fmax_hz", 100.0))
    lowpass = _as_float(expected.get("preprocessed_lowpass_hz"), 200.0)
    highpass = _as_float(expected.get("preprocessed_highpass_hz"), 1.0)
    fail_count = int(quality_epoch.get("quality_status", pd.Series(dtype=str)).astype(str).eq("fail").sum())
    warn_count = int(quality_epoch.get("quality_status", pd.Series(dtype=str)).astype(str).eq("warn").sum())
    rows = [
        {"check": "valid_epoch_count", "value": int(np.sum(valid_epoch)), "status": "ok" if np.sum(valid_epoch) >= int(conn_cfg.get("min_epochs", 5)) else "fail", "note": "quality fail and nonfinite epochs excluded; warn epochs retained"},
        {"check": "effective_valid_duration_s", "value": float(np.sum(valid_epoch) * data.shape[-1] / sfreq), "status": "ok", "note": "sum of retained epoch durations; epochs are not concatenated"},
        {"check": "quality_fail_epoch_count", "value": fail_count, "status": "ok" if fail_count == 0 else "warn", "note": "quality flags are retained in the audit tables"},
        {"check": "quality_warn_epoch_count", "value": warn_count, "status": "ok" if warn_count == 0 else "warn", "note": "warn epochs are retained unless quality status is fail"},
        {"check": "nonfinite_epoch_count", "value": n_nonfinite_epochs, "status": "ok" if n_nonfinite_epochs == 0 else "fail", "note": "nonfinite epochs are excluded from spectral estimation"},
        {"check": "low_frequency_edge", "value": fmin, "status": "ok" if fmin >= highpass + 1.0 else "warn", "note": f"connectivity fmin={fmin:g} Hz; known/configured high-pass edge={highpass:g} Hz"},
        {"check": "high_frequency_edge", "value": fmax, "status": "ok" if fmax <= lowpass - 5.0 else "warn", "note": f"connectivity fmax={fmax:g} Hz; known/configured low-pass edge={lowpass:g} Hz"},
        {"check": "line_noise_policy", "value": ",".join(str(x) for x in conn_cfg.get("exclude_line_noise_hz", [])), "status": "ok", "note": "line-noise bins are flagged/excluded in band summaries; no extra notch or rereference is applied"},
        {"check": "reference_policy", "value": "acquisition_reference_preserved", "status": "ok", "note": "no bipolar, within-region average, orthogonalisation, or FOOOF-derived cross-spectrum is used"},
    ]
    return pd.DataFrame(rows)


def _run_rank_sensitivity(data: np.ndarray, sfreq: float, region_info: dict[str, Any], valid_epoch: np.ndarray, config: dict[str, Any]) -> pd.DataFrame:
    conn_cfg = config.get("connectivity", {})
    if not bool(conn_cfg.get("rank_sensitivity_enabled", True)):
        return pd.DataFrame([{"status": "disabled_by_config"}])
    offsets = [int(item) for item in conn_cfg.get("rank_sensitivity_offsets", [-1, 0, 1])]
    rows: list[dict[str, Any]] = []
    for region_a, region_b in selected_region_pairs(tuple(region_info["groups"]), config):
        seed_group = region_info["groups"][region_a]
        target_group = region_info["groups"][region_b]
        seed_base = region_info["rank_map"][region_a]
        target_base = region_info["rank_map"][region_b]
        for offset in offsets:
            rank_seed = max(1, min(len(seed_group), seed_base + offset))
            rank_target = max(1, min(len(target_group), target_base + offset))
            try:
                results = _estimate_multivariate(data[valid_epoch], sfreq, region_info["region_indices"][region_a], region_info["region_indices"][region_b], rank_seed, rank_target, config)
                for method, connection in zip(MULTIVARIATE_METHODS, results):
                    values, frequencies = _connection_values(connection)
                    metric = np.abs(values[0]) if method == "mic" else values[0]
                    metric = metric[~_line_noise_mask(frequencies, config)]
                    rows.append({"region_a": region_a, "region_b": region_b, "method": method, "rank_offset": offset, "rank_seed": rank_seed, "rank_target": rank_target, "mean_strength_2_100hz": float(np.nanmean(metric)), "max_strength_2_100hz": float(np.nanmax(metric)), "n_epochs": int(np.sum(valid_epoch)), "status": "ok"})
            except Exception as exc:  # noqa: BLE001 - retain failed sensitivity checks
                rows.append({"region_a": region_a, "region_b": region_b, "rank_offset": offset, "rank_seed": rank_seed, "rank_target": rank_target, "status": f"failed: {type(exc).__name__}: {exc}"})
    return pd.DataFrame(rows)


def _epoch_signal_profile(data: np.ndarray, valid_epoch: np.ndarray) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    rms = np.sqrt(np.mean(np.square(data), axis=(1, 2)))
    median = float(np.nanmedian(rms[valid_epoch])) if np.any(valid_epoch) else np.nan
    mad = float(np.nanmedian(np.abs(rms[valid_epoch] - median))) if np.any(valid_epoch) else np.nan
    scale = 1.4826 * mad if mad > 0 else np.nan
    for epoch_index, value in enumerate(rms):
        robust_z = (value - median) / scale if np.isfinite(scale) else np.nan
        rows.append({"epoch_index": epoch_index, "signal_rms": float(value), "robust_z_vs_valid_epochs": float(robust_z) if np.isfinite(robust_z) else np.nan, "quality_valid_for_connectivity": bool(valid_epoch[epoch_index]), "signal_heterogeneity_flag": bool(np.isfinite(robust_z) and abs(robust_z) > 3.5), "flag_note": "descriptive flag only; not an automatic exclusion"})
    return pd.DataFrame(rows)


def _run_segment_stability(data: np.ndarray, sfreq: float, region_info: dict[str, Any], valid_epoch: np.ndarray, config: dict[str, Any]) -> pd.DataFrame:
    conn_cfg = config.get("connectivity", {})
    if not bool(conn_cfg.get("stability_enabled", True)):
        return pd.DataFrame([{"check_type": "segment_stability", "status": "disabled_by_config"}])
    valid_indices = np.flatnonzero(valid_epoch)
    if len(valid_indices) < 2:
        return pd.DataFrame([{"check_type": "segment_stability", "status": "not_run_insufficient_epochs"}])
    rng = np.random.default_rng(int(conn_cfg.get("stability_seed", 20260906)))
    subset_size = max(2, int(np.floor(len(valid_indices) * float(conn_cfg.get("stability_subsample_fraction", 0.75)))))
    subsets: dict[str, np.ndarray] = {
        "first_half": valid_indices[: max(1, len(valid_indices) // 2)],
        "second_half": valid_indices[max(1, len(valid_indices) // 2) :],
    }
    for index in range(int(conn_cfg.get("stability_n_subsamples", 2))):
        subsets[f"random_subsample_{index + 1}"] = np.sort(rng.choice(valid_indices, size=min(subset_size, len(valid_indices)), replace=False))
    rows: list[dict[str, Any]] = [
        {"check_type": "equal_epoch_sampling", "status": "not_applicable_single_file", "note": "requires multiple condition nodes; no condition-level equalisation is applied to this single file"}
    ]
    for subset_name, indices in subsets.items():
        subset_data = data[indices]
        for region_a, region_b in selected_region_pairs(tuple(region_info["groups"]), config):
            try:
                multivariate = _estimate_multivariate(subset_data, sfreq, region_info["region_indices"][region_a], region_info["region_indices"][region_b], region_info["rank_map"][region_a], region_info["rank_map"][region_b], config)
                for method, connection in zip(MULTIVARIATE_METHODS, multivariate):
                    values, frequencies = _connection_values(connection)
                    keep = ~_line_noise_mask(frequencies, config)
                    metric = np.abs(values[0]) if method == "mic" else values[0]
                    rows.append({"check_type": "segment_stability", "subset_name": subset_name, "region_a": region_a, "region_b": region_b, "method": method, "mean_strength_2_100hz": float(np.nanmean(metric[keep])), "n_epochs": len(indices), "effective_duration_s": float(len(indices) * data.shape[-1] / sfreq), "status": "ok"})
                bivariate = _estimate_bivariate(subset_data, sfreq, region_info["region_indices"][region_a], region_info["region_indices"][region_b], ["wpli2_debiased"], config)
                values, frequencies = _connection_values(bivariate[0])
                keep = ~_line_noise_mask(frequencies, config)
                pair_means = np.nanmean(values[:, keep], axis=1)
                rows.append({"check_type": "segment_stability", "subset_name": subset_name, "region_a": region_a, "region_b": region_b, "method": "wpli2_debiased", "mean_strength_2_100hz": float(np.nanmedian(pair_means)), "n_epochs": len(indices), "effective_duration_s": float(len(indices) * data.shape[-1] / sfreq), "status": "ok", "n_channel_pairs": int(values.shape[0])})
            except Exception as exc:  # noqa: BLE001 - retain failed stability checks
                rows.append({"check_type": "segment_stability", "subset_name": subset_name, "region_a": region_a, "region_b": region_b, "status": f"failed: {type(exc).__name__}: {exc}"})
    return pd.DataFrame(rows)


def compute_connectivity(
    data: np.ndarray,
    sfreq: float,
    channel_table: pd.DataFrame,
    quality_epoch: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Estimate MIC, MIM and wPLI² across valid epochs without concatenation."""
    conn_cfg = config.get("connectivity", {})
    methods = [str(method) for method in conn_cfg.get("methods", ["mic", "mim", "wpli2_debiased"])]
    unsupported = sorted(set(methods) - set(MULTIVARIATE_METHODS) - set(BIVARIATE_METHODS))
    empty: dict[str, Any] = {
        "status": "not_run",
        "spectrum": pd.DataFrame(),
        "region_summary": pd.DataFrame(),
        "band_summary": pd.DataFrame(),
        "patterns": pd.DataFrame(),
        "redundancy_correlation": pd.DataFrame(),
        "redundancy_singular_values": pd.DataFrame(),
        "rank_summary": pd.DataFrame(),
        "rank_sensitivity": pd.DataFrame(),
        "stability": pd.DataFrame(),
        "epoch_profile": pd.DataFrame(),
        "input_checks": pd.DataFrame(),
        "failures": pd.DataFrame(columns=FAILURE_COLUMNS),
        "metadata": {},
    }
    if unsupported:
        empty["status"] = f"not_run_unsupported_methods: {unsupported}"
        return empty
    groups = _channel_groups(channel_table)
    if len(groups) < 2 or any(len(group) == 0 for group in groups.values()):
        empty["status"] = "not_run_channel_region_mapping_incomplete"
        return empty
    array_data = np.asarray(data, dtype=float)
    valid_epoch, n_nonfinite_epochs = _finite_epoch_mask(array_data, quality_epoch)
    n_valid = int(np.sum(valid_epoch))
    min_epochs = int(conn_cfg.get("min_epochs", 5))
    empty["epoch_profile"] = _epoch_signal_profile(array_data, valid_epoch)
    empty["input_checks"] = _connectivity_input_checks(array_data, sfreq, quality_epoch, valid_epoch, config, n_nonfinite_epochs)
    if n_valid < min_epochs:
        empty["status"] = f"not_run_insufficient_valid_epochs: {n_valid} < {min_epochs}"
        return empty
    region_info = assess_region_redundancy(array_data, sfreq, channel_table, valid_epoch, config)
    rows: list[dict[str, Any]] = []
    pattern_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    effective_duration = float(n_valid * array_data.shape[-1] / sfreq)
    for region_a, region_b in selected_region_pairs(tuple(region_info["groups"]), config):
        seed_group = region_info["groups"][region_a]
        target_group = region_info["groups"][region_b]
        seed_indices = region_info["region_indices"][region_a]
        target_indices = region_info["region_indices"][region_b]
        rank_seed = region_info["rank_map"][region_a]
        rank_target = region_info["rank_map"][region_b]
        if any(method in methods for method in MULTIVARIATE_METHODS):
            try:
                multivariate = _estimate_multivariate(array_data[valid_epoch], sfreq, seed_indices, target_indices, rank_seed, rank_target, config)
                for method, connection in zip(MULTIVARIATE_METHODS, multivariate):
                    if method not in methods:
                        continue
                    values, frequencies = _connection_values(connection)
                    meta = _spectral_meta(connection, config)
                    line_noise = _line_noise_mask(frequencies, config)
                    for frequency_index, frequency in enumerate(frequencies):
                        row = _base_row(region_a, region_b, seed_group, target_group, method, frequency, values[0, frequency_index], n_valid, effective_duration, rank_seed, rank_target, meta, "multivariate_region_pair")
                        row["frequency_is_excluded_line_noise"] = bool(line_noise[frequency_index])
                        rows.append(row)
                    if method == "mic":
                        pattern_rows.extend(_pattern_rows(connection, region_a, region_b, seed_group, target_group))
            except Exception as exc:  # noqa: BLE001 - preserve pair-level failure
                failure_rows.append({"region_a": region_a, "region_b": region_b, "method": "mic_mim", "failure_reason": f"{type(exc).__name__}: {exc}", "n_epochs": n_valid, "rank_seed": rank_seed, "rank_target": rank_target})
        bivariate_methods = [method for method in BIVARIATE_METHODS if method in methods]
        if bivariate_methods:
            try:
                bivariate = _estimate_bivariate(array_data[valid_epoch], sfreq, seed_indices, target_indices, bivariate_methods, config)
                pair_count = len(seed_indices) * len(target_indices)
                for method, connection in zip(bivariate_methods, bivariate):
                    values, frequencies = _connection_values(connection)
                    meta = _spectral_meta(connection, config)
                    line_noise = _line_noise_mask(frequencies, config)
                    pair_rows = list(zip(np.repeat(seed_indices, len(target_indices)), np.tile(target_indices, len(seed_indices))))
                    for pair_index, (seed_index, target_index) in enumerate(pair_rows):
                        seed_channel = channel_table.loc[channel_table["array_index"] == seed_index, "channel_name"].iloc[0]
                        target_channel = channel_table.loc[channel_table["array_index"] == target_index, "channel_name"].iloc[0]
                        for frequency_index, frequency in enumerate(frequencies):
                            row = _base_row(region_a, region_b, seed_group, target_group, method, frequency, values[pair_index, frequency_index], n_valid, effective_duration, rank_seed, rank_target, meta, "cross_region_channel_pair", str(seed_channel), str(target_channel))
                            row["frequency_is_excluded_line_noise"] = bool(line_noise[frequency_index])
                            row["n_channel_pairs_total"] = pair_count
                            rows.append(row)
            except Exception as exc:  # noqa: BLE001 - preserve pair-level failure
                failure_rows.append({"region_a": region_a, "region_b": region_b, "method": ",".join(bivariate_methods), "failure_reason": f"{type(exc).__name__}: {exc}", "n_epochs": n_valid, "rank_seed": rank_seed, "rank_target": rank_target})
    spectrum = pd.DataFrame(rows)
    if spectrum.empty:
        empty.update({"status": "failed_empty_result", "redundancy_correlation": region_info["correlation"], "redundancy_singular_values": region_info["singular_values"], "rank_summary": region_info["summary"], "failures": pd.DataFrame(failure_rows, columns=FAILURE_COLUMNS)})
        return empty
    empty.update(
        {
            "status": "ok" if not failure_rows else "ok_with_pair_failures",
            "spectrum": spectrum,
            "region_summary": _summarize_region_spectrum(spectrum),
            "band_summary": _band_summary(spectrum, config),
            "patterns": pd.DataFrame(pattern_rows),
            "redundancy_correlation": region_info["correlation"],
            "redundancy_singular_values": region_info["singular_values"],
            "rank_summary": region_info["summary"],
            "rank_sensitivity": _run_rank_sensitivity(array_data, sfreq, region_info, valid_epoch, config),
            "stability": _run_segment_stability(array_data, sfreq, region_info, valid_epoch, config),
            "failures": pd.DataFrame(failure_rows, columns=FAILURE_COLUMNS),
            "metadata": {
                "n_valid_epochs": n_valid,
                "effective_valid_duration_s": effective_duration,
                "methods_requested": methods,
                "spectral_mode": str(conn_cfg.get("mode", "multitaper")),
                "mt_bandwidth_hz": _as_float(conn_cfg.get("mt_bandwidth_hz")),
                "mt_adaptive": bool(conn_cfg.get("mt_adaptive", False)),
                "mt_low_bias": bool(conn_cfg.get("mt_low_bias", True)),
                "frequency_range_hz": [float(conn_cfg.get("fmin_hz", 2.0)), float(conn_cfg.get("fmax_hz", 100.0))],
                "frequency_step_hz": round(float(np.median(np.diff(np.sort(spectrum["frequency_hz"].dropna().unique())))), 10) if spectrum["frequency_hz"].nunique() > 1 else np.nan,
                "n_tapers_note": "MNE-Connectivity 0.9.0 did not expose a usable n_tapers attribute; no value was inferred",
                "frequency_grid_definition": "MNE-Connectivity multitaper frequency grid; full grid retained in connectivity_spectrum.csv",
                "line_noise_policy": "flagged and excluded only from configured band summaries; no extra notch or rereference",
                "multivariate_interpretation": "MIC absolute value is a strength display; MIM is raw unnormalised and may exceed 1; neither is causal direction",
                "wpli_interpretation": "wpli2_debiased remains squared and finite negative estimates are retained",
                "identity_status": "file-level result only until animal/session/dose node metadata are registered",
            },
        }
    )
    return empty
