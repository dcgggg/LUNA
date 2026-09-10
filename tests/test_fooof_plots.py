from __future__ import annotations

import numpy as np
import pandas as pd

from lfp_analysis.fooof_plots import ordered_channels, prepare_fooof


def _tables() -> dict[str, pd.DataFrame]:
    models = pd.DataFrame(
        [
            {"channel_array_index": 0, "channel_name": "TETFP01", "fit_status": "ok", "fit_quality_status": "pass", "offset": -8.0, "exponent": 1.2, "fit_low_hz": 2.0, "fit_high_hz": 40.0, "n_peaks": 2},
            {"channel_array_index": 1, "channel_name": "TETFP05", "fit_status": "ok", "fit_quality_status": "pass", "offset": -8.2, "exponent": 1.4, "fit_low_hz": 2.0, "fit_high_hz": 40.0, "n_peaks": 0},
        ]
    )
    peaks = pd.DataFrame(
        [
            {"channel_array_index": 0, "channel_name": "TETFP01", "peak_index": 0, "center_frequency_hz": 6.0, "peak_power_log10": 0.2, "peak_height_log10": 0.2, "bandwidth_hz": 4.0},
            {"channel_array_index": 0, "channel_name": "TETFP01", "peak_index": 1, "center_frequency_hz": 7.0, "peak_power_log10": 0.5, "peak_height_log10": 0.5, "bandwidth_hz": 2.0},
        ]
    )
    frequencies = np.array([2.0, 6.0, 8.0])
    curves = pd.DataFrame(
        [
            {"channel_array_index": index, "channel_name": name, "frequency_hz": frequency, "observed_log10_power": -8.0, "aperiodic_log10_power": -8.2, "periodic_component_log10_additive": 0.2, "residual_log10": 0.0}
            for index, name in ((0, "TETFP01"), (1, "TETFP05"))
            for frequency in frequencies
        ]
    )
    metadata = pd.DataFrame(
        [
            {"channel_name": "TETFP01", "physical_channel_number": 1, "region": "M1"},
            {"channel_name": "TETFP05", "physical_channel_number": 5, "region": "STR"},
        ]
    )
    return {"model": models, "peaks": peaks, "curves": curves, "channel_table": metadata}


def test_fooof_preparation_uses_physical_metadata_and_representative_peak() -> None:
    prepared = prepare_fooof(_tables(), [{"name": "theta", "low_hz": 4.0, "high_hz": 8.0}], selected_band="theta", peak_mode="representative")
    assert [row["physical_channel_number"] for row in ordered_channels(prepared["models"], prepared["curves"])] == ["1", "5"]
    selected = prepared["peaks_display"].set_index("channel_name")
    assert selected.loc["TETFP01", "center_frequency_hz"] == 7.0
    assert selected.loc["TETFP01", "selection_rule"] == "max_peak_power_log10_in_band"
    assert selected.loc["TETFP05", "peak_selection_status"] == "no_peak_in_band"


def test_fooof_peak_boundary_is_left_closed_right_open() -> None:
    prepared = prepare_fooof(_tables(), [{"name": "theta", "low_hz": 4.0, "high_hz": 7.0}], selected_band="theta", peak_mode="all")
    assert prepared["peaks_filtered"]["center_frequency_hz"].tolist() == [6.0]
