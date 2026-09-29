"""Privacy-conscious runtime and connectivity diagnostics for LUNA."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata as importlib_metadata
import importlib.util
import json
import os
import platform
import re
import sys
import tempfile
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Any

from . import __version__
from .app_paths import (
    default_config_directory,
    default_log_directory,
    default_metadata_directory,
    default_output_directory,
    user_config_directory,
    user_data_directory,
)

PACKAGE_CHECKS = (
    ("numpy", "numpy", "numpy", ()),
    ("scipy", "scipy", "scipy", ()),
    ("pandas", "pandas", "pandas", ()),
    ("matplotlib", "matplotlib", "matplotlib", ()),
    ("mne", "mne", "mne", ()),
    ("mne-connectivity", "mne_connectivity", "mne-connectivity", ("spectral_connectivity_epochs",)),
    ("netCDF4", "netCDF4", "netCDF4", ()),
    ("xarray", "xarray", "xarray", ()),
    ("scikit-learn", "sklearn", "scikit-learn", ()),
    ("joblib", "joblib", "joblib", ()),
    ("PySide6", "PySide6", "PySide6", ("QtCore.QObject", "QtWidgets.QApplication")),
    ("specparam", "specparam", "specparam", ("SpectralModel",)),
    ("fooof", "fooof", "fooof", ("FOOOF",)),
    ("pybispectra", "pybispectra", "pybispectra", ("TDE", "compute_fft")),
    ("numba", "numba", "numba", ()),
    ("llvmlite", "llvmlite", "llvmlite", ()),
    ("threadpoolctl", "threadpoolctl", "threadpoolctl", ("threadpool_info",)),
)

def redact_text(value: Any) -> str:
    """Remove absolute local paths while retaining traceback lines and context."""
    text = str(value)
    # Redact before home-prefix normalization; otherwise descendants such as a
    # private project folder below C:\Users\name could remain in the report.
    text = re.sub(r"(?i)(?<![\w])(?:[A-Z]:[\\/]|\\\\[^\\\s]+\\[^\\\s]+\\)[^\r\n\"']+", "<local-path>", text)
    # On POSIX, redact absolute paths including one-level paths and paths with
    # spaces. Do not start inside URLs or Windows drive paths.
    text = re.sub(r"(?<![\w:/])/[^\r\n\"']+", "<local-path>", text)
    return text


def _safe_invocation_name(value: str) -> str:
    """Report the launcher name without exposing its installation location."""
    return PureWindowsPath(str(value)).name if value else ""


def _safe_module_location(module_path: str) -> str:
    """Keep a useful package-relative location without sharing machine paths."""
    if not module_path:
        return ""
    normalized = module_path.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    for marker in ("site-packages", "dist-packages", "lfp_analysis"):
        if marker in parts:
            return "/".join(parts[parts.index(marker) :])
    return "/".join(parts[-3:])


def _module_import_status(module_name: str, attributes: tuple[str, ...]) -> dict[str, Any]:
    try:
        module = importlib.import_module(module_name)
        missing = []
        for name in attributes:
            owner_name, separator, attribute_name = name.rpartition(".")
            owner = importlib.import_module(f"{module_name}.{owner_name}") if separator else module
            if not hasattr(owner, attribute_name if separator else name):
                missing.append(name)
        if missing:
            return {"status": "api_missing", "missing_symbols": missing, "module_location": _safe_module_location(getattr(module, "__file__", ""))}
        return {"status": "ok", "module_location": _safe_module_location(getattr(module, "__file__", ""))}
    except Exception as exc:  # noqa: BLE001 - report binary/import failures without aborting diagnostics
        return {"status": "failed", "error_type": type(exc).__name__, "error": redact_text(exc)}


def _version(distribution: str) -> str:
    try:
        return importlib_metadata.version(distribution)
    except importlib_metadata.PackageNotFoundError:
        return "not_installed"
    except Exception as exc:  # noqa: BLE001 - report metadata backend failures
        return f"version_lookup_failed:{type(exc).__name__}"


def _write_probe(directory: Path, label: str) -> dict[str, Any]:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".luna-write-check-", dir=directory, delete=True):
            pass
        return {"writable": True, "location": label}
    except Exception as exc:  # noqa: BLE001 - diagnostic should report each inaccessible location
        return {"writable": False, "location": label, "error_type": type(exc).__name__, "error": redact_text(exc)}


def _runtime_modules() -> dict[str, str]:
    result: dict[str, str] = {}
    for name in ("lfp_analysis", "lfp_analysis.gui", "lfp_analysis.connectivity", "lfp_analysis.gui_engine", "mne_connectivity", "pybispectra"):
        try:
            spec = importlib.util.find_spec(name)
            result[name] = _safe_module_location(spec.origin) if spec and spec.origin else ("namespace_or_builtin" if spec else "not_found")
        except Exception as exc:  # noqa: BLE001 - preserve import-path lookup diagnostics
            result[name] = f"lookup_failed:{type(exc).__name__}:{redact_text(exc)}"
    return result


def _threadpools() -> list[dict[str, Any]] | dict[str, str]:
    try:
        module = importlib.import_module("threadpoolctl")
        return [
            {
                "internal_api": entry.get("internal_api"),
                "prefix": entry.get("prefix"),
                "version": entry.get("version"),
                "num_threads": entry.get("num_threads"),
                "architecture": entry.get("architecture"),
            }
            for entry in module.threadpool_info()
        ]
    except Exception as exc:  # noqa: BLE001 - threadpool reporting must not prevent a report
        return {"status": "unavailable", "error": f"{type(exc).__name__}: {redact_text(exc)}"}


def run_connectivity_smoke_test() -> dict[str, Any]:
    """Exercise every MNE-Connectivity estimator on deterministic synthetic epochs."""
    started = time.perf_counter()
    methods = ["mic", "mim", "wpli", "dpli", "wpli2_debiased", "imcoh", "coh"]
    data_shape = [6, 4, 3000]
    sfreq_hz = 500.0
    report: dict[str, Any] = {
        "status": "failed",
        "synthetic_only": True,
        "signal_samples_included": False,
        "estimator": "lfp_analysis.connectivity.compute_connectivity",
        "methods_requested": methods,
        "data_shape_epochs_channels_times": data_shape,
        "sfreq_hz": sfreq_hz,
        "parameters": {
            "mode": "multitaper",
            "fmin_hz": 5.0,
            "fmax_hz": 80.0,
            "mt_bandwidth_hz": 6.0,
            "n_jobs": 1,
            "min_epochs": 5,
            "rank_sensitivity_enabled": False,
            "stability_enabled": False,
        },
    }
    try:
        import mne
        import pandas as pd

        from .connectivity import (
            BIVARIATE_METHODS,
            MULTIVARIATE_METHODS,
            compute_connectivity,
        )
        from .quality import assess_quality
        from .synthetic import make_synthetic_epochs

        methods = list(dict.fromkeys((*MULTIVARIATE_METHODS, *BIVARIATE_METHODS)))
        report["methods_requested"] = methods
        data, channel_names = make_synthetic_epochs(
            n_epochs=data_shape[0],
            n_channels=data_shape[1],
            n_times=data_shape[2],
            sfreq=sfreq_hz,
            seed=20260929,
        )
        quality_config = {
            "quality": {
                "line_noise_hz": [],
                "flat_std_threshold": 1e-15,
                "max_abs_z_threshold": 20.0,
                "saturation_fraction_threshold": 0.01,
            }
        }
        quality = assess_quality(data, sfreq_hz, channel_names, quality_config)
        channel_table = pd.DataFrame(
            {
                "array_index": range(len(channel_names)),
                "channel_name": channel_names,
                "region": ["SIM_A", "SIM_A", "SIM_B", "SIM_B"],
            }
        )
        config = {
            **quality_config,
            "connectivity": {
                "methods": methods,
                "mode": "multitaper",
                "fmin_hz": 5.0,
                "fmax_hz": 80.0,
                "fdecim": 1,
                "mt_bandwidth_hz": 6.0,
                "mt_adaptive": False,
                "mt_low_bias": True,
                "n_components": 1,
                "n_jobs": 1,
                "min_epochs": 5,
                "rank_strategy": "data_driven_energy_99pct",
                "rank_relative_tolerance": 1e-6,
                "rank_variance_threshold": 0.99,
                "fixed_rank_by_region": {},
                "rank_sensitivity_enabled": False,
                "stability_enabled": False,
                "stability_n_subsamples": 0,
                "line_noise": {
                    "frequency_hz": 50.0,
                    "mask_width_hz": 1.0,
                    "harmonics": False,
                    "mask_for_analysis": False,
                    "mask_for_plot": False,
                },
                "region_pair_summary": "median",
            },
            "bands": {"theta": [4.0, 8.0], "alpha": [8.0, 12.0]},
            "expected_data": {"preprocessed_highpass_hz": 1.0, "preprocessed_lowpass_hz": 200.0},
        }
        previous_mne_log_level = mne.set_log_level("WARNING", return_old_level=True)
        try:
            result = compute_connectivity(
                data,
                sfreq_hz,
                channel_table,
                quality["epoch"],
                config,
                analysis_task_id="luna-diagnostic-synthetic-smoke",
            )
        finally:
            mne.set_log_level(previous_mne_log_level)
    except Exception as exc:  # noqa: BLE001 - diagnostics must serialize backend/runtime failures
        report.update(
            {
                "status": "failed",
                "failure_stage": "synthetic_connectivity_smoke_test",
                "error_type": type(exc).__name__,
                "error": redact_text(exc),
                "traceback": redact_text(traceback.format_exc()),
            }
        )
        report["elapsed_s"] = float(time.perf_counter() - started)
        return report

    spectrum = result.get("spectrum")
    observed_methods = set()
    if isinstance(spectrum, pd.DataFrame) and not spectrum.empty and "method" in spectrum:
        observed_methods = set(spectrum["method"].dropna().astype(str))
    failure_rows = result.get("failures")
    failure_by_method: dict[str, dict[str, str]] = {}
    if isinstance(failure_rows, pd.DataFrame) and not failure_rows.empty:
        for row in failure_rows.to_dict("records"):
            for method in str(row.get("method", "")).split(","):
                method = method.strip()
                if method:
                    failure_by_method[method] = {
                        "failure_stage": str(row.get("failure_stage", "estimation")),
                        "reason": redact_text(row.get("failure_reason", "")),
                    }
                    details = row.get("failure_traceback")
                    if details:
                        failure_by_method[method]["traceback"] = redact_text(details)

    method_status: dict[str, dict[str, Any]] = {}
    for method in methods:
        failure = failure_by_method.get(method)
        if method in observed_methods and failure is None:
            method_status[method] = {"status": "ok"}
        elif failure is not None:
            method_status[method] = {"status": "failed", **failure}
        else:
            method_status[method] = {"status": "failed", "reason": "no result rows returned for requested method"}

    frequencies = (
        pd.to_numeric(spectrum["frequency_hz"], errors="coerce").dropna()
        if isinstance(spectrum, pd.DataFrame) and not spectrum.empty and "frequency_hz" in spectrum
        else pd.Series(dtype=float)
    )
    calls = result.get("estimation_calls")
    ranks: list[dict[str, Any]] = []
    if isinstance(calls, pd.DataFrame) and not calls.empty:
        rank_cols = [column for column in ("rank_seed", "rank_target") if column in calls]
        if rank_cols:
            rank_rows = calls[rank_cols].dropna(how="all").drop_duplicates()
            ranks = [
                {
                    column: int(value) if float(value).is_integer() else float(value)
                    for column, value in row.items()
                    if pd.notna(value)
                }
                for row in rank_rows.to_dict("records")
            ]

    report.update(
        {
            "status": "ok" if result.get("status") == "ok" and all(row["status"] == "ok" for row in method_status.values()) else "failed",
            "engine_status": str(result.get("status", "unknown")),
            "n_valid_epochs": int(result.get("metadata", {}).get("n_valid_epochs", data_shape[0])),
            "method_results": method_status,
            "observed_methods": sorted(observed_methods),
            "n_spectrum_rows": len(spectrum) if isinstance(spectrum, pd.DataFrame) else 0,
            "frequency_grid_hz": {
                "n": frequencies.nunique(),
                "min": float(frequencies.min()) if not frequencies.empty else None,
                "max": float(frequencies.max()) if not frequencies.empty else None,
            },
            "n_estimator_calls": len(calls) if isinstance(calls, pd.DataFrame) else 0,
            "rank_pairs": ranks,
        }
    )
    if report["status"] != "ok" and report.get("engine_status") == "not_run_connectivity_backend_unavailable":
        report["status"] = "dependency_unavailable"
        report["install_extra"] = "connectivity"
    report["elapsed_s"] = float(time.perf_counter() - started)
    return report


def collect_diagnostics(
    *,
    output_dir: str | Path | None = None,
    input_file: str | Path | None = None,
    connectivity_self_test: bool = False,
) -> dict[str, Any]:
    """Collect environment/import/path facts; never reads signal samples or all env vars."""
    package_versions: dict[str, dict[str, Any]] = {}
    for distribution, module_name, version_name, attributes in PACKAGE_CHECKS:
        package_versions[distribution] = {
            "version": _version(version_name),
            "import": _module_import_status(module_name, attributes),
        }

    try:
        ownership = importlib_metadata.packages_distributions().get("lfp_analysis", [])
    except Exception:  # noqa: BLE001 - ownership metadata is diagnostic-only
        ownership = []
    ownership = sorted(set(ownership))

    data_root = user_data_directory()
    project_root = Path(__file__).resolve().parents[2]
    app_paths = {
        "user_data": _write_probe(data_root, "LUNA user data"),
        "user_config": _write_probe(user_config_directory(), "LUNA user configuration"),
        "logs": _write_probe(default_log_directory(project_root), "LUNA logs"),
        "metadata": _write_probe(default_metadata_directory(project_root), "metadata configuration"),
        "config": _write_probe(default_config_directory(project_root), "application configuration"),
        "default_results": _write_probe(default_output_directory(project_root), "default analysis results"),
        "temp": _write_probe(Path(tempfile.gettempdir()), "system temporary directory"),
    }
    if output_dir is not None:
        app_paths["requested_output"] = _write_probe(Path(output_dir).expanduser().resolve(), "requested output directory")

    safe_env = {
        key: os.environ[key]
        for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMBA_NUM_THREADS", "QT_QPA_PLATFORM")
        if key in os.environ
    }
    report: dict[str, Any] = {
        "schema": "luna-diagnostic/1.0",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "luna_version": __version__,
        "runtime": {
            "os": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "interpreter": "<venv>/" + "/".join(Path(sys.executable).parts[-2:]) if sys.prefix != sys.base_prefix else "<system python>/" + Path(sys.executable).name,
            "virtual_environment": sys.prefix != sys.base_prefix,
            "environment_prefix": "<venv>" if sys.prefix != sys.base_prefix else "<system python>",
            "base_prefix": "<base python>",
        },
        "entry_and_modules": {
            "invoked_as": _safe_invocation_name(sys.argv[0] if sys.argv else ""),
            "module_locations": _runtime_modules(),
            "lfp_analysis_distribution_owners": ownership,
            "duplicate_import_namespace_warning": len(ownership) > 1,
        },
        "packages": package_versions,
        "numeric_backend": {"threadpools": _threadpools(), "allowlisted_thread_environment": safe_env},
        "writable_locations": app_paths,
        "privacy": {
            "signal_data_included": False,
            "all_environment_variables_included": False,
            "home_path_redacted": True,
            "custom_paths_redacted": True,
        },
    }
    if input_file is not None:
        report["input_metadata"] = inspect_input_metadata(input_file)
    if connectivity_self_test:
        report["connectivity_self_test"] = run_connectivity_smoke_test()
    return report


def inspect_input_metadata(input_file: str | Path) -> dict[str, Any]:
    """Inspect FIF headers without loading or recording signal values/channel names."""
    path = Path(input_file).expanduser().resolve()
    result: dict[str, Any] = {"path": "<selected local file>", "exists": path.is_file(), "suffix": "".join(path.suffixes[-2:])}
    if not path.is_file():
        return result
    result["size_bytes"] = path.stat().st_size
    try:
        mne = importlib.import_module("mne")
        epochs = mne.read_epochs(path, preload=False, verbose="ERROR")
        result.update(
            {
                "n_epochs": len(epochs),
                "n_channels": len(epochs.ch_names),
                "n_times": len(epochs.times),
                "sfreq_hz": float(epochs.info["sfreq"]),
                "tmin_s": float(epochs.tmin),
                "tmax_s": float(epochs.tmax),
                "channel_names_included": False,
                "signal_samples_loaded": False,
            }
        )
        epochs.close() if hasattr(epochs, "close") else None
        return result
    except Exception as exc:  # noqa: BLE001 - include the exact FIF inspection failure in the report
        result["inspection_error"] = {"type": type(exc).__name__, "message": redact_text(exc), "traceback": redact_text(traceback.format_exc())}
        return result


def write_failure_report(path: str | Path, context: dict[str, Any]) -> Path:
    """Write a redacted failure report with parameters/shape but no signal arrays."""
    payload = {
        "schema": "luna-failure/1.0",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "environment": {
            "os": platform.system(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "luna_version": __version__,
        },
        "failure": _redact_tree(context),
        "privacy": {"signal_data_included": False, "home_path_redacted": True},
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target.with_suffix(target.suffix + f".{os.getpid()}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temp_path.replace(target)
    return target


def _redact_tree(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _redact_tree(item) for key, item in value.items() if key.lower() not in {"data", "signal", "raw_signal", "samples", "environment_variables"}}
    if isinstance(value, (list, tuple)):
        return [_redact_tree(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Path):
        return redact_text(value)
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a privacy-conscious LUNA runtime diagnostic report.")
    parser.add_argument("--output", type=Path, help="write JSON report to this path; otherwise print to stdout")
    parser.add_argument("--output-dir", type=Path, help="also test whether this results directory is writable")
    parser.add_argument("--input", type=Path, help="optionally inspect FIF header metadata only; signal samples are not loaded")
    parser.add_argument(
        "--self-test-connectivity",
        action="store_true",
        help="run all installed MNE-Connectivity methods on synthetic data (no study data is used)",
    )
    args = parser.parse_args(argv)
    report = collect_diagnostics(
        output_dir=args.output_dir,
        input_file=args.input,
        connectivity_self_test=args.self_test_connectivity,
    )
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        target = args.output.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target.with_suffix(target.suffix + ".tmp")
        temp_path.write_text(serialized, encoding="utf-8")
        temp_path.replace(target)
        print(f"LUNA diagnostic report written: {redact_text(target)}")
    else:
        print(serialized)
    self_test = report.get("connectivity_self_test")
    return 2 if self_test is not None and self_test.get("status") != "ok" else 0


if __name__ == "__main__":
    raise SystemExit(main())
