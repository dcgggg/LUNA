from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from .config import load_config
from .connectivity import compute_connectivity
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
from .plotting import plot_band_power, plot_psd, plot_quality_matrix, plot_waveforms
from .quality import assess_quality
from .spectral import compute_band_power, compute_psd, summarize_psd


def _write_frame(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _file_registry_row(tables: dict[str, pd.DataFrame], input_path: Path) -> dict[str, Any] | None:
    files = tables.get("files", pd.DataFrame())
    if files.empty or "file_path" not in files:
        return None
    candidates = files.loc[files["file_path"].astype(str).map(lambda value: Path(value).expanduser().resolve() == input_path)]
    if candidates.empty:
        candidates = files.loc[files["file_path"].astype(str).map(lambda value: Path(value).name == input_path.name)]
    return candidates.iloc[0].to_dict() if not candidates.empty else None


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
    registry_row = _file_registry_row(tables, input_path)
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
    )
    plot_quality_matrix(quality["epoch_channel"], figures / "quality_epoch_channel", dpi=int(config.get("plotting", {}).get("dpi", 150)))
    plot_psd(psd_summary["channel"], figures / "psd_channel", dpi=int(config.get("plotting", {}).get("dpi", 150)))
    plot_band_power(band_power, figures / "band_power", dpi=int(config.get("plotting", {}).get("dpi", 150)))

    parameterization_status = "disabled_by_config"
    if bool(config.get("parameterization", {}).get("enabled", False)):
        fits = fit_channel_psd_table(psd_summary["channel"], config)
        _write_frame(fits["model"], output / "parameterization_model.csv")
        _write_frame(fits["peaks"], output / "parameterization_peaks.csv")
        parameterization_status = "completed_with_failure_rows_preserved"
    else:
        _write_frame(pd.DataFrame([{"status": parameterization_status, "reason": "enable only after PSD scale/range review"}]), output / "parameterization_status.csv")

    connectivity_status = "disabled_by_config"
    if bool(config.get("connectivity", {}).get("enabled", False)):
        connectivity = compute_connectivity(loaded.data, loaded.sfreq, channel_table, quality["epoch"], config)
        _write_frame(connectivity["spectrum"], output / "connectivity_spectrum.csv")
        _write_frame(connectivity["region_summary"], output / "connectivity_region_summary.csv")
        connectivity_status = str(connectivity["status"])
    else:
        _write_frame(pd.DataFrame([{"status": connectivity_status, "reason": "requires confirmed mapping and cross-epoch review"}]), output / "connectivity_status.csv")

    expected = config.get("expected_data", {})
    file_quality = quality["file"].iloc[0].to_dict()
    animal_id = registry_row.get("animal_id") if registry_row else None
    has_animal_id = animal_id is not None and not pd.isna(animal_id) and str(animal_id).strip().lower() not in {"", "nan", "none"}
    identity_status = "registered" if has_animal_id else "file_only_identity_unresolved"
    manifest = {
        "analysis_version": "0.1.0",
        "input_path": str(input_path),
        "input_sha256": sha256_file(input_path),
        "input_size_bytes": input_path.stat().st_size,
        "file_id": file_id,
        "identity_status": identity_status,
        "registry_row": registry_row,
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
        "connectivity_status": connectivity_status,
        "animal_level_statistics_run": False,
        "limitations": [
            "Actual_record_start/end are not inferred from event values.",
            "No animal-level inference is run when identity metadata is absent.",
            "Quality flags are not silent exclusions.",
        ],
    }
    write_json(manifest, output / "run_manifest.json")
    shutil.copy2(config_path, output / "config_used.yaml")
    return manifest


def run_batch(files_csv: str | Path, config_path: str | Path, output_dir: str | Path, metadata_dir: str | Path = "metadata") -> pd.DataFrame:
    files = pd.read_csv(files_csv, dtype=str)
    rows: list[dict[str, Any]] = []
    output_root = Path(output_dir)
    for index, row in files.iterrows():
        file_path = str(row.get("file_path", "")).strip()
        result = {
            "row_index": int(index),
            "file_id": row.get("file_id", ""),
            "file_path": file_path,
            "status": "skipped",
            "reason": "",
            "output_dir": "",
        }
        if str(row.get("include_file_level", "")).lower() in {"false", "0", "no"}:
            result["reason"] = "include_file_level=false"
            rows.append(result)
            continue
        path = Path(file_path).expanduser()
        if not path.is_file():
            result["reason"] = "file_not_found"
            rows.append(result)
            continue
        file_id = str(row.get("file_id") or path.stem)
        target = output_root / file_id
        try:
            run_single_file(path, config_path, target, metadata_dir=metadata_dir)
            result.update({"status": "completed", "output_dir": str(target.resolve())})
        except Exception as exc:  # noqa: BLE001 - batch manifest must retain per-file failures
            result["status"] = "failed"
            result["reason"] = f"{type(exc).__name__}: {exc}"
        rows.append(result)
    manifest = pd.DataFrame(rows)
    _write_frame(manifest, output_root / "batch_manifest.csv")
    return manifest
