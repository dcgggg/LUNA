"""Backend used by the desktop GUI.

This module is intentionally Qt-free.  It freezes a GUI snapshot, validates
it, calls the existing analysis functions, and writes an auditable run bundle.
The Qt window only schedules this work and renders the returned tables/plots.
"""

from __future__ import annotations

import copy
import json
import platform
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import load_config
from .connectivity import compute_connectivity
from .gui_specs import normalize_gui_values, validate_snapshot
from .io import channel_info_table, read_fif, sha256_file
from .metadata import load_metadata_tables
from .parameterization import fit_channel_psd_table
from .quality import assess_quality
from .spectral import compute_band_power, compute_psd, summarize_psd
from .time_delay import compute_time_delay


class AnalysisCancelled(RuntimeError):
    """Raised when a GUI task is cancelled between backend stages."""


ProgressCallback = Callable[[str, int], None]
ResultCallback = Callable[[dict[str, Any]], None]


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def _atomic_json(value: Any, path: Path) -> None:
    _atomic_write_text(path, json.dumps(_jsonable(value), ensure_ascii=False, indent=2))


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temp, index=False)
    temp.replace(path)


def _atomic_npz(path: Path, **arrays: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp.npz")
    np.savez_compressed(temp, **arrays)
    temp.replace(path)


def _safe_id(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "._-" else "_" for char in str(value))
    return cleaned.strip("._") or "file"


def _value_or_blank(value: Any) -> Any:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    return value


def _with_provenance(frame: pd.DataFrame, provenance: dict[str, Any] | None) -> pd.DataFrame:
    output = frame.copy()
    for key, value in (provenance or {}).items():
        if key not in output.columns:
            output[key] = _value_or_blank(value)
    return output


def _package_versions() -> dict[str, str]:
    names = ("numpy", "scipy", "pandas", "matplotlib", "mne", "mne-connectivity", "specparam", "fooof", "pybispectra", "PySide6")
    result: dict[str, str] = {"python": platform.python_version(), "platform": platform.platform()}
    for name in names:
        try:
            result[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result[name] = "not_installed"
    return result


def inspect_file(path: str | Path, metadata_dir: str | Path = "metadata") -> dict[str, Any]:
    """Read one FIF and return UI-facing metadata plus the loaded object."""
    input_path = Path(path).expanduser().resolve()
    loaded = read_fif(input_path)
    tables = load_metadata_tables(metadata_dir)
    channel_table = channel_info_table(loaded, tables.get("channel_map"))
    registry_row: dict[str, Any] = {}
    files = tables.get("files", pd.DataFrame())
    if not files.empty and "file_path" in files.columns:
        candidates = files.loc[files["file_path"].astype(str).map(lambda value: Path(value).name == input_path.name)]
        if not candidates.empty:
            registry_row = candidates.iloc[0].to_dict()
    return {
        "path": input_path,
        "loaded": loaded,
        "channel_table": channel_table,
        "n_epochs": int(loaded.data.shape[0]),
        "n_channels": int(loaded.data.shape[1]),
        "n_times": int(loaded.data.shape[2]),
        "sfreq": float(loaded.sfreq),
        "tmin": float(loaded.tmin),
        "tmax": float(loaded.tmax),
        "effective_duration_s": float(loaded.data.shape[0] * loaded.data.shape[2] / loaded.sfreq),
        "sha256": sha256_file(input_path),
        "registry_row": registry_row,
    }


def _selected_epoch_indices(snapshot: dict[str, Any], n_epochs: int) -> list[int]:
    values = snapshot.get("selected_epoch_indices")
    if values is None:
        return list(range(n_epochs))
    return sorted({int(value) for value in values if 0 <= int(value) < n_epochs})


def _selected_channel_indices(snapshot: dict[str, Any], channel_table: pd.DataFrame) -> list[int]:
    names = set(map(str, snapshot.get("selected_channel_names", [])))
    return [int(row.array_index) for row in channel_table.itertuples() if str(row.channel_name) in names]


def _time_slice(snapshot: dict[str, Any], loaded: Any) -> tuple[int, int, float, float]:
    selection = snapshot.get("selection", {})
    start_s = float(selection.get("time_start_s", loaded.tmin))
    end_s = float(selection.get("time_end_s", loaded.tmax + 1.0 / loaded.sfreq))
    start_index = round((start_s - loaded.tmin) * loaded.sfreq)
    end_index = round((end_s - loaded.tmin) * loaded.sfreq)
    start_index = max(0, min(start_index, loaded.data.shape[-1] - 1))
    end_index = max(start_index + 1, min(end_index, loaded.data.shape[-1]))
    actual_start = loaded.tmin + start_index / loaded.sfreq
    actual_end = loaded.tmin + end_index / loaded.sfreq
    return start_index, end_index, actual_start, actual_end


def build_runtime_config(base_config: dict[str, Any], snapshot: dict[str, Any], sfreq: float, n_times: int) -> dict[str, Any]:
    config = copy.deepcopy(base_config)
    values = copy.deepcopy(snapshot.get("values", {}))
    normalized = normalize_gui_values(values, sfreq, n_times)
    for section in ("psd", "parameterization", "connectivity", "time_delay", "relative_power"):
        if section in normalized:
            config.setdefault(section, {}).update(normalized[section])
    selected = set(snapshot.get("indicators", []))
    indicator_to_method = {"MIC": "mic", "MIM": "mim", "wpli2_debiased": "wpli2_debiased"}
    methods = [indicator_to_method[indicator] for indicator in ("MIC", "MIM", "wpli2_debiased") if indicator in selected]
    config.setdefault("connectivity", {})["methods"] = methods
    config["connectivity"]["enabled"] = bool(methods)
    config["connectivity"]["selected_region_pairs"] = snapshot.get("selected_region_pairs", [])
    config["connectivity"]["fixed_rank_by_region"] = {
        region: int(values.get("connectivity", {}).get(f"fixed_rank_{region}", 0) or 0)
        for region in ("M1", "STR", "PF", "SNr")
        if int(values.get("connectivity", {}).get(f"fixed_rank_{region}", 0) or 0) > 0
    }
    config["connectivity"]["stability_n_subsamples"] = int(values.get("connectivity", {}).get("stability_n_subsamples", 2))
    config["parameterization"]["enabled"] = "FOOOF" in selected
    config["time_delay"]["enabled"] = "Time Delay" in selected
    bands = values.get("bands")
    if isinstance(bands, list) and bands:
        config["bands"] = {str(item["name"]): [float(item["low_hz"]), float(item["high_hz"])] for item in bands}
    config.setdefault("relative_power", {})["denominator_hz"] = [
        float(values.get("relative_power", {}).get("denominator_low_hz", config.get("relative_power", {}).get("denominator_hz", [1.0, 100.0])[0])),
        float(values.get("relative_power", {}).get("denominator_high_hz", config.get("relative_power", {}).get("denominator_hz", [1.0, 100.0])[1])),
    ]
    return config


def _save_table_group(base: Path, tables: dict[str, pd.DataFrame], provenance: dict[str, Any] | None = None) -> dict[str, str]:
    paths: dict[str, str] = {}
    for name, frame in tables.items():
        if frame is None:
            continue
        path = base / f"{name}.csv"
        _atomic_csv(_with_provenance(frame if isinstance(frame, pd.DataFrame) else pd.DataFrame(frame), provenance), path)
        paths[name] = str(path.name)
    return paths


def _save_psd_npz(base: Path, psd: pd.DataFrame, selected_data: np.ndarray, sfreq: float) -> None:
    if psd.empty:
        _atomic_npz(base / "psd_arrays.npz", selected_data=selected_data, sfreq=np.asarray([sfreq]))
        return
    frequencies = np.sort(psd["frequency_hz"].dropna().unique().astype(float))
    epochs = sorted(psd["epoch_index"].dropna().astype(int).unique())
    channels = sorted(psd["channel_array_index"].dropna().astype(int).unique())
    values = np.full((len(epochs), len(channels), len(frequencies)), np.nan)
    epoch_index = {value: index for index, value in enumerate(epochs)}
    channel_index = {value: index for index, value in enumerate(channels)}
    frequency_index = {value: index for index, value in enumerate(frequencies)}
    for row in psd.itertuples():
        if getattr(row, "status", "") == "ok" and np.isfinite(row.psd_value):
            values[epoch_index[int(row.epoch_index)], channel_index[int(row.channel_array_index)], frequency_index[float(row.frequency_hz)]] = float(row.psd_value)
    _atomic_npz(
        base / "psd_arrays.npz",
        selected_data=selected_data,
        sfreq=np.asarray([sfreq]),
        frequencies=frequencies,
        epoch_indices=np.asarray(epochs),
        channel_array_indices=np.asarray(channels),
        psd=values,
    )


def _metric_plot_data(metric: str, tables: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Return a compact plotting payload; GUI owns the actual Figure."""
    return {"metric": metric, "tables": tables}


def _save_metric_figures(metric: str, tables: dict[str, pd.DataFrame], file_dir: Path, file_id: str) -> list[str]:
    """Save compact preview and editable vector figures for each completed metric."""
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    figures_dir = file_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    fig, axis = plt.subplots(figsize=(9, 5))
    title = f"{file_id} | {metric}"
    if metric == "Quality":
        table = tables.get("quality_epoch_channel", pd.DataFrame())
        if not table.empty:
            matrix = table.pivot(index="epoch_index", columns="channel_name", values="issue_score").fillna(0)
            image = axis.imshow(matrix.to_numpy(float), aspect="auto", cmap="magma")
            axis.set_xlabel("Channel")
            axis.set_ylabel("Epoch")
            axis.set_xticks(np.arange(len(matrix.columns)), matrix.columns, rotation=90, fontsize=7)
            fig.colorbar(image, ax=axis, label="Quality issue score")
        else:
            axis.text(0.5, 0.5, "No quality table", ha="center", va="center", transform=axis.transAxes)
    elif metric == "PSD":
        table = tables.get("channel", pd.DataFrame())
        for channel, group in table.groupby("channel_name") if not table.empty else []:
            axis.plot(group["frequency_hz"], group["psd_value"], linewidth=0.8, label=str(channel))
        axis.set_xlabel("Frequency (Hz)")
        axis.set_ylabel("PSD (source unit²/Hz)")
        axis.set_yscale("log")
        if not table.empty:
            axis.legend(fontsize=6, ncol=2)
    elif metric == "Band Power":
        table = tables.get("band_power_summary", pd.DataFrame())
        if table.empty:
            table = tables.get("band_power", pd.DataFrame())
        if not table.empty:
            summary = table.groupby("band", as_index=False)["absolute_power"].mean()
            axis.bar(summary["band"].astype(str), summary["absolute_power"])
            axis.tick_params(axis="x", rotation=45)
            axis.set_ylabel("Mean absolute power (source unit²)")
        else:
            axis.text(0.5, 0.5, "No band-power rows", ha="center", va="center", transform=axis.transAxes)
    elif metric == "FOOOF":
        table = tables.get("curves", pd.DataFrame())
        for channel, group in table.groupby("channel_name") if not table.empty else []:
            group = group.sort_values("frequency_hz")
            axis.plot(group["frequency_hz"], group["observed_power"], linewidth=0.7, label=f"{channel} observed")
            axis.plot(group["frequency_hz"], group["full_model_power"], linewidth=0.9, linestyle="--", label=f"{channel} model")
        axis.set_xlabel("Frequency (Hz)")
        axis.set_ylabel("Power")
        axis.set_yscale("log")
        if not table.empty:
            axis.legend(fontsize=6, ncol=2)
    elif metric == "Connectivity":
        table = tables.get("region_summary", pd.DataFrame())
        for (region_a, region_b), group in table.groupby(["region_a", "region_b"]) if not table.empty else []:
            method = str(group["method"].iloc[0])
            axis.plot(group["frequency_hz"], group["value_strength"], linewidth=0.8, label=f"{method} {region_a}-{region_b}")
        axis.set_xlabel("Frequency (Hz)")
        axis.set_ylabel("Connection strength (method-specific)")
        if not table.empty:
            axis.legend(fontsize=6, ncol=2)
    elif metric == "Time Delay":
        table = tables.get("region_spectrum", pd.DataFrame())
        if not table.empty:
            first_pairs = list(table[["region_a", "region_b"]].drop_duplicates().itertuples(index=False, name=None))[:6]
            for region_a, region_b in first_pairs:
                group = table.loc[(table["region_a"] == region_a) & (table["region_b"] == region_b) & table["antisymmetrized"].astype(bool)]
                if not group.empty:
                    axis.plot(group["delay_ms"], group["estimate_strength"], linewidth=0.8, label=f"{region_a}-{region_b}")
            axis.set_xlabel("Delay (ms); positive = seed leads target")
            axis.set_ylabel("TDE estimate strength")
            axis.legend(fontsize=6, ncol=2)
        else:
            axis.text(0.5, 0.5, "No time-delay rows", ha="center", va="center", transform=axis.transAxes)
    axis.set_title(title)
    axis.grid(True, color="#dddddd", linewidth=0.4)
    fig.tight_layout()
    base = figures_dir / _safe_id(metric.lower())
    fig.savefig(base.with_suffix(".png"), dpi=150)
    fig.savefig(base.with_suffix(".svg"))
    plt.close(fig)
    return [str(base.with_suffix(".png").relative_to(file_dir)), str(base.with_suffix(".svg").relative_to(file_dir))]


def run_gui_analysis(
    snapshot: dict[str, Any],
    config_path: str | Path,
    metadata_dir: str | Path,
    progress: ProgressCallback | None = None,
    result_callback: ResultCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Run selected metrics for each file and write a complete GUI run bundle."""
    cancel_event = cancel_event or threading.Event()
    progress = progress or (lambda _message, _percent: None)
    result_callback = result_callback or (lambda _result: None)
    started = datetime.now(UTC).isoformat()
    run_id = str(snapshot.get("run_id") or f"run_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}")
    output_root = Path(snapshot["output_dir"]).expanduser().resolve()
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    frozen_snapshot = copy.deepcopy(snapshot)
    frozen_snapshot["run_id"] = run_id
    _atomic_json(frozen_snapshot, run_dir / "parameters.json")
    base_config = load_config(config_path)
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "started_at_utc": started,
        "finished_at_utc": None,
        "config_path": str(Path(config_path).resolve()),
        "metadata_dir": str(Path(metadata_dir).resolve()),
        "software": _package_versions(),
        "indicators": list(snapshot.get("indicators", [])),
        "files": [],
        "errors": [],
        "warnings": [],
    }
    _atomic_json(manifest, run_dir / "run_manifest.json")
    input_files = list(snapshot.get("input_files", []))
    total_steps = max(1, len(input_files) * max(1, len(snapshot.get("indicators", []))))
    completed_steps = 0

    def update(message: str) -> None:
        progress(message, min(99, int(completed_steps / total_steps * 100)))

    try:
        for file_position, input_file in enumerate(input_files):
            if cancel_event.is_set():
                raise AnalysisCancelled("用户取消运行")
            input_path = Path(input_file).expanduser().resolve()
            update(f"读取 {input_path.name} ({file_position + 1}/{len(input_files)})")
            try:
                loaded_info = inspect_file(input_path, metadata_dir)
                loaded = loaded_info["loaded"]
                full_channel_table = loaded_info["channel_table"]
                quality = assess_quality(loaded.data, loaded.sfreq, loaded.ch_names, base_config)
                channel_indices = _selected_channel_indices(snapshot, full_channel_table)
                epoch_indices = _selected_epoch_indices(snapshot, loaded.data.shape[0])
                start_index, end_index, actual_start, actual_end = _time_slice(snapshot, loaded)
                errors, warnings = validate_snapshot(snapshot, loaded.sfreq, end_index - start_index, loaded.data.shape[0], full_channel_table)
                if errors:
                    raise ValueError("；".join(errors))
                if warnings:
                    manifest["warnings"].extend([f"{input_path.name}: {warning}" for warning in warnings])
                selected_table = full_channel_table.loc[full_channel_table["array_index"].isin(channel_indices)].copy().reset_index(drop=True)
                if not channel_indices:
                    raise ValueError(f"{input_path.name}: 当前文件没有匹配所选通道名；请重新核对通道映射。")
                if not epoch_indices:
                    raise ValueError(f"{input_path.name}: 当前文件没有匹配所选 epoch。")
                selected_table["array_index"] = np.arange(len(selected_table), dtype=int)
                selected_data = loaded.data[np.ix_(epoch_indices, channel_indices, np.arange(start_index, end_index))]
                selected_quality = quality["epoch"].loc[quality["epoch"]["epoch_index"].isin(epoch_indices)].copy().reset_index(drop=True)
                selected_quality["original_epoch_index"] = epoch_indices
                runtime_config = build_runtime_config(base_config, snapshot, loaded.sfreq, end_index - start_index)
                file_id = _safe_id(input_path.stem)
                registry_row = loaded_info.get("registry_row", {})
                provenance = {
                    "animal_id": registry_row.get("animal_id", ""),
                    "session_id": registry_row.get("session_id", ""),
                    "file_id": file_id,
                    "nominal_dose_time_min": registry_row.get("nominal_dose_time_min", ""),
                    "drug": registry_row.get("drug", ""),
                    "dose_state": registry_row.get("dose_state", ""),
                    "ldn_status": registry_row.get("ldn_status", ""),
                    "ldn_day": registry_row.get("ldn_day", ""),
                }
                file_dir = run_dir / f"{file_position + 1:02d}_{file_id}"
                file_dir.mkdir(parents=True, exist_ok=True)
                _atomic_json(
                    {
                        "file_id": file_id,
                        "input_path": str(input_path),
                        "input_sha256": loaded_info["sha256"],
                        "n_epochs_selected": len(epoch_indices),
                        "n_channels_selected": len(channel_indices),
                        "selected_epoch_indices": epoch_indices,
                        "selected_channel_names": selected_table["channel_name"].astype(str).tolist(),
                        "time_start_s": actual_start,
                        "time_end_s": actual_end,
                        "effective_valid_duration_s": float(len(epoch_indices) * (end_index - start_index) / loaded.sfreq),
                        "registry_row": registry_row,
                        "provenance_columns": provenance,
                        "runtime_config": runtime_config,
                        "quality_warnings": warnings,
                    },
                    file_dir / "file_manifest.json",
                )
                _save_table_group(file_dir, {"channel_table": selected_table, "quality_epoch": selected_quality, "quality_epoch_channel": quality["epoch_channel"].loc[quality["epoch_channel"]["epoch_index"].isin(epoch_indices) & quality["epoch_channel"]["channel_array_index"].isin(channel_indices)].copy()}, provenance)
                _atomic_npz(file_dir / "selected_data.npz", data=selected_data, sfreq=np.asarray([loaded.sfreq]), times=np.arange(start_index, end_index) / loaded.sfreq + loaded.tmin, epoch_indices=np.asarray(epoch_indices), channel_indices=np.asarray(channel_indices))
                metric_records: list[dict[str, Any]] = []
                selected = set(snapshot.get("indicators", []))

                def begin_metric(metric: str, file_name: str = input_path.name) -> None:
                    nonlocal completed_steps
                    if cancel_event.is_set():
                        raise AnalysisCancelled("用户取消运行")
                    update(f"{file_name}: 运行 {metric}")

                # Quality is cheap and also provides the valid-epoch mask used by
                # cross-epoch metrics.  It is saved for every GUI run.
                if "Quality" in selected:
                    begin_metric("Quality")
                    tables = {"quality_epoch": quality["epoch"], "quality_epoch_channel": quality["epoch_channel"], "quality_channel": quality["channel"], "quality_file": quality["file"]}
                    paths = _save_table_group(file_dir / "quality", tables, provenance)
                    figure_paths = _save_metric_figures("Quality", tables, file_dir, file_id)
                    record = {"metric": "Quality", "status": "completed", "paths": {"tables": paths, "figures": figure_paths}}
                    metric_records.append(record)
                    result_callback({**_metric_plot_data("Quality", tables), "file_id": file_id, "file_dir": str(file_dir), "record": record})
                    completed_steps += 1

                psd_result: dict[str, Any] | None = None
                if selected.intersection({"PSD", "Band Power", "FOOOF"}):
                    begin_metric("PSD")
                    psd = compute_psd(selected_data, loaded.sfreq, selected_table["channel_name"].astype(str).tolist(), runtime_config)
                    summary = summarize_psd(psd, selected_table, runtime_config.get("psd", {}).get("epoch_aggregation", "mean"))
                    psd_result = {"epoch": psd, "channel": summary["channel"], "region": summary["region"]}
                    paths = _save_table_group(file_dir / "psd", {"psd_epoch_channel": psd, "psd_channel_summary": summary["channel"], "psd_region_summary": summary["region"]}, provenance)
                    _save_psd_npz(file_dir / "psd", psd, selected_data, loaded.sfreq)
                    figure_paths = _save_metric_figures("PSD", psd_result, file_dir, file_id)
                    record = {"metric": "PSD", "status": "completed", "paths": {"tables": paths, "figures": figure_paths, "arrays": "psd/psd_arrays.npz"}, "parameters": runtime_config.get("psd", {})}
                    metric_records.append(record)
                    result_callback({**_metric_plot_data("PSD", psd_result), "file_id": file_id, "file_dir": str(file_dir), "record": record})
                    completed_steps += 1

                if "Band Power" in selected and psd_result is not None:
                    begin_metric("Band Power")
                    bands = compute_band_power(psd_result["epoch"], runtime_config)
                    aggregation = str(runtime_config.get("psd", {}).get("epoch_aggregation", "mean"))
                    band_summary = (
                        bands.groupby(["channel_array_index", "channel_name", "band", "band_low_hz", "band_high_hz"], as_index=False)
                        .agg(
                            absolute_power=("absolute_power", aggregation),
                            relative_power=("relative_power", aggregation),
                            n_epochs=("epoch_index", "nunique"),
                            status=("status", "first"),
                        )
                    ) if not bands.empty else pd.DataFrame()
                    paths = _save_table_group(file_dir / "band_power", {"band_power_epoch_channel": bands, "band_power_summary": band_summary}, provenance)
                    figure_paths = _save_metric_figures("Band Power", {"band_power": bands, "band_power_summary": band_summary}, file_dir, file_id)
                    record = {"metric": "Band Power", "status": "completed", "paths": {"tables": paths, "figures": figure_paths}, "parameters": {"bands": runtime_config.get("bands", {}), "relative_power": runtime_config.get("relative_power", {}), "epoch_aggregation": aggregation}}
                    metric_records.append(record)
                    result_callback({**_metric_plot_data("Band Power", {"band_power": bands, "band_power_summary": band_summary}), "file_id": file_id, "file_dir": str(file_dir), "record": record})
                    completed_steps += 1

                if "FOOOF" in selected and psd_result is not None:
                    begin_metric("FOOOF")
                    fits = fit_channel_psd_table(psd_result["channel"], runtime_config)
                    paths = _save_table_group(file_dir / "fooof", fits, provenance)
                    figure_paths = _save_metric_figures("FOOOF", fits, file_dir, file_id)
                    record = {"metric": "FOOOF", "status": "completed", "paths": {"tables": paths, "figures": figure_paths}, "parameters": runtime_config.get("parameterization", {})}
                    metric_records.append(record)
                    result_callback({**_metric_plot_data("FOOOF", fits), "file_id": file_id, "file_dir": str(file_dir), "record": record})
                    completed_steps += 1

                if selected.intersection({"MIC", "MIM", "wpli2_debiased"}):
                    begin_metric("Connectivity")
                    connectivity = compute_connectivity(selected_data, loaded.sfreq, selected_table, selected_quality, runtime_config)
                    paths = _save_table_group(file_dir / "connectivity", {key: connectivity[key] for key in ("spectrum", "region_summary", "band_summary", "patterns", "redundancy_correlation", "redundancy_singular_values", "rank_summary", "rank_sensitivity", "stability", "epoch_profile", "input_checks", "failures")}, provenance)
                    _atomic_json(connectivity.get("metadata", {}), file_dir / "connectivity" / "connectivity_metadata.json")
                    figure_paths = _save_metric_figures("Connectivity", connectivity, file_dir, file_id)
                    record = {"metric": "Connectivity", "status": str(connectivity.get("status", "unknown")), "paths": {"tables": paths, "figures": figure_paths, "metadata": "connectivity/connectivity_metadata.json"}, "parameters": runtime_config.get("connectivity", {})}
                    metric_records.append(record)
                    result_callback({**_metric_plot_data("Connectivity", connectivity), "file_id": file_id, "file_dir": str(file_dir), "record": record})
                    completed_steps += 3

                if "Time Delay" in selected:
                    begin_metric("Time Delay")
                    time_delay = compute_time_delay(selected_data, loaded.sfreq, selected_table, selected_quality, runtime_config)
                    paths = _save_table_group(file_dir / "time_delay", {key: time_delay[key] for key in ("spectrum", "region_spectrum", "channel_pair_summary", "band_summary", "input_checks", "failures")}, provenance)
                    _atomic_json(time_delay.get("metadata", {}), file_dir / "time_delay" / "time_delay_metadata.json")
                    figure_paths = _save_metric_figures("Time Delay", time_delay, file_dir, file_id)
                    record = {"metric": "Time Delay", "status": str(time_delay.get("status", "unknown")), "paths": {"tables": paths, "figures": figure_paths, "metadata": "time_delay/time_delay_metadata.json"}, "parameters": runtime_config.get("time_delay", {})}
                    metric_records.append(record)
                    result_callback({**_metric_plot_data("Time Delay", time_delay), "file_id": file_id, "file_dir": str(file_dir), "record": record})
                    completed_steps += 1

                for metric_record in metric_records:
                    metric_record["file_dir"] = str(file_dir.relative_to(run_dir))
                _atomic_json(metric_records, file_dir / "results_index.json")
                file_record = {
                    "file_id": file_id,
                    "input_path": str(input_path),
                    "input_sha256": loaded_info["sha256"],
                    "status": "completed",
                    "n_epochs": len(epoch_indices),
                    "n_channels": len(channel_indices),
                    "effective_valid_duration_s": float(len(epoch_indices) * (end_index - start_index) / loaded.sfreq),
                    "file_dir": str(file_dir.relative_to(run_dir)),
                    "metrics": metric_records,
                }
                manifest["files"].append(file_record)
                _atomic_json(manifest, run_dir / "run_manifest.json")
            except AnalysisCancelled:
                raise
            except Exception as exc:  # noqa: BLE001 - GUI retains per-file failures
                error = {"file": str(input_path), "error": f"{type(exc).__name__}: {exc}"}
                manifest["errors"].append(error)
                _atomic_json(manifest, run_dir / "run_manifest.json")
                result_callback({"metric": "File", "status": "failed", "file_id": input_path.stem, "error": error["error"], "file_dir": str(run_dir)})
        manifest["status"] = "completed_with_errors" if manifest["errors"] else "completed"
    except AnalysisCancelled as exc:
        manifest["status"] = "cancelled"
        manifest["errors"].append({"error": str(exc)})
    except Exception as exc:  # noqa: BLE001 - manifest must preserve fatal errors
        manifest["status"] = "failed"
        manifest["errors"].append({"error": f"{type(exc).__name__}: {exc}"})
    manifest["finished_at_utc"] = datetime.now(UTC).isoformat()
    _atomic_json(manifest, run_dir / "run_manifest.json")
    progress("运行结束：" + str(manifest["status"]), 100)
    return {"run_dir": str(run_dir), "manifest": manifest}


def load_saved_run(run_dir: str | Path) -> dict[str, Any]:
    """Load a GUI run bundle without requiring the original FIF."""
    root = Path(run_dir).expanduser().resolve()
    manifest = json.loads((root / "run_manifest.json").read_text(encoding="utf-8"))
    parameters = json.loads((root / "parameters.json").read_text(encoding="utf-8")) if (root / "parameters.json").is_file() else {}
    return {"run_dir": str(root), "manifest": manifest, "parameters": parameters}


def load_saved_table(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path)
