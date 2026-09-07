from __future__ import annotations

import os

import pandas as pd
import pytest

from lfp_analysis.gui_engine import build_runtime_config
from lfp_analysis.gui_specs import validate_snapshot


def _channel_table() -> pd.DataFrame:
    rows = []
    for index, (name, region) in enumerate(
        [("M1-1", "M1"), ("M1-2", "M1"), ("STR-1", "STR"), ("STR-2", "STR"), ("PF-1", "PF"), ("PF-2", "PF"), ("SNr-1", "SNr"), ("SNr-2", "SNr")]
    ):
        rows.append({"array_index": index, "channel_name": name, "region": region})
    return pd.DataFrame(rows)


def _values() -> dict:
    return {
        "psd": {"window": "hann", "window_seconds": 1.0, "overlap_percent": 50.0, "nfft": 0, "detrend": "constant", "average": "mean", "epoch_aggregation": "mean", "fmin_hz": 1.0, "fmax_hz": 100.0},
        "parameterization": {"fit_low_hz": 2.0, "fit_high_hz": 80.0, "peak_width_low_hz": 1.0, "peak_width_high_hz": 12.0, "max_n_peaks": 6, "min_peak_height": 0.0, "peak_threshold": 2.0, "min_r_squared": 0.9, "aperiodic_mode": "fixed"},
        "connectivity": {"fmin_hz": 2.0, "fmax_hz": 80.0, "mt_bandwidth_hz": 4.0, "min_epochs": 5, "rank_strategy": "data_driven_energy_99pct", "rank_variance_threshold": 0.99, "stability_n_subsamples": 0},
        "time_delay": {"analysis_sfreq_hz": 200.0, "max_delay_ms": 500.0, "fmin_hz": 2.0, "fmax_hz": 80.0},
        "bands": [{"name": "theta", "low_hz": 4.0, "high_hz": 8.0}],
        "relative_power": {"denominator_low_hz": 1.0, "denominator_high_hz": 80.0},
    }


def _snapshot(**changes):
    snapshot = {
        "indicators": ["PSD"],
        "selected_channel_names": _channel_table()["channel_name"].tolist(),
        "selected_epoch_indices": list(range(5)),
        "selected_region_pairs": [["M1", "STR"]],
        "selection": {"time_start_s": 0.0, "time_end_s": 5.0},
        "values": _values(),
    }
    snapshot.update(changes)
    return snapshot


def test_gui_validation_rejects_welch_window_longer_than_selection() -> None:
    snapshot = _snapshot(values={**_values(), "psd": {**_values()["psd"], "window_seconds": 6.0}})
    errors, _warnings = validate_snapshot(snapshot, 1000.0, 5000, 5, _channel_table())
    assert any("超过选定时间窗" in error for error in errors)


def test_runtime_config_maps_gui_methods_and_fixed_rank() -> None:
    snapshot = _snapshot(indicators=["MIC", "MIM", "wpli2_debiased"], values={**_values(), "connectivity": {**_values()["connectivity"], "rank_strategy": "fixed_rank", "fixed_rank_M1": 2}})
    config = build_runtime_config({}, snapshot, 1000.0, 5000)
    assert config["connectivity"]["methods"] == ["mic", "mim", "wpli2_debiased"]
    assert config["connectivity"]["fixed_rank_by_region"] == {"M1": 2}
    assert config["connectivity"]["selected_region_pairs"] == [["M1", "STR"]]


@pytest.mark.skipif(os.environ.get("CI") == "true", reason="Qt window test is local/offscreen")
def test_main_window_constructs_offscreen(monkeypatch) -> None:
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from lfp_analysis.gui import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert len(window.indicator_checks) == 8
    assert len(window.parameter_widgets) >= 28
    window.close()
    app.quit()
