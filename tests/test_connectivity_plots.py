from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from lfp_analysis.connectivity_plots import (
    plot_channel_pair_matrix,
    plot_matrix,
    plot_spectrum,
    prepare_connectivity,
)


def _tables() -> dict[str, pd.DataFrame]:
    frequencies = [5.0, 6.0, 7.0]
    spectrum = []
    bands = []
    for method, component, values in (("mic", 1, [0.2, -0.4, 0.3]), ("mic", 2, [0.1, 0.2, -0.1]), ("mim", np.nan, [1.2, 1.4, 1.3])):
        for frequency, value in zip(frequencies, values, strict=True):
            spectrum.append({"method": method, "region_a": "M1", "region_b": "STR", "component_index": component, "frequency_hz": frequency, "value_raw": value, "value_strength": abs(value) if method == "mic" else value, "n_epochs": 8, "frequency_is_excluded_line_noise": False})
        bands.append({"method": method, "region_a": "M1", "region_b": "STR", "component_index": component, "band": "alpha", "band_low_hz": 5.0, "band_high_hz": 7.0, "value_raw_or_summary": np.mean(values), "value_strength": np.mean(np.abs(values)) if method == "mic" else np.mean(values), "status": "ok"})
    return {"region_summary": pd.DataFrame(spectrum), "band_summary": pd.DataFrame(bands)}


def test_connectivity_plot_uses_same_component_and_band_value():
    tables = _tables()
    prepared = prepare_connectivity(tables, "mic", 1, [["M1", "STR"]])
    figure, axes = plt.subplots(1, 2, figsize=(8, 4))
    plot_spectrum(axes[0], prepared, {"name": "alpha", "low_hz": 5.0, "high_hz": 7.0})
    info = plot_matrix(axes[1], figure, prepared, {"name": "alpha", "low_hz": 5.0, "high_hz": 7.0})
    line = axes[0].lines[0]
    assert np.allclose(line.get_ydata(), [0.2, 0.4, 0.3])
    assert info["matrix"][0, 1] == np.mean(np.abs([0.2, -0.4, 0.3]))
    assert info["matrix"][1, 0] == info["matrix"][0, 1]
    assert info["matrix"][0, 0] != info["matrix"][0, 0]
    plt.close(figure)


def test_mim_plot_keeps_raw_value_and_does_not_use_mic_component_axis():
    prepared = prepare_connectivity(_tables(), "mim", 99, [["M1", "STR"]])
    assert len(prepared["spectrum"]) == 3
    assert np.allclose(prepared["spectrum"]["display_value"], [1.2, 1.4, 1.3])
    figure, axis = plt.subplots(figsize=(5, 3))
    plot_spectrum(axis, prepared)
    assert axis.get_ylabel().startswith("MIM")
    plt.close(figure)


def test_dpli_matrix_is_directional_and_channel_pair_plot_preserves_pairs():
    spectrum = pd.DataFrame(
        [
            {"method": "dpli", "region_a": "M1", "region_b": "STR", "component_index": np.nan, "frequency_hz": 5.0, "value_raw": 0.8, "value_strength": 0.8, "aggregation_level": "cross_region_channel_pair", "seed_channel": "M1-1", "target_channel": "STR-1", "n_epochs": 8, "frequency_is_excluded_line_noise": False},
            {"method": "dpli", "region_a": "STR", "region_b": "M1", "component_index": np.nan, "frequency_hz": 5.0, "value_raw": 0.2, "value_strength": 0.2, "aggregation_level": "cross_region_channel_pair", "seed_channel": "STR-1", "target_channel": "M1-1", "n_epochs": 8, "frequency_is_excluded_line_noise": False},
        ]
    )
    bands = pd.DataFrame(
        [
            {"method": "dpli", "region_a": "M1", "region_b": "STR", "component_index": np.nan, "band": "alpha", "band_low_hz": 5.0, "band_high_hz": 5.0, "value_raw_or_summary": 0.8, "value_strength": 0.8, "status": "ok"},
            {"method": "dpli", "region_a": "STR", "region_b": "M1", "component_index": np.nan, "band": "alpha", "band_low_hz": 5.0, "band_high_hz": 5.0, "value_raw_or_summary": 0.2, "value_strength": 0.2, "status": "ok"},
        ]
    )
    channel_bands = pd.DataFrame(
        [
            {"method": "dpli", "region_a": "M1", "region_b": "STR", "seed_channel": "M1-1", "target_channel": "STR-1", "band": "alpha", "band_low_hz": 5.0, "band_high_hz": 5.0, "value_raw_or_summary": 0.8, "value_strength": 0.8, "status": "ok"},
            {"method": "dpli", "region_a": "STR", "region_b": "M1", "seed_channel": "STR-1", "target_channel": "M1-1", "band": "alpha", "band_low_hz": 5.0, "band_high_hz": 5.0, "value_raw_or_summary": 0.2, "value_strength": 0.2, "status": "ok"},
        ]
    )
    tables = {"region_summary": spectrum, "band_summary": bands, "channel_pair_band_summary": channel_bands}
    prepared = prepare_connectivity(tables, "dpli", None, [["M1", "STR"]])
    figure, axes = plt.subplots(1, 2, figsize=(8, 4))
    info = plot_matrix(axes[0], figure, prepared, {"name": "alpha", "low_hz": 5.0, "high_hz": 5.0})
    assert info["matrix"][0, 1] == 0.8
    assert info["matrix"][1, 0] == 0.2
    assert axes[0].images[0].norm.vmin == 0.0
    assert axes[0].images[0].norm.vmax == 1.0
    assert axes[0].images[0].norm.vcenter == 0.5
    spectrum_prepared = prepare_connectivity(tables, "dpli", None, [["M1", "STR"]])
    plot_spectrum(axes[1], spectrum_prepared)
    assert axes[1].get_ylim() == (0.0, 1.0)
    assert any(abs(line.get_ydata()[0] - 0.5) < 1e-12 for line in axes[1].lines)
    plot_channel_pair_matrix(axes[1], figure, prepared, {"name": "alpha", "low_hz": 5.0, "high_hz": 5.0}, ("M1", "STR"))
    assert axes[1].images
    plt.close(figure)
