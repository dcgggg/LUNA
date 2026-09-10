from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _model_class(backend: str):
    """Select the requested parameterization implementation."""
    if backend == "specparam":
        try:
            from specparam import SpectralModel

            return SpectralModel
        except ImportError:
            pass
    try:
        from fooof import FOOOF

        return FOOOF
    except ImportError as exc:
        raise ImportError("Install specparam or fooof for parameterization") from exc


def _extract_fit_components(model: Any, model_class: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, float]:
    """Extract model components in log10 space for specparam or FOOOF."""
    if model_class.__name__ == "SpectralModel" and hasattr(model, "results"):
        aperiodic = np.asarray(model.results.params.aperiodic.asdict().get("aperiodic_fit", []), dtype=float)
        peaks = np.asarray(model.results.params.periodic.asdict().get("peak_fit", []), dtype=float)
        metrics = getattr(model.results.metrics, "results", {})
        full_log = np.asarray(model.results.model.get_component("full", "log"), dtype=float)
        aperiodic_log = np.asarray(model.results.model.get_component("aperiodic", "log"), dtype=float)
        peak_log = np.asarray(model.results.model.get_component("peak", "log"), dtype=float)
        r_squared = float(metrics.get("gof_rsquared", np.nan))
        error = float(metrics.get("error_mae", np.nan))
    else:
        aperiodic = np.asarray(getattr(model, "aperiodic_params_", []), dtype=float)
        peaks = np.asarray(getattr(model, "peak_params_", []), dtype=float)
        full_log = np.asarray(getattr(model, "fooofed_spectrum_", []), dtype=float)
        aperiodic_log = np.asarray(getattr(model, "_ap_fit", []), dtype=float)
        peak_log = np.asarray(getattr(model, "_peak_fit", []), dtype=float)
        r_squared = float(getattr(model, "r_squared_", np.nan))
        error = float(getattr(model, "error_", np.nan))
    return aperiodic, peaks, full_log, aperiodic_log, peak_log, r_squared, error


def _empty_model_row(context: dict[str, Any], base: dict[str, Any], fit_range: list[float], n_bins: int) -> dict[str, Any]:
    return {
        **context,
        **base,
        "fit_low_hz": float(fit_range[0]),
        "fit_high_hz": float(fit_range[1]),
        "n_frequency_bins": int(n_bins),
    }


def fit_single_psd_detailed(
    frequencies: np.ndarray,
    power: np.ndarray,
    config: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fit one aggregated linear PSD and return parameters plus model curves.

    The input power is linear PSD. The model is fit in the implementation's
    documented log10 representation. Failure rows are retained and are never
    silently dropped.
    """
    context = context or {}
    parameter_cfg = config.get("parameterization", {})
    backend_requested = str(parameter_cfg.get("backend", "specparam"))
    fit_range = list(parameter_cfg.get("fit_range_hz", [2.0, 150.0]))
    base = {
        **context,
        "backend_requested": backend_requested,
        "backend_used": "",
        "aperiodic_mode": str(parameter_cfg.get("aperiodic_mode", "fixed")),
        "fit_status": "failed",
        "fit_quality_status": "not_available",
        "peak_status": "fit_failed",
        "n_peaks": 0,
        "failure_reason": "",
        "r_squared": np.nan,
        "error": np.nan,
        "offset": np.nan,
        "exponent": np.nan,
        "knee": np.nan,
        "min_r_squared_requested": float(parameter_cfg.get("min_r_squared", np.nan)),
    }
    peak_rows: list[dict[str, Any]] = []
    model_rows: list[dict[str, Any]] = []
    curve_rows: list[pd.DataFrame] = []
    frequencies = np.asarray(frequencies, dtype=float)
    power = np.asarray(power, dtype=float)
    finite = np.isfinite(frequencies) & np.isfinite(power) & (power > 0)
    finite &= (frequencies >= fit_range[0]) & (frequencies <= fit_range[1])
    n_bins = int(np.sum(finite))
    if n_bins < 10:
        base["failure_reason"] = "fewer_than_10_positive_finite_frequency_bins"
        model_rows.append(_empty_model_row(context, base, fit_range, n_bins))
        return base, pd.DataFrame(peak_rows), pd.DataFrame(model_rows), pd.DataFrame()

    fit_frequencies = frequencies[finite]
    fit_power = power[finite]
    try:
        Model = _model_class(backend_requested)
        model_kwargs = {
            "peak_width_limits": tuple(parameter_cfg.get("peak_width_limits_hz", [1.0, 12.0])),
            "max_n_peaks": int(parameter_cfg.get("max_n_peaks", 6)),
            "min_peak_height": float(parameter_cfg.get("min_peak_height", 0.0)),
            "peak_threshold": float(parameter_cfg.get("peak_threshold", 2.0)),
            "aperiodic_mode": str(parameter_cfg.get("aperiodic_mode", "fixed")),
            "verbose": False,
        }
        try:
            model = Model(**model_kwargs)
        except TypeError:
            # Some specparam development builds expose a smaller constructor;
            # retain the requested values in the GUI snapshot but only pass
            # arguments supported by that installed backend.
            model_kwargs.pop("peak_threshold", None)
            model = Model(**model_kwargs)
        model.fit(fit_frequencies, fit_power, fit_range)
        aperiodic, peaks, full_log, aperiodic_log, peak_log, r_squared, error = _extract_fit_components(model, Model)
        if aperiodic.size < 2:
            raise ValueError("aperiodic_parameters_missing")
        if not (len(full_log) == len(fit_frequencies) == len(aperiodic_log) == len(peak_log)):
            raise ValueError("model_component_length_mismatch")

        base.update(
            {
                "fit_status": "ok",
                "backend_used": Model.__name__,
                "r_squared": r_squared,
                "error": error,
                "n_peaks": len(peaks.reshape(-1, 3)),
                "peak_status": "peaks_detected" if len(peaks.reshape(-1, 3)) else "no_peaks_detected",
            }
        )
        base["offset"] = float(aperiodic[0])
        if aperiodic.size == 2:
            base["exponent"] = float(aperiodic[1])
        else:
            base["knee"] = float(aperiodic[1])
            base["exponent"] = float(aperiodic[2])
        min_r_squared = float(parameter_cfg.get("min_r_squared", np.nan))
        base["fit_quality_status"] = "pass" if np.isfinite(r_squared) and r_squared >= min_r_squared else "below_configured_min_r_squared"

        for peak_index, peak in enumerate(peaks.reshape(-1, 3)):
            gaussian_sigma_hz = float(peak[2])
            peak_rows.append(
                {
                    **context,
                    "peak_index": peak_index,
                    "center_frequency_hz": float(peak[0]),
                    "peak_height_log10": float(peak[1]),
                    "peak_power_log10": float(peak[1]),
                    # The backend stores the Gaussian width as sigma.  The
                    # reported FOOOF/specparam BW is the full two-sided width
                    # 2*sigma, not FWHM.
                    "bandwidth_hz": 2.0 * gaussian_sigma_hz,
                    "gaussian_sigma_hz": gaussian_sigma_hz,
                    "bandwidth_definition": "full_width_2sigma",
                    "fit_status": base["fit_status"],
                    "fit_quality_status": base["fit_quality_status"],
                    "r_squared": r_squared,
                    "error": error,
                    "fit_low_hz": float(fit_range[0]),
                    "fit_high_hz": float(fit_range[1]),
                }
            )

        observed_log = np.log10(fit_power)
        full_power = np.power(10.0, full_log)
        aperiodic_power = np.power(10.0, aperiodic_log)
        periodic_power = full_power - aperiodic_power
        observed_minus_aperiodic_log = observed_log - aperiodic_log
        gaussian_columns: dict[str, np.ndarray] = {}
        for peak_index, peak in enumerate(peaks.reshape(-1, 3)):
            center_frequency, peak_power_log10, gaussian_sigma_hz = [float(value) for value in peak]
            # FOOOF/specparam defines bandwidth as 2 * sigma.  Reconstruct
            # each log10 Gaussian with the fitted CF/PW/BW parameters rather
            # than treating BW as sigma or exponentiating PW as raw PSD.
            sigma_hz = gaussian_sigma_hz
            if sigma_hz > 0:
                gaussian_columns[f"gaussian_{peak_index}_log10"] = peak_power_log10 * np.exp(
                    -0.5 * ((fit_frequencies - center_frequency) / sigma_hz) ** 2
                )
        gaussian_sum = np.sum(np.vstack(list(gaussian_columns.values())), axis=0) if gaussian_columns else np.zeros_like(fit_frequencies)
        curve_rows.append(
            pd.DataFrame(
                {
                    **context,
                    "frequency_hz": fit_frequencies,
                    "observed_power": fit_power,
                    "observed_log10_power": observed_log,
                    "full_model_power": full_power,
                    "full_model_log10_power": full_log,
                    "aperiodic_power": aperiodic_power,
                    "aperiodic_log10_power": aperiodic_log,
                    "periodic_component_power": periodic_power,
                    "periodic_component_log10_additive": peak_log,
                    "periodic_model_log10": peak_log,
                    "observed_minus_aperiodic_log10": observed_minus_aperiodic_log,
                    "reconstructed_gaussian_sum_log10": gaussian_sum,
                    "residual_log10": observed_log - full_log,
                    "periodic_component_negative": periodic_power < 0,
                    "fit_status": base["fit_status"],
                    "fit_quality_status": base["fit_quality_status"],
                    "backend_used": Model.__name__,
                }
            )
        )
        if gaussian_columns:
            for column, values in gaussian_columns.items():
                curve_rows[-1][column] = values
        model_rows.append(_empty_model_row(context, base, fit_range, n_bins))
        return base, pd.DataFrame(peak_rows), pd.DataFrame(model_rows), pd.concat(curve_rows, ignore_index=True)
    except Exception as exc:  # noqa: BLE001 - failed fits must be preserved
        base["failure_reason"] = f"{type(exc).__name__}: {exc}"
        model_rows.append(_empty_model_row(context, base, fit_range, n_bins))
        return base, pd.DataFrame(peak_rows), pd.DataFrame(model_rows), pd.DataFrame()


def fit_single_psd(
    frequencies: np.ndarray,
    power: np.ndarray,
    config: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    """Backward-compatible wrapper returning parameters and peaks only."""
    result = fit_single_psd_detailed(frequencies, power, config, context)
    return result[0], result[1], result[2]


def fit_channel_psd_table(psd_summary: pd.DataFrame, config: dict[str, Any]) -> dict[str, pd.DataFrame]:
    model_rows: list[pd.DataFrame] = []
    peak_rows: list[pd.DataFrame] = []
    curve_rows: list[pd.DataFrame] = []
    for (array_index, channel_name), group in psd_summary.groupby(["channel_array_index", "channel_name"]):
        context = {
            "channel_array_index": array_index,
            "channel_name": channel_name,
        }
        for column in (
            "source_unit",
            "psd_unit",
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
        ):
            if column in group:
                context[column] = group[column].iloc[0]
        _, peaks, model, curves = fit_single_psd_detailed(
            group["frequency_hz"].to_numpy(),
            group["psd_value"].to_numpy(),
            config,
            context,
        )
        model_rows.append(model)
        peak_rows.append(peaks)
        if not curves.empty:
            curve_rows.append(curves)
    return {
        "model": pd.concat(model_rows, ignore_index=True) if model_rows else pd.DataFrame(),
        "peaks": pd.concat(peak_rows, ignore_index=True) if peak_rows else pd.DataFrame(),
        "curves": pd.concat(curve_rows, ignore_index=True) if curve_rows else pd.DataFrame(),
    }
