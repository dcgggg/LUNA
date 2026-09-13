import json
from types import SimpleNamespace

import numpy as np
import pytest

from lfp_analysis.gui_engine import (
    _selected_epoch_indices,
    _time_slice,
    load_saved_run,
    resolve_manifest_path,
)


def test_saved_run_schema_is_checked_and_legacy_schema_is_readable(tmp_path):
    (tmp_path / "run_manifest.json").write_text(json.dumps({"files": []}), encoding="utf-8")
    loaded = load_saved_run(tmp_path)
    assert loaded["manifest"]["schema_version"] == 1

    (tmp_path / "run_manifest.json").write_text(json.dumps({"schema_version": 99, "files": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported saved run schema_version"):
        load_saved_run(tmp_path)


def test_saved_run_paths_must_stay_inside_run_directory(tmp_path):
    assert resolve_manifest_path(tmp_path, "file/quality.csv").parent == tmp_path / "file"
    with pytest.raises(ValueError, match="escapes"):
        resolve_manifest_path(tmp_path, "../outside.csv")
    with pytest.raises(ValueError, match="relative"):
        resolve_manifest_path(tmp_path, tmp_path / "outside.csv")


def test_per_file_epoch_selection_is_not_silently_clipped(tmp_path):
    path = tmp_path / "same-name.fif"
    snapshot = {
        "selected_epoch_indices": [0, 1],
        "selected_epoch_indices_by_file": {str(path): [2]},
    }
    assert _selected_epoch_indices(snapshot, 3, path) == [2]
    with pytest.raises(ValueError, match="out_of_range"):
        _selected_epoch_indices({"selected_epoch_indices": [3]}, 3, path)


def test_per_file_time_selection_is_not_silently_clipped(tmp_path):
    loaded = SimpleNamespace(
        tmin=0.0,
        tmax=0.999,
        sfreq=1000.0,
        data=np.zeros((2, 1, 1000)),
    )
    snapshot = {"selection": {"time_start_s": 0.1, "time_end_s": 0.9}}
    assert _time_slice(snapshot, loaded, tmp_path / "sample.fif")[:2] == (100, 900)
    with pytest.raises(ValueError, match="time_window_out_of_range"):
        _time_slice({"selection": {"time_start_s": 0.0, "time_end_s": 1.1}}, loaded, tmp_path / "sample.fif")
