from __future__ import annotations

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")

from lfp_analysis.connectivity_plots import plot_spectrum, prepare_connectivity
from lfp_analysis.connectivity_processing import (
    bin_spectrum,
    diagnose_frequency_table,
    frequency_alignment_index,
    frequency_mask,
    quantify_band_cv,
    resolve_line_noise_settings,
    smooth_for_display,
    validate_frequency_axis,
)


def _spectrum(values: list[float], frequencies: list[float] | None = None) -> pd.DataFrame:
    frequencies = frequencies or list(np.arange(1.0, len(values) + 1.0))
    return pd.DataFrame(
        {
            "method": ["mic"] * len(values),
            "region_a": ["M1"] * len(values),
            "region_b": ["STR"] * len(values),
            "component_index": [1] * len(values),
            "frequency_hz": frequencies,
            "value_raw": values,
            "value_strength": np.abs(values),
            "frequency_is_excluded_line_noise": [False] * len(values),
        }
    )


def test_default_line_noise_has_one_source_and_no_implicit_60_hz() -> None:
    config = {"connectivity": {"fmax_hz": 100.0, "line_noise": {"frequency_hz": 50.0, "mask_width_hz": 1.0, "harmonics": True}}}
    settings = resolve_line_noise_settings(config)
    assert settings["centres_hz"] == [50.0, 100.0]
    frequencies = np.asarray([49.6, 50.0, 50.4, 59.8, 60.0, 60.2])
    assert frequency_mask(frequencies, config).tolist() == [True, True, True, False, False, False]


def test_explicit_legacy_60_hz_remains_supported() -> None:
    config = {"connectivity": {"exclude_line_noise_hz": [50.0, 60.0], "line_noise_half_width_hz": 0.5}}
    frequencies = np.asarray([50.0, 60.0, 70.0])
    assert frequency_mask(frequencies, config).tolist() == [True, True, False]


def test_frequency_diagnostics_keeps_finite_masked_values_and_reports_nan() -> None:
    frame = _spectrum([1.0, np.nan, 3.0, 4.0], [49.8, 50.0, 50.2, 60.0])
    frame.loc[frame["frequency_hz"].eq(50.0), "frequency_is_masked_for_plot"] = True
    diagnostics = diagnose_frequency_table(frame, {"connectivity": {"line_noise": {"frequency_hz": 50.0, "mask_width_hz": 1.0}}})
    masked = diagnostics.loc[diagnostics["frequency_hz"].eq(50.0)].iloc[0]
    invalid = diagnostics.loc[diagnostics["frequency_hz"].eq(50.0)].iloc[0]
    assert bool(masked["is_masked"])
    assert int(masked["n_finite"]) == 0
    assert int(invalid["n_nan"]) == 1
    assert invalid["processing_stage"] == "post_estimation_row_materialization"


def test_smoothing_does_not_cross_masked_frequency_interval() -> None:
    frame = _spectrum([1.0, 2.0, 3.0, 100.0, 100.0, 6.0, 7.0, 8.0])
    config = {
        "connectivity": {"line_noise": {"frequency_hz": 4.5, "mask_width_hz": 1.0}},
        "visualization": {"connectivity": {"display_smoothing": {"enabled": True, "sigma_hz": 0.8}}},
    }
    smoothed = smooth_for_display(frame, config)
    assert not smoothed.empty
    assert frame["value_strength"].tolist() == [1.0, 2.0, 3.0, 100.0, 100.0, 6.0, 7.0, 8.0]
    left = float(smoothed.loc[smoothed["frequency_hz"].eq(3.0), "display_value_smoothed"].iloc[0])
    right = float(smoothed.loc[smoothed["frequency_hz"].eq(6.0), "display_value_smoothed"].iloc[0])
    assert left < 20.0
    assert right < 20.0
    assert smoothed.loc[smoothed["frequency_hz"].isin([4.0, 5.0]), "display_value_smoothed"].isna().all()


def test_binning_marks_masked_bins_instead_of_bridging_them() -> None:
    frame = _spectrum([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    config = {"connectivity": {"frequency_binning": {"enabled": True, "width_hz": 2.0}, "line_noise": {"frequency_hz": 3.5, "mask_width_hz": 1.0}}}
    binned = bin_spectrum(frame, config)
    assert "masked_frequency_bin" in set(binned["status"])
    assert binned.loc[binned["status"].eq("masked_frequency_bin"), "value_raw_or_summary"].isna().all()


def test_band_cv_is_reported_from_raw_values_within_configured_band() -> None:
    frame = _spectrum([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0])
    table = quantify_band_cv(frame, {"bands": {"low": [1.0, 4.0]}})
    assert table.loc[0, "band"] == "low"
    assert table.loc[0, "n_valid_points"] == 4
    assert float(table.loc[0, "band_cv"]) > 0


def test_frequency_axis_validation_allows_explicit_float_tolerance() -> None:
    assert validate_frequency_axis([1.0, 1.2, 1.4])["frequency_step_hz"] == pytest.approx(0.2)
    assert frequency_alignment_index([1.0, 1.2, 1.4], [1.0000001, 1.3999999], tolerance_hz=1e-5).tolist() == [0, 2]
    with pytest.raises(ValueError):
        validate_frequency_axis([1.0, 1.0, 2.0])


def test_spectrum_view_title_and_xlim_distinguish_full_and_selected_band() -> None:
    frame = _spectrum([0.1, 0.2, 0.3, 0.4], [1.0, 2.0, 3.0, 4.0])
    prepared = prepare_connectivity({"region_summary": frame}, "mic", 1, [["M1", "STR"]])
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots()
    plot_spectrum(axis, prepared, {"name": "delta", "low_hz": 2.0, "high_hz": 3.0}, view_mode="selected_band")
    assert axis.get_xlim() == pytest.approx((2.0, 3.0))
    assert "仅显示选定频段" in axis.get_title()
    plot_spectrum(axis, prepared, {"name": "delta", "low_hz": 2.0, "high_hz": 3.0}, view_mode="full_highlight")
    assert "全频谱" in axis.get_title()
    assert axis.get_xlim()[0] < 2.0
    plt.close(figure)
