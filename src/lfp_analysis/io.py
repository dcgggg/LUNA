from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class LoadedFIF:
    path: Path
    epochs: Any
    data: np.ndarray
    ch_names: list[str]
    sfreq: float
    events: np.ndarray
    selection: np.ndarray
    drop_log: tuple[tuple[str, ...], ...]
    tmin: float
    tmax: float


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def read_fif(path: str | Path) -> LoadedFIF:
    """Read an epoched FIF without modifying it or applying extra cleaning."""
    import mne

    input_path = Path(path).expanduser().resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    epochs = mne.read_epochs(input_path, preload=True, verbose=False)
    data = np.asarray(epochs.get_data(), dtype=float)
    return LoadedFIF(
        path=input_path,
        epochs=epochs,
        data=data,
        ch_names=list(epochs.ch_names),
        sfreq=float(epochs.info["sfreq"]),
        events=np.asarray(epochs.events),
        selection=np.asarray(epochs.selection),
        drop_log=tuple(tuple(str(item) for item in row) for row in epochs.drop_log),
        tmin=float(epochs.tmin),
        tmax=float(epochs.tmax),
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def write_json(value: Any, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        json.dump(_jsonable(value), handle, ensure_ascii=False, indent=2)


def channel_info_table(loaded: LoadedFIF, channel_map: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return actual channel names and MNE metadata without inferring physical numbers."""
    mapping = {}
    if channel_map is not None and not channel_map.empty and "channel_name" in channel_map:
        mapping = channel_map.set_index("channel_name").to_dict(orient="index")
    rows: list[dict[str, Any]] = []
    for array_index, name in enumerate(loaded.ch_names):
        info = loaded.epochs.info["chs"][array_index]
        mapped = mapping.get(name, {})
        rows.append(
            {
                "array_index": array_index,
                "channel_name": name,
                "mne_channel_type": loaded.epochs.get_channel_types(picks=[array_index])[0],
                "mne_unit_code": info.get("unit"),
                "physical_channel_number": mapped.get("physical_channel_number", ""),
                "region": mapped.get("region", ""),
                "hemisphere": mapped.get("hemisphere", ""),
                "probe_or_tetrode": mapped.get("probe_or_tetrode", ""),
                "mapping_status": "mapped" if mapped else "unmapped",
            }
        )
    return pd.DataFrame(rows)


def epoch_trace_table(loaded: LoadedFIF, file_id: str) -> pd.DataFrame:
    """Build a trace table while keeping candidate/drop information explicit.

    MNE's ``epochs.events`` contains retained events after epoch rejection. For a
    dropped candidate whose original event row is not available in the loaded
    object, the event field remains blank rather than being reconstructed.
    """
    selection_to_saved = {int(original): saved for saved, original in enumerate(loaded.selection)}
    rows: list[dict[str, Any]] = []
    for candidate_index, reasons in enumerate(loaded.drop_log):
        saved_index = selection_to_saved.get(candidate_index)
        event_value: Any = ""
        selection_value: Any = ""
        if saved_index is not None and saved_index < len(loaded.events):
            event_value = int(loaded.events[saved_index, 2])
            selection_value = int(loaded.selection[saved_index])
        rows.append(
            {
                "file_id": file_id,
                "saved_index": "" if saved_index is None else saved_index,
                "original_candidate_index": candidate_index,
                "events_raw_value": event_value,
                "selection_value": selection_value,
                "confirmed_time_start_s": "",
                "confirmed_time_end_s": "",
                "quality_status": "dropped_upstream" if reasons else "retained_pending_quality",
                "quality_flags": "",
                "drop_reason": ";".join(reasons),
                "time_coordinate_note": "events raw value retained; not interpreted as original recording time",
            }
        )
    return pd.DataFrame(rows)


def raw_trace_artifacts(loaded: LoadedFIF, output_dir: str | Path) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    write_json(loaded.events, output / "events_raw.json")
    write_json(loaded.selection, output / "selection.json")
    write_json(loaded.drop_log, output / "drop_log.json")

