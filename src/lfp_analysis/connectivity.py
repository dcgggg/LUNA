from __future__ import annotations

import time
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd

from .connectivity_processing import (
    bin_spectrum,
    diagnose_frequency_table,
    estimate_multitaper_metadata,
    frequency_mask,
    quantify_band_cv,
    quantify_roughness,
    resolve_line_noise_settings,
    smooth_for_display,
    validate_frequency_axis,
)
from .quality import align_epoch_quality

REGION_ORDER = ("M1", "STR", "PF", "SNr")
MULTIVARIATE_METHODS = ("mic", "mim")
BIVARIATE_METHODS = ("wpli", "dpli", "wpli2_debiased", "imcoh", "coh")
FAILURE_COLUMNS = [
    "region_a",
    "region_b",
    "method",
    "failure_reason",
    "n_epochs",
    "rank_seed",
    "rank_target",
    "n_components_requested",
]
ESTIMATION_CALL_COLUMNS = [
    "analysis_task_id",
    "call_index",
    "call_purpose",
    "estimator_api",
    "estimator_scope",
    "region_pair",
    "seed_array_indices",
    "target_array_indices",
    "seed_channel_count",
    "target_channel_count",
    "methods",
    "input_shape",
    "n_epochs",
    "n_channels",
    "n_times",
    "epoch_duration_s",
    "sfreq_hz",
    "fmin_hz",
    "fmax_hz",
    "mode",
    "mt_bandwidth_hz",
    "mt_adaptive",
    "mt_low_bias",
    "n_tapers",
    "time_bandwidth_product",
    "rank_seed",
    "rank_target",
    "n_frequencies_returned",
    "frequency_grid_hz",
    "cache_hit",
    "cache_status",
    "status",
    "elapsed_s",
    "error",
]


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


def _finite_epoch_mask(
    data: np.ndarray,
    quality_epoch: pd.DataFrame,
    epoch_ids: list[int] | np.ndarray | None = None,
) -> tuple[np.ndarray, int]:
    aligned_quality = align_epoch_quality(quality_epoch, len(data), epoch_ids)
    quality_status = aligned_quality["quality_status"].astype(str).str.lower()
    quality_valid = quality_status.isin({"pass", "ok", "warn"}).to_numpy()
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
    if configured is None:
        return all_pairs
    if not configured:
        return []
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
    if str(conn_cfg.get("rank_strategy", "data_driven_energy_99pct")).strip().lower() != "fixed_rank":
        fixed_rank = {}
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
        covariance = np.atleast_2d(np.cov(values)) if values.shape[1] > 1 else np.zeros((len(indices), len(indices)))
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
        "n_jobs": int(conn_cfg.get("n_jobs", 1)),
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


def _new_estimation_call(
    data: np.ndarray,
    sfreq: float,
    seed_indices: np.ndarray,
    target_indices: np.ndarray,
    rank_seed: int | None,
    rank_target: int | None,
    methods: list[str],
    config: dict[str, Any],
    analysis_task_id: str,
    call_purpose: str,
    region_pair: tuple[str, str] | None,
    estimator_scope: str,
) -> dict[str, Any]:
    """Create an auditable record for one MNE-Connectivity invocation."""
    conn_cfg = config.get("connectivity", {})
    taper_meta = estimate_multitaper_metadata(int(data.shape[-1]), float(sfreq), config)
    mode = str(conn_cfg.get("mode", "multitaper"))
    return {
        "analysis_task_id": analysis_task_id,
        "call_index": np.nan,
        "call_purpose": call_purpose,
        "estimator_api": "mne_connectivity.spectral_connectivity_epochs",
        "estimator_scope": estimator_scope,
        "region_pair": "" if region_pair is None else f"{region_pair[0]}->{region_pair[1]}",
        "seed_array_indices": ",".join(str(int(value)) for value in np.asarray(seed_indices, dtype=int)),
        "target_array_indices": ",".join(str(int(value)) for value in np.asarray(target_indices, dtype=int)),
        "seed_channel_count": int(np.asarray(seed_indices).size),
        "target_channel_count": int(np.asarray(target_indices).size),
        "methods": "|".join(methods),
        "input_shape": "×".join(str(int(value)) for value in data.shape),
        "n_epochs": int(data.shape[0]),
        "n_channels": int(data.shape[1]),
        "n_times": int(data.shape[2]),
        "epoch_duration_s": float(data.shape[2] / sfreq),
        "sfreq_hz": float(sfreq),
        "fmin_hz": float(conn_cfg.get("fmin_hz", 2.0)),
        "fmax_hz": float(conn_cfg.get("fmax_hz", 100.0)),
        "mode": mode,
        "mt_bandwidth_hz": float(conn_cfg.get("mt_bandwidth_hz", np.nan)) if mode == "multitaper" else np.nan,
        "mt_adaptive": bool(conn_cfg.get("mt_adaptive", False)) if mode == "multitaper" else np.nan,
        "mt_low_bias": bool(conn_cfg.get("mt_low_bias", True)) if mode == "multitaper" else np.nan,
        "n_tapers": taper_meta.get("n_tapers", np.nan),
        "time_bandwidth_product": taper_meta.get("time_bandwidth_product", np.nan),
        "rank_seed": rank_seed if rank_seed is not None else np.nan,
        "rank_target": rank_target if rank_target is not None else np.nan,
        "n_frequencies_returned": np.nan,
        "frequency_grid_hz": np.nan,
        "cache_hit": False,
        "cache_status": "no_estimator_cache_configured",
        "status": "running",
        "elapsed_s": np.nan,
        "error": "",
    }


def _finish_estimation_call(call: dict[str, Any], result: list[Any] | None = None, error: Exception | None = None) -> None:
    """Complete a call record without changing the estimator result."""
    if result:
        frequencies = np.asarray(getattr(result[0], "freqs", []), dtype=float)
        call["n_frequencies_returned"] = int(frequencies.size)
        if frequencies.size > 1:
            call["frequency_grid_hz"] = float(np.median(np.diff(frequencies)))
    call["status"] = "failed" if error is not None else "ok"
    if error is not None:
        call["error"] = f"{type(error).__name__}: {error}"


def _estimate_multivariate(
    data: np.ndarray,
    sfreq: float,
    seed_indices: np.ndarray,
    target_indices: np.ndarray,
    rank_seed: int,
    rank_target: int,
    methods: list[str],
    config: dict[str, Any],
    *,
    call_log: list[dict[str, Any]] | None = None,
    analysis_task_id: str = "connectivity_task",
    call_purpose: str = "main",
    region_pair: tuple[str, str] | None = None,
) -> dict[str, Any]:
    if not methods:
        return {}
    estimator = _load_connectivity_api()
    conn_cfg = config.get("connectivity", {})
    requested_components = int(conn_cfg.get("n_components", 1))
    backend_components = requested_components if "mic" in methods else 1
    call = _new_estimation_call(
        data,
        sfreq,
        seed_indices,
        target_indices,
        rank_seed,
        rank_target,
        methods,
        config,
        analysis_task_id,
        call_purpose,
        region_pair,
        "multivariate",
    )
    started = time.perf_counter()
    try:
        returned = _as_list(
            estimator(
                data,
                method=methods if len(methods) > 1 else methods[0],
                indices=(np.asarray([seed_indices], dtype=int), np.asarray([target_indices], dtype=int)),
                rank=(np.asarray([rank_seed], dtype=int), np.asarray([rank_target], dtype=int)),
                n_components=backend_components,
                **_connectivity_kwargs(sfreq, config),
            )
        )
    except Exception as error:
        _finish_estimation_call(call, error=error)
        raise
    else:
        _finish_estimation_call(call, returned)
    finally:
        call["elapsed_s"] = float(time.perf_counter() - started)
        if call_log is not None:
            call["call_index"] = len(call_log) + 1
            call_log.append(call)
    if len(returned) != len(methods):
        error = ValueError(f"MNE-Connectivity returned {len(returned)} multivariate results for {methods}")
        _finish_estimation_call(call, error=error)
        raise error
    return dict(zip(methods, returned, strict=True))


def _estimate_bivariate(
    data: np.ndarray,
    sfreq: float,
    seed_indices: np.ndarray,
    target_indices: np.ndarray,
    methods: list[str],
    config: dict[str, Any],
    *,
    call_log: list[dict[str, Any]] | None = None,
    analysis_task_id: str = "connectivity_task",
    call_purpose: str = "main",
    region_pair: tuple[str, str] | None = None,
) -> list[Any]:
    if not methods:
        return []
    estimator = _load_connectivity_api()
    pair_seed = np.repeat(seed_indices, len(target_indices)).astype(int)
    pair_target = np.tile(target_indices, len(seed_indices)).astype(int)
    call = _new_estimation_call(
        data,
        sfreq,
        seed_indices,
        target_indices,
        None,
        None,
        methods,
        config,
        analysis_task_id,
        call_purpose,
        region_pair,
        "bivariate",
    )
    started = time.perf_counter()
    try:
        returned = _as_list(
            estimator(
                data,
                method=methods if len(methods) > 1 else methods[0],
                indices=(pair_seed, pair_target),
                rank=None,
                **_connectivity_kwargs(sfreq, config),
            )
        )
    except Exception as error:
        _finish_estimation_call(call, error=error)
        raise
    else:
        _finish_estimation_call(call, returned)
    finally:
        call["elapsed_s"] = float(time.perf_counter() - started)
        if call_log is not None:
            call["call_index"] = len(call_log) + 1
            call_log.append(call)
    if len(returned) != len(methods):
        error = ValueError(f"MNE-Connectivity returned {len(returned)} bivariate results for {methods}")
        _finish_estimation_call(call, error=error)
        raise error
    return returned


def _connection_values(connection: Any) -> tuple[np.ndarray, np.ndarray]:
    """Return connectivity data as [connection, component, frequency].

    MNE-Connectivity uses two dimensions for a single-component result and
    three dimensions for multivariate MIC.  Normalising here prevents later
    summaries and plots from silently dropping MIC components.
    """
    values = np.asarray(connection.get_data(), dtype=float)
    if values.ndim == 1:
        values = values[None, None, :]
    elif values.ndim == 2:
        values = values[:, None, :]
    elif values.ndim != 3:
        raise ValueError(f"Unexpected connectivity result dimensions: {values.shape}")
    frequencies = np.asarray(connection.freqs, dtype=float)
    validate_frequency_axis(frequencies)
    if values.shape[-1] != frequencies.size:
        raise ValueError(f"Connectivity frequency axis mismatch: data={values.shape}, freqs={frequencies.shape}")
    return values, frequencies


def _line_noise_mask(frequencies: np.ndarray, config: dict[str, Any]) -> np.ndarray:
    return frequency_mask(frequencies, config, purpose="analysis")


def _method_display_definition(method: str) -> tuple[str, str]:
    if method == "mic":
        return "abs(value_raw)", "MIC raw sign retained; strength is absolute value"
    if method == "mim":
        return "value_raw", "MIM raw unnormalised value; values >1 are retained"
    if method == "wpli2_debiased":
        return "value_raw", "wpli2_debiased raw value; negative finite estimates retained"
    if method == "wpli":
        return "value_raw", "wPLI raw channel-pair estimate; region display is an equal-weight channel-pair summary"
    if method == "dpli":
        return "value_raw", "dPLI raw ordered channel-pair estimate; 0.5 is the backend neutral reference"
    return "value_raw", "raw auxiliary bivariate estimate"


def _region_pair_aggregation(method: str, config: dict[str, Any]) -> str:
    """Resolve the explicit bivariate channel-pair aggregation rule."""
    configured = str(config.get("connectivity", {}).get("region_pair_summary", "mean")).strip().lower()
    if configured in {"median", "median_over_valid_channel_pairs"}:
        return "median"
    # Preserve the meaning of the previous default for old non-GUI configs.
    if configured == "median_over_valid_channel_pairs_for_wpli_only" and method == "wpli2_debiased":
        return "median"
    return "mean"


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
    component_index: float | None = None,
    n_components_requested: int | None = None,
    n_components_returned: int | None = None,
) -> dict[str, Any]:
    definition, note = _method_display_definition(method)
    nonfinite_type = "finite"
    if np.isnan(value):
        nonfinite_type = "nan"
    elif np.isinf(value):
        nonfinite_type = "inf"
    return {
        "region_a": region_a,
        "region_b": region_b,
        "seed_region": region_a,
        "target_region": region_b,
        "direction_order": f"{region_a}->{region_b}",
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
        "component_index": component_index,
        "n_components_requested": n_components_requested,
        "n_components_returned": n_components_returned,
        "frequency_hz": float(frequency),
        "value_raw": float(value) if np.isfinite(value) else np.nan,
        "value_nonfinite_type": nonfinite_type,
        "value_strength": abs(float(value)) if method == "mic" and np.isfinite(value) else (float(value) if np.isfinite(value) else np.nan),
        "display_value_definition": definition,
        "estimate_note": note,
        "n_epochs": n_epochs,
        "effective_duration_s": effective_duration,
        "frequency_is_excluded_line_noise": False,
        **spectral_meta,
    }


def _spectral_meta(connection: Any, config: dict[str, Any], n_times: int | None = None, sfreq: float | None = None) -> dict[str, Any]:
    attrs = getattr(connection, "attrs", {}) or {}
    conn_cfg = config.get("connectivity", {})
    rank = attrs.get("rank")
    frequencies = np.asarray(connection.freqs, dtype=float)
    taper_meta = estimate_multitaper_metadata(n_times, sfreq, config) if n_times is not None and sfreq is not None else {}
    return {
        "spectral_mode": str(conn_cfg.get("mode", "multitaper")),
        "mt_bandwidth_hz": _as_float(conn_cfg.get("mt_bandwidth_hz")),
        "mt_adaptive": bool(conn_cfg.get("mt_adaptive", False)),
        "mt_low_bias": bool(conn_cfg.get("mt_low_bias", True)),
        "n_tapers": _as_float(attrs.get("n_tapers"), taper_meta.get("n_tapers", np.nan)),
        "time_bandwidth_product": taper_meta.get("time_bandwidth_product", np.nan),
        "n_tapers_note": taper_meta.get("n_tapers_note", "not estimated"),
        "estimated_rank_metadata": str(rank),
        "frequency_grid_hz": float(np.median(np.diff(frequencies))) if len(frequencies) > 1 else np.nan,
    }


def _pattern_rows(connection: Any, region_a: str, region_b: str, seed_group: pd.DataFrame, target_group: pd.DataFrame) -> list[dict[str, Any]]:
    patterns = getattr(connection, "attrs", {}).get("patterns")
    if patterns is None:
        return []
    array = np.asarray(patterns, dtype=float)
    # MNE-Connectivity 0.9: single component is
    # (2, n_connections, n_channels, n_freqs), while multiple MIC
    # components are (2, n_connections, n_components, n_channels, n_freqs).
    if array.ndim == 4:
        array = array[:, :, None, :, :]
    if array.ndim != 5:
        return []
    rows: list[dict[str, Any]] = []
    for side, group in enumerate((seed_group, target_group)):
        if side >= array.shape[0]:
            continue
        side_array = array[side, 0]
        n_components = side_array.shape[0]
        if side_array.ndim != 3:
            continue
        for component_index in range(n_components):
            component_array = side_array[component_index]
            for channel_index, channel_name in enumerate(group["channel_name"]):
                if channel_index >= component_array.shape[0]:
                    continue
                for frequency_index, value in enumerate(component_array[channel_index]):
                    rows.append(
                        {
                            "region_a": region_a,
                            "region_b": region_b,
                            "method": "mic",
                            "component_index": component_index + 1,
                            "n_components_returned": n_components,
                            "pattern_role": "seed" if side == 0 else "target",
                            "channel_name": channel_name,
                            "array_index": int(group.iloc[channel_index]["array_index"]),
                            "frequency_hz": float(connection.freqs[frequency_index]),
                            "pattern_value": float(value),
                            "pattern_note": "official MIC spatial pattern; not a direct biological contribution weight",
                        }
                    )
    return rows


def _summarize_region_spectrum(spectrum: pd.DataFrame, config: dict[str, Any] | None = None) -> pd.DataFrame:
    if spectrum.empty:
        return pd.DataFrame()
    component_column = "component_index" if "component_index" in spectrum.columns else None
    group_columns = ["method", "region_a", "region_b"]
    if component_column:
        group_columns.append(component_column)
    group_columns.append("frequency_hz")
    rows: list[dict[str, Any]] = []
    for keys, group in spectrum.groupby(group_columns, dropna=False):
        if component_column:
            method, region_a, region_b, component_index, frequency = keys
        else:
            method, region_a, region_b, frequency = keys
            component_index = np.nan
        if group["aggregation_level"].iloc[0] == "multivariate_region_pair":
            value = float(group["value_raw"].iloc[0])
            strength = abs(value) if method == "mic" else value
            n_pairs = np.nan
            n_negative = int(np.sum(group["value_raw"] < 0))
        else:
            pair_columns = ["seed_channel", "target_channel"]
            if all(column in group.columns for column in pair_columns):
                pair_values = group.groupby(pair_columns, dropna=False)["value_raw"].mean()
            else:
                pair_values = group["value_raw"]
            aggregation = _region_pair_aggregation(str(method), config or {})
            value = float(pair_values.median() if aggregation == "median" else pair_values.mean())
            strength = value
            n_pairs = int(pair_values.notna().sum())
            n_negative = int(np.sum(pair_values < 0))
        first = group.iloc[0]
        rows.append(
            {
                "method": method,
                "region_a": region_a,
                "region_b": region_b,
                "component_index": component_index,
                "frequency_hz": float(frequency),
                "value_raw": value,
                "value_strength": strength,
                "n_channel_pairs": n_pairs,
                "n_negative_estimates": n_negative,
                "aggregation_definition": "multivariate result" if group["aggregation_level"].iloc[0] == "multivariate_region_pair" else f"{_region_pair_aggregation(str(method), config or {})} across valid cross-region channel pairs",
                "n_epochs": first["n_epochs"],
                "effective_duration_s": first["effective_duration_s"],
                "rank_seed": first["rank_seed"],
                "rank_target": first["rank_target"],
                "frequency_is_excluded_line_noise": first["frequency_is_excluded_line_noise"],
                "spectral_mode": first["spectral_mode"],
                "mt_bandwidth_hz": first["mt_bandwidth_hz"],
                "mt_adaptive": first.get("mt_adaptive", np.nan),
                "mt_low_bias": first.get("mt_low_bias", np.nan),
                "n_tapers": first["n_tapers"],
                "n_components_requested": first.get("n_components_requested", np.nan),
                "n_components_returned": first.get("n_components_returned", np.nan),
            }
        )
    return pd.DataFrame(rows)


def _band_summary(spectrum: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    if spectrum.empty:
        return pd.DataFrame()
    bands = config.get("bands", {})
    rows: list[dict[str, Any]] = []
    group_columns = ["method", "region_a", "region_b"]
    if "component_index" in spectrum.columns:
        group_columns.append("component_index")
    for keys, group in spectrum.groupby(group_columns, dropna=False):
        if len(group_columns) == 4:
            method, region_a, region_b, component_index = keys
        else:
            method, region_a, region_b = keys
            component_index = np.nan
        for band, bounds in bands.items():
            in_band = group.loc[(group["frequency_hz"] >= float(bounds[0])) & (group["frequency_hz"] <= float(bounds[1]))].copy()
            used = in_band.loc[~in_band["frequency_is_excluded_line_noise"]].copy()
            if used.empty:
                rows.append(
                    {
                        "method": method,
                        "region_a": region_a,
                        "region_b": region_b,
                        "component_index": component_index,
                        "band": band,
                        "band_low_hz": bounds[0],
                        "band_high_hz": bounds[1],
                        "status": "no_frequency_bins_in_range",
                    }
                )
                continue
            if method == "mic":
                value = float(np.mean(np.abs(used["value_raw"])))
                definition = "mean_absolute_MIC_across_frequency"
                n_pairs = np.nan
            else:
                pair_columns = ["seed_channel", "target_channel"]
                if all(column in used.columns for column in pair_columns):
                    per_pair = used.groupby(pair_columns, dropna=False)["value_raw"].mean()
                else:
                    per_pair = used["value_raw"]
                aggregation = _region_pair_aggregation(str(method), config)
                value = float(per_pair.median() if aggregation == "median" else per_pair.mean())
                definition = f"mean_across_frequency_then_{aggregation}_across_valid_channel_pairs"
                n_pairs = int(per_pair.size)
            first = used.iloc[0]
            coverage_fraction = float(used["frequency_hz"].nunique() / max(1, in_band["frequency_hz"].nunique()))
            rows.append(
                {
                    "method": method,
                    "region_a": region_a,
                    "region_b": region_b,
                    "component_index": component_index,
                    "band": band,
                    "band_low_hz": float(bounds[0]),
                    "band_high_hz": float(bounds[1]),
                    "value_raw_or_summary": value,
                    "value_strength": value,
                    "aggregation_definition": definition,
                    "n_channel_pairs": n_pairs,
                    "n_frequencies_used": int(used["frequency_hz"].nunique()),
                    "n_frequencies_excluded_line_noise": int(in_band["frequency_is_excluded_line_noise"].sum()),
                    "frequency_coverage_fraction": coverage_fraction,
                    "n_epochs": first["n_epochs"],
                    "effective_duration_s": first["effective_duration_s"],
                    "rank_seed": first["rank_seed"],
                    "rank_target": first["rank_target"],
                    "n_components_requested": first.get("n_components_requested", np.nan),
                    "n_components_returned": first.get("n_components_returned", np.nan),
                    "status": "ok" if coverage_fraction >= 1.0 else "partial_frequency_coverage",
                }
            )
    return pd.DataFrame(rows)


def _channel_pair_band_summary(spectrum: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Summarise each saved bivariate channel pair within each configured band."""
    if spectrum.empty or "aggregation_level" not in spectrum.columns:
        return pd.DataFrame()
    pair_spectrum = spectrum.loc[spectrum["aggregation_level"].astype(str).eq("cross_region_channel_pair")].copy()
    if pair_spectrum.empty:
        return pd.DataFrame()
    group_columns = ["method", "region_a", "region_b", "seed_channel", "target_channel"]
    rows: list[dict[str, Any]] = []
    for keys, group in pair_spectrum.groupby(group_columns, dropna=False):
        method, region_a, region_b, seed_channel, target_channel = keys
        for band, bounds in (config.get("bands", {}) or {}).items():
            in_band = group.loc[
                (group["frequency_hz"] >= float(bounds[0]))
                & (group["frequency_hz"] <= float(bounds[1]))
            ].copy()
            used = in_band.loc[~in_band["frequency_is_excluded_line_noise"].fillna(False)].copy()
            first = group.iloc[0]
            if used.empty:
                rows.append(
                    {
                        "method": method,
                        "region_a": region_a,
                        "region_b": region_b,
                        "seed_region": region_a,
                        "target_region": region_b,
                        "direction_order": f"{region_a}->{region_b}",
                        "seed_channel": seed_channel,
                        "target_channel": target_channel,
                        "band": band,
                        "band_low_hz": float(bounds[0]),
                        "band_high_hz": float(bounds[1]),
                        "value_raw_or_summary": np.nan,
                        "value_strength": np.nan,
                        "n_frequencies_used": 0,
                        "n_epochs": first.get("n_epochs", np.nan),
                        "effective_duration_s": first.get("effective_duration_s", np.nan),
                        "status": "no_frequency_bins_in_range",
                    }
                )
                continue
            value = float(used["value_raw"].mean())
            coverage_fraction = float(used["frequency_hz"].nunique() / max(1, in_band["frequency_hz"].nunique()))
            rows.append(
                {
                    "method": method,
                    "region_a": region_a,
                    "region_b": region_b,
                    "seed_region": region_a,
                    "target_region": region_b,
                    "direction_order": f"{region_a}->{region_b}",
                    "seed_channel": seed_channel,
                    "target_channel": target_channel,
                    "band": band,
                    "band_low_hz": float(bounds[0]),
                    "band_high_hz": float(bounds[1]),
                    "value_raw_or_summary": value,
                    "value_strength": value,
                    "aggregation_definition": "mean_across_frequency_within_one_channel_pair",
                    "n_frequencies_used": int(used["frequency_hz"].nunique()),
                    "n_frequencies_excluded_line_noise": int(in_band["frequency_is_excluded_line_noise"].fillna(False).sum()),
                    "frequency_coverage_fraction": coverage_fraction,
                    "n_epochs": first.get("n_epochs", np.nan),
                    "effective_duration_s": first.get("effective_duration_s", np.nan),
                    "rank_seed": first.get("rank_seed", np.nan),
                    "rank_target": first.get("rank_target", np.nan),
                    "status": "ok" if coverage_fraction >= 1.0 else "partial_frequency_coverage",
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
    low_frequency_cycles = fmin * data.shape[-1] / sfreq
    fail_count = int(quality_epoch.get("quality_status", pd.Series(dtype=str)).astype(str).eq("fail").sum())
    warn_count = int(quality_epoch.get("quality_status", pd.Series(dtype=str)).astype(str).eq("warn").sum())
    rows = [
        {"check": "valid_epoch_count", "value": int(np.sum(valid_epoch)), "status": "ok" if np.sum(valid_epoch) >= int(conn_cfg.get("min_epochs", 5)) else "fail", "note": "quality fail and nonfinite epochs excluded; warn epochs retained"},
        {"check": "effective_valid_duration_s", "value": float(np.sum(valid_epoch) * data.shape[-1] / sfreq), "status": "ok", "note": "sum of retained epoch durations; epochs are not concatenated"},
        {"check": "quality_fail_epoch_count", "value": fail_count, "status": "ok" if fail_count == 0 else "warn", "note": "quality flags are retained in the audit tables"},
        {"check": "quality_warn_epoch_count", "value": warn_count, "status": "ok" if warn_count == 0 else "warn", "note": "warn epochs are retained unless quality status is fail"},
        {"check": "nonfinite_epoch_count", "value": n_nonfinite_epochs, "status": "ok" if n_nonfinite_epochs == 0 else "fail", "note": "nonfinite epochs are excluded from spectral estimation"},
        {"check": "low_frequency_edge", "value": fmin, "status": "ok" if fmin >= highpass + 1.0 else "warn", "note": f"connectivity fmin={fmin:g} Hz; known/configured high-pass edge={highpass:g} Hz"},
        {"check": "low_frequency_cycles", "value": low_frequency_cycles, "status": "ok" if low_frequency_cycles >= 5.0 else "warn", "note": "MNE-Connectivity recommends enough cycles within each epoch; values below 5 cycles are marked as potentially unreliable"},
        {"check": "high_frequency_edge", "value": fmax, "status": "ok" if fmax <= lowpass - 5.0 else "warn", "note": f"connectivity fmax={fmax:g} Hz; known/configured low-pass edge={lowpass:g} Hz"},
        {"check": "line_noise_policy", "value": ",".join(str(x) for x in resolve_line_noise_settings(config)["centres_hz"]), "status": "ok", "note": "line-noise bins are flagged/excluded in configured summaries; raw frequency rows are retained; no extra notch or rereference is applied"},
        {"check": "spectral_parameters", "value": f"methods={','.join(str(method) for method in conn_cfg.get('methods', []))}; mode={conn_cfg.get('mode', 'multitaper')}; faverage=False; fdecim={int(conn_cfg.get('fdecim', 1))}; n_jobs={int(conn_cfg.get('n_jobs', 1))}", "status": "ok", "note": "full frequency grid retained; input is aligned epoch-wise time-domain data and epochs are not concatenated"},
        {"check": "multivariate_parameters", "value": f"rank_strategy={conn_cfg.get('rank_strategy', 'data_driven_energy_99pct')}; n_components={int(conn_cfg.get('n_components', 1))}", "status": "ok", "note": "rank is used only for MIC/MIM; MIC component count does not change MIM total interaction"},
        {"check": "bivariate_parameters", "value": f"region_pair_summary={_region_pair_aggregation('wpli', config)}; dpli_zero_imaginary_csd=0.5", "status": "ok", "note": "wPLI/dPLI are estimated for every selected cross-region channel pair; dPLI retains both ordered directions"},
        {"check": "reference_policy", "value": "acquisition_reference_preserved", "status": "ok", "note": "no bipolar, within-region average, orthogonalisation, or FOOOF-derived cross-spectrum is used"},
    ]
    return pd.DataFrame(rows)


def _frequency_products(spectrum: pd.DataFrame, config: dict[str, Any]) -> dict[str, pd.DataFrame]:
    """Build audit and optional display products from the untouched spectrum."""
    if spectrum.empty:
        return {
            "frequency_diagnostics": diagnose_frequency_table(spectrum, config),
            "roughness": quantify_roughness(spectrum),
            "band_cv": quantify_band_cv(spectrum, config),
            "binned_spectrum": pd.DataFrame(),
            "display_spectrum": pd.DataFrame(),
            "display_roughness": pd.DataFrame(),
        }
    settings = resolve_line_noise_settings(config)
    frequencies = pd.to_numeric(spectrum["frequency_hz"], errors="coerce").to_numpy(float)
    spectrum["frequency_is_masked_for_analysis"] = frequency_mask(frequencies, config, purpose="analysis")
    spectrum["frequency_is_masked_for_plot"] = frequency_mask(frequencies, config, purpose="plot")
    spectrum["line_noise_mask_source"] = np.where(
        spectrum["frequency_is_masked_for_plot"], settings["mask_source"], ""
    )
    spectrum["line_noise_mask_reason"] = np.where(
        spectrum["frequency_is_masked_for_plot"], "configured line-noise interval; raw value retained", ""
    )
    # Keep the historical column for downstream consumers and older saved
    # tables.  It represents the analysis/band-summary mask.
    spectrum["frequency_is_excluded_line_noise"] = spectrum["frequency_is_masked_for_analysis"]
    display_spectrum = smooth_for_display(spectrum, config)
    display_roughness = pd.DataFrame()
    if not display_spectrum.empty and "display_value_smoothed" in display_spectrum:
        roughness_input = display_spectrum.copy()
        roughness_input["value_strength"] = pd.to_numeric(roughness_input["display_value_smoothed"], errors="coerce")
        display_roughness = quantify_roughness(roughness_input)
    return {
        "frequency_diagnostics": diagnose_frequency_table(spectrum, config),
        "roughness": quantify_roughness(spectrum),
        "band_cv": quantify_band_cv(spectrum, config),
        "binned_spectrum": bin_spectrum(spectrum, config),
        "display_spectrum": display_spectrum,
        "display_roughness": display_roughness,
    }


def _run_rank_sensitivity(
    data: np.ndarray,
    sfreq: float,
    region_info: dict[str, Any],
    valid_epoch: np.ndarray,
    config: dict[str, Any],
    *,
    call_log: list[dict[str, Any]] | None = None,
    analysis_task_id: str = "connectivity_task",
) -> pd.DataFrame:
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
                requested_methods = [method for method in MULTIVARIATE_METHODS if method in conn_cfg.get("methods", MULTIVARIATE_METHODS)]
                results = _estimate_multivariate(
                    data[valid_epoch],
                    sfreq,
                    region_info["region_indices"][region_a],
                    region_info["region_indices"][region_b],
                    rank_seed,
                    rank_target,
                    requested_methods,
                    config,
                    call_log=call_log,
                    analysis_task_id=analysis_task_id,
                    call_purpose="rank_sensitivity",
                    region_pair=(region_a, region_b),
                )
                for method, connection in results.items():
                    values, frequencies = _connection_values(connection)
                    keep = ~_line_noise_mask(frequencies, config)
                    for component_index in range(values.shape[1]):
                        metric = np.abs(values[0, component_index]) if method == "mic" else values[0, component_index]
                        metric = metric[keep]
                        rows.append(
                            {
                                "region_a": region_a,
                                "region_b": region_b,
                                "method": method,
                                "component_index": component_index + 1 if method == "mic" else np.nan,
                                "rank_offset": offset,
                                "rank_seed": rank_seed,
                                "rank_target": rank_target,
                                "mean_strength_2_100hz": float(np.nanmean(metric)),
                                "max_strength_2_100hz": float(np.nanmax(metric)),
                                "n_epochs": int(np.sum(valid_epoch)),
                                "status": "ok",
                            }
                        )
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


def _run_segment_stability(
    data: np.ndarray,
    sfreq: float,
    region_info: dict[str, Any],
    valid_epoch: np.ndarray,
    config: dict[str, Any],
    *,
    call_log: list[dict[str, Any]] | None = None,
    analysis_task_id: str = "connectivity_task",
) -> pd.DataFrame:
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
                requested_methods = [method for method in MULTIVARIATE_METHODS if method in conn_cfg.get("methods", MULTIVARIATE_METHODS)]
                multivariate = _estimate_multivariate(
                    subset_data,
                    sfreq,
                    region_info["region_indices"][region_a],
                    region_info["region_indices"][region_b],
                    region_info["rank_map"][region_a],
                    region_info["rank_map"][region_b],
                    requested_methods,
                    config,
                    call_log=call_log,
                    analysis_task_id=analysis_task_id,
                    call_purpose="segment_stability",
                    region_pair=(region_a, region_b),
                )
                for method, connection in multivariate.items():
                    values, frequencies = _connection_values(connection)
                    keep = ~_line_noise_mask(frequencies, config)
                    for component_index in range(values.shape[1]):
                        metric = np.abs(values[0, component_index]) if method == "mic" else values[0, component_index]
                        rows.append(
                            {
                                "check_type": "segment_stability",
                                "subset_name": subset_name,
                                "region_a": region_a,
                                "region_b": region_b,
                                "method": method,
                                "component_index": component_index + 1 if method == "mic" else np.nan,
                                "mean_strength_2_100hz": float(np.nanmean(metric[keep])),
                                "n_epochs": len(indices),
                                "effective_duration_s": float(len(indices) * data.shape[-1] / sfreq),
                                "status": "ok",
                            }
                        )
                configured_methods = conn_cfg.get("methods", ["mic", "mim", "wpli2_debiased"])
                bivariate_methods = [method for method in BIVARIATE_METHODS if method in configured_methods]
                if bivariate_methods:
                    bivariate = _estimate_bivariate(
                        subset_data,
                        sfreq,
                        region_info["region_indices"][region_a],
                        region_info["region_indices"][region_b],
                        bivariate_methods,
                        config,
                        call_log=call_log,
                        analysis_task_id=analysis_task_id,
                        call_purpose="segment_stability",
                        region_pair=(region_a, region_b),
                    )
                    for method, connection in zip(bivariate_methods, bivariate, strict=True):
                        values, frequencies = _connection_values(connection)
                        keep = ~_line_noise_mask(frequencies, config)
                        pair_means = np.nanmean(values[:, 0, keep], axis=1)
                        aggregation = _region_pair_aggregation(method, config)
                        summary_value = float(np.nanmedian(pair_means) if aggregation == "median" else np.nanmean(pair_means))
                        rows.append({"check_type": "segment_stability", "subset_name": subset_name, "region_a": region_a, "region_b": region_b, "direction_order": f"{region_a}->{region_b}", "method": method, "mean_strength_2_100hz": summary_value, "aggregation_definition": f"mean_across_frequency_then_{aggregation}_across_channel_pairs", "n_epochs": len(indices), "effective_duration_s": float(len(indices) * data.shape[-1] / sfreq), "status": "ok", "n_channel_pairs": int(values.shape[0])})
                    if "dpli" in bivariate_methods:
                        reverse = _estimate_bivariate(
                            subset_data,
                            sfreq,
                            region_info["region_indices"][region_b],
                            region_info["region_indices"][region_a],
                            ["dpli"],
                            config,
                            call_log=call_log,
                            analysis_task_id=analysis_task_id,
                            call_purpose="segment_stability_dpli_reverse",
                            region_pair=(region_b, region_a),
                        )[0]
                        values, frequencies = _connection_values(reverse)
                        keep = ~_line_noise_mask(frequencies, config)
                        pair_means = np.nanmean(values[:, 0, keep], axis=1)
                        aggregation = _region_pair_aggregation("dpli", config)
                        summary_value = float(np.nanmedian(pair_means) if aggregation == "median" else np.nanmean(pair_means))
                        rows.append({"check_type": "segment_stability", "subset_name": subset_name, "region_a": region_b, "region_b": region_a, "direction_order": f"{region_b}->{region_a}", "method": "dpli", "mean_strength_2_100hz": summary_value, "aggregation_definition": f"mean_across_frequency_then_{aggregation}_across_channel_pairs", "n_epochs": len(indices), "effective_duration_s": float(len(indices) * data.shape[-1] / sfreq), "status": "ok", "n_channel_pairs": int(values.shape[0])})
            except Exception as exc:  # noqa: BLE001 - retain failed stability checks
                rows.append({"check_type": "segment_stability", "subset_name": subset_name, "region_a": region_a, "region_b": region_b, "status": f"failed: {type(exc).__name__}: {exc}"})
    return pd.DataFrame(rows)


def _append_bivariate_rows(
    rows: list[dict[str, Any]],
    failure_rows: list[dict[str, Any]],
    data: np.ndarray,
    sfreq: float,
    region_a: str,
    region_b: str,
    seed_group: pd.DataFrame,
    target_group: pd.DataFrame,
    seed_indices: np.ndarray,
    target_indices: np.ndarray,
    rank_seed: int,
    rank_target: int,
    methods: list[str],
    n_epochs: int,
    effective_duration: float,
    channel_table: pd.DataFrame,
    config: dict[str, Any],
    *,
    call_log: list[dict[str, Any]] | None = None,
    analysis_task_id: str = "connectivity_task",
    call_purpose: str = "main",
) -> None:
    """Append ordered bivariate channel-pair rows and retain pair failures."""
    if not methods:
        return
    try:
        results = _estimate_bivariate(
            data,
            sfreq,
            seed_indices,
            target_indices,
            methods,
            config,
            call_log=call_log,
            analysis_task_id=analysis_task_id,
            call_purpose=call_purpose,
            region_pair=(region_a, region_b),
        )
        pair_rows = list(zip(np.repeat(seed_indices, len(target_indices)), np.tile(target_indices, len(seed_indices))))
        expected_pairs = len(pair_rows)
        for method, connection in zip(methods, results, strict=True):
            values, frequencies = _connection_values(connection)
            if values.shape[0] != expected_pairs:
                raise ValueError(f"{method} returned {values.shape[0]} channel pairs; expected {expected_pairs}")
            meta = _spectral_meta(connection, config, data.shape[-1], sfreq)
            line_noise = _line_noise_mask(frequencies, config)
            for pair_index, (seed_index, target_index) in enumerate(pair_rows):
                seed_channel = channel_table.loc[channel_table["array_index"] == seed_index, "channel_name"].iloc[0]
                target_channel = channel_table.loc[channel_table["array_index"] == target_index, "channel_name"].iloc[0]
                for frequency_index, frequency in enumerate(frequencies):
                    row = _base_row(
                        region_a,
                        region_b,
                        seed_group,
                        target_group,
                        method,
                        frequency,
                        values[pair_index, 0, frequency_index],
                        n_epochs,
                        effective_duration,
                        rank_seed,
                        rank_target,
                        meta,
                        "cross_region_channel_pair",
                        str(seed_channel),
                        str(target_channel),
                    )
                    row["frequency_is_excluded_line_noise"] = bool(line_noise[frequency_index])
                    row["n_channel_pairs_total"] = expected_pairs
                    rows.append(row)
    except Exception as exc:  # noqa: BLE001 - preserve pair-level failure
        failure_rows.append(
            {
                "region_a": region_a,
                "region_b": region_b,
                "method": ",".join(methods),
                "failure_reason": f"{type(exc).__name__}: {exc}",
                "n_epochs": n_epochs,
                "rank_seed": rank_seed,
                "rank_target": rank_target,
                "n_components_requested": np.nan,
            }
        )


def compute_connectivity(
    data: np.ndarray,
    sfreq: float,
    channel_table: pd.DataFrame,
    quality_epoch: pd.DataFrame,
    config: dict[str, Any],
    *,
    analysis_task_id: str | None = None,
) -> dict[str, Any]:
    """Estimate selected multivariate and bivariate connectivity without concatenation."""
    conn_cfg = config.get("connectivity", {})
    methods = [str(method).strip().lower() for method in conn_cfg.get("methods", ["mic", "mim", "wpli2_debiased"])]
    requested_components = int(conn_cfg.get("n_components", 1))
    task_id = str(analysis_task_id or config.get("analysis_task_id") or "connectivity_task")
    call_log: list[dict[str, Any]] = []
    unsupported = sorted(set(methods) - set(MULTIVARIATE_METHODS) - set(BIVARIATE_METHODS))
    empty: dict[str, Any] = {
        "status": "not_run",
        "spectrum": pd.DataFrame(),
        "region_summary": pd.DataFrame(),
        "band_summary": pd.DataFrame(),
        "channel_pair_band_summary": pd.DataFrame(),
        "patterns": pd.DataFrame(),
        "redundancy_correlation": pd.DataFrame(),
        "redundancy_singular_values": pd.DataFrame(),
        "rank_summary": pd.DataFrame(),
        "rank_sensitivity": pd.DataFrame(),
        "stability": pd.DataFrame(),
        "epoch_profile": pd.DataFrame(),
        "input_checks": pd.DataFrame(),
        "failures": pd.DataFrame(columns=FAILURE_COLUMNS),
        "frequency_diagnostics": pd.DataFrame(),
        "roughness": pd.DataFrame(),
        "binned_spectrum": pd.DataFrame(),
        "display_spectrum": pd.DataFrame(),
        "display_roughness": pd.DataFrame(),
        "band_cv": pd.DataFrame(),
        "estimation_calls": pd.DataFrame(columns=ESTIMATION_CALL_COLUMNS),
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
    if n_valid < 2:
        empty["status"] = f"not_run_insufficient_valid_epochs_for_cross_epoch_estimate: {n_valid} < 2"
        return empty
    if n_valid < min_epochs:
        empty["status"] = f"not_run_insufficient_valid_epochs: {n_valid} < {min_epochs}"
        return empty
    region_info = assess_region_redundancy(array_data, sfreq, channel_table, valid_epoch, config)
    effective_duration = float(n_valid * array_data.shape[-1] / sfreq)
    pairs_to_run = selected_region_pairs(tuple(region_info["groups"]), config)
    if not pairs_to_run:
        empty.update(
            {
                "status": "not_run_no_selected_region_pairs",
                "redundancy_correlation": region_info["correlation"],
                "redundancy_singular_values": region_info["singular_values"],
                "rank_summary": region_info["summary"],
                "metadata": {"selected_region_pairs": [], "n_valid_epochs": n_valid, "effective_valid_duration_s": effective_duration},
            }
        )
        return empty
    rows: list[dict[str, Any]] = []
    pattern_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    for region_a, region_b in pairs_to_run:
        seed_group = region_info["groups"][region_a]
        target_group = region_info["groups"][region_b]
        seed_indices = region_info["region_indices"][region_a]
        target_indices = region_info["region_indices"][region_b]
        rank_seed = region_info["rank_map"][region_a]
        rank_target = region_info["rank_map"][region_b]
        multivariate_methods = [method for method in MULTIVARIATE_METHODS if method in methods]
        if requested_components < 1 and "mic" in multivariate_methods:
            failure_rows.append(
                {
                    "region_a": region_a,
                    "region_b": region_b,
                    "method": "mic",
                    "failure_reason": "n_components must be at least 1",
                    "n_epochs": n_valid,
                    "rank_seed": rank_seed,
                    "rank_target": rank_target,
                    "n_components_requested": requested_components,
                }
            )
            multivariate_methods.remove("mic")
        if "mic" in multivariate_methods and requested_components > min(rank_seed, rank_target):
            failure_rows.append(
                {
                    "region_a": region_a,
                    "region_b": region_b,
                    "method": "mic",
                    "failure_reason": f"n_components={requested_components} exceeds min(actual rank {rank_seed}, {rank_target})",
                    "n_epochs": n_valid,
                    "rank_seed": rank_seed,
                    "rank_target": rank_target,
                    "n_components_requested": requested_components,
                }
            )
            multivariate_methods.remove("mic")
        if multivariate_methods:
            try:
                multivariate = _estimate_multivariate(
                    array_data[valid_epoch],
                    sfreq,
                    seed_indices,
                    target_indices,
                    rank_seed,
                    rank_target,
                    multivariate_methods,
                    config,
                    call_log=call_log,
                    analysis_task_id=task_id,
                    call_purpose="main",
                    region_pair=(region_a, region_b),
                )
                for method, connection in multivariate.items():
                    values, frequencies = _connection_values(connection)
                    meta = _spectral_meta(connection, config, array_data.shape[-1], sfreq)
                    line_noise = _line_noise_mask(frequencies, config)
                    for component_index in range(values.shape[1]):
                        component_label = component_index + 1 if method == "mic" else None
                        for frequency_index, frequency in enumerate(frequencies):
                            row = _base_row(
                                region_a,
                                region_b,
                                seed_group,
                                target_group,
                                method,
                                frequency,
                                values[0, component_index, frequency_index],
                                n_valid,
                                effective_duration,
                                rank_seed,
                                rank_target,
                                meta,
                                "multivariate_region_pair",
                                component_index=component_label,
                                n_components_requested=requested_components,
                                n_components_returned=values.shape[1],
                            )
                            row["frequency_is_excluded_line_noise"] = bool(line_noise[frequency_index])
                            rows.append(row)
                    if method == "mic":
                        pattern_rows.extend(_pattern_rows(connection, region_a, region_b, seed_group, target_group))
            except Exception as exc:  # noqa: BLE001 - preserve pair-level failure
                failure_rows.append(
                    {
                        "region_a": region_a,
                        "region_b": region_b,
                        "method": ",".join(multivariate_methods),
                        "failure_reason": f"{type(exc).__name__}: {exc}",
                        "n_epochs": n_valid,
                        "rank_seed": rank_seed,
                        "rank_target": rank_target,
                        "n_components_requested": requested_components,
                    }
                )
        bivariate_methods = [method for method in BIVARIATE_METHODS if method in methods]
        _append_bivariate_rows(
            rows,
            failure_rows,
            array_data[valid_epoch],
            sfreq,
            region_a,
            region_b,
            seed_group,
            target_group,
            seed_indices,
            target_indices,
            rank_seed,
            rank_target,
            bivariate_methods,
            n_valid,
            effective_duration,
            channel_table,
            config,
            call_log=call_log,
            analysis_task_id=task_id,
            call_purpose="main",
        )
        # dPLI is directional: retain both ordered estimates rather than
        # mirroring the canonical region pair in the downstream matrix.
        if "dpli" in bivariate_methods:
            _append_bivariate_rows(
                rows,
                failure_rows,
                array_data[valid_epoch],
                sfreq,
                region_b,
                region_a,
                target_group,
                seed_group,
                target_indices,
                seed_indices,
                rank_target,
                rank_seed,
                ["dpli"],
                n_valid,
                effective_duration,
                channel_table,
                config,
                call_log=call_log,
                analysis_task_id=task_id,
                call_purpose="main_dpli_reverse",
            )
    spectrum = pd.DataFrame(rows)
    if spectrum.empty:
        empty.update({"status": "failed_empty_result", "redundancy_correlation": region_info["correlation"], "redundancy_singular_values": region_info["singular_values"], "rank_summary": region_info["summary"], "failures": pd.DataFrame(failure_rows, columns=FAILURE_COLUMNS), "estimation_calls": pd.DataFrame(call_log, columns=ESTIMATION_CALL_COLUMNS)})
        return empty
    frequency_products = _frequency_products(spectrum, config)
    empty.update(
        {
            "status": "ok" if not failure_rows else "ok_with_pair_failures",
            "spectrum": spectrum,
            "region_summary": _summarize_region_spectrum(spectrum, config),
            "band_summary": _band_summary(spectrum, config),
            "channel_pair_band_summary": _channel_pair_band_summary(spectrum, config),
            "patterns": pd.DataFrame(pattern_rows),
            "redundancy_correlation": region_info["correlation"],
            "redundancy_singular_values": region_info["singular_values"],
            "rank_summary": region_info["summary"],
            "rank_sensitivity": _run_rank_sensitivity(array_data, sfreq, region_info, valid_epoch, config, call_log=call_log, analysis_task_id=task_id),
            "stability": _run_segment_stability(array_data, sfreq, region_info, valid_epoch, config, call_log=call_log, analysis_task_id=task_id),
            "failures": pd.DataFrame(failure_rows, columns=FAILURE_COLUMNS),
            "estimation_calls": pd.DataFrame(call_log, columns=ESTIMATION_CALL_COLUMNS),
            **frequency_products,
            "metadata": {
                "n_valid_epochs": n_valid,
                "effective_valid_duration_s": effective_duration,
                "methods_requested": methods,
                "n_components_requested": requested_components,
                "n_jobs": int(conn_cfg.get("n_jobs", 1)),
                "analysis_task_id": task_id,
                "estimation_call_count": len(call_log),
                "estimation_cache_note": "cache_hit is false because no estimator cache is configured; call_purpose separates main, rank_sensitivity, and segment_stability estimates",
                "selected_region_pairs": [list(pair) for pair in pairs_to_run],
                "channel_sets_by_region": {region: group["channel_name"].astype(str).tolist() for region, group in region_info["groups"].items()},
                "selected_rank_by_region": {region: int(value) for region, value in region_info["rank_map"].items()},
                "rank_selection_note": "auto rank is a reproducible numerical/data-coverage rule, not an optimal physiological dimension",
                "spectral_mode": str(conn_cfg.get("mode", "multitaper")),
                "mt_bandwidth_hz": _as_float(conn_cfg.get("mt_bandwidth_hz")),
                "mt_adaptive": bool(conn_cfg.get("mt_adaptive", False)),
                "mt_low_bias": bool(conn_cfg.get("mt_low_bias", True)),
                **estimate_multitaper_metadata(array_data.shape[-1], sfreq, config),
                "frequency_range_hz": [float(conn_cfg.get("fmin_hz", 2.0)), float(conn_cfg.get("fmax_hz", 100.0))],
                "raw_spectrum_long_shape": [int(spectrum.shape[0]), int(spectrum.shape[1])],
                "region_summary_shape": [int(empty["region_summary"].shape[0]), int(empty["region_summary"].shape[1])],
                "plot_frequency_indices_note": "plot_frequency_index is zero-based within each method in connectivity_frequency_diagnostics.csv",
                "frequency_step_hz": round(float(np.median(np.diff(np.sort(spectrum["frequency_hz"].dropna().unique())))), 10) if spectrum["frequency_hz"].nunique() > 1 else np.nan,
                "frequency_grid_definition": "MNE-Connectivity multitaper frequency grid; full grid retained in connectivity_spectrum.csv",
                "line_noise_policy": resolve_line_noise_settings(config),
                "line_noise_policy_note": "line-noise intervals are annotations; no raw value is replaced and no interpolation crosses a flagged interval",
                "frequency_diagnostics_definition": "one row per method and frequency; finite/NaN/Inf counts are calculated from the saved raw long table",
                "roughness_definition": "median absolute adjacent difference, total variation and coefficient of variation over unmasked contiguous raw frequency segments",
                "display_smoothing_definition": "optional Gaussian smoothing within each continuous valid segment; display-only table, never used for band summaries",
                "multivariate_interpretation": "MIC absolute value is a strength display; MIM is raw unnormalised and may exceed 1; neither is causal direction",
                "wpli_interpretation": "wPLI is bounded [0, 1]; wpli2_debiased remains squared and finite negative estimates are retained",
                "dpli_interpretation": "dPLI is computed for both ordered channel directions; backend uses heaviside(imag(CSD), 0.5), so exactly zero imaginary CSD contributes 0.5",
                "dpli_neutral_reference": 0.5,
                "region_pair_aggregation": str(conn_cfg.get("region_pair_summary", "mean")),
                "identity_status": "file-level result only until animal/session/dose node metadata are registered",
            },
        }
    )
    return empty
