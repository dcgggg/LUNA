from __future__ import annotations

from fractions import Fraction
from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import resample_poly

from .connectivity import region_channel_pairs, selected_region_pairs
from .quality import align_epoch_quality

TDE_METHOD_NAMES = {
    1: "phase_periodicity_phase_only",
    2: "phase_combination_phase_only",
    3: "phase_periodicity_bispectrum_weighted",
    4: "phase_combination_bispectrum_weighted",
}
TDE_FAILURE_COLUMNS = ["region_a", "region_b", "method", "antisymmetrized", "failure_reason", "n_epochs"]
SPECTRUM_COLUMNS = [
    "region_a",
    "region_b",
    "method",
    "method_name",
    "antisymmetrized",
    "seed_channel",
    "target_channel",
    "frequency_band",
    "band_low_hz",
    "band_high_hz",
    "delay_ms",
    "estimate_strength",
    "n_epochs",
    "effective_duration_s",
    "analysis_sfreq_hz",
    "n_points",
    "delay_resolution_ms",
    "status",
]
PAIR_SUMMARY_COLUMNS = [
    "region_a",
    "region_b",
    "method",
    "method_name",
    "antisymmetrized",
    "seed_channel",
    "target_channel",
    "frequency_band",
    "band_low_hz",
    "band_high_hz",
    "peak_delay_ms",
    "peak_strength",
    "delay_resolution_ms",
    "direction_relative_to_seed_target",
    "n_epochs",
    "effective_duration_s",
    "status",
]


def _as_float(value: Any, default: float = np.nan) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int_list(value: Any, default: list[int]) -> list[int]:
    if value is None:
        return list(default)
    if isinstance(value, (int, np.integer)):
        value = [value]
    return [int(item) for item in value]


def _valid_epoch_mask(
    data: np.ndarray,
    quality_epoch: pd.DataFrame,
    epoch_ids: list[int] | np.ndarray | None = None,
) -> tuple[np.ndarray, int]:
    aligned_quality = align_epoch_quality(quality_epoch, len(data), epoch_ids)
    status = aligned_quality["quality_status"].astype(str).str.lower()
    quality_valid = status.isin({"pass", "ok", "warn"}).to_numpy()
    finite_valid = np.all(np.isfinite(data), axis=(1, 2))
    return quality_valid & finite_valid, int(np.sum(~finite_valid))


def _frequency_bands(config: dict[str, Any], analysis_sfreq: float) -> list[tuple[str, float, float]]:
    tde_cfg = config.get("time_delay", {})
    fmin = _as_float(tde_cfg.get("fmin_hz"), 2.0)
    fmax = _as_float(tde_cfg.get("fmax_hz"), min(80.0, analysis_sfreq / 2.0))
    nyquist = analysis_sfreq / 2.0
    if fmin < 0 or fmax <= fmin or fmax > nyquist:
        raise ValueError(f"invalid TDE frequency range: {fmin:g}-{fmax:g} Hz for Nyquist {nyquist:g} Hz")
    configured = tde_cfg.get("frequency_bands") or {"broadband": [fmin, fmax]}
    bands: list[tuple[str, float, float]] = [("broadband", fmin, fmax)]
    for name, limits in configured.items():
        if name == "broadband":
            continue
        if not isinstance(limits, (list, tuple)) or len(limits) != 2:
            raise ValueError(f"TDE frequency band {name!r} must contain [low_hz, high_hz]")
        low, high = map(float, limits)
        if low < fmin or high > fmax or high <= low:
            raise ValueError(f"TDE band {name!r}={limits} is outside configured {fmin:g}-{fmax:g} Hz range")
        bands.append((str(name), low, high))
    return bands


def _prepare_data(data: np.ndarray, sfreq: float, config: dict[str, Any]) -> tuple[np.ndarray, float, dict[str, Any]]:
    tde_cfg = config.get("time_delay", {})
    requested_sfreq = _as_float(tde_cfg.get("analysis_sfreq_hz"), sfreq)
    if requested_sfreq <= 0 or requested_sfreq > sfreq:
        raise ValueError(f"TDE analysis_sfreq_hz must be in (0, source_sfreq], got {requested_sfreq:g}")
    ratio = Fraction(requested_sfreq / sfreq).limit_denominator(1000)
    actual_sfreq = float(sfreq * ratio.numerator / ratio.denominator)
    if np.isclose(actual_sfreq, sfreq):
        prepared = np.asarray(data, dtype=float).copy()
        resampling = {
            "applied": False,
            "source_sfreq_hz": float(sfreq),
            "requested_sfreq_hz": requested_sfreq,
            "analysis_sfreq_hz": float(sfreq),
            "up": 1,
            "down": 1,
            "method": "none",
        }
    else:
        resample_window = tde_cfg.get("resample_window", "kaiser")
        if resample_window == "kaiser":
            resample_window = ("kaiser", 5.0)
        prepared = resample_poly(
            np.asarray(data, dtype=float),
            up=ratio.numerator,
            down=ratio.denominator,
            axis=-1,
            window=resample_window,
        )
        resampling = {
            "applied": True,
            "source_sfreq_hz": float(sfreq),
            "requested_sfreq_hz": requested_sfreq,
            "analysis_sfreq_hz": actual_sfreq,
            "up": int(ratio.numerator),
            "down": int(ratio.denominator),
            "method": "scipy.signal.resample_poly_with_antialias_filter",
        }
    return prepared, actual_sfreq, resampling


def _delay_points(n_times: int, sfreq: float, config: dict[str, Any]) -> tuple[int, float, tuple[float, float]]:
    tde_cfg = config.get("time_delay", {})
    configured = tde_cfg.get("n_points")
    if configured not in (None, "", "null"):
        n_points = int(configured)
    else:
        max_delay_ms = _as_float(tde_cfg.get("max_delay_ms"), 1000.0)
        n_points = 2 * round(max_delay_ms / 1000.0 * sfreq) + 1
    if n_points < 3:
        raise ValueError("TDE n_points must be at least 3")
    if n_points % 2 == 0:
        n_points += 1
    resolution_ms = 1000.0 / sfreq
    half_window_ms = (n_points - 1) / (2.0 * sfreq) * 1000.0
    return n_points, resolution_ms, (-half_window_ms, half_window_ms)


def _direction_label(delay_ms: float, resolution_ms: float) -> str:
    if not np.isfinite(delay_ms):
        return "unresolved"
    if abs(delay_ms) <= resolution_ms / 2.0:
        return "near_zero_delay"
    return "seed_to_target_positive" if delay_ms > 0 else "target_to_seed_negative"


def _empty_result(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "spectrum": pd.DataFrame(columns=SPECTRUM_COLUMNS),
        "region_spectrum": pd.DataFrame(),
        "channel_pair_summary": pd.DataFrame(columns=PAIR_SUMMARY_COLUMNS),
        "band_summary": pd.DataFrame(),
        "input_checks": pd.DataFrame(columns=["check", "value", "status", "note"]),
        "failures": pd.DataFrame(columns=TDE_FAILURE_COLUMNS),
        "metadata": {},
    }


def _load_pybispectra() -> tuple[Any, Any]:
    try:
        from pybispectra import TDE, compute_fft
    except ImportError as exc:
        raise ImportError(f"Install pybispectra for time-delay analysis: {exc}") from exc
    return TDE, compute_fft


def _as_result_tuple(results: Any) -> tuple[Any, ...]:
    return results if isinstance(results, tuple) else (results,)


def _append_result_rows(
    rows: list[dict[str, Any]],
    pair_rows: list[dict[str, Any]],
    result: Any,
    region_a: str,
    region_b: str,
    method: int,
    antisymmetrized: bool,
    bands: list[tuple[str, float, float]],
    channel_pairs: pd.DataFrame,
    n_epochs: int,
    effective_duration: float,
    analysis_sfreq: float,
    n_points: int,
    resolution_ms: float,
) -> None:
    values = np.asarray(result.get_results(copy=False), dtype=float)
    times = np.asarray(result.times, dtype=float)
    if values.ndim != 3 or values.shape[1] != len(bands) or values.shape[2] != len(times):
        raise ValueError(f"unexpected PyBispectra TDE result shape: {values.shape}")
    method_name = TDE_METHOD_NAMES.get(method, f"method_{method}")
    for connection_index, pair in channel_pairs.reset_index(drop=True).iterrows():
        for band_index, (band_name, band_low, band_high) in enumerate(bands):
            curve = values[connection_index, band_index]
            peak_index = int(np.nanargmax(curve)) if np.any(np.isfinite(curve)) else -1
            peak_delay = float(times[peak_index]) if peak_index >= 0 else np.nan
            peak_strength = float(curve[peak_index]) if peak_index >= 0 else np.nan
            pair_rows.append(
                {
                    "region_a": region_a,
                    "region_b": region_b,
                    "method": method,
                    "method_name": method_name,
                    "antisymmetrized": antisymmetrized,
                    "seed_channel": pair["seed_channel"],
                    "target_channel": pair["target_channel"],
                    "frequency_band": band_name,
                    "band_low_hz": band_low,
                    "band_high_hz": band_high,
                    "peak_delay_ms": peak_delay,
                    "peak_strength": peak_strength,
                    "delay_resolution_ms": resolution_ms,
                    "direction_relative_to_seed_target": _direction_label(peak_delay, resolution_ms),
                    "n_epochs": n_epochs,
                    "effective_duration_s": effective_duration,
                    "status": "ok" if peak_index >= 0 else "no_finite_peak",
                }
            )
            if peak_index < 0:
                continue
            for delay_index, delay_ms in enumerate(times):
                rows.append(
                    {
                        "region_a": region_a,
                        "region_b": region_b,
                        "method": method,
                        "method_name": method_name,
                        "antisymmetrized": antisymmetrized,
                        "seed_channel": pair["seed_channel"],
                        "target_channel": pair["target_channel"],
                        "frequency_band": band_name,
                        "band_low_hz": band_low,
                        "band_high_hz": band_high,
                        "delay_ms": float(delay_ms),
                        "estimate_strength": float(curve[delay_index]),
                        "n_epochs": n_epochs,
                        "effective_duration_s": effective_duration,
                        "analysis_sfreq_hz": analysis_sfreq,
                        "n_points": n_points,
                        "delay_resolution_ms": resolution_ms,
                        "status": "ok",
                    }
                )


def _region_summary(spectrum: pd.DataFrame) -> pd.DataFrame:
    if spectrum.empty:
        return pd.DataFrame()
    spectrum = spectrum.copy()
    spectrum["_channel_pair"] = spectrum["seed_channel"].astype(str) + "||" + spectrum["target_channel"].astype(str)
    keys = ["region_a", "region_b", "method", "method_name", "antisymmetrized", "frequency_band", "band_low_hz", "band_high_hz", "delay_ms"]
    summary = (
        spectrum.groupby(keys, dropna=False)
        .agg(
            estimate_strength=("estimate_strength", "median"),
            estimate_strength_mean=("estimate_strength", "mean"),
            estimate_strength_sd=("estimate_strength", "std"),
            n_channel_pairs=("_channel_pair", "nunique"),
            n_epochs=("n_epochs", "first"),
            effective_duration_s=("effective_duration_s", "first"),
            analysis_sfreq_hz=("analysis_sfreq_hz", "first"),
            n_points=("n_points", "first"),
            delay_resolution_ms=("delay_resolution_ms", "first"),
        )
        .reset_index()
    )
    return summary


def _band_summary(region_spectrum: pd.DataFrame, pair_summary: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    if region_spectrum.empty:
        return pd.DataFrame()
    group_columns = ["region_a", "region_b", "method", "method_name", "antisymmetrized", "frequency_band", "band_low_hz", "band_high_hz"]
    rows: list[dict[str, Any]] = []
    for key, group in region_spectrum.groupby(group_columns, dropna=False):
        peak = group.loc[group["estimate_strength"].idxmax()]
        pair_group = pair_summary.loc[
            (pair_summary["region_a"] == peak["region_a"])
            & (pair_summary["region_b"] == peak["region_b"])
            & (pair_summary["method"] == peak["method"])
            & (pair_summary["antisymmetrized"] == peak["antisymmetrized"])
            & (pair_summary["frequency_band"] == peak["frequency_band"])
        ]
        pair_median = float(pair_group["peak_delay_ms"].median()) if not pair_group.empty else np.nan
        pair_mad = float((pair_group["peak_delay_ms"] - pair_median).abs().median()) if not pair_group.empty else np.nan
        delay_min = float(group["delay_ms"].min())
        delay_max = float(group["delay_ms"].max())
        boundary_margin = _as_float(config.get("time_delay", {}).get("quality_boundary_margin_ms"), 10.0)
        max_pair_mad = _as_float(config.get("time_delay", {}).get("quality_max_channel_pair_mad_ms"), 100.0)
        quality_flags: list[str] = []
        if float(peak["delay_ms"]) <= delay_min + boundary_margin or float(peak["delay_ms"]) >= delay_max - boundary_margin:
            quality_flags.append("peak_at_delay_window_edge")
        if np.isfinite(pair_mad) and pair_mad > max_pair_mad:
            quality_flags.append("high_channel_pair_delay_dispersion")
        if np.isfinite(pair_median) and abs(float(peak["delay_ms"]) - pair_median) > max_pair_mad:
            quality_flags.append("region_peak_differs_from_channel_median")
        rows.append(
            {
                **dict(zip(group_columns, key)),
                "region_peak_delay_ms": float(peak["delay_ms"]),
                "region_peak_strength": float(peak["estimate_strength"]),
                "channel_pair_median_delay_ms": pair_median,
                "channel_pair_mad_delay_ms": pair_mad,
                "channel_pair_median_peak_strength": float(pair_group["peak_strength"].median()) if not pair_group.empty else np.nan,
                "n_channel_pairs": len(pair_group),
                "n_epochs": int(peak["n_epochs"]),
                "effective_duration_s": float(peak["effective_duration_s"]),
                "delay_resolution_ms": float(peak["delay_resolution_ms"]),
                "direction_relative_to_seed_target": _direction_label(float(peak["delay_ms"]), float(peak["delay_resolution_ms"])),
                "delay_window_min_ms": delay_min,
                "delay_window_max_ms": delay_max,
                "quality_flag": ";".join(quality_flags) if quality_flags else "ok",
                "status": "ok",
            }
        )
    return pd.DataFrame(rows)


def compute_time_delay(
    data: np.ndarray,
    sfreq: float,
    channel_table: pd.DataFrame,
    quality_epoch: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Compute PyBispectra TDE over valid, non-concatenated epochs.

    Positive delay means the seed region/channel leads the target region/channel;
    it is a signal timing convention, not proof of anatomical or causal direction.
    """
    tde_cfg = config.get("time_delay", {})
    result = _empty_result("not_run")
    try:
        TDE, compute_fft = _load_pybispectra()
    except ImportError as exc:
        result["status"] = "not_run_missing_optional_dependency"
        result["failures"] = pd.DataFrame([{"region_a": "", "region_b": "", "method": "", "antisymmetrized": "", "failure_reason": str(exc), "n_epochs": 0}], columns=TDE_FAILURE_COLUMNS)
        return result
    groups = region_channel_pairs(channel_table)
    if groups.empty:
        result["status"] = "not_run_channel_region_mapping_incomplete"
        return result
    region_names = tuple(dict.fromkeys(groups["region_a"].tolist() + groups["region_b"].tolist()))
    pair_config = {"connectivity": {"selected_region_pairs": tde_cfg.get("selected_region_pairs")}}
    requested_pairs = selected_region_pairs(region_names, pair_config)
    if tde_cfg.get("selected_region_pairs") is not None:
        requested_keys = {frozenset(pair) for pair in requested_pairs}
        groups = groups.loc[
            groups.apply(lambda row: frozenset((str(row["region_a"]), str(row["region_b"]))) in requested_keys, axis=1)
        ].copy()
        if groups.empty:
            result["status"] = "not_run_no_selected_region_pairs"
            return result
    valid_epoch, n_nonfinite = _valid_epoch_mask(np.asarray(data), quality_epoch)
    n_valid = int(valid_epoch.sum())
    min_epochs = int(tde_cfg.get("min_epochs", 5))
    duration = float(n_valid * data.shape[-1] / sfreq)
    result["input_checks"] = pd.DataFrame(
        [
            {"check": "valid_epoch_count", "value": n_valid, "status": "ok" if n_valid >= min_epochs else "fail", "note": "quality fail and nonfinite epochs are excluded; no epochs are concatenated"},
            {"check": "nonfinite_epoch_count", "value": n_nonfinite, "status": "ok" if n_nonfinite == 0 else "warn", "note": "nonfinite epochs are retained in quality trace and excluded from TDE"},
            {"check": "effective_valid_duration_s", "value": duration, "status": "ok", "note": "sum of valid epoch durations; not a continuous recording duration"},
            {"check": "selected_region_pair_count", "value": len(requested_pairs), "status": "ok", "note": "only selected cross-region pairs are estimated; seed/target labels preserve the TDE convention"},
            {"check": "reference_policy", "value": "acquisition_reference_preserved", "status": "ok", "note": "no rereference, bipolar derivation, or orthogonalisation"},
        ],
        columns=["check", "value", "status", "note"],
    )
    if n_valid < min_epochs:
        result["status"] = f"not_run_insufficient_valid_epochs: {n_valid} < {min_epochs}"
        return result
    try:
        prepared, analysis_sfreq, resampling = _prepare_data(np.asarray(data)[valid_epoch], float(sfreq), config)
        bands = _frequency_bands(config, analysis_sfreq)
        n_points, resolution_ms, delay_window = _delay_points(prepared.shape[-1], analysis_sfreq, config)
        method_values = _as_int_list(tde_cfg.get("methods"), [int(tde_cfg.get("primary_method", 1))])
        configured_antisym = tde_cfg.get("antisymmetrized")
        if configured_antisym is None:
            configured_antisym = [bool(tde_cfg.get("primary_antisymmetrized", True))]
        antisym_values = [bool(value) for value in configured_antisym]
        if any(method not in TDE_METHOD_NAMES for method in method_values):
            raise ValueError(f"TDE methods must be integers 1-4, got {method_values}")
        if not antisym_values:
            raise ValueError("time_delay.antisymmetrized must contain at least one boolean")
        fft_coeffs, freqs = compute_fft(
            prepared,
            sampling_freq=analysis_sfreq,
            # PyBispectra uses the FFT length to define the returned delay
            # window. The configured n_points therefore controls both the
            # delay window and the frequency grid; this trade-off is recorded.
            n_points=n_points,
            window=str(tde_cfg.get("fft_window", "hamming")),
            n_jobs=int(tde_cfg.get("n_jobs", 1)),
            verbose=False,
        )
        result["input_checks"] = pd.concat(
            [
                result["input_checks"],
                pd.DataFrame(
                    [
                        {"check": "analysis_sfreq_hz", "value": analysis_sfreq, "status": "ok", "note": "TDE-only analysis sampling rate after configured anti-aliased resampling"},
                        {"check": "delay_window_ms", "value": f"{delay_window[0]:g},{delay_window[1]:g}", "status": "ok", "note": "PyBispectra delay window determined by TDE FFT n_points"},
                        {"check": "delay_resolution_ms", "value": resolution_ms, "status": "ok", "note": "one delay sample per analysis sampling interval"},
                        {"check": "fft_frequency_resolution_hz", "value": analysis_sfreq / n_points, "status": "ok", "note": "frequency grid trade-off induced by the configured delay window"},
                        {"check": "frequency_bands", "value": ";".join(f"{name}:{low:g}-{high:g}Hz" for name, low, high in bands), "status": "ok", "note": "configured frequency-resolved TDE bands; no per-result peak selection"},
                    ],
                    columns=["check", "value", "status", "note"],
                ),
            ],
            ignore_index=True,
        )
        spectrum_rows: list[dict[str, Any]] = []
        pair_summary_rows: list[dict[str, Any]] = []
        failure_rows: list[dict[str, Any]] = []
        for (region_a, region_b), pair_group in groups.groupby(["region_a", "region_b"], sort=False):
            pair_group = pair_group.reset_index(drop=True)
            indices = (tuple(pair_group["seed_array_index"].astype(int)), tuple(pair_group["target_array_index"].astype(int)))
            for method in method_values:
                for antisymmetrized in antisym_values:
                    try:
                        tde = TDE(data=fft_coeffs, freqs=freqs, sampling_freq=analysis_sfreq, verbose=False)
                        tde.compute(
                            indices=indices,
                            fmin=tuple(band[1] for band in bands),
                            fmax=tuple(band[2] for band in bands),
                            antisym=antisymmetrized,
                            method=method,
                            n_jobs=int(tde_cfg.get("n_jobs", 1)),
                        )
                        results = _as_result_tuple(tde.results)
                        if len(results) != 1:
                            raise ValueError(f"expected one result for one method/antisym setting, got {len(results)}")
                        _append_result_rows(
                            spectrum_rows,
                            pair_summary_rows,
                            results[0],
                            str(region_a),
                            str(region_b),
                            method,
                            antisymmetrized,
                            bands,
                            pair_group,
                            n_valid,
                            duration,
                            analysis_sfreq,
                            n_points,
                            resolution_ms,
                        )
                    except Exception as exc:  # noqa: BLE001 - preserve pair/method failure
                        failure_rows.append({"region_a": region_a, "region_b": region_b, "method": method, "antisymmetrized": antisymmetrized, "failure_reason": f"{type(exc).__name__}: {exc}", "n_epochs": n_valid})
        spectrum = pd.DataFrame(spectrum_rows, columns=SPECTRUM_COLUMNS)
        pair_summary = pd.DataFrame(pair_summary_rows, columns=PAIR_SUMMARY_COLUMNS)
        region_spectrum = _region_summary(spectrum)
        result.update(
            {
                "status": "ok" if not failure_rows else "ok_with_pair_failures",
                "spectrum": spectrum,
                "region_spectrum": region_spectrum,
                "channel_pair_summary": pair_summary,
                "band_summary": _band_summary(region_spectrum, pair_summary, config),
                "failures": pd.DataFrame(failure_rows, columns=TDE_FAILURE_COLUMNS),
                "metadata": {
                    "backend": "pybispectra",
                    "pybispectra_version": __import__("pybispectra").__version__,
                    "n_valid_epochs": n_valid,
                    "effective_valid_duration_s": duration,
                    "source_sfreq_hz": float(sfreq),
                    "analysis_sfreq_hz": analysis_sfreq,
                    "resampling": resampling,
                    "fft_window": str(tde_cfg.get("fft_window", "hamming")),
                    "fft_n_points": n_points,
                    "fft_frequency_resolution_hz": float(analysis_sfreq / n_points),
                    "tde_n_points": n_points,
                    "delay_window_ms": list(delay_window),
                    "delay_resolution_ms": resolution_ms,
                    "methods": method_values,
                    "antisymmetrized": antisym_values,
                    "frequency_bands": [{"name": name, "low_hz": low, "high_hz": high} for name, low, high in bands],
                    "selected_region_pairs": [list(pair) for pair in requested_pairs],
                    "n_channel_pairs_per_region_pair": {
                        f"{region_a}-{region_b}": len(group)
                        for (region_a, region_b), group in groups.groupby(["region_a", "region_b"], sort=False)
                    },
                    "sign_convention": "positive delay means seed region/channel leads target region/channel; negative means target leads seed",
                    "interpretation_limit": "delay sign is not anatomical or causal proof; common reference and signal mixing are not eliminated by antisymmetrisation",
                    "n_nonfinite_epochs_excluded": n_nonfinite,
                    "identity_status": "file-level result until animal/session/dose metadata are registered",
                },
            }
        )
        return result
    except Exception as exc:  # noqa: BLE001 - return explicit analysis failure
        result["status"] = f"failed: {type(exc).__name__}: {exc}"
        result["failures"] = pd.DataFrame([{"region_a": "", "region_b": "", "method": "", "antisymmetrized": "", "failure_reason": f"{type(exc).__name__}: {exc}", "n_epochs": n_valid}], columns=TDE_FAILURE_COLUMNS)
        return result
