import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from lfp_analysis import diagnostics
from lfp_analysis.diagnostics import write_failure_report


def test_connectivity_smoke_test_runs_all_estimator_methods() -> None:
    pytest.importorskip("mne_connectivity")

    report = diagnostics.run_connectivity_smoke_test()

    assert report["status"] == "ok"
    assert report["synthetic_only"] is True
    assert report["signal_samples_included"] is False
    assert report["n_valid_epochs"] == 6
    assert report["data_shape_epochs_channels_times"] == [6, 4, 3000]
    assert report["frequency_grid_hz"]["min"] == 5.0
    assert report["frequency_grid_hz"]["max"] == 80.0
    assert set(report["method_results"]) == {
        "mic",
        "mim",
        "wpli",
        "dpli",
        "wpli2_debiased",
        "imcoh",
        "coh",
    }
    assert {item["status"] for item in report["method_results"].values()} == {"ok"}
    assert report["rank_pairs"]
    assert json.loads(json.dumps(report))["status"] == "ok"


def test_connectivity_smoke_test_distinguishes_missing_backend(monkeypatch) -> None:
    import pandas as pd

    from lfp_analysis import connectivity

    methods = ["mic", "mim", "wpli", "dpli", "wpli2_debiased", "imcoh", "coh"]

    def missing_backend(*args, **kwargs):
        return {
            "status": "not_run_connectivity_backend_unavailable",
            "spectrum": pd.DataFrame(),
            "failures": pd.DataFrame(
                [
                    {
                        "method": method,
                        "failure_stage": "connectivity_backend_import",
                        "failure_reason": "synthetic missing backend",
                        "failure_traceback": "",
                    }
                    for method in methods
                ]
            ),
            "estimation_calls": pd.DataFrame(),
            "metadata": {"n_valid_epochs": 6},
        }

    monkeypatch.setattr(connectivity, "compute_connectivity", missing_backend)

    report = diagnostics.run_connectivity_smoke_test()

    assert report["status"] == "dependency_unavailable"
    assert report["install_extra"] == "connectivity"
    assert {item["status"] for item in report["method_results"].values()} == {"failed"}
    assert all(
        item["failure_stage"] == "connectivity_backend_import"
        for item in report["method_results"].values()
    )


def test_diagnostic_command_returns_nonzero_for_failed_connectivity_smoke(monkeypatch, capsys) -> None:
    def failed_report(**kwargs):
        assert kwargs["connectivity_self_test"] is True
        return {"connectivity_self_test": {"status": "failed"}}

    monkeypatch.setattr(diagnostics, "collect_diagnostics", failed_report)

    assert diagnostics.main(["--self-test-connectivity"]) == 2
    assert '"status": "failed"' in capsys.readouterr().out


def test_diagnostic_checks_pyside6_submodule_api(monkeypatch) -> None:
    modules = {
        "PySide6": SimpleNamespace(__file__="site-packages/PySide6/__init__.py"),
        "PySide6.QtCore": SimpleNamespace(QObject=object),
        "PySide6.QtWidgets": SimpleNamespace(QApplication=object),
    }

    def import_module(name: str):
        return modules[name]

    monkeypatch.setattr(diagnostics.importlib, "import_module", import_module)

    status = diagnostics._module_import_status("PySide6", ("QtCore.QObject", "QtWidgets.QApplication"))

    assert status["status"] == "ok"


def test_diagnostic_reports_missing_pyside6_symbol(monkeypatch) -> None:
    modules = {
        "PySide6": SimpleNamespace(__file__="site-packages/PySide6/__init__.py"),
        "PySide6.QtCore": SimpleNamespace(QObject=object),
        "PySide6.QtWidgets": SimpleNamespace(),
    }

    def import_module(name: str):
        return modules[name]

    monkeypatch.setattr(diagnostics.importlib, "import_module", import_module)

    status = diagnostics._module_import_status("PySide6", ("QtCore.QObject", "QtWidgets.QApplication"))

    assert status["status"] == "api_missing"
    assert status["missing_symbols"] == ["QtWidgets.QApplication"]


def test_failure_report_is_atomic_shape_only_and_redacts_local_path(tmp_path: Path) -> None:
    target = tmp_path / "diagnostics" / "failure.json"
    report = write_failure_report(
        target,
        {
            "stage": "connectivity_backend_import",
            "traceback": 'File "C:\\Users\\Researcher\\LUNA\\src\\module.py", line 12',
            "input": {"shape_epochs_channels_times": [8, 16, 5000], "sampling_rate_hz": 1000.0},
            "data": [[1.0, 2.0]],
            "environment_variables": {"TOKEN": "must not appear"},
        },
    )
    assert report == target
    text = target.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert payload["failure"]["input"]["shape_epochs_channels_times"] == [8, 16, 5000]
    assert "C:\\Users\\Researcher" not in text
    assert "must not appear" not in text
    assert '"data"' not in text
    assert not list(target.parent.glob("*.tmp"))


@pytest.mark.parametrize(
    "local_path",
    [
        r"C:\Users\Researcher\Documents\Sensitive Study\Subject A\record.fif",
        "/Users/researcher/Documents/Sensitive Study/Subject A/record.fif",
        "/tmp/Sensitive Study/Subject A/record.fif",
    ],
)
def test_redaction_hides_entire_local_path_without_breaking_urls(local_path: str) -> None:
    redacted = diagnostics.redact_text(f'Failed to open "{local_path}". See https://example.org/help.')

    assert "<local-path>" in redacted
    assert "Sensitive Study" not in redacted
    assert "Subject A" not in redacted
    assert "https://example.org/help." in redacted


def test_invocation_report_contains_only_launcher_name() -> None:
    assert diagnostics._safe_invocation_name(
        r"C:\Users\Researcher\AppData\Local\Programs\LUNA\Scripts\luna-diagnose.exe"
    ) == "luna-diagnose.exe"
    assert diagnostics._safe_invocation_name("/Users/researcher/.venv/bin/luna-diagnose") == "luna-diagnose"
