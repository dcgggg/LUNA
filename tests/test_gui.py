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
        "connectivity": {"mode": "multitaper", "fmin_hz": 2.0, "fmax_hz": 80.0, "mt_bandwidth_hz": 4.0, "mt_adaptive": False, "mt_low_bias": True, "n_components": 1, "n_jobs": 1, "min_epochs": 5, "region_pair_summary": "mean", "rank_strategy": "data_driven_energy_99pct", "rank_variance_threshold": 0.99, "stability_n_subsamples": 0},
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


def test_analysis_parameter_change_does_not_refresh_raw_preview() -> None:
    from lfp_analysis.gui import MainWindow

    class Dummy:
        raw_refreshes = 0

        def _update_selection_label(self) -> None:
            pass

        def _set_dirty(self, _value: bool) -> None:
            pass

        def _update_raw_preview(self) -> None:
            self.raw_refreshes += 1

        def _refresh_band_power_filters(self) -> None:
            pass

        def _refresh_fooof_filters(self) -> None:
            pass

        def _selection_changed(self) -> None:
            MainWindow._selection_changed(self)

    dummy = Dummy()
    MainWindow._selection_changed(dummy)
    assert dummy.raw_refreshes == 0
    MainWindow._channel_selection_changed(dummy)
    assert dummy.raw_refreshes == 1


def test_runtime_config_maps_gui_methods_and_fixed_rank() -> None:
    snapshot = _snapshot(indicators=["MIC", "MIM", "wpli", "dpli", "wpli2_debiased"], values={**_values(), "connectivity": {**_values()["connectivity"], "rank_strategy": "fixed_rank", "fixed_rank_M1": 2}})
    config = build_runtime_config({}, snapshot, 1000.0, 5000)
    assert config["connectivity"]["methods"] == ["mic", "mim", "wpli", "dpli", "wpli2_debiased"]
    assert config["connectivity"]["fixed_rank_by_region"] == {"M1": 2}
    assert config["connectivity"]["selected_region_pairs"] == [["M1", "STR"]]
    assert config["connectivity"]["mode"] == "multitaper"
    assert config["connectivity"]["n_components"] == 1
    assert config["connectivity"]["n_jobs"] == 1
    assert config["connectivity"]["region_pair_summary"] == "mean"


def test_runtime_config_maps_multitaper_psd_parameters() -> None:
    values = _values()
    values["psd"] = {
        **values["psd"],
        "method": "multitaper",
        "multitaper_bandwidth_hz": 5.0,
        "multitaper_adaptive": True,
        "multitaper_low_bias": False,
        "multitaper_normalization": "full",
        "multitaper_remove_dc": False,
        "multitaper_n_jobs": 2,
    }
    snapshot = _snapshot(values=values)
    config = build_runtime_config({}, snapshot, 1000.0, 5000)
    assert config["psd"]["method"] == "multitaper"
    assert config["psd"]["multitaper_bandwidth_hz"] == 5.0
    assert config["psd"]["multitaper_adaptive"] is True
    assert config["psd"]["multitaper_low_bias"] is False
    assert config["psd"]["multitaper_normalization"] == "full"
    assert config["psd"]["multitaper_remove_dc"] is False
    assert config["psd"]["multitaper_n_jobs"] == 2
    errors, _warnings = validate_snapshot(snapshot, 1000.0, 5000, 5, _channel_table())
    assert not errors


@pytest.mark.skipif(os.environ.get("CI") == "true", reason="Qt window test is local/offscreen")
def test_main_window_constructs_offscreen(monkeypatch) -> None:
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from lfp_analysis.gui import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    assert len(window.indicator_checks) == 10
    assert {"wpli", "dpli"}.issubset(window.indicator_checks)
    assert window.pair_checks
    assert len(window.parameter_widgets) >= 28
    window.indicator_checks["PSD"].setChecked(True)
    app.processEvents()
    method = window.parameter_widgets["psd.method"]
    method.setCurrentText("multitaper")
    app.processEvents()
    assert window.parameter_widgets["psd.multitaper_bandwidth_hz"].isEnabled()
    assert not window.parameter_widgets["psd.window_seconds"].isEnabled()
    assert window.parameter_widgets["psd.multitaper_normalization"].currentText() == "length"
    window.indicator_checks["wpli"].setChecked(True)
    app.processEvents()
    assert window.parameter_widgets["connectivity.region_pair_summary"].isEnabled()
    window.indicator_checks["MIC"].setChecked(False)
    window.indicator_checks["MIM"].setChecked(False)
    app.processEvents()
    assert not window.parameter_widgets["connectivity.rank_strategy"].isEnabled()
    assert not window.parameter_widgets["connectivity.n_components"].isVisible()
    assert window.minimumSize().width() >= 900
    assert window.minimumSize().height() >= 600
    assert not window.status_text.isVisible()
    window.log_toggle.setChecked(True)
    app.processEvents()
    assert window.status_text.isVisible()
    assert window.log_toggle.text() == "收起详细日志"
    window.log_toggle.setChecked(False)
    for width, height in ((980, 620), (1366, 768), (1920, 1080)):
        window.resize(width, height)
        app.processEvents()
        assert window.run_button.isVisible()
        assert window.general_plot_widget.isVisible()
        assert window.general_plot_widget.width() >= 500
    window.close()
    app.quit()


@pytest.mark.skipif(os.environ.get("CI") == "true", reason="Qt window test is local/offscreen")
def test_connectivity_view_links_matrix_selection_to_spectrum(monkeypatch) -> None:
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from lfp_analysis.connectivity_gui import ConnectivityView

    app = QApplication.instance() or QApplication([])
    view = ConnectivityView()
    frequencies = [5.0, 6.0]
    spectrum = pd.DataFrame(
        [
            {"method": "mic", "region_a": "M1", "region_b": "STR", "component_index": 1, "frequency_hz": f, "value_raw": v, "value_strength": abs(v), "n_epochs": 8, "frequency_is_excluded_line_noise": False}
            for f, v in zip(frequencies, [0.2, -0.3], strict=True)
        ]
    )
    bands = pd.DataFrame([{"method": "mic", "region_a": "M1", "region_b": "STR", "component_index": 1, "band": "alpha", "band_low_hz": 5.0, "band_high_hz": 6.0, "value_raw_or_summary": 0.25, "value_strength": 0.25, "status": "ok"}])
    view.set_payload({"metric": "Connectivity", "file_id": "synthetic", "tables": {"region_summary": spectrum, "band_summary": bands}})
    assert view.metric_combo.currentData() == "mic"
    assert view.pair_list.count() == 1
    view._matrix_clicked(type("Event", (), {"inaxes": view.matrix_figure.axes[0], "xdata": 1.0, "ydata": 0.0})())
    assert view._focus_pair == ("M1", "STR")
    assert len(view.spectrum_figure.axes[0].lines) == 1
    view.close()
    app.quit()


@pytest.mark.skipif(os.environ.get("CI") == "true", reason="Qt window test is local/offscreen")
def test_connectivity_view_multiband_and_dpli_display(monkeypatch) -> None:
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from lfp_analysis.connectivity_gui import ConnectivityView

    app = QApplication.instance() or QApplication([])
    rows = []
    bands = []
    for method in ("mic", "dpli"):
        for band, low, high, value in (("delta", 1.0, 4.0, 0.3), ("theta", 4.0, 8.0, 0.7)):
            rows.append({"method": method, "region_a": "M1", "region_b": "STR", "component_index": 1, "frequency_hz": low + 0.5, "value_raw": value, "value_strength": value, "n_epochs": 8})
            bands.append({"method": method, "region_a": "M1", "region_b": "STR", "component_index": 1, "band": band, "band_low_hz": low, "band_high_hz": high, "value_raw_or_summary": value, "value_strength": value, "status": "ok"})
            if method == "dpli":
                rows[-1] = {**rows[-1], "region_a": "STR", "region_b": "M1", "value_raw": 1.0 - value, "value_strength": 1.0 - value}
                bands[-1] = {**bands[-1], "region_a": "STR", "region_b": "M1", "value_raw_or_summary": 1.0 - value, "value_strength": 1.0 - value}
    view = ConnectivityView()
    view.set_payload({"metric": "Connectivity", "file_id": "synthetic", "tables": {"region_summary": pd.DataFrame(rows), "band_summary": pd.DataFrame(bands)}})
    assert len([axis for axis in view.matrix_figure.axes if axis.images]) == 2
    index = view.metric_combo.findData("dpli")
    view.metric_combo.setCurrentIndex(index)
    app.processEvents()
    assert view.matrix_figure.axes[0].images[0].norm.vcenter == 0.5
    assert view.matrix_figure.axes[0].images[0].norm.vmin == 0.0
    assert view.matrix_figure.axes[0].images[0].norm.vmax == 1.0
    view.close()
    app.quit()
