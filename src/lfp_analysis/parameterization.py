from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _model_class(backend: str):
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


def fit_single_psd(
    frequencies: np.ndarray,
    power: np.ndarray,
    config: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    """Fit one aggregated PSD with specparam/FOOOF and retain failures."""
    context = context or {}
    parameter_cfg = config.get("parameterization", {})
    base = {
        **context,
        "backend_requested": parameter_cfg.get("backend", "specparam"),
        "fit_status": "failed",
        "failure_reason": "",
        "r_squared": np.nan,
        "error": np.nan,
        "offset": np.nan,
        "exponent": np.nan,
        "knee": np.nan,
    }
    peak_rows: list[dict[str, Any]] = []
    model_rows: list[dict[str, Any]] = []
    frequencies = np.asarray(frequencies, dtype=float)
    power = np.asarray(power, dtype=float)
    finite = np.isfinite(frequencies) & np.isfinite(power) & (power > 0)
    fit_range = parameter_cfg.get("fit_range_hz", [2.0, 150.0])
    finite &= (frequencies >= fit_range[0]) & (frequencies <= fit_range[1])
    if np.sum(finite) < 10:
        base["failure_reason"] = "fewer_than_10_positive_finite_frequency_bins"
        return base, pd.DataFrame(peak_rows), pd.DataFrame(model_rows)
    try:
        Model = _model_class(str(parameter_cfg.get("backend", "specparam")))
        model = Model(
            peak_width_limits=tuple(parameter_cfg.get("peak_width_limits_hz", [1.0, 12.0])),
            max_n_peaks=int(parameter_cfg.get("max_n_peaks", 6)),
            min_peak_height=float(parameter_cfg.get("min_peak_height", 0.0)),
            aperiodic_mode=str(parameter_cfg.get("aperiodic_mode", "fixed")),
            verbose=False,
        )
        model.fit(frequencies[finite], power[finite], fit_range)
        if Model.__name__ == "SpectralModel" and hasattr(model, "results"):
            aperiodic = np.asarray(model.results.params.aperiodic.asdict().get("aperiodic_fit", []), dtype=float)
            peaks = np.asarray(model.results.params.periodic.asdict().get("peak_fit", []), dtype=float)
            metrics = getattr(model.results.metrics, "results", {})
            r_squared = metrics.get("gof_rsquared", np.nan)
            error = metrics.get("error_mae", np.nan)
        else:
            aperiodic = np.asarray(getattr(model, "aperiodic_params_", []), dtype=float)
            peaks = np.asarray(getattr(model, "peak_params_", []), dtype=float)
            r_squared = getattr(model, "r_squared_", np.nan)
            error = getattr(model, "error_", np.nan)
        base.update(
            {
                "fit_status": "ok",
                "backend_used": Model.__name__,
                "r_squared": float(r_squared),
                "error": float(error),
            }
        )
        if aperiodic.size >= 2:
            base["offset"] = float(aperiodic[0])
            if aperiodic.size == 2:
                base["exponent"] = float(aperiodic[1])
            else:
                base["knee"] = float(aperiodic[1])
                base["exponent"] = float(aperiodic[2])
        for peak_index, peak in enumerate(peaks.reshape(-1, 3)):
            peak_rows.append(
                {
                    **context,
                    "peak_index": peak_index,
                    "center_frequency_hz": float(peak[0]),
                    "peak_height_log10": float(peak[1]),
                    "bandwidth_hz": float(peak[2]),
                    "fit_status": base["fit_status"],
                }
            )
        model_rows.append({**context, **base, "fit_low_hz": fit_range[0], "fit_high_hz": fit_range[1]})
        return base, pd.DataFrame(peak_rows), pd.DataFrame(model_rows)
    except Exception as exc:  # noqa: BLE001 - failed fits are retained as result rows
        base["failure_reason"] = f"{type(exc).__name__}: {exc}"
        model_rows.append({**context, **base, "fit_low_hz": fit_range[0], "fit_high_hz": fit_range[1]})
        return base, pd.DataFrame(peak_rows), pd.DataFrame(model_rows)


def fit_channel_psd_table(psd_summary: pd.DataFrame, config: dict[str, Any]) -> dict[str, pd.DataFrame]:
    model_rows: list[pd.DataFrame] = []
    peak_rows: list[pd.DataFrame] = []
    for (array_index, channel_name), group in psd_summary.groupby(["channel_array_index", "channel_name"]):
        _, peaks, model = fit_single_psd(
            group["frequency_hz"].to_numpy(),
            group["psd_value"].to_numpy(),
            config,
            {"channel_array_index": array_index, "channel_name": channel_name},
        )
        model_rows.append(model)
        peak_rows.append(peaks)
    return {
        "model": pd.concat(model_rows, ignore_index=True) if model_rows else pd.DataFrame(),
        "peaks": pd.concat(peak_rows, ignore_index=True) if peak_rows else pd.DataFrame(),
    }
