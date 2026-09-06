from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .quality import assess_quality
from .spectral import compute_band_power, compute_psd, summarize_psd


def make_synthetic_epochs(
    n_epochs: int = 6,
    n_channels: int = 4,
    n_times: int = 5000,
    sfreq: float = 1000.0,
    seed: int = 7,
) -> tuple[np.ndarray, list[str]]:
    """Make explicitly synthetic signals for algorithm checks, not study results."""
    rng = np.random.default_rng(seed)
    time = np.arange(n_times) / sfreq
    data = rng.normal(0, 0.2, size=(n_epochs, n_channels, n_times))
    for epoch in range(n_epochs):
        for channel in range(n_channels):
            data[epoch, channel] += 1.0 * np.sin(2 * np.pi * 10 * time)
            data[epoch, channel] += 0.5 * np.sin(2 * np.pi * 40 * time + channel * 0.1)
    return data, [f"SIM_CH_{index + 1:02d}" for index in range(n_channels)]


def validate_synthetic(output_dir: str | Path) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    data, ch_names = make_synthetic_epochs()
    config = {
        "quality": {"line_noise_hz": [], "flat_std_threshold": 1e-15, "max_abs_z_threshold": 20, "saturation_fraction_threshold": 0.01},
        "psd": {"fmin_hz": 1, "fmax_hz": 100, "nperseg": 1000, "noverlap": 500, "window": "hann", "detrend": "constant", "scaling": "density", "average": "mean"},
        "bands": {"theta": [4, 8], "alpha": [8, 12], "low_gamma": [30, 55]},
        "relative_power": {"denominator_hz": [1, 100], "exclude_line_noise_hz": []},
    }
    quality = assess_quality(data, 1000.0, ch_names, config)
    psd = compute_psd(data, 1000.0, ch_names, config)
    summaries = summarize_psd(psd)
    bands = compute_band_power(psd, config)
    quality["epoch_channel"].to_csv(output / "synthetic_quality_epoch_channel.csv", index=False)
    summaries["channel"].to_csv(output / "synthetic_psd_channel.csv", index=False)
    bands.to_csv(output / "synthetic_band_power.csv", index=False)
    peak_rows = []
    for channel_name, group in summaries["channel"].groupby("channel_name"):
        peak = group.loc[group["psd_value"].idxmax()]
        peak_rows.append({"channel_name": channel_name, "peak_frequency_hz": peak["frequency_hz"]})
    peak_table = pd.DataFrame(peak_rows)
    peak_table.to_csv(output / "synthetic_peak_check.csv", index=False)
    return {
        "status": "ok",
        "synthetic_only": True,
        "peak_frequency_min_hz": float(peak_table["peak_frequency_hz"].min()),
        "peak_frequency_max_hz": float(peak_table["peak_frequency_hz"].max()),
        "n_psd_rows": len(psd),
        "effective_duration_s": float(quality["file"]["effective_valid_duration_s"].iloc[0]),
    }
