from pathlib import Path

import pandas as pd

from lfp_analysis import pipeline


def _write_batch_csv(path: Path, rows: list[dict[str, str]]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_minimal_metadata(directory: Path) -> None:
    directory.mkdir()
    pd.DataFrame(
        [{"channel_name": "record-1", "physical_channel_number": "1", "region": "R1"}]
    ).to_csv(directory / "channel_map.csv", index=False)


def test_run_batch_preflights_duplicate_ids_and_preserves_partial_success(tmp_path: Path, monkeypatch):
    first = tmp_path / "one" / "record.fif"
    second = tmp_path / "two" / "record.fif"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    csv_path = tmp_path / "files.csv"
    _write_batch_csv(
        csv_path,
        [
            {"file_id": "same", "file_path": str(first), "include_file_level": "true"},
            {"file_id": "same", "file_path": str(second), "include_file_level": "true"},
            {"file_id": "unique", "file_path": str(first), "include_file_level": "false"},
        ],
    )
    called: list[Path] = []

    def fake_run_single_file(input_path, config_path, output_dir, metadata_dir="metadata"):
        called.append(Path(input_path))
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        return {}

    monkeypatch.setattr(pipeline, "run_single_file", fake_run_single_file)
    metadata_dir = tmp_path / "metadata"
    _write_minimal_metadata(metadata_dir)
    result = pipeline.run_batch(csv_path, "config.yaml", tmp_path / "results", metadata_dir=metadata_dir)

    assert called == []
    assert set(result.loc[result["row_index"].isin([0, 1]), "reason"]) == {"duplicate_output_target"}
    assert result.loc[result["row_index"] == 2, "reason"].item() == "include_file_level=false"


def test_run_batch_does_not_overwrite_nonempty_output_and_runs_other_file(tmp_path: Path, monkeypatch):
    first = tmp_path / "first.fif"
    second = tmp_path / "second.fif"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    csv_path = tmp_path / "files.csv"
    _write_batch_csv(
        csv_path,
        [
            {"file_id": "old", "file_path": str(first), "include_file_level": "true"},
            {"file_id": "new", "file_path": str(second), "include_file_level": "true"},
        ],
    )
    output_root = tmp_path / "results"
    existing = output_root / "old"
    existing.mkdir(parents=True)
    (existing / "keep.txt").write_text("keep", encoding="utf-8")
    called: list[str] = []

    def fake_run_single_file(input_path, config_path, output_dir, metadata_dir="metadata"):
        called.append(Path(input_path).name)
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(pipeline, "run_single_file", fake_run_single_file)
    metadata_dir = tmp_path / "metadata"
    _write_minimal_metadata(metadata_dir)
    result = pipeline.run_batch(csv_path, "config.yaml", output_root, metadata_dir=metadata_dir)

    assert called == ["second.fif"]
    assert result.loc[result["row_index"] == 0, "reason"].item() == "output_target_exists_nonempty"
    assert result.loc[result["row_index"] == 1, "status"].item() == "completed"
    assert (existing / "keep.txt").read_text(encoding="utf-8") == "keep"
