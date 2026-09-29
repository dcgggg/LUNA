"""Small end-to-end checks for the declared desktop/connectivity install."""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import mne
import numpy as np
import pandas as pd
import yaml

from lfp_analysis.diagnostics import inspect_input_metadata
from lfp_analysis.gui_engine import (
    load_saved_run,
    load_saved_table,
    resolve_manifest_path,
    run_gui_analysis,
)


def _make_known_lag_epochs(path: Path) -> tuple[list[str], np.ndarray]:
    """Write labelled synthetic epochs with a lagged cross-region source."""
    rng = np.random.default_rng(20260928)
    sfreq = 500.0
    n_epochs = 8
    n_times = 2000
    times = np.arange(n_times) / sfreq
    data = np.empty((n_epochs, 4, n_times), dtype=float)
    delay_samples = 4

    for epoch_index in range(n_epochs):
        phase_a, phase_b = rng.uniform(0.0, 2.0 * np.pi, size=2)
        source_a = np.sin(2.0 * np.pi * 10.0 * times + phase_a)
        source_b = np.sin(2.0 * np.pi * 24.0 * times + phase_b)
        delayed_a = np.concatenate((np.zeros(delay_samples), source_a[:-delay_samples]))
        delayed_b = np.concatenate((np.zeros(delay_samples), source_b[:-delay_samples]))
        noise = rng.normal(scale=0.18, size=(4, n_times))
        data[epoch_index] = 20e-6 * np.stack(
            (
                source_a + 0.35 * source_b,
                0.25 * source_a + source_b,
                delayed_a + 0.35 * delayed_b,
                0.25 * delayed_a + delayed_b,
            )
        ) + 3e-6 * noise

    channel_names = ["QC_A_01", "QC_A_02", "QC_B_01", "QC_B_02"]
    info = mne.create_info(channel_names, sfreq=sfreq, ch_types=["eeg"] * len(channel_names))
    events = np.column_stack((np.arange(n_epochs) * (n_times + 100), np.zeros(n_epochs, dtype=int), np.ones(n_epochs, dtype=int)))
    epochs = mne.EpochsArray(
        data,
        info,
        events=events,
        event_id={"synthetic": 1},
        tmin=0.0,
        baseline=None,
        verbose=False,
    )
    epochs.save(path, overwrite=True, verbose=False)
    return channel_names, data


def test_connectivity_compute_save_and_reload_from_synthetic_fif(tmp_path: Path) -> None:
    """Exercise the same file→compute→bundle→reload path used by the GUI."""
    input_path = tmp_path / "synthetic-lagged-epo.fif"
    channel_names, _data = _make_known_lag_epochs(input_path)
    diagnostic_header = inspect_input_metadata(input_path)
    assert diagnostic_header["n_epochs"] == 8
    assert diagnostic_header["n_channels"] == len(channel_names)
    assert diagnostic_header["channel_names_included"] is False
    assert diagnostic_header["signal_samples_loaded"] is False
    assert diagnostic_header["path"] == "<selected local file>"

    config_path = tmp_path / "smoke.yaml"
    config = copy.deepcopy(yaml.safe_load((Path(__file__).resolve().parents[1] / "configs" / "default.yaml").read_text(encoding="utf-8")))
    config["expected_data"].update(
        sampling_rate_hz=500.0,
        n_channels=4,
        n_times_per_epoch=2000,
        preprocessed_highpass_hz=1.0,
        preprocessed_lowpass_hz=200.0,
    )
    config["quality"]["line_noise_hz"] = []
    config["connectivity"].update(
        methods=["mic", "mim", "wpli", "dpli", "wpli2_debiased"],
        mode="multitaper",
        fmin_hz=5.0,
        fmax_hz=80.0,
        mt_bandwidth_hz=6.0,
        n_jobs=1,
        min_epochs=5,
        rank_sensitivity_enabled=False,
        stability_enabled=False,
        stability_n_subsamples=0,
        line_noise={"frequency_hz": 50.0, "mask_width_hz": 1.0, "harmonics": False, "mask_for_analysis": True, "mask_for_plot": True},
    )
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    region_by_name = {
        channel_names[0]: "QC_A",
        channel_names[1]: "QC_A",
        channel_names[2]: "QC_B",
        channel_names[3]: "QC_B",
    }
    snapshot = {
        "run_id": "synthetic-connectivity-platform-smoke",
        "input_files": [str(input_path)],
        "output_dir": str(tmp_path / "results"),
        "indicators": ["MIC", "MIM", "wpli", "dpli", "wpli2_debiased"],
        "selected_channel_names": channel_names,
        "selected_epoch_indices": list(range(8)),
        "selected_region_pairs": [["QC_A", "QC_B"]],
        "channel_mapping": [
            {"channel_name": name, "physical_channel_number": "", "region": region_by_name[name], "label": ""}
            for name in channel_names
        ],
        "selection": {"time_start_s": 0.0, "time_end_s": 4.0},
        "values": {
            "connectivity": {
                "mode": "multitaper",
                "fmin_hz": 5.0,
                "fmax_hz": 80.0,
                "mt_bandwidth_hz": 6.0,
                "mt_adaptive": False,
                "mt_low_bias": True,
                "n_components": 1,
                "n_jobs": 1,
                "min_epochs": 5,
                "rank_strategy": "data_driven_energy_99pct",
                "rank_variance_threshold": 0.99,
                "stability_n_subsamples": 0,
            }
        },
    }

    run = run_gui_analysis(snapshot, config_path, tmp_path / "metadata")
    assert run["manifest"]["status"] == "completed", run["manifest"]["errors"]
    file_record = run["manifest"]["files"][0]
    assert file_record["identity_status"] == "file_only_identity_unresolved"
    connectivity_record = next(item for item in file_record["metrics"] if item["metric"] == "Connectivity")
    assert connectivity_record["status"] == "ok"

    bundle = load_saved_run(run["run_dir"])
    assert bundle["manifest"]["run_id"] == snapshot["run_id"]
    assert bundle["parameters"]["indicators"] == snapshot["indicators"]
    spectrum_path = resolve_manifest_path(
        Path(run["run_dir"]) / file_record["file_dir"] / "connectivity",
        connectivity_record["paths"]["tables"]["spectrum"],
        "connectivity spectrum",
    )
    spectrum = load_saved_table(spectrum_path)
    required_methods = {"mic", "mim", "wpli", "dpli", "wpli2_debiased"}
    assert required_methods.issubset(set(spectrum["method"].dropna().astype(str)))
    assert set(spectrum["region_a"].dropna().astype(str)) == {"QC_A", "QC_B"}
    assert set(spectrum["region_b"].dropna().astype(str)) == {"QC_A", "QC_B"}
    assert (pd.to_numeric(spectrum["n_epochs"], errors="coerce") == 8).all()
    assert spectrum["frequency_hz"].between(5.0, 80.0).all()
    assert np.isfinite(pd.to_numeric(spectrum["value_raw"], errors="coerce")).any()

    arrays_path = resolve_manifest_path(
        Path(run["run_dir"]) / file_record["file_dir"],
        connectivity_record["paths"]["arrays"],
        "connectivity arrays",
    )
    with np.load(arrays_path) as arrays:
        assert {"frequency_hz", "value_raw", "value_strength", "method"}.issubset(arrays.files)
        assert arrays["frequency_hz"].ndim == 1
        assert arrays["value_raw"].shape == arrays["frequency_hz"].shape
        assert arrays["value_strength"].shape == arrays["frequency_hz"].shape
        assert set(arrays["method"].astype(str)) == required_methods
        assert arrays["frequency_hz"].size == len(spectrum)

    persisted_manifest = json.loads((Path(run["run_dir"]) / "run_manifest.json").read_text(encoding="utf-8"))
    assert persisted_manifest["status"] == "completed"
    assert persisted_manifest["files"][0]["metrics"][0]["metric"] == "Connectivity"


def test_offscreen_gui_import_psd_save_and_reload_history(tmp_path: Path, monkeypatch) -> None:
    """Exercise a real Qt window through synthetic-FIF import and saved-result reload."""
    import pytest

    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    from PySide6 import QtCore, QtWidgets
    from PySide6.QtWidgets import QApplication

    from lfp_analysis import gui as gui_module

    project_root = tmp_path / "isolated-app"
    config_dir = project_root / "configs"
    config_dir.mkdir(parents=True)
    config = copy.deepcopy(
        yaml.safe_load((Path(__file__).resolve().parents[1] / "configs" / "default.yaml").read_text(encoding="utf-8"))
    )
    config["expected_data"].update(sampling_rate_hz=500.0, n_channels=4, n_times_per_epoch=2000)
    config["quality"]["line_noise_hz"] = []
    config["psd"].update(method="welch", fmin_hz=2.0, fmax_hz=80.0, nperseg=500, noverlap=250)
    config_path = config_dir / "default.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(gui_module, "PROJECT_ROOT", project_root)

    qsettings_type = QtCore.QSettings
    settings_path = tmp_path / "isolated-LUNA.ini"

    def isolated_qsettings(organization: str, application: str):
        if (organization, application) == ("LUNA", "LUNA"):
            return qsettings_type(str(settings_path), qsettings_type.Format.IniFormat)
        return qsettings_type(organization, application)

    monkeypatch.setattr(gui_module.QtCore, "QSettings", isolated_qsettings)
    input_path = tmp_path / "synthetic-gui-epo.fif"
    _make_known_lag_epochs(input_path)
    output_dir = tmp_path / "gui-results"
    app = QApplication.instance() or QApplication([])
    window = gui_module.MainWindow(output_dir=str(output_dir))
    reopened = None
    reported_errors: list[str] = []
    window._show_message = lambda _icon, title, message: reported_errors.append(f"{title}: {message}")

    def wait_until(predicate, *, timeout_s: float = 60.0) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return True
            time.sleep(0.01)
        app.processEvents()
        return bool(predicate())

    try:
        window.show()
        window.load_paths([str(input_path)])
        assert wait_until(lambda: window.current_info is not None), (
            f"GUI FIF import did not finish; errors={reported_errors}; state={window.task_label.text()}"
        )
        assert int(window.current_info["n_epochs"]) == 8
        assert float(window.current_info["sfreq"]) == 500.0
        for indicator, checkbox in window.indicator_checks.items():
            checkbox.setChecked(indicator == "PSD")

        window._run()
        assert wait_until(lambda: not window._running and window.loaded_run is not None), (
            f"GUI PSD task did not finish; errors={reported_errors}; state={window.task_label.text()}"
        )
        assert window.loaded_run["manifest"]["status"] == "completed", window.loaded_run["manifest"].get("errors")
        run_dir = Path(window.loaded_run["run_dir"])
        file_metrics = window.loaded_run["manifest"]["files"][0]["metrics"]
        psd_record = next(record for record in file_metrics if record["metric"] == "PSD")
        assert psd_record["status"] == "completed"
        file_root = resolve_manifest_path(run_dir, window.loaded_run["manifest"]["files"][0]["file_dir"], "file_dir")
        saved_tables = psd_record.get("paths", {}).get("tables", {})
        assert saved_tables
        assert all((file_root / "psd" / relative).is_file() for relative in saved_tables.values())

        reopened = gui_module.MainWindow(output_dir=str(output_dir))
        reopened._show_message = lambda _icon, title, message: reported_errors.append(f"reload {title}: {message}")
        reopened.show()
        monkeypatch.setattr(
            QtWidgets.QFileDialog,
            "getExistingDirectory",
            staticmethod(lambda *_args, **_kwargs: str(run_dir)),
        )
        reopened._load_history()
        app.processEvents()
        assert reopened.loaded_run is not None
        assert reopened.loaded_run["manifest"]["run_id"] == window.loaded_run["manifest"]["run_id"]
        assert reopened.result_combo.count() >= 1
        assert any(payload.get("metric") == "PSD" for payload in reopened.result_payloads.values())
        assert "历史运行" in reopened.task_label.text()
        assert not reported_errors, reported_errors
    finally:
        if reopened is not None:
            reopened.close()
        window.close()
        app.processEvents()
