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

from .app_info import DEFAULT_CONFIG_FILENAME
from .band_power_plots import (
    ordered_bands,
    ordered_channels,
    plot_comparison,
    plot_overview,
    prepare_band_power,
)
from .colors import DEFAULT_COLOR_TEMPLATE, channel_colors
from .config import audit_config, load_config
from .connectivity import compute_connectivity
from .connectivity_plots import (
    available_bands,
    available_components,
    available_methods,
    plot_matrix,
    plot_spectrum,
    prepare_connectivity,
)
from .fooof_plots import ordered_channels as ordered_fooof_channels
from .fooof_plots import (
    plot_aperiodic_details,
    plot_fooof_overview,
    plot_peak_distribution,
    plot_peak_parameters,
    plot_periodic_curves,
    plot_periodic_heatmap,
    plot_single_channel_detail,
    prepare_fooof,
)
from .gui_specs import normalize_gui_values, validate_snapshot
from .identity import resolve_registry_match, stable_file_uid
from .io import channel_info_table, read_fif, sha256_file
from .mapping import apply_mapping
from .metadata import load_metadata_tables
from .parameterization import fit_channel_psd_table
from .quality import assess_quality
from .resources import packaged_resource_path
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


def inspect_file(
    path: str | Path,
    metadata_dir: str | Path = "metadata",
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Read one FIF and return UI-facing metadata plus an automatic quality check.

    The check is deliberately performed during background inspection, before any
    analysis indicator is run.  It uses the configured thresholds and never
    changes, filters, rejects, or overwrites the input data.
    """
    input_path = Path(path).expanduser().resolve()
    loaded = read_fif(input_path)
    tables = load_metadata_tables(metadata_dir)
    channel_table = channel_info_table(loaded, tables.get("channel_map"))
    resolved_config_path = Path(config_path).expanduser().resolve() if config_path else Path(__file__).resolve().parents[2] / "configs" / DEFAULT_CONFIG_FILENAME
    if not resolved_config_path.is_file():
        resolved_config_path = packaged_resource_path(f"configs/{DEFAULT_CONFIG_FILENAME}")
    quality_config = load_config(resolved_config_path) if resolved_config_path.is_file() else {}
    quality = assess_quality(loaded.data, loaded.sfreq, loaded.ch_names, quality_config)
    quality_file = quality["file"].iloc[0].to_dict() if not quality["file"].empty else {}
    dropped_candidates = [
        {"original_candidate_index": index, "drop_reason": ";".join(reasons)}
        for index, reasons in enumerate(loaded.drop_log)
        if reasons
    ]
    files = tables.get("files", pd.DataFrame())
    input_sha256 = sha256_file(input_path)
    registry_match = resolve_registry_match(files, input_path, metadata_dir)
    registry_row = registry_match.get("registry_row") or {}
    animal_id = _value_or_blank(registry_row.get("animal_id"))
    session_id = _value_or_blank(registry_row.get("session_id"))
    identity_status = "registered_identity" if str(animal_id).strip() and str(session_id).strip() else "file_only_identity_unresolved"
    file_uid = stable_file_uid(input_path, input_sha256)
    display_name = input_path.name
    return {
        "path": input_path,
        "normalized_path": str(input_path),
        "file_uid": file_uid,
        "file_stem": input_path.stem,
        "display_name": display_name,
        "file_id": _value_or_blank(registry_match.get("registry_file_id")) or _safe_id(input_path.stem),
        "registry_file_id": _value_or_blank(registry_match.get("registry_file_id")),
        "registry_match_status": registry_match.get("status", "unregistered"),
        "registry_match_candidates": registry_match.get("candidate_file_ids", []),
        "identity_status": identity_status,
        "loaded": loaded,
        "channel_table": channel_table,
        "n_epochs": int(loaded.data.shape[0]),
        "n_channels": int(loaded.data.shape[1]),
        "n_times": int(loaded.data.shape[2]),
        "sfreq": float(loaded.sfreq),
        "tmin": float(loaded.tmin),
        "tmax": float(loaded.tmax),
        "nominal_duration_s": float(loaded.data.shape[0] * loaded.data.shape[2] / loaded.sfreq),
        "effective_duration_s": float(quality_file.get("effective_valid_duration_s", 0.0)),
        "n_candidate_epochs": len(loaded.drop_log),
        "n_dropped_candidates": len(dropped_candidates),
        "dropped_candidates": dropped_candidates,
        "quality": quality,
        "quality_file": quality_file,
        "quality_config_path": str(resolved_config_path),
        "sha256": input_sha256,
        "registry_row": registry_row,
    }


def _file_specific_snapshot_value(
    snapshot: dict[str, Any],
    name: str,
    input_path: Path | None = None,
    file_uid: str | None = None,
) -> Any:
    """Resolve an optional per-file snapshot value before the global default."""
    per_file = snapshot.get(f"{name}_by_file", {})
    if isinstance(per_file, dict):
        keys = [str(input_path) if input_path is not None else "", file_uid or ""]
        if input_path is not None:
            keys.extend([input_path.name, input_path.stem])
        for key in keys:
            if key and key in per_file:
                return per_file[key]
    return snapshot.get(name)


def _selected_epoch_indices(
    snapshot: dict[str, Any],
    n_epochs: int,
    input_path: Path | None = None,
    file_uid: str | None = None,
) -> list[int]:
    values = _file_specific_snapshot_value(snapshot, "selected_epoch_indices", input_path, file_uid)
    if values is None:
        return list(range(n_epochs))
    selected = [int(value) for value in values]
    invalid = sorted({value for value in selected if value < 0 or value >= n_epochs})
    if invalid:
        raise ValueError(f"selected_epoch_indices_out_of_range: {invalid} for n_epochs={n_epochs}")
    return sorted(set(selected))


def _selected_channel_indices(
    snapshot: dict[str, Any],
    channel_table: pd.DataFrame,
    input_path: Path | None = None,
    file_uid: str | None = None,
) -> list[int]:
    selected_names = _file_specific_snapshot_value(snapshot, "selected_channel_names", input_path, file_uid)
    names = set(map(str, selected_names or []))
    return [int(row.array_index) for row in channel_table.itertuples() if str(row.channel_name) in names]


def _time_slice(
    snapshot: dict[str, Any],
    loaded: Any,
    input_path: Path | None = None,
    file_uid: str | None = None,
) -> tuple[int, int, float, float]:
    selection = _file_specific_snapshot_value(snapshot, "selection", input_path, file_uid) or {}
    start_s = float(selection.get("time_start_s", loaded.tmin))
    end_s = float(selection.get("time_end_s", loaded.tmax + 1.0 / loaded.sfreq))
    epoch_end = float(loaded.tmax) + 1.0 / float(loaded.sfreq)
    tolerance = 0.5 / float(loaded.sfreq)
    if start_s < float(loaded.tmin) - tolerance or end_s > epoch_end + tolerance:
        raise ValueError(
            f"selection_time_window_out_of_range: {start_s:g}-{end_s:g} s; "
            f"supported={float(loaded.tmin):g}-{epoch_end:g} s"
        )
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
    psd_method = str(config.get("psd", {}).get("method", "welch")).lower()
    common_psd_keys = {"method", "fmin_hz", "fmax_hz", "scaling", "epoch_aggregation"}
    welch_psd_keys = {"window", "window_seconds", "overlap_percent", "nperseg", "noverlap", "nfft", "detrend", "average"}
    multitaper_psd_keys = {
        "multitaper_bandwidth_hz",
        "multitaper_adaptive",
        "multitaper_low_bias",
        "multitaper_normalization",
        "multitaper_remove_dc",
        "multitaper_n_jobs",
    }
    active_psd_keys = common_psd_keys | (welch_psd_keys if psd_method == "welch" else multitaper_psd_keys)
    config["psd"] = {key: value for key, value in config.get("psd", {}).items() if key in active_psd_keys}
    selected = set(snapshot.get("indicators", []))
    indicator_to_method = {
        "MIC": "mic",
        "MIM": "mim",
        "wpli": "wpli",
        "dpli": "dpli",
        "wpli2_debiased": "wpli2_debiased",
    }
    methods = [indicator_to_method[indicator] for indicator in ("MIC", "MIM", "wpli", "dpli", "wpli2_debiased") if indicator in selected]
    config.setdefault("connectivity", {})["methods"] = methods
    config["connectivity"]["enabled"] = bool(methods)
    config["connectivity"]["selected_region_pairs"] = snapshot.get("selected_region_pairs", [])
    config.setdefault("time_delay", {})["selected_region_pairs"] = snapshot.get("selected_region_pairs", [])
    gui_connectivity = values.get("connectivity", {}) or {}
    configured_rank_map = gui_connectivity.get("fixed_rank_by_region", {})
    if isinstance(configured_rank_map, dict) and configured_rank_map:
        config["connectivity"]["fixed_rank_by_region"] = {
            str(region): int(rank)
            for region, rank in configured_rank_map.items()
            if str(region).strip() and int(rank or 0) > 0
        }
    else:
        # Preserve direct API/preset compatibility with older fixed-rank keys.
        config["connectivity"]["fixed_rank_by_region"] = {
            region: int(gui_connectivity.get(f"fixed_rank_{region}", 0) or 0)
            for region in ("M1", "STR", "PF", "SNr")
            if int(gui_connectivity.get(f"fixed_rank_{region}", 0) or 0) > 0
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


def _attach_fooof_channel_metadata(fits: dict[str, pd.DataFrame], selected_table: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Add physical channel and region metadata without inferring it from position."""
    metadata = selected_table[["array_index", "physical_channel_number", "region"]].rename(columns={"array_index": "channel_array_index"}).copy()
    output: dict[str, pd.DataFrame] = {}
    for name, table in fits.items():
        frame = table.copy()
        if frame.empty or "channel_array_index" not in frame.columns:
            output[name] = frame
            continue
        for column in ("physical_channel_number", "region"):
            if column in frame.columns:
                frame = frame.drop(columns=[column])
        output[name] = frame.merge(metadata, on="channel_array_index", how="left")
    return output


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


def _save_connectivity_npz(base: Path, spectrum: pd.DataFrame) -> None:
    """Save the complete connectivity long table in a compact array bundle."""
    if spectrum.empty:
        _atomic_npz(base / "connectivity_arrays.npz")
        return
    frame = spectrum.reset_index(drop=True)

    def string_array(column: str) -> np.ndarray:
        if column not in frame:
            return np.asarray([], dtype=str)
        return np.asarray(frame[column].fillna("").astype(str).to_numpy(), dtype=str)

    _atomic_npz(
        base / "connectivity_arrays.npz",
        frequency_hz=pd.to_numeric(frame.get("frequency_hz", np.nan), errors="coerce").to_numpy(float),
        value_raw=pd.to_numeric(frame.get("value_raw", np.nan), errors="coerce").to_numpy(float),
        value_strength=pd.to_numeric(frame.get("value_strength", np.nan), errors="coerce").to_numpy(float),
        component_index=pd.to_numeric(frame.get("component_index", np.nan), errors="coerce").to_numpy(float),
        frequency_is_masked_for_analysis=frame.get("frequency_is_masked_for_analysis", pd.Series(False, index=frame.index)).fillna(False).to_numpy(bool),
        frequency_is_masked_for_plot=frame.get("frequency_is_masked_for_plot", pd.Series(False, index=frame.index)).fillna(False).to_numpy(bool),
        method=string_array("method"),
        region_a=string_array("region_a"),
        region_b=string_array("region_b"),
        seed_region=string_array("seed_region"),
        target_region=string_array("target_region"),
        direction_order=string_array("direction_order"),
        seed_channel=string_array("seed_channel"),
        target_channel=string_array("target_channel"),
        n_epochs=pd.to_numeric(frame.get("n_epochs", np.nan), errors="coerce").to_numpy(float),
        rank_seed=pd.to_numeric(frame.get("rank_seed", np.nan), errors="coerce").to_numpy(float),
        rank_target=pd.to_numeric(frame.get("rank_target", np.nan), errors="coerce").to_numpy(float),
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
        metadata_table = tables.get("channel_table", pd.DataFrame())
        metadata = metadata_table.to_dict("records") if isinstance(metadata_table, pd.DataFrame) else []
        by_name = {str(row.get("channel_name", "")): row for row in metadata}
        for channel, group in table.groupby("channel_name") if not table.empty else []:
            row = by_name.get(str(channel), {"channel_name": str(channel), "region": "未映射"})
            color = channel_colors([row], DEFAULT_COLOR_TEMPLATE).get(str(channel), "#777777")
            axis.plot(group["frequency_hz"], group["psd_value"], linewidth=0.8, color=color, label=str(channel))
        axis.set_xlabel("Frequency (Hz)")
        axis.set_ylabel("PSD (source unit²/Hz)")
        axis.set_yscale("log")
        if not table.empty:
            axis.legend(fontsize=6, ncol=2)
    elif metric == "Band Power":
        prepared = prepare_band_power(tables, power_kind="absolute", aggregation="mean")
        bands = ordered_bands(prepared["summary"])
        channels = ordered_channels(prepared["summary"])
        overview_fig = fig
        plot_overview(
            axis,
            overview_fig,
            prepared,
            power_kind="absolute",
            scale="linear",
            selected_channel=channels[0]["channel_name"] if channels else None,
            selected_band=bands[0]["band"] if bands else None,
            show_values=False,
            title=f"{file_id} | Band Power | Overview",
            language="en",
        )
        fig.subplots_adjust(left=0.12, right=0.90, bottom=0.16, top=0.88)
        overview_base = figures_dir / "band_power_overview"
        fig.savefig(overview_base.with_suffix(".png"), dpi=150)
        fig.savefig(overview_base.with_suffix(".svg"))
        plt.close(fig)

        compare_fig, compare_axis = plt.subplots(figsize=(9, 4.5))
        plot_comparison(
            compare_axis,
            prepared,
            mode="channel",
            power_kind="absolute",
            scale="linear",
            selected_channel=channels[0]["channel_name"] if channels else None,
            selected_band=bands[0]["band"] if bands else None,
            show_epoch_distribution=False,
            title=f"{file_id} | Band Power | Compare channels",
            language="en",
        )
        compare_fig.subplots_adjust(left=0.11, right=0.98, bottom=0.18, top=0.88)
        compare_base = figures_dir / "band_power_compare"
        compare_fig.savefig(compare_base.with_suffix(".png"), dpi=150)
        compare_fig.savefig(compare_base.with_suffix(".svg"))
        plt.close(compare_fig)

        combined_fig, combined_axes = plt.subplots(2, 1, figsize=(10, 10), constrained_layout=True)
        plot_overview(
            combined_axes[0],
            combined_fig,
            prepared,
            power_kind="absolute",
            scale="linear",
            selected_channel=channels[0]["channel_name"] if channels else None,
            selected_band=bands[0]["band"] if bands else None,
            show_values=False,
            title=f"{file_id} | Band Power | Overview",
            language="en",
        )
        plot_comparison(
            combined_axes[1],
            prepared,
            mode="channel",
            power_kind="absolute",
            scale="linear",
            selected_channel=channels[0]["channel_name"] if channels else None,
            selected_band=bands[0]["band"] if bands else None,
            show_epoch_distribution=False,
            title=f"{file_id} | Band Power | Compare channels",
            language="en",
        )
        combined_base = figures_dir / "band_power_combined"
        combined_fig.savefig(combined_base.with_suffix(".png"), dpi=150)
        combined_fig.savefig(combined_base.with_suffix(".svg"))
        plt.close(combined_fig)
        return [
            str(path.relative_to(file_dir))
            for path in (
                overview_base.with_suffix(".png"),
                overview_base.with_suffix(".svg"),
                compare_base.with_suffix(".png"),
                compare_base.with_suffix(".svg"),
                combined_base.with_suffix(".png"),
                combined_base.with_suffix(".svg"),
            )
        ]
    elif metric == "FOOOF":
        display_bands = tables.get("display_bands", {})
        first_band = next(iter(display_bands), None) if isinstance(display_bands, dict) else (display_bands[0].get("name") if display_bands else None)
        prepared = prepare_fooof(
            tables,
            display_bands,
            selected_band=first_band,
            peak_mode="representative",
        )
        channels = ordered_fooof_channels(prepared["models"], prepared["curves"])
        selected_channel = channels[0]["channel_name"] if channels else None
        selected_region = str(channels[0].get("region", "全部")) if channels else "全部"
        overview_base = figures_dir / "fooof_overview"
        overview_fig = fig
        overview_fig.clear()
        overview_axes = np.asarray(overview_fig.subplots(2, 3), dtype=object)
        plot_fooof_overview(overview_fig, overview_axes, prepared, selected_region, selected_channel, "overlay", True, True, language="en")
        overview_fig.savefig(overview_base.with_suffix(".png"), dpi=150)
        overview_fig.savefig(overview_base.with_suffix(".svg"))
        plt.close(overview_fig)

        aperiodic_fig = plt.figure(figsize=(10, 5))
        aperiodic_axes = np.asarray(aperiodic_fig.subplots(1, 2), dtype=object)
        plot_aperiodic_details(aperiodic_fig, aperiodic_axes, prepared, selected_channel, True, language="en")
        aperiodic_base = figures_dir / "fooof_aperiodic"
        aperiodic_fig.savefig(aperiodic_base.with_suffix(".png"), dpi=150)
        aperiodic_fig.savefig(aperiodic_base.with_suffix(".svg"))
        plt.close(aperiodic_fig)

        periodic_fig = plt.figure(figsize=(10, 7))
        plot_periodic_curves(periodic_fig, "region", prepared, selected_region, [row["channel_name"] for row in channels], "overlay", True, True, language="en")
        periodic_base = figures_dir / "fooof_periodic_curves"
        periodic_fig.savefig(periodic_base.with_suffix(".png"), dpi=150)
        periodic_fig.savefig(periodic_base.with_suffix(".svg"))
        plt.close(periodic_fig)

        heatmap_fig = plt.figure(figsize=(10, 5))
        plot_periodic_heatmap(heatmap_fig, prepared, language="en")
        heatmap_base = figures_dir / "fooof_periodic_heatmap"
        heatmap_fig.savefig(heatmap_base.with_suffix(".png"), dpi=150)
        heatmap_fig.savefig(heatmap_base.with_suffix(".svg"))
        plt.close(heatmap_fig)

        peaks_fig = plt.figure(figsize=(12, 4.5))
        plot_peak_parameters(peaks_fig, prepared, selected_channel, True, language="en")
        peaks_base = figures_dir / "fooof_peak_parameters"
        peaks_fig.savefig(peaks_base.with_suffix(".png"), dpi=150)
        peaks_fig.savefig(peaks_base.with_suffix(".svg"))
        plt.close(peaks_fig)

        distribution_fig = plt.figure(figsize=(9, 5))
        plot_peak_distribution(distribution_fig, prepared, language="en")
        distribution_base = figures_dir / "fooof_peak_distribution"
        distribution_fig.savefig(distribution_base.with_suffix(".png"), dpi=150)
        distribution_fig.savefig(distribution_base.with_suffix(".svg"))
        plt.close(distribution_fig)

        detail_fig = plt.figure(figsize=(11, 7))
        plot_single_channel_detail(detail_fig, prepared, selected_channel, True, language="en")
        detail_base = figures_dir / "fooof_channel_detail"
        detail_fig.savefig(detail_base.with_suffix(".png"), dpi=150)
        detail_fig.savefig(detail_base.with_suffix(".svg"))
        plt.close(detail_fig)
        return [
            str(path.relative_to(file_dir))
            for base in (overview_base, aperiodic_base, periodic_base, heatmap_base, peaks_base, distribution_base, detail_base)
            for path in (base.with_suffix(".png"), base.with_suffix(".svg"))
        ]
    elif metric == "Connectivity":
        methods = available_methods(tables)
        if not methods:
            axis.text(0.5, 0.5, "No connectivity result", ha="center", va="center", transform=axis.transAxes)
            axis.set_axis_off()
        else:
            summary = tables.get("region_summary", pd.DataFrame())
            selected_pairs = (
                [list(pair) for pair in summary[["region_a", "region_b"]].drop_duplicates().itertuples(index=False, name=None)]
                if isinstance(summary, pd.DataFrame) and not summary.empty
                else None
            )
            component = available_components(tables)[0]
            bands = available_bands(tables)
            band = bands[0] if bands else None
            saved: list[str] = []
            for method in methods:
                prepared = prepare_connectivity(tables, method, component, selected_pairs)
                spectrum_base = figures_dir / f"connectivity_{method}_spectrum"
                plot_spectrum(axis, prepared, band, "linear", f"{file_id} | ", 9)
                fig.savefig(spectrum_base.with_suffix(".png"), dpi=150)
                fig.savefig(spectrum_base.with_suffix(".svg"))
                saved.extend(str(path.relative_to(file_dir)) for path in (spectrum_base.with_suffix(".png"), spectrum_base.with_suffix(".svg")))
                plt.close(fig)
                fig, axis = plt.subplots(figsize=(9, 5))

                matrix_fig, matrix_axis = plt.subplots(figsize=(6.5, 5.5), constrained_layout=True)
                plot_matrix(matrix_axis, matrix_fig, prepared, band, "linear", f"{file_id} | ", 9)
                matrix_base = figures_dir / f"connectivity_{method}_matrix"
                matrix_fig.savefig(matrix_base.with_suffix(".png"), dpi=150)
                matrix_fig.savefig(matrix_base.with_suffix(".svg"))
                saved.extend(str(path.relative_to(file_dir)) for path in (matrix_base.with_suffix(".png"), matrix_base.with_suffix(".svg")))
                plt.close(matrix_fig)

                combined_fig, combined_axes = plt.subplots(2, 1, figsize=(10, 9), constrained_layout=True)
                plot_spectrum(combined_axes[0], prepared, band, "linear", f"{file_id} | ", 9)
                plot_matrix(combined_axes[1], combined_fig, prepared, band, "linear", f"{file_id} | ", 9)
                combined_base = figures_dir / f"connectivity_{method}_combined"
                combined_fig.savefig(combined_base.with_suffix(".png"), dpi=150)
                combined_fig.savefig(combined_base.with_suffix(".svg"))
                saved.extend(str(path.relative_to(file_dir)) for path in (combined_base.with_suffix(".png"), combined_base.with_suffix(".svg")))
                plt.close(combined_fig)
            plt.close(fig)
            return saved
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
    fig.subplots_adjust(left=0.11, right=0.96, bottom=0.16, top=0.88)
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
        "schema_version": 2,
        "run_id": run_id,
        "status": "running",
        "started_at_utc": started,
        "finished_at_utc": None,
        "config_path": str(Path(config_path).resolve()),
        "metadata_dir": str(Path(metadata_dir).resolve()),
        "software": _package_versions(),
        "configuration_audit": audit_config(base_config),
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
                loaded_info = inspect_file(input_path, metadata_dir, config_path)
                loaded = loaded_info["loaded"]
                if loaded_info.get("registry_match_status", "").endswith("_conflict"):
                    manifest["warnings"].append(
                        f"{input_path.name}: metadata registry match conflict; file-level results remain unassigned "
                        f"(candidates={loaded_info.get('registry_match_candidates', [])})"
                    )
                full_channel_table = loaded_info["channel_table"]
                mapping_by_file = snapshot.get("channel_mappings_by_file", {})
                mapping_rows_for_file = (
                    mapping_by_file.get(str(input_path), mapping_by_file.get(loaded_info["file_uid"], snapshot.get("channel_mapping", [])))
                    if isinstance(mapping_by_file, dict)
                    else snapshot.get("channel_mapping", [])
                )
                if isinstance(mapping_rows_for_file, list) and mapping_rows_for_file:
                    full_channel_table = apply_mapping(full_channel_table, {"channels": mapping_rows_for_file})
                quality = loaded_info["quality"]
                channel_indices = _selected_channel_indices(snapshot, full_channel_table, input_path, loaded_info["file_uid"])
                epoch_indices = _selected_epoch_indices(snapshot, loaded.data.shape[0], input_path, loaded_info["file_uid"])
                start_index, end_index, actual_start, actual_end = _time_slice(snapshot, loaded, input_path, loaded_info["file_uid"])
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
                runtime_config = build_runtime_config(base_config, snapshot, loaded.sfreq, end_index - start_index)
                selected_pairs = _file_specific_snapshot_value(snapshot, "selected_region_pairs", input_path, loaded_info["file_uid"])
                if selected_pairs is not None:
                    runtime_config.setdefault("connectivity", {})["selected_region_pairs"] = selected_pairs
                    runtime_config.setdefault("time_delay", {})["selected_region_pairs"] = selected_pairs
                analysis_quality = assess_quality(
                    selected_data,
                    loaded.sfreq,
                    selected_table["channel_name"].astype(str).tolist(),
                    runtime_config,
                )
                analysis_quality["epoch"]["original_epoch_index"] = epoch_indices
                analysis_quality["epoch"]["analysis_epoch_index"] = np.arange(len(epoch_indices), dtype=int)
                analysis_quality["epoch_channel"]["original_epoch_index"] = analysis_quality["epoch_channel"]["epoch_index"].map(
                    dict(enumerate(epoch_indices))
                )
                analysis_quality["epoch_channel"]["analysis_epoch_index"] = analysis_quality["epoch_channel"]["epoch_index"]
                selected_quality = analysis_quality["epoch"]
                file_id = _safe_id(str(loaded_info.get("file_id") or input_path.stem))
                registry_row = loaded_info.get("registry_row", {})
                provenance = {
                    "animal_id": registry_row.get("animal_id", ""),
                    "session_id": registry_row.get("session_id", ""),
                    "file_id": file_id,
                    "file_uid": loaded_info["file_uid"],
                    "registry_file_id": loaded_info.get("registry_file_id", ""),
                    "registry_match_status": loaded_info.get("registry_match_status", "unregistered"),
                    "identity_status": loaded_info.get("identity_status", "file_only_identity_unresolved"),
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
                        "file_uid": loaded_info["file_uid"],
                        "display_name": loaded_info.get("display_name", input_path.name),
                        "registry_file_id": loaded_info.get("registry_file_id", ""),
                        "registry_match_status": loaded_info.get("registry_match_status", "unregistered"),
                        "registry_match_candidates": loaded_info.get("registry_match_candidates", []),
                        "identity_status": loaded_info.get("identity_status", "file_only_identity_unresolved"),
                        "input_path": str(input_path),
                        "input_sha256": loaded_info["sha256"],
                        "n_epochs_selected": len(epoch_indices),
                        "n_channels_selected": len(channel_indices),
                        "selected_epoch_indices": epoch_indices,
                        "selected_channel_names": selected_table["channel_name"].astype(str).tolist(),
                        "time_start_s": actual_start,
                        "time_end_s": actual_end,
                        "selected_nominal_duration_s": float(len(epoch_indices) * (end_index - start_index) / loaded.sfreq),
                        "analysis_effective_valid_duration_s": float(analysis_quality["file"].iloc[0]["effective_valid_duration_s"]),
                        "effective_valid_duration_s": float(analysis_quality["file"].iloc[0]["effective_valid_duration_s"]),
                        "registry_row": registry_row,
                        "provenance_columns": provenance,
                        "runtime_config": runtime_config,
                        "quality_warnings": warnings,
                    },
                    file_dir / "file_manifest.json",
                )
                full_quality_channel = quality["epoch_channel"].loc[
                    quality["epoch_channel"]["epoch_index"].isin(epoch_indices)
                    & quality["epoch_channel"]["channel_array_index"].isin(channel_indices)
                ].copy()
                _save_table_group(
                    file_dir,
                    {
                        "channel_table": selected_table,
                        "quality_epoch": selected_quality,
                        "quality_epoch_channel": analysis_quality["epoch_channel"],
                        "quality_full_epoch": quality["epoch"],
                        "quality_full_epoch_channel": quality["epoch_channel"],
                        "quality_selected_full_channel": full_quality_channel,
                    },
                    provenance,
                )
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
                    tables = {
                        "quality_epoch": selected_quality,
                        "quality_epoch_channel": analysis_quality["epoch_channel"],
                        "quality_channel": analysis_quality["channel"],
                        "quality_file": analysis_quality["file"],
                        "quality_full_epoch": quality["epoch"],
                        "quality_full_epoch_channel": quality["epoch_channel"],
                        "quality_full_channel": quality["channel"],
                        "quality_full_file": quality["file"],
                    }
                    paths = _save_table_group(file_dir / "quality", tables, provenance)
                    figure_paths = _save_metric_figures("Quality", tables, file_dir, file_id)
                    record = {"metric": "Quality", "status": "completed", "paths": {"tables": paths, "figures": figure_paths}}
                    metric_records.append(record)
                    result_callback({**_metric_plot_data("Quality", tables), "file_id": file_id, "file_uid": loaded_info["file_uid"], "display_name": loaded_info.get("display_name", input_path.name), "file_dir": str(file_dir), "record": record})
                    completed_steps += 1

                psd_result: dict[str, Any] | None = None
                if selected.intersection({"PSD", "Band Power", "FOOOF"}):
                    begin_metric("PSD")
                    psd = compute_psd(selected_data, loaded.sfreq, selected_table["channel_name"].astype(str).tolist(), runtime_config)
                    summary = summarize_psd(psd, selected_table, runtime_config.get("psd", {}).get("epoch_aggregation", "mean"))
                    psd_result = {"epoch": psd, "channel": summary["channel"], "region": summary["region"], "channel_table": selected_table}
                    paths = _save_table_group(file_dir / "psd", {"psd_epoch_channel": psd, "psd_channel_summary": summary["channel"], "psd_region_summary": summary["region"]}, provenance)
                    _save_psd_npz(file_dir / "psd", psd, selected_data, loaded.sfreq)
                    figure_paths = _save_metric_figures("PSD", psd_result, file_dir, file_id)
                    record = {"metric": "PSD", "status": "completed", "paths": {"tables": paths, "figures": figure_paths, "arrays": "psd/psd_arrays.npz"}, "parameters": runtime_config.get("psd", {})}
                    metric_records.append(record)
                    result_callback({**_metric_plot_data("PSD", psd_result), "file_id": file_id, "file_uid": loaded_info["file_uid"], "display_name": loaded_info.get("display_name", input_path.name), "file_dir": str(file_dir), "record": record})
                    completed_steps += 1

                if "Band Power" in selected and psd_result is not None:
                    begin_metric("Band Power")
                    bands = compute_band_power(psd_result["epoch"], runtime_config)
                    channel_metadata = selected_table[["array_index", "physical_channel_number", "region"]].rename(
                        columns={"array_index": "channel_array_index"}
                    )
                    bands = bands.merge(channel_metadata, on="channel_array_index", how="left")
                    aggregation = str(runtime_config.get("psd", {}).get("epoch_aggregation", "mean"))
                    band_summary = (
                        bands.groupby(
                            [
                                "channel_array_index",
                                "channel_name",
                                "physical_channel_number",
                                "region",
                                "band",
                                "band_low_hz",
                                "band_high_hz",
                            ],
                            as_index=False,
                        )
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
                    result_callback({**_metric_plot_data("Band Power", {"band_power": bands, "band_power_summary": band_summary}), "file_id": file_id, "file_uid": loaded_info["file_uid"], "display_name": loaded_info.get("display_name", input_path.name), "file_dir": str(file_dir), "record": record})
                    completed_steps += 1

                if "FOOOF" in selected and psd_result is not None:
                    begin_metric("FOOOF")
                    fits = _attach_fooof_channel_metadata(fit_channel_psd_table(psd_result["channel"], runtime_config), selected_table)
                    paths = _save_table_group(file_dir / "fooof", fits, provenance)
                    fooof_payload_tables = {
                        **fits,
                        "channel_table": selected_table,
                        "display_bands": runtime_config.get("bands", {}),
                    }
                    figure_paths = _save_metric_figures("FOOOF", fooof_payload_tables, file_dir, file_id)
                    record = {
                        "metric": "FOOOF",
                        "status": "completed",
                        "paths": {"tables": paths, "figures": figure_paths},
                        "parameters": {**runtime_config.get("parameterization", {}), "display_bands": runtime_config.get("bands", {})},
                    }
                    metric_records.append(record)
                    result_callback({**_metric_plot_data("FOOOF", fooof_payload_tables), "file_id": file_id, "file_uid": loaded_info["file_uid"], "display_name": loaded_info.get("display_name", input_path.name), "file_dir": str(file_dir), "record": record})
                    completed_steps += 1

                if selected.intersection({"MIC", "MIM", "wpli", "dpli", "wpli2_debiased"}):
                    begin_metric("Connectivity")
                    connectivity = compute_connectivity(
                        selected_data,
                        loaded.sfreq,
                        selected_table,
                        selected_quality,
                        runtime_config,
                        analysis_task_id=f"{snapshot.get('run_id', 'gui')}/{file_id}/connectivity",
                    )
                    # Keep the exact mapping used by this run in the live
                    # payload so custom region names also drive the viewer.
                    connectivity["channel_table"] = selected_table
                    paths = _save_table_group(file_dir / "connectivity", {key: connectivity[key] for key in ("spectrum", "region_summary", "band_summary", "channel_pair_band_summary", "patterns", "redundancy_correlation", "redundancy_singular_values", "rank_summary", "rank_sensitivity", "stability", "epoch_profile", "input_checks", "failures", "frequency_diagnostics", "roughness", "band_cv", "binned_spectrum", "display_spectrum", "display_roughness", "estimation_calls")}, provenance)
                    _save_connectivity_npz(file_dir / "connectivity", connectivity.get("spectrum", pd.DataFrame()))
                    _atomic_json(connectivity.get("metadata", {}), file_dir / "connectivity" / "connectivity_metadata.json")
                    figure_paths = _save_metric_figures("Connectivity", connectivity, file_dir, file_id)
                    record = {"metric": "Connectivity", "status": str(connectivity.get("status", "unknown")), "paths": {"tables": paths, "figures": figure_paths, "arrays": "connectivity/connectivity_arrays.npz", "metadata": "connectivity/connectivity_metadata.json"}, "parameters": {**runtime_config.get("connectivity", {}), "estimation_call_count": len(connectivity.get("estimation_calls", pd.DataFrame()))}}
                    metric_records.append(record)
                    result_callback({**_metric_plot_data("Connectivity", connectivity), "file_id": file_id, "file_uid": loaded_info["file_uid"], "display_name": loaded_info.get("display_name", input_path.name), "file_dir": str(file_dir), "record": record})
                    completed_steps += 3

                if "Time Delay" in selected:
                    begin_metric("Time Delay")
                    time_delay = compute_time_delay(selected_data, loaded.sfreq, selected_table, selected_quality, runtime_config)
                    paths = _save_table_group(file_dir / "time_delay", {key: time_delay[key] for key in ("spectrum", "region_spectrum", "channel_pair_summary", "band_summary", "input_checks", "failures")}, provenance)
                    _atomic_json(time_delay.get("metadata", {}), file_dir / "time_delay" / "time_delay_metadata.json")
                    figure_paths = _save_metric_figures("Time Delay", time_delay, file_dir, file_id)
                    record = {"metric": "Time Delay", "status": str(time_delay.get("status", "unknown")), "paths": {"tables": paths, "figures": figure_paths, "metadata": "time_delay/time_delay_metadata.json"}, "parameters": runtime_config.get("time_delay", {})}
                    metric_records.append(record)
                    result_callback({**_metric_plot_data("Time Delay", time_delay), "file_id": file_id, "file_uid": loaded_info["file_uid"], "display_name": loaded_info.get("display_name", input_path.name), "file_dir": str(file_dir), "record": record})
                    completed_steps += 1

                for metric_record in metric_records:
                    metric_record["file_dir"] = str(file_dir.relative_to(run_dir))
                _atomic_json(metric_records, file_dir / "results_index.json")
                file_record = {
                    "file_id": file_id,
                    "file_uid": loaded_info["file_uid"],
                    "display_name": loaded_info.get("display_name", input_path.name),
                    "registry_file_id": loaded_info.get("registry_file_id", ""),
                    "registry_match_status": loaded_info.get("registry_match_status", "unregistered"),
                    "identity_status": loaded_info.get("identity_status", "file_only_identity_unresolved"),
                    "input_path": str(input_path),
                    "input_sha256": loaded_info["sha256"],
                    "status": "completed",
                    "n_epochs": len(epoch_indices),
                    "n_channels": len(channel_indices),
                    "selected_nominal_duration_s": float(len(epoch_indices) * (end_index - start_index) / loaded.sfreq),
                    "analysis_effective_valid_duration_s": float(analysis_quality["file"].iloc[0]["effective_valid_duration_s"]),
                    "effective_valid_duration_s": float(analysis_quality["file"].iloc[0]["effective_valid_duration_s"]),
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
                result_callback({"metric": "File", "status": "failed", "file_id": input_path.stem, "file_uid": stable_file_uid(input_path, "unreadable"), "display_name": input_path.name, "error": error["error"], "file_dir": str(run_dir)})
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
    manifest_path = root / "run_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Saved run manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise TypeError("Saved run manifest must be a JSON object")
    schema_version = int(manifest.get("schema_version", 1))
    if schema_version not in {1, 2}:
        raise ValueError(f"Unsupported saved run schema_version={schema_version}; supported versions are 1 and 2")
    if not isinstance(manifest.get("files", []), list):
        raise TypeError("Saved run manifest field 'files' must be a list")
    manifest.setdefault("schema_version", schema_version)
    parameters = json.loads((root / "parameters.json").read_text(encoding="utf-8")) if (root / "parameters.json").is_file() else {}
    return {"run_dir": str(root), "manifest": manifest, "parameters": parameters}


def resolve_manifest_path(root: str | Path, relative_path: str | Path, label: str = "manifest path") -> Path:
    """Resolve a manifest path without allowing absolute paths or traversal."""
    root_path = Path(root).expanduser().resolve()
    raw = Path(relative_path) if relative_path not in (None, "") else Path(".")
    if raw.is_absolute():
        raise ValueError(f"{label} must be relative to the saved run: {relative_path}")
    resolved = (root_path / raw).resolve()
    try:
        resolved.relative_to(root_path)
    except ValueError as exc:
        raise ValueError(f"{label} escapes the saved run directory: {relative_path}") from exc
    return resolved


def load_saved_table(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path)
