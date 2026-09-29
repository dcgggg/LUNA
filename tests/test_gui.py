from __future__ import annotations

import copy
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from lfp_analysis.gui_engine import build_runtime_config
from lfp_analysis.gui_specs import normalize_gui_values, validate_snapshot

_SKIP_QT_WINDOW_TESTS = (
    os.environ.get("CI", "").lower() == "true"
    and os.environ.get("LUNA_RUN_QT_TESTS") != "1"
)


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


def test_worker_emits_failure_even_when_diagnostic_write_fails(monkeypatch, tmp_path) -> None:
    from lfp_analysis import gui as gui_module

    def fail_analysis(*_args, **_kwargs):
        raise RuntimeError("connectivity backend failed")

    def fail_report(*_args, **_kwargs):
        raise PermissionError("diagnostic directory is read-only")

    monkeypatch.setattr(gui_module, "run_gui_analysis", fail_analysis)
    monkeypatch.setattr(gui_module, "write_failure_report", fail_report)
    monkeypatch.setattr(gui_module, "default_log_directory", lambda _root: tmp_path)
    worker = gui_module.AnalysisWorker(
        {"run_id": "diagnostic-write-failure", "indicators": ["MIC"], "values": {"connectivity": {"n_jobs": 1}}},
        tmp_path / "config.yaml",
        tmp_path / "metadata",
    )
    outcomes = []
    worker.finished.connect(outcomes.append)

    worker.run()

    assert len(outcomes) == 1
    assert outcomes[0]["manifest"]["status"] == "failed"
    assert "connectivity backend failed" in outcomes[0]["manifest"]["errors"][0]
    assert "diagnostic directory is read-only" in outcomes[0]["diagnostic_report_error"]


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
    assert "window" not in config["psd"]
    assert "nperseg" not in config["psd"]
    errors, _warnings = validate_snapshot(snapshot, 1000.0, 5000, 5, _channel_table())
    assert not errors


def test_gui_optional_parameterization_check_uses_configured_backend(monkeypatch) -> None:
    from lfp_analysis import gui as gui_module
    from lfp_analysis.gui import MainWindow

    calls = []

    def availability(method, **kwargs):
        calls.append((method, kwargs))
        return False, "backend unavailable"

    monkeypatch.setattr(gui_module, "optional_method_availability", availability)
    window_stub = SimpleNamespace(base_config={"parameterization": {"backend": "fooof"}})

    assert MainWindow._optional_method_availability(window_stub, "FOOOF") == (False, "backend unavailable")
    assert calls == [("FOOOF", {"parameterization_backend": "fooof"})]


def test_close_event_tolerates_a_qthread_already_deleted_by_qt() -> None:
    pytest.importorskip("PySide6")
    import shiboken6
    from PySide6 import QtCore, QtGui

    from lfp_analysis.gui import MainWindow

    app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
    thread = QtCore.QThread()
    thread.deleteLater()
    app.sendPostedEvents(thread, QtCore.QEvent.Type.DeferredDelete)
    assert not shiboken6.isValid(thread)

    fake_window = SimpleNamespace(
        _inspection_save_pending=False,
        analysis_worker=None,
        analysis_thread=None,
        inspect_thread=thread,
    )
    event = QtGui.QCloseEvent()
    MainWindow.closeEvent(fake_window, event)
    assert event.isAccepted()


def test_runtime_config_passes_only_active_welch_parameters() -> None:
    snapshot = _snapshot()
    config = build_runtime_config({}, snapshot, 1000.0, 5000)
    assert config["psd"]["method"] == "welch"
    assert config["psd"]["window"] == "hann"
    assert config["psd"]["nperseg"] == 1000
    assert "multitaper_bandwidth_hz" not in config["psd"]
    assert "multitaper_n_jobs" not in config["psd"]


def test_psd_normalization_does_not_mutate_values_and_drops_inactive_branch() -> None:
    values = _values()
    values["psd"].update(
        {
            "method": "multitaper",
            "multitaper_bandwidth_hz": 4.0,
            "multitaper_n_jobs": 1,
        }
    )
    original = copy.deepcopy(values)
    normalized = normalize_gui_values(values, 1000.0, 5000)
    assert values == original
    assert normalized["psd"]["method"] == "multitaper"
    assert "window_seconds" not in normalized["psd"]
    assert "nperseg" not in normalized["psd"]


@pytest.mark.skipif(_SKIP_QT_WINDOW_TESTS, reason="Set LUNA_RUN_QT_TESTS=1 to opt into offscreen Qt window tests in CI")
def test_main_window_constructs_offscreen(monkeypatch, request, tmp_path) -> None:
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtWidgets
    from PySide6.QtWidgets import QApplication

    from lfp_analysis import gui as gui_module
    from lfp_analysis.gui import (
        GLOBAL_ACTION_HEIGHT,
        HEADER_LOGO_HEIGHT,
        HEADER_LOGO_WIDTH,
        RESULT_TABLE_EXPANDED_HEIGHT,
        MainWindow,
    )

    app = QApplication.instance() or QApplication([])
    settings_class = QtCore.QSettings
    settings_file = tmp_path / "LUNA.ini"

    def isolated_qsettings(organization: str, application: str):
        if (organization, application) == ("LUNA", "LUNA"):
            return settings_class(str(settings_file), settings_class.Format.IniFormat)
        return settings_class(organization, application)

    monkeypatch.setattr(gui_module.QtCore, "QSettings", isolated_qsettings)
    splitter_settings = settings_class(str(settings_file), settings_class.Format.IniFormat)
    assert Path(splitter_settings.fileName()).resolve() == settings_file.resolve()
    splitter_settings.sync()
    had_saved_width = splitter_settings.contains("main_analysis_panel_width")
    saved_width = splitter_settings.value("main_analysis_panel_width")

    def restore_splitter_setting() -> None:
        if had_saved_width:
            splitter_settings.setValue("main_analysis_panel_width", saved_width)
        else:
            splitter_settings.remove("main_analysis_panel_width")
        splitter_settings.sync()

    request.addfinalizer(restore_splitter_setting)
    splitter_settings.setValue("main_analysis_panel_width", 320)
    splitter_settings.sync()
    window = MainWindow()
    opened_help_topics: list[str] = []

    class StubAnalysisHelpDialog:
        def __init__(self, topic_id: str, _parent) -> None:
            opened_help_topics.append(topic_id)

        def exec(self) -> int:
            return 0

    from lfp_analysis import gui as gui_module

    monkeypatch.setattr(gui_module, "AnalysisHelpDialog", StubAnalysisHelpDialog)
    window._current_result_payload = lambda: {"metric": "PSD"}
    window.analysis_help_button.click()
    assert opened_help_topics == ["psd"]
    window.show()
    app.processEvents()
    assert len(window.indicator_checks) == 10
    assert {"wpli", "dpli"}.issubset(window.indicator_checks)
    assert window.pair_checks
    assert len(window.parameter_widgets) >= 28
    assert window.color_template_combo.count() >= 6
    assert window.band_power_view.show_distribution_check.isChecked()
    assert window.fooof_view.peak_mode_combo.currentData() == "representative"
    assert window.fooof_view.curve_mode_combo.currentData() == "observed"
    assert window.fooof_view.band_combo.currentData() is None
    header = window.findChild(QtWidgets.QWidget, "topToolbarPanel")
    assert header is not None
    assert header.width() == window.centralWidget().width() - 12
    assert not hasattr(window, "header_scroll")
    assert header.height() < 122
    assert window.header_logo.size() == QtCore.QSize(HEADER_LOGO_WIDTH, HEADER_LOGO_HEIGHT)
    assert window.header_logo_path.name == "luna-logo.svg"
    assert window.header_logo.pixmap() is not None
    assert not window.header_logo.pixmap().isNull()
    assert {
        window.run_button.height(),
        window.cancel_button.height(),
        window.save_result_button.height(),
        window.export_figure_button.height(),
    } == {GLOBAL_ACTION_HEIGHT}
    assert window.general_plot_scroll.horizontalScrollBarPolicy() == QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert not window.band_power_view.plot_scroll.widget().isAncestorOf(window.band_power_view.power_combo)
    fooof_scroll = window.fooof_view._page_scrolls["总览"]
    assert not fooof_scroll.widget().isAncestorOf(window.fooof_view.quality_combo)
    assert not window.connectivity_view.plot_scroll.widget().isAncestorOf(window.connectivity_view.metric_combo)
    assert not window.table.isVisible()
    assert window.table.rowCount() == 0
    assert window.table_toggle.text() == "▶ 展开结果表"
    assert not window.status_text.isVisible()
    assert not window.quality_alert_text.isVisible()
    window.indicator_checks["PSD"].setChecked(True)
    app.processEvents()
    method = window.parameter_widgets["psd.method"]
    window.parameter_widgets["psd.window_seconds"].setValue(1.5)
    method.setCurrentText("multitaper")
    app.processEvents()
    assert window._psd_method_stack.currentWidget() is window._psd_multitaper_panel
    assert window.parameter_widgets["psd.multitaper_bandwidth_hz"].isEnabled()
    assert not window.parameter_widgets["psd.window_seconds"].isEnabled()
    assert window._psd_welch_panel.isHidden()
    assert not window.parameter_widgets["psd.window_seconds"].isVisible()
    assert not window._psd_multitaper_panel.isHidden()
    assert window.parameter_widgets["psd.multitaper_bandwidth_hz"].isVisible()
    assert window._psd_method_stack.sizeHint().height() == window._psd_multitaper_panel.sizeHint().height()
    assert window.parameter_widgets["psd.multitaper_normalization"].currentText() == "length"
    window.parameter_widgets["psd.multitaper_bandwidth_hz"].setValue(5.5)
    active_multitaper = window._read_parameter_values()["psd"]
    assert "window_seconds" not in active_multitaper
    assert active_multitaper["multitaper_bandwidth_hz"] == 5.5
    method.setCurrentText("welch")
    app.processEvents()
    assert window._psd_method_stack.currentWidget() is window._psd_welch_panel
    assert not window._psd_welch_panel.isHidden()
    assert window._psd_multitaper_panel.isHidden()
    assert not window.parameter_widgets["psd.multitaper_bandwidth_hz"].isVisible()
    assert window._psd_method_stack.sizeHint().height() == window._psd_welch_panel.sizeHint().height()
    assert window.parameter_widgets["psd.window_seconds"].value() == 1.5
    active_welch = window._read_parameter_values()["psd"]
    assert "multitaper_bandwidth_hz" not in active_welch
    window.indicator_checks["wpli"].setChecked(True)
    app.processEvents()
    assert window.parameter_widgets["connectivity.region_pair_summary"].isEnabled()
    window.indicator_checks["MIC"].setChecked(False)
    window.indicator_checks["MIM"].setChecked(False)
    app.processEvents()
    assert not window.parameter_widgets["connectivity.rank_strategy"].isEnabled()
    assert not window.parameter_widgets["connectivity.n_components"].isVisible()
    assert window.minimumSize().width() == 860
    assert window.minimumSize().height() == 600
    assert not window.status_text.isVisible()
    window.log_toggle.setChecked(True)
    app.processEvents()
    assert window.status_text.isVisible()
    assert window.log_toggle.text() == "收起详细日志"
    window.log_toggle.setChecked(False)
    observed_header_heights = []
    observed_plot_widths = []
    observed_plot_heights = []
    observed_analysis_widths = []
    for width, height in ((860, 600), (1366, 768), (1920, 1080)):
        window.resize(width, height)
        app.processEvents()
        observed_header_heights.append(header.height())
        assert window.run_button.isVisible()
        assert window.general_plot_widget.isVisible()
        assert not window.analysis_config_scroll.horizontalScrollBar().isVisible()
        observed_plot_widths.append(window.general_plot_scroll.viewport().width())
        observed_plot_heights.append(window.general_plot_scroll.viewport().height())
        observed_analysis_widths.append(window.analysis_config_scroll.width())
        for control in (
            window.save_inspection_button,
            window.previous_project_data_button,
            window.next_project_data_button,
            window.next_unchecked_button,
        ):
            assert control.width() >= control.minimumSizeHint().width()
            assert control.geometry().right() <= window.inspection_controls_grid.geometry().right()
    assert max(observed_header_heights) - min(observed_header_heights) <= 2
    assert max(observed_header_heights) <= 110
    assert observed_analysis_widths[1] <= 360
    assert observed_plot_widths[1] >= 1000
    assert observed_plot_widths[2] > observed_plot_widths[1]
    assert observed_plot_heights[1] >= 420

    normal_left_width = window.analysis_config_scroll.width()
    window.focus_plot_button.setChecked(True)
    app.processEvents()
    assert not window.analysis_config_scroll.isVisible()
    assert window.focus_plot_button.text() == "退出专注绘图"
    assert window.result_stack.isVisible()
    window.focus_plot_button.setChecked(False)
    app.processEvents()
    assert window.analysis_config_scroll.isVisible()
    assert window.analysis_config_scroll.width() >= min(normal_left_width, 280)

    window.resize(860, 600)
    app.processEvents()
    combo_position = window.result_combo.mapTo(window, QtCore.QPoint(0, 0))
    window.general_plot_scroll.verticalScrollBar().setValue(window.general_plot_scroll.verticalScrollBar().maximum())
    app.processEvents()
    assert window.result_combo.mapTo(window, QtCore.QPoint(0, 0)) == combo_position
    window._set_result_table_source(pd.DataFrame({"value": [1, 2]}), reset=True)
    assert window.table.rowCount() == 0
    assert not window._result_table_loaded
    window.table_toggle.setChecked(True)
    window.quality_toggle.setChecked(True)
    window.log_toggle.setChecked(True)
    app.processEvents()
    assert window.table.rowCount() == 2
    assert window._result_table_loaded
    assert window.table.height() == RESULT_TABLE_EXPANDED_HEIGHT
    assert window.table_toggle.text() == "▼ 收起结果表"
    assert window.status_text.isVisible()
    assert window.quality_alert_text.isVisible()
    assert header.height() == observed_header_heights[-1]
    window.table_toggle.setChecked(False)
    window.quality_toggle.setChecked(False)
    window.log_toggle.setChecked(False)
    app.processEvents()
    assert not window.table.isVisible()
    assert window.table.minimumHeight() == 0
    assert window.table.maximumHeight() == 0
    assert window.table_toggle.text() == "▶ 展开结果表"
    window._set_result_table_source(pd.DataFrame({"replacement": [3]}), reset=True)
    assert not window.table.isVisible()
    assert window.table.rowCount() == 0
    assert not window._result_table_source.empty
    shown: list[str] = []
    window._show_payload = lambda payload, **_kwargs: shown.append(str(payload.get("metric")))
    window._active_analysis_task_id = "delivery-test"
    window._result_ready(
        {
            "task_id": "delivery-test",
            "metric": "Band Power",
            "file_id": "synthetic",
            "file_uid": "synthetic-uid",
            "tables": {},
            "record": {},
        }
    )
    app.processEvents()
    assert shown == ["Band Power"]
    window.close()
    app.quit()


@pytest.mark.skipif(_SKIP_QT_WINDOW_TESTS, reason="Set LUNA_RUN_QT_TESTS=1 to opt into offscreen Qt window tests in CI")
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
    assert view.band_selection_button.text() == "频带 1/1"
    assert view.pair_selection_button.text() == "脑区对 1/1"
    assert view.band_list.isHidden()
    assert view.pair_scroll.isHidden()
    assert view.more_settings_panel.isHidden()
    assert not view.plot_scroll.widget().isAncestorOf(view.more_settings_button)
    view.more_settings_button.setChecked(True)
    app.processEvents()
    assert not view.more_settings_panel.isHidden()
    view.more_settings_button.setChecked(False)
    app.processEvents()
    view._matrix_clicked(type("Event", (), {"inaxes": view.matrix_figure.axes[0], "xdata": 1.0, "ydata": 0.0})())
    assert view._focus_pair == ("M1", "STR")
    assert len(view.spectrum_figure.axes[0].lines) == 1
    pair_action = view.pair_selection_menu.actions()[0]
    pair_action.setChecked(False)
    app.processEvents()
    assert view._selected_pairs() == []
    assert view.pair_selection_button.text() == "脑区对 0/1"
    assert "请选择至少一个脑区对" in view.status_label.text()
    pair_action.setChecked(True)
    app.processEvents()
    assert view._selected_pairs() == [("M1", "STR")]
    assert view.pair_selection_button.text() == "脑区对 1/1"

    tde_spectrum = pd.DataFrame([{
        "region_a": "M1", "region_b": "STR", "method": "phase_periodicity_phase_only",
        "antisymmetrized": True, "frequency_band": "alpha", "band_low_hz": 5.0,
        "band_high_hz": 6.0, "delay_ms": -5.0, "estimate_strength": 0.2,
    }])
    tde_summary = pd.DataFrame([{
        "region_a": "M1", "region_b": "STR", "frequency_band": "alpha",
        "band_low_hz": 5.0, "band_high_hz": 6.0, "region_peak_delay_ms": -5.0,
        "region_peak_strength": 0.2, "channel_pair_median_delay_ms": -5.0,
        "channel_pair_mad_delay_ms": 0.0, "n_channel_pairs": 1,
    }])
    view.set_payload({"metric": "Time Delay", "file_id": "synthetic", "tables": {"region_spectrum": tde_spectrum, "band_summary": tde_summary}})
    assert view.more_settings_button.isHidden()
    assert view.scale_label.isHidden()
    view.set_payload({"metric": "Connectivity", "file_id": "synthetic", "tables": {"region_summary": spectrum, "band_summary": bands}})
    assert not view.more_settings_button.isHidden()
    assert view.more_settings_panel.isHidden()

    original_refresh_impl = view._refresh_impl

    def fail_refresh() -> None:
        raise ValueError("synthetic refresh failure")

    view._refresh_impl = fail_refresh
    view._refresh()
    assert "刷新失败" in view.status_label.text()
    assert "未显示未标记的旧结果" in view.status_label.text()
    view._refresh_impl = original_refresh_impl
    view.close()
    app.quit()


@pytest.mark.skipif(_SKIP_QT_WINDOW_TESTS, reason="Set LUNA_RUN_QT_TESTS=1 to opt into offscreen Qt window tests in CI")
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


@pytest.mark.skipif(_SKIP_QT_WINDOW_TESTS, reason="Set LUNA_RUN_QT_TESTS=1 to opt into offscreen Qt window tests in CI")
def test_connectivity_view_separates_line_noise_marker_from_plot_exclusion(monkeypatch) -> None:
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from lfp_analysis.connectivity_gui import ConnectivityView

    app = QApplication.instance() or QApplication([])
    frequencies = [49.0, 49.5, 50.0, 50.5, 51.0]
    spectrum = pd.DataFrame(
        [
            {
                "method": "mim",
                "region_a": "M1",
                "region_b": "STR",
                "component_index": float("nan"),
                "frequency_hz": frequency,
                "value_raw": frequency / 100.0,
                "value_strength": frequency / 100.0,
                "n_epochs": 8,
                "frequency_is_masked_for_plot": frequency == 50.0,
                "frequency_is_excluded_line_noise": frequency == 50.0,
            }
            for frequency in frequencies
        ]
    )
    bands = pd.DataFrame(
        [{
            "method": "mim", "region_a": "M1", "region_b": "STR", "component_index": float("nan"),
            "band": "line", "band_low_hz": 49.0, "band_high_hz": 51.0,
            "value_raw_or_summary": 0.5, "value_strength": 0.5, "status": "ok",
        }]
    )
    view = ConnectivityView()
    view.set_payload({"metric": "Connectivity", "file_id": "synthetic", "tables": {"region_summary": spectrum, "band_summary": bands}})
    assert not view.line_noise_markers_check.isChecked()
    assert not view.line_noise_exclusion_check.isChecked()
    assert np.isfinite(view.spectrum_figure.axes[0].lines[0].get_ydata()).all()

    before = np.asarray(view.spectrum_figure.axes[0].lines[0].get_ydata(), dtype=float).copy()
    view.line_noise_markers_check.setChecked(True)
    app.processEvents()
    assert np.array_equal(before, np.asarray(view.spectrum_figure.axes[0].lines[0].get_ydata(), dtype=float), equal_nan=True)
    assert any("工频标记" in str(p.get_label()) for p in view.spectrum_figure.axes[0].patches)

    view.line_noise_exclusion_check.setChecked(True)
    app.processEvents()
    assert np.isnan(view.spectrum_figure.axes[0].lines[0].get_ydata()[2])
    view.line_noise_exclusion_check.setChecked(False)
    app.processEvents()
    assert np.isfinite(view.spectrum_figure.axes[0].lines[0].get_ydata()).all()
    view.line_noise_markers_check.setChecked(False)
    app.processEvents()
    assert not any("工频标记" in str(p.get_label()) for p in view.spectrum_figure.axes[0].patches)
    view.close()
    app.quit()
