from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from .app_info import APP_VERSION
from .config import audit_config, load_config
from .connectivity import compute_connectivity
from .identity import normalize_path, resolve_registry_match, stable_file_uid
from .io import (
    channel_info_table,
    epoch_trace_table,
    raw_trace_artifacts,
    read_fif,
    sha256_file,
    write_json,
)
from .metadata import load_metadata_tables, validate_metadata_tables
from .parameterization import fit_channel_psd_table
from .plotting import (
    plot_band_power,
    plot_connectivity_band_matrices,
    plot_connectivity_channel_pairs,
    plot_connectivity_rank_sensitivity,
    plot_connectivity_redundancy,
    plot_connectivity_spectrum,
    plot_parameterization_components,
    plot_parameterization_fit,
    plot_psd,
    plot_quality_matrix,
    plot_time_delay_band_matrix,
    plot_time_delay_spectrum,
    plot_waveforms,
)
from .quality import assess_quality
from .spectral import compute_band_power, compute_psd, summarize_psd
from .time_delay import compute_time_delay


def _write_frame(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if frame.empty and len(frame.columns) == 0:
        frame = pd.DataFrame(columns=["status"])
    frame.to_csv(path, index=False)


def _file_registry_row(tables: dict[str, pd.DataFrame], input_path: Path) -> dict[str, Any] | None:
    files = tables.get("files", pd.DataFrame())
    match = resolve_registry_match(files, input_path)
    row = match.get("registry_row")
    return row if isinstance(row, dict) else None


def run_single_file(
    input_path: str | Path,
    config_path: str | Path,
    output_dir: str | Path,
    metadata_dir: str | Path = "metadata",
) -> dict[str, Any]:
    input_path = Path(input_path).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = load_config(config_path)
    tables = load_metadata_tables(metadata_dir)
    metadata_issues = validate_metadata_tables(tables)
    _write_frame(metadata_issues, output / "metadata_validation.csv")
    identity_match = resolve_registry_match(tables.get("files", pd.DataFrame()), input_path, metadata_dir)
    registry_row = identity_match.get("registry_row") if isinstance(identity_match.get("registry_row"), dict) else None
    loaded_sha256 = sha256_file(input_path)
    file_uid = stable_file_uid(input_path, loaded_sha256)
    file_id = str(registry_row.get("file_id")) if registry_row and registry_row.get("file_id") else input_path.stem

    loaded = read_fif(input_path)
    channel_table = channel_info_table(loaded, tables.get("channel_map"))
    trace = epoch_trace_table(loaded, file_id)
    raw_trace_artifacts(loaded, output / "traceability")
    _write_frame(channel_table, output / "channel_table.csv")
    _write_frame(trace, output / "epochs_trace.csv")

    quality = assess_quality(loaded.data, loaded.sfreq, loaded.ch_names, config)
    _write_frame(quality["epoch_channel"], output / "quality_epoch_channel.csv")
    _write_frame(quality["epoch"], output / "quality_epoch.csv")
    _write_frame(quality["channel"], output / "quality_channel.csv")
    _write_frame(quality["file"], output / "quality_file.csv")

    psd = compute_psd(loaded.data, loaded.sfreq, loaded.ch_names, config)
    psd_summary = summarize_psd(psd, channel_table)
    band_power = compute_band_power(psd, config)
    unit_codes = sorted({str(value) for value in channel_table["mne_unit_code"].dropna().unique()})
    source_unit = "V" if unit_codes == ["107"] else (f"mne_unit_code:{','.join(unit_codes)}" if unit_codes else "unknown")
    psd_unit = f"{source_unit}^2/Hz"
    band_power_unit = f"{source_unit}^2"
    for frame in [psd, psd_summary["channel"], psd_summary["region"]]:
        if not frame.empty:
            frame["source_unit"] = source_unit
            frame["psd_unit"] = psd_unit
    if not band_power.empty:
        band_power["source_unit"] = source_unit
        band_power["absolute_power_unit"] = band_power_unit
        band_power["relative_power_unit"] = "fraction"
    _write_frame(psd, output / "psd_epoch_channel.csv")
    _write_frame(psd_summary["channel"], output / "psd_channel_summary.csv")
    _write_frame(psd_summary["region"], output / "psd_region_summary.csv")
    _write_frame(band_power, output / "band_power_epoch_channel.csv")

    figures = output / "figures"
    plot_waveforms(
        loaded.data,
        loaded.sfreq,
        loaded.ch_names,
        figures / "raw_waveforms",
        max_epochs=int(config.get("plotting", {}).get("max_waveform_epochs", 6)),
        seconds=float(config.get("plotting", {}).get("waveform_seconds", 1.0)),
        title_prefix=f"{file_id}; input FIF is read-only",
        regions=channel_table.set_index("channel_name").reindex(loaded.ch_names)["region"].fillna("未映射").astype(str).tolist() if "channel_name" in channel_table.columns and "region" in channel_table.columns else None,
    )
    plot_quality_matrix(quality["epoch_channel"], figures / "quality_epoch_channel", dpi=int(config.get("plotting", {}).get("dpi", 150)))
    plot_psd(psd_summary["channel"], figures / "psd_channel", dpi=int(config.get("plotting", {}).get("dpi", 150)))
    plot_band_power(band_power, figures / "band_power", dpi=int(config.get("plotting", {}).get("dpi", 150)))

    parameterization_status = "disabled_by_config"
    if bool(config.get("parameterization", {}).get("enabled", False)):
        fits = fit_channel_psd_table(psd_summary["channel"], config)
        _write_frame(fits["model"], output / "parameterization_model.csv")
        _write_frame(fits["peaks"], output / "parameterization_peaks.csv")
        _write_frame(fits["curves"], output / "parameterization_curves.csv")
        failures = fits["model"].loc[fits["model"].get("fit_status", pd.Series(dtype=str)).ne("ok")] if not fits["model"].empty else pd.DataFrame()
        _write_frame(failures, output / "parameterization_failures.csv")
        plot_parameterization_fit(
            fits["curves"],
            fits["model"],
            figures / "parameterization_fit",
            dpi=int(config.get("plotting", {}).get("dpi", 150)),
        )
        plot_parameterization_components(
            fits["curves"],
            fits["model"],
            figures / "parameterization_components",
            dpi=int(config.get("plotting", {}).get("dpi", 150)),
        )
        n_failures = len(failures)
        n_fits = int((fits["model"].get("fit_status", pd.Series(dtype=str)) == "ok").sum())
        parameterization_status = f"completed_{n_fits}_fits_{n_failures}_failures_preserved"
    else:
        _write_frame(pd.DataFrame([{"status": parameterization_status, "reason": "enable only after PSD scale/range review"}]), output / "parameterization_status.csv")

    connectivity_status = "disabled_by_config"
    if bool(config.get("connectivity", {}).get("enabled", False)):
        connectivity = compute_connectivity(
            loaded.data,
            loaded.sfreq,
            channel_table,
            quality["epoch"],
            config,
            analysis_task_id=f"{file_uid}/connectivity",
        )
        _write_frame(connectivity["spectrum"], output / "connectivity_spectrum.csv")
        _write_frame(connectivity["region_summary"], output / "connectivity_region_summary.csv")
        _write_frame(connectivity["band_summary"], output / "connectivity_band_summary.csv")
        _write_frame(connectivity["channel_pair_band_summary"], output / "connectivity_channel_pair_band_summary.csv")
        _write_frame(connectivity["patterns"], output / "connectivity_patterns.csv")
        _write_frame(connectivity["redundancy_correlation"], output / "connectivity_redundancy_correlation.csv")
        _write_frame(connectivity["redundancy_singular_values"], output / "connectivity_redundancy_singular_values.csv")
        _write_frame(connectivity["rank_summary"], output / "connectivity_rank_summary.csv")
        _write_frame(connectivity["rank_sensitivity"], output / "connectivity_rank_sensitivity.csv")
        _write_frame(connectivity["stability"], output / "connectivity_stability.csv")
        _write_frame(connectivity["epoch_profile"], output / "connectivity_epoch_profile.csv")
        _write_frame(connectivity["input_checks"], output / "connectivity_input_checks.csv")
        _write_frame(connectivity["failures"], output / "connectivity_failures.csv")
        _write_frame(connectivity["frequency_diagnostics"], output / "connectivity_frequency_diagnostics.csv")
        _write_frame(connectivity["roughness"], output / "connectivity_roughness.csv")
        _write_frame(connectivity["band_cv"], output / "connectivity_band_cv.csv")
        _write_frame(connectivity["binned_spectrum"], output / "connectivity_binned_spectrum.csv")
        _write_frame(connectivity["display_spectrum"], output / "connectivity_display_spectrum.csv")
        _write_frame(connectivity["display_roughness"], output / "connectivity_display_roughness.csv")
        _write_frame(connectivity["estimation_calls"], output / "connectivity_estimation_calls.csv")
        write_json(connectivity["metadata"], output / "connectivity_metadata.json")
        plot_connectivity_redundancy(
            connectivity["redundancy_correlation"],
            connectivity["redundancy_singular_values"],
            connectivity["rank_summary"],
            figures / "connectivity_redundancy",
            dpi=int(config.get("plotting", {}).get("dpi", 150)),
        )
        for method in ("mic", "mim", "wpli", "dpli", "wpli2_debiased"):
            if not connectivity["region_summary"].empty and method in set(connectivity["region_summary"].get("method", pd.Series(dtype=str))):
                plot_connectivity_spectrum(
                    connectivity["region_summary"],
                    method,
                    figures / f"connectivity_{method}_spectrum",
                    dpi=int(config.get("plotting", {}).get("dpi", 150)),
                )
        plot_connectivity_band_matrices(
            connectivity["band_summary"],
            figures / "connectivity_band_matrices",
            dpi=int(config.get("plotting", {}).get("dpi", 150)),
        )
        for method in ("wpli", "dpli", "wpli2_debiased", "imcoh", "coh"):
            if method in set(connectivity["spectrum"].get("method", pd.Series(dtype=str))):
                plot_connectivity_channel_pairs(
                    connectivity["spectrum"],
                    figures / f"connectivity_{method}_channel_pairs",
                    dpi=int(config.get("plotting", {}).get("dpi", 150)),
                    method=method,
                )
        if not connectivity["rank_sensitivity"].empty and "region_a" in connectivity["rank_sensitivity"]:
            plot_connectivity_rank_sensitivity(
                connectivity["rank_sensitivity"],
                figures / "connectivity_rank_sensitivity",
                dpi=int(config.get("plotting", {}).get("dpi", 150)),
            )
        connectivity_status = str(connectivity["status"])
    else:
        _write_frame(pd.DataFrame([{"status": connectivity_status, "reason": "requires confirmed mapping and cross-epoch review"}]), output / "connectivity_status.csv")
    time_delay_status = "disabled_by_config"
    if bool(config.get("time_delay", {}).get("enabled", False)):
        time_delay = compute_time_delay(loaded.data, loaded.sfreq, channel_table, quality["epoch"], config)
        _write_frame(time_delay["spectrum"], output / "time_delay_spectrum.csv")
        _write_frame(time_delay["region_spectrum"], output / "time_delay_region_spectrum.csv")
        _write_frame(time_delay["channel_pair_summary"], output / "time_delay_channel_pair_summary.csv")
        _write_frame(time_delay["band_summary"], output / "time_delay_band_summary.csv")
        _write_frame(time_delay["input_checks"], output / "time_delay_input_checks.csv")
        _write_frame(time_delay["failures"], output / "time_delay_failures.csv")
        write_json(time_delay["metadata"], output / "time_delay_metadata.json")
        if not time_delay["region_spectrum"].empty:
            methods = sorted(time_delay["region_spectrum"]["method"].dropna().astype(int).unique())
            antisym_modes = sorted(time_delay["region_spectrum"]["antisymmetrized"].dropna().astype(bool).unique())
            for method in methods:
                for antisymmetrized in antisym_modes:
                    suffix = "antisym" if antisymmetrized else "standard"
                    plot_time_delay_spectrum(
                        time_delay["region_spectrum"],
                        method,
                        antisymmetrized,
                        figures / f"time_delay_method_{method}_{suffix}_spectrum",
                        dpi=int(config.get("plotting", {}).get("dpi", 150)),
                    )
                    if not time_delay["band_summary"].empty:
                        plot_time_delay_band_matrix(
                            time_delay["band_summary"],
                            method,
                            antisymmetrized,
                            figures / f"time_delay_method_{method}_{suffix}_band_matrix",
                            dpi=int(config.get("plotting", {}).get("dpi", 150)),
                        )
        time_delay_status = str(time_delay["status"])
    else:
        _write_frame(pd.DataFrame([{"status": time_delay_status, "reason": "disabled_by_config"}]), output / "time_delay_status.csv")

    expected = config.get("expected_data", {})
    file_quality = quality["file"].iloc[0].to_dict()
    animal_id = registry_row.get("animal_id") if registry_row else None
    session_id = registry_row.get("session_id") if registry_row else None
    has_animal_id = animal_id is not None and not pd.isna(animal_id) and str(animal_id).strip().lower() not in {"", "nan", "none"}
    has_session_id = session_id is not None and not pd.isna(session_id) and str(session_id).strip().lower() not in {"", "nan", "none"}
    identity_status = "registered" if has_animal_id and has_session_id else "file_only_identity_unresolved"
    manifest = {
        "schema_version": 2,
        "analysis_version": APP_VERSION,
        "status": "completed",
        "input_path": str(input_path),
        "input_sha256": loaded_sha256,
        "input_size_bytes": input_path.stat().st_size,
        "file_id": file_id,
        "file_uid": file_uid,
        "file_stem": input_path.stem,
        "display_name": input_path.name,
        "identity_status": identity_status,
        "registry_file_id": registry_row.get("file_id", "") if registry_row else "",
        "registry_match_status": identity_match.get("status", "unregistered"),
        "registry_match_candidates": identity_match.get("candidate_file_ids", []),
        "registry_row": registry_row,
        "metadata_validation_error_count": int((metadata_issues.get("severity", pd.Series(dtype=str)) == "error").sum()),
        "metadata_validation_warning_count": int((metadata_issues.get("severity", pd.Series(dtype=str)) == "warning").sum()),
        "configuration_audit": audit_config(config),
        "n_epochs": int(loaded.data.shape[0]),
        "n_channels": int(loaded.data.shape[1]),
        "n_times": int(loaded.data.shape[2]),
        "sampling_rate_hz": loaded.sfreq,
        "epoch_tmin_s": loaded.tmin,
        "epoch_tmax_s": loaded.tmax,
        "effective_valid_duration_s": file_quality["effective_valid_duration_s"],
        "events_are_retained_raw_values": True,
        "event_time_interpretation": "not converted to original recording time",
        "expected_check_results": {
            "sampling_rate_matches_config": loaded.sfreq == float(expected.get("sampling_rate_hz", loaded.sfreq)),
            "channel_count_matches_config": loaded.data.shape[1] == int(expected.get("n_channels", loaded.data.shape[1])),
            "times_per_epoch_matches_config": loaded.data.shape[2] == int(expected.get("n_times_per_epoch", loaded.data.shape[2])),
        },
        "parameterization_status": parameterization_status,
        "parameterization_fit_range_hz": config.get("parameterization", {}).get("fit_range_hz"),
        "connectivity_status": connectivity_status,
        "connectivity_frequency_range_hz": [
            config.get("connectivity", {}).get("fmin_hz", None),
            config.get("connectivity", {}).get("fmax_hz", None),
        ],
        "connectivity_effective_duration_s": connectivity.get("metadata", {}).get("effective_valid_duration_s") if "connectivity" in locals() else None,
        "time_delay_status": time_delay_status,
        "time_delay_effective_duration_s": time_delay.get("metadata", {}).get("effective_valid_duration_s") if "time_delay" in locals() else None,
        "animal_level_statistics_run": False,
        "limitations": [
            "Actual_record_start/end are not inferred from event values.",
            "No animal-level inference is run when identity metadata is absent or ambiguous.",
            "Quality flags are not silent exclusions.",
        ],
    }
    write_json(manifest, output / "run_manifest.json")
    shutil.copy2(config_path, output / "config_used.yaml")
    return manifest


def run_batch(files_csv: str | Path, config_path: str | Path, output_dir: str | Path, metadata_dir: str | Path = "metadata") -> pd.DataFrame:
    files = pd.read_csv(files_csv, dtype=str).fillna("")
    rows: list[dict[str, Any]] = []
    output_root = Path(output_dir).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    def text(value: Any) -> str:
        return "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value).strip()

    tables = load_metadata_tables(metadata_dir)
    metadata_issues = validate_metadata_tables(tables)
    metadata_errors = int((metadata_issues.get("severity", pd.Series(dtype=str)) == "error").sum())
    metadata_error_reason = "metadata_validation_error" if metadata_errors else ""
    active: list[dict[str, Any]] = []
    path_rows: dict[str, list[int]] = {}
    target_rows: dict[str, list[int]] = {}

    for index, row in files.iterrows():
        file_path = text(row.get("file_path", ""))
        explicit_file_id = text(row.get("file_id", ""))
        result: dict[str, Any] = {
            "row_index": int(index),
            "file_id": explicit_file_id,
            "file_uid": "",
            "file_path": file_path,
            "status": "skipped",
            "reason": "",
            "output_dir": "",
        }
        if text(row.get("include_file_level", "")).lower() in {"false", "0", "no"}:
            result["reason"] = "include_file_level=false"
            rows.append(result)
            continue
        if metadata_error_reason:
            result["reason"] = metadata_error_reason
            rows.append(result)
            continue
        if not file_path:
            result["reason"] = "missing_file_path"
            rows.append(result)
            continue
        path = normalize_path(file_path, Path(files_csv).expanduser().resolve().parent)
        if not path.is_file():
            result["reason"] = "file_not_found"
            rows.append(result)
            continue
        file_id = explicit_file_id or path.stem
        safe_file_id = "".join(char if char.isalnum() or char in "._-" else "_" for char in file_id).strip("._") or "file"
        target = output_root / safe_file_id
        path_key = os.path.normcase(str(path))
        target_key = os.path.normcase(str(target))
        file_sha = sha256_file(path)
        result.update({"file_id": file_id, "file_uid": stable_file_uid(path, file_sha), "output_dir": str(target)})
        active.append({"row_index": int(index), "result": result, "path": path, "target": target, "path_key": path_key, "target_key": target_key})
        path_rows.setdefault(path_key, []).append(int(index))
        target_rows.setdefault(target_key, []).append(int(index))
        rows.append(result)

    row_by_index = {int(item["row_index"]): item for item in active}
    conflict_indices: set[int] = set()
    for duplicate_indices in path_rows.values():
        if len(duplicate_indices) > 1:
            conflict_indices.update(duplicate_indices)
            for row_index in duplicate_indices:
                row_by_index[row_index]["result"]["reason"] = "duplicate_input_path"
    for duplicate_indices in target_rows.values():
        if len(duplicate_indices) > 1:
            conflict_indices.update(duplicate_indices)
            for row_index in duplicate_indices:
                row_by_index[row_index]["result"]["reason"] = "duplicate_output_target"
    for item in active:
        row_index = int(item["row_index"])
        result = item["result"]
        if row_index in conflict_indices:
            continue
        target = item["target"]
        if target.exists() and any(target.iterdir()):
            result["reason"] = "output_target_exists_nonempty"
            conflict_indices.add(row_index)

    for item in active:
        row_index = int(item["row_index"])
        result = item["result"]
        if row_index in conflict_indices:
            result["status"] = "skipped"
            continue
        try:
            run_single_file(item["path"], config_path, item["target"], metadata_dir=metadata_dir)
            result.update({"status": "completed", "output_dir": str(item["target"].resolve()), "reason": ""})
        except Exception as exc:  # noqa: BLE001 - batch manifest must retain per-file failures
            result["status"] = "failed"
            result["reason"] = f"{type(exc).__name__}: {exc}"
    manifest = pd.DataFrame(rows)
    _write_frame(manifest, output_root / "batch_manifest.csv")
    return manifest
