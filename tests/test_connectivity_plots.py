from __future__ import annotations

import warnings
from io import BytesIO
from itertools import combinations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from lfp_analysis.connectivity_plots import (
    plot_band_matrices,
    plot_channel_pair_matrices,
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


def test_multiband_matrices_use_one_colorbar_axis_per_panel():
    tables = _tables()
    prepared = prepare_connectivity(tables, "mic", 1, [["M1", "STR"]])
    bands = [
        {"name": "alpha", "low_hz": 5.0, "high_hz": 7.0},
        {"name": "beta", "low_hz": 7.0, "high_hz": 10.0},
    ]
    figure = plt.figure(figsize=(10, 6), constrained_layout=True)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        info = plot_band_matrices(figure, prepared, bands)
        figure.canvas.draw()
        figure.savefig(BytesIO(), format="png")
    assert not any("tight_layout" in str(item.message) for item in caught)
    assert len(info["colorbar_axes"]) == 2
    assert len([axis for axis in figure.axes if axis.images]) == 2
    assert len(figure.axes) == 4
    # Repainting clears the old cax objects instead of accumulating them.
    plot_band_matrices(figure, prepared, bands[:1])
    assert len([axis for axis in figure.axes if axis.images]) == 1
    assert len(figure.axes) == 2

    channel_tables = dict(tables)
    channel_tables["channel_pair_band_summary"] = pd.DataFrame(
        [
            {"method": "wpli", "region_a": "M1", "region_b": "STR", "seed_channel": "M1-1", "target_channel": "STR-1", "band": "alpha", "band_low_hz": 5.0, "band_high_hz": 7.0, "value_raw_or_summary": 0.2},
            {"method": "wpli", "region_a": "M1", "region_b": "STR", "seed_channel": "M1-1", "target_channel": "STR-1", "band": "beta", "band_low_hz": 7.0, "band_high_hz": 10.0, "value_raw_or_summary": 0.4},
        ]
    )
    channel_prepared = prepare_connectivity(channel_tables, "wpli", None, [["M1", "STR"]])
    channel_info = plot_channel_pair_matrices(figure, channel_prepared, bands, ("M1", "STR"))
    assert len(channel_info["colorbar_axes"]) == 2
    assert len([axis for axis in figure.axes if axis.images]) == 2
    assert len(figure.axes) == 4
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


def _six_pair_rows(rows_per_pair: int = 491) -> pd.DataFrame:
    regions = ("M1", "STR", "PF", "SNr")
    rows = []
    for pair_index, (region_a, region_b) in enumerate(combinations(regions, 2)):
        for frequency_index in range(rows_per_pair):
            rows.append(
                {
                    "method": "mic",
                    "region_a": region_a,
                    "region_b": region_b,
                    "component_index": 1,
                    "frequency_hz": float(frequency_index),
                    "value_raw": float(pair_index * 10000 + frequency_index + 1),
                    "value_strength": float(pair_index * 10000 + frequency_index + 1),
                }
            )
    return pd.DataFrame(rows)


def test_prepare_connectivity_filters_labels_and_values_as_one_rowwise_unit():
    source = _six_pair_rows()
    before = source.copy(deep=True)
    pairs = [("M1", "STR"), ("M1", "PF"), ("M1", "SNr"), ("STR", "PF"), ("STR", "SNr"), ("PF", "SNr")]

    for selected, expected_count in ((pairs, 2946), (pairs[:5], 2455), (pairs[1:5], 1964), (pairs[1:4], 1473), ([], 0)):
        prepared = prepare_connectivity({"region_summary": source}, "mic", 1, selected)
        frame = prepared["spectrum"]
        assert len(frame) == expected_count
        assert prepared["selected_pairs_empty"] is (not selected)
        if not frame.empty:
            assert frame["pair_label"].notna().all()
            assert frame["pair_label"].map(lambda label: label in {f"{a}–{b}" for a, b in pairs}).all()
            for pair_index, pair in enumerate(pairs):
                expected = pair_index * 10000 + 1
                selected_rows = frame.loc[frame["pair_label"].eq(f"{pair[0]}–{pair[1]}")]
                if not selected_rows.empty:
                    assert selected_rows["value_raw"].iloc[0] == expected
                    assert selected_rows["display_value"].iloc[0] == expected
    pd.testing.assert_frame_equal(source, before)


def test_prepare_connectivity_handles_shuffled_noncontiguous_and_unequal_rows():
    source = _six_pair_rows()
    shuffled = source.sample(frac=1.0, random_state=42).copy()
    shuffled.index = np.arange(10000, 10000 + len(shuffled) * 2, 2)
    selected = [("M1", "PF"), ("STR", "SNr"), ("PF", "SNr")]
    prepared = prepare_connectivity({"region_summary": shuffled}, "mic", 1, selected)
    frame = prepared["spectrum"]
    expected_labels = [
        f"{row.region_a}–{row.region_b}"
        for row in shuffled.itertuples(index=False)
        if (row.region_a, row.region_b) in selected
    ]
    assert frame["pair_label"].tolist() == expected_labels
    assert frame["pair_label"].tolist() == [
        f"{row.region_a}–{row.region_b}" for row in frame.itertuples(index=False)
    ]

    unequal = source.drop(source.index[491 + 100 : 491 + 150]).copy()
    unequal_before = unequal.copy(deep=True)
    prepared_unequal = prepare_connectivity({"region_summary": unequal}, "mic", 1, selected)
    assert len(prepared_unequal["spectrum"]) == 441 + 491 + 491
    pd.testing.assert_frame_equal(unequal, unequal_before)


def test_prepare_connectivity_empty_selection_and_directed_rows_are_explicit():
    directed = pd.DataFrame(
        [
            {"method": "dpli", "region_a": "M1", "region_b": "STR", "frequency_hz": 5.0, "value_raw": 0.8},
            {"method": "dpli", "region_a": "STR", "region_b": "M1", "frequency_hz": 5.0, "value_raw": 0.2},
        ]
    )
    empty = prepare_connectivity({"region_summary": directed}, "dpli", None, [])
    assert empty["spectrum"].empty
    assert empty["selected_pairs_empty"] is True

    both_directions = prepare_connectivity({"region_summary": directed}, "dpli", None, [("M1", "STR")])
    assert both_directions["spectrum"]["display_pair_label"].tolist() == ["M1→STR", "STR→M1"]
    assert both_directions["spectrum"]["value_raw"].tolist() == [0.8, 0.2]

    forward_only = prepare_connectivity({"region_summary": directed}, "dpli", None, [("M1", "STR")], exact_direction=True)
    assert forward_only["spectrum"]["display_pair_label"].tolist() == ["M1→STR"]
    assert forward_only["spectrum"]["value_raw"].tolist() == [0.8]


def test_line_noise_marker_and_plot_exclusion_are_independent() -> None:
    frame = pd.DataFrame(
        [
            {
                "method": "mim",
                "region_a": "M1",
                "region_b": "STR",
                "component_index": np.nan,
                "frequency_hz": frequency,
                "value_raw": frequency / 100.0,
                "value_strength": frequency / 100.0,
                "frequency_is_masked_for_plot": frequency == 50.0,
                "frequency_is_excluded_line_noise": frequency == 50.0,
            }
            for frequency in (49.0, 49.5, 50.0, 50.5, 51.0)
        ]
    )
    prepared = prepare_connectivity({"region_summary": frame}, "mim", None, [("M1", "STR")])
    prepared_before = prepared["spectrum"].copy(deep=True)
    figure, axis = plt.subplots(figsize=(5, 3))

    plot_spectrum(axis, prepared)
    line = axis.lines[0]
    assert np.isfinite(line.get_ydata()).all()
    assert not any("工频标记" in str(p.get_label()) for p in axis.patches)

    plot_spectrum(axis, prepared, show_line_noise_markers=True, exclude_line_noise=False)
    marked_y = np.asarray(axis.lines[0].get_ydata(), dtype=float)
    assert np.isfinite(marked_y).all()
    assert any("工频标记" in str(p.get_label()) for p in axis.patches)

    plot_spectrum(axis, prepared, show_line_noise_markers=False, exclude_line_noise=True)
    excluded_y = np.asarray(axis.lines[0].get_ydata(), dtype=float)
    assert np.isnan(excluded_y[2])
    assert np.isfinite(excluded_y[[0, 1, 3, 4]]).all()
    pd.testing.assert_frame_equal(prepared["spectrum"], prepared_before)
    plt.close(figure)
