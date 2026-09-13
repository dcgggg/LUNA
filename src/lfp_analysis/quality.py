from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import welch


def _robust_max_z(signal: np.ndarray) -> float:
    finite = signal[np.isfinite(signal)]
    if finite.size == 0:
        return float("nan")
    median = np.median(finite)
    mad = np.median(np.abs(finite - median))
    scale = 1.4826 * mad
    if scale <= np.finfo(float).eps:
        scale = np.std(finite)
    if scale <= np.finfo(float).eps:
        return 0.0
    return float(np.max(np.abs((finite - median) / scale)))


def _line_noise_ratio(signal: np.ndarray, sfreq: float, candidates: list[float]) -> float:
    finite = signal[np.isfinite(signal)]
    if finite.size < 8 or not candidates:
        return float("nan")
    nperseg = min(1000, finite.size)
    freqs, power = welch(finite, fs=sfreq, nperseg=nperseg, noverlap=nperseg // 2, scaling="density")
    ratios = []
    for line_hz in candidates:
        idx = int(np.argmin(np.abs(freqs - float(line_hz))))
        local = (freqs >= line_hz - 5) & (freqs <= line_hz + 5)
        local[idx] = False
        baseline = np.median(power[local]) if np.any(local) else np.nan
        ratios.append(power[idx] / baseline if baseline > 0 else np.nan)
    return float(np.nanmax(ratios)) if np.any(np.isfinite(ratios)) else float("nan")


def _epoch_hash(epoch: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(epoch).tobytes()).hexdigest()


def align_epoch_quality(
    quality_epoch: pd.DataFrame | None,
    n_epochs: int,
    epoch_ids: list[int] | np.ndarray | None = None,
) -> pd.DataFrame:
    """Align epoch-level QC rows to the data order without silent reordering.

    ``analysis_epoch_index`` is preferred for selected data. ``epoch_index`` is
    used for full-file data or when explicit ``epoch_ids`` are supplied. A
    legacy table without an identifier is accepted only when its row count is
    exactly equal to the data count and is marked as row-order alignment. Any
    missing quality row or status is conservative and therefore not valid.
    """
    frame = quality_epoch.copy() if isinstance(quality_epoch, pd.DataFrame) else pd.DataFrame()
    expected = list(range(int(n_epochs))) if epoch_ids is None else [int(value) for value in epoch_ids]
    if len(expected) != int(n_epochs) or len(set(expected)) != len(expected):
        raise ValueError("epoch_ids_must_be_unique_and_match_data_length")

    key = "analysis_epoch_index" if "analysis_epoch_index" in frame.columns else ("epoch_index" if "epoch_index" in frame.columns else None)
    if key is None:
        if len(frame) != int(n_epochs):
            frame = pd.DataFrame(index=range(int(n_epochs)))
            frame["quality_alignment_status"] = "missing_epoch_identifier_and_row"
        else:
            frame = frame.reset_index(drop=True)
            frame["quality_alignment_status"] = "legacy_row_order"
        frame["analysis_epoch_index"] = np.arange(int(n_epochs), dtype=int)
    else:
        identifiers = pd.to_numeric(frame[key], errors="coerce")
        if identifiers.isna().any() or identifiers.duplicated().any():
            raise ValueError(f"{key}_must_be_unique_and_finite")
        indexed = frame.assign(_epoch_key=identifiers.astype(int)).set_index("_epoch_key", drop=False)
        frame = indexed.reindex(expected).reset_index(drop=True)
        frame["analysis_epoch_index"] = np.arange(int(n_epochs), dtype=int)
        frame["quality_alignment_status"] = np.where(frame[key].notna(), "id_aligned", "missing_epoch_row")
    if "quality_status" not in frame.columns:
        frame["quality_status"] = "missing_quality_status"
    frame["quality_status"] = frame["quality_status"].where(frame["quality_status"].notna(), "missing_quality_status")
    return frame


def assess_quality(data: np.ndarray, sfreq: float, ch_names: list[str], config: dict[str, Any]) -> dict[str, pd.DataFrame]:
    """Return flags and metrics without changing or excluding signal data."""
    data = np.asarray(data, dtype=float)
    if data.ndim != 3:
        raise ValueError(f"Expected data shape (epochs, channels, times), got {data.shape}")
    quality_cfg = config.get("quality", {})
    flat_threshold = float(quality_cfg.get("flat_std_threshold", 1e-15))
    max_z_threshold = float(quality_cfg.get("max_abs_z_threshold", 20.0))
    saturation_threshold = float(quality_cfg.get("saturation_fraction_threshold", 0.01))
    duplicate_detection = str(quality_cfg.get("duplicate_epoch_detection", True)).strip().lower() in {"1", "true", "yes", "on"}
    line_candidates = [float(value) for value in quality_cfg.get("line_noise_hz", [])]
    line_ratio_threshold = float(quality_cfg.get("line_noise_peak_ratio_threshold", 8.0))
    epoch_hashes = [_epoch_hash(epoch) for epoch in data]
    duplicate_hashes = {value for value in epoch_hashes if epoch_hashes.count(value) > 1} if duplicate_detection else set()

    rows: list[dict[str, Any]] = []
    for epoch_index, epoch in enumerate(data):
        for channel_index, channel_name in enumerate(ch_names):
            signal = epoch[channel_index]
            finite = np.isfinite(signal)
            finite_count = int(np.sum(finite))
            nan_count = int(np.sum(np.isnan(signal)))
            inf_count = int(np.sum(np.isinf(signal)))
            finite_signal = signal[finite]
            std = float(np.std(finite_signal)) if finite_count else float("nan")
            max_abs = float(np.max(np.abs(finite_signal))) if finite_count else float("nan")
            max_z = _robust_max_z(signal)
            saturation_fraction = 0.0
            if finite_count:
                signal_max = np.max(finite_signal)
                signal_min = np.min(finite_signal)
                saturation_fraction = float(
                    max(np.mean(finite_signal == signal_max), np.mean(finite_signal == signal_min))
                )
            line_ratio = _line_noise_ratio(signal, sfreq, line_candidates)
            flags: list[str] = []
            if nan_count or inf_count:
                flags.append("nonfinite")
            if finite_count == 0 or (finite_count and std <= flat_threshold):
                flags.append("flat")
            if np.isfinite(max_z) and max_z > max_z_threshold:
                flags.append("abnormal_amplitude")
            if saturation_fraction >= saturation_threshold and finite_count:
                flags.append("possible_saturation")
            if np.isfinite(line_ratio) and line_ratio >= line_ratio_threshold:
                flags.append("line_noise_peak")
            if epoch_hashes[epoch_index] in duplicate_hashes:
                flags.append("duplicate_epoch")
            status = "fail" if any(flag in flags for flag in ("nonfinite", "flat")) else ("warn" if flags else "ok")
            rows.append(
                {
                    "epoch_index": epoch_index,
                    "channel_array_index": channel_index,
                    "channel_name": channel_name,
                    "finite_sample_count": finite_count,
                    "nonfinite_sample_count": nan_count + inf_count,
                    "std": std,
                    "max_abs": max_abs,
                    "max_abs_robust_z": max_z,
                    "saturation_fraction": saturation_fraction,
                    "line_noise_peak_ratio": line_ratio,
                    "quality_status": status,
                    "quality_flags": ";".join(flags),
                    "issue_score": len(flags),
                }
            )
    channel_df = pd.DataFrame(rows)
    epoch_df = (
        channel_df.groupby("epoch_index", as_index=False)
        .agg(
            n_channels=("channel_name", "size"),
            n_fail_channels=("quality_status", lambda values: int(np.sum(values == "fail"))),
            n_warn_channels=("quality_status", lambda values: int(np.sum(values == "warn"))),
            min_finite_samples=("finite_sample_count", "min"),
            max_issue_score=("issue_score", "max"),
        )
    )
    epoch_df["valid_duration_s"] = epoch_df["min_finite_samples"] / float(sfreq)
    epoch_df["quality_status"] = np.where(
        epoch_df["n_fail_channels"] > 0,
        "fail",
        np.where(epoch_df["n_warn_channels"] > 0, "warn", "ok"),
    )
    channel_summary = (
        channel_df.groupby(["channel_array_index", "channel_name"], as_index=False)
        .agg(
            n_epochs=("epoch_index", "nunique"),
            n_fail_epochs=("quality_status", lambda values: int(np.sum(values == "fail"))),
            n_warn_epochs=("quality_status", lambda values: int(np.sum(values == "warn"))),
            mean_std=("std", "mean"),
            max_abs=("max_abs", "max"),
            max_issue_score=("issue_score", "max"),
        )
    )
    file_summary = pd.DataFrame(
        [
            {
                "n_epochs": data.shape[0],
                "n_channels": data.shape[1],
                "n_times": data.shape[2],
                "sampling_rate_hz": sfreq,
                "nominal_duration_s": data.shape[0] * data.shape[2] / sfreq,
                "effective_valid_duration_s": float(epoch_df["valid_duration_s"].sum()),
                "n_fail_epoch_channel_rows": int(np.sum(channel_df["quality_status"] == "fail")),
                "n_warn_epoch_channel_rows": int(np.sum(channel_df["quality_status"] == "warn")),
                "n_duplicate_epoch_rows": int(len(epoch_hashes) - len(set(epoch_hashes))) if duplicate_detection else 0,
                "duplicate_epoch_detection": duplicate_detection,
                "check_frequency_band_hz": quality_cfg.get("check_frequency_band_hz", [1.0, 200.0]),
                "frequency_band_check_status": "not_evaluated_by_time_domain_qc; verify against PSD frequency range",
            }
        ]
    )
    return {
        "epoch_channel": channel_df,
        "epoch": epoch_df,
        "channel": channel_summary,
        "file": file_summary,
    }
